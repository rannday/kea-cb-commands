# DHCPv4 subnet lifecycle (Kea 3.2.1)

## Upstream findings before implementation

The pinned source is `kea-Kea-3.2.1`. Both backends implement the same native
`ConfigBackendPoolDHCPv4::getSubnet4` and `deleteSubnet4` overloads for a
`SubnetID` or prefix string. The hook resolves the current manager pool on each
invocation and requires exactly one configured PostgreSQL or MySQL backend.
It does not rely on the pool's multiple-backend traversal or aggregation rules.

Evidence in the upstream source tree:

| Concern | Source and behavior |
| --- | --- |
| Identity reads | `src/hooks/dhcp/pgsql/pgsql_cb_dhcp4.cc`, `getSubnet4` (ID and prefix); `mysql/mysql_cb_dhcp4.cc`, same overloads. Reads reconstruct pools, options and server associations. |
| Multiple backends | `src/lib/config_backend/base_config_backend_pool.h`: `getPropertyPtrConst` returns the first non-null object among matching backends; `createUpdateDeleteProperty` rejects zero matches with `NoSuchDatabase` and multiple matches with `AmbiguousDatabase`. The hook rejects multiple configured backends before either operation. |
| Visibility | `pgsql_cb_impl.h`, server-tag filtering; `ONE(tag)` includes universal `all` objects as well as the requested tag. `ALL()` means universal objects, not every server. Internal `ANY()` reads include other tags and unassigned objects. |
| Deletion | Both backend implementations, `deleteSubnet4` and `deleteTransactional`: the tagged delete matches an exact association, then deletes the entire subnet row. It does not detach one association. |
| Transactions | `PgSqlTransaction` / `MySqlTransaction` enclose `ScopedAuditRevision`, native delete and commit. Exceptions roll back table changes and audit records. PostgreSQL sequences can still advance on rollback. Preflight reads are outside this transaction. |
| Children | Official database creation scripts: subnet delete triggers remove pools and subnet options; foreign keys cascade association and dependent option rows. Server records remain. |
| Audit | Native deletion uses message `subnet deleted`, cascade flag true, and one subnet DELETE entry. Child audit entries are suppressed. Revision timestamps record deletion; there is no surviving subnet modification timestamp to update. |
| Shared networks | Native APIs can retrieve/delete member subnets, but inherited settings require their shared-network context. This hook rejects those subnets for both commands. |
| Leases | Configuration deletion neither calls `LeaseMgr` nor deletes lease records. Lease storage is separate from configuration storage. Deletion does not revoke leases or stop an already active runtime subnet. |
| Activation | `src/lib/dhcpsrv/cb_ctl_dhcp4.cc`, subnet DELETE audit processing: a separate native pull removes the active subnet by ID. Full reload/restart instead reconstructs configuration. None is performed by these commands. |

The exact-tag, single-association deletion guard uses an internal `ANY()` identity
lookup. It rejects unassigned, multiply associated and differently tagged rows,
including a universal row selected through a specific server tag. Public requests
cannot supply `ANY`, multiple tags or a backend selector.

## Operational boundary

As with `cb-subnet4-set`, operators must serialize independent configuration
writers across validation and mutation. Native APIs do not expose a transaction
covering these preflight reads and the write, or a compare-and-delete operation.
A concurrent writer could replace an identity, change associations or attach a
shared network after validation. Do not use mutation commands without coordinated
exclusive access to the configuration being changed.

Deletion requires `preserve-leases: true`. This acknowledges that leases remain
valid until their normal expiry and that runtime allocation can continue until
separate activation. It is not a lease scan or a claim that no active leases exist.
A local lease scan cannot establish absence across independent DHCP servers, and
can race with allocations. Do not reuse an ID/prefix or its address space while
retained leases could conflict. Coordinate activation on every affected server,
including servers consuming universal configuration. No lease deletion is added.

See [commands](commands.md) for the wire contracts and
[development](development.md) for reproducible validation.

## Verification coverage

Both disposable SQL fixtures run the shared `tests/lifecycle.py` suite with
multithreading disabled and enabled. It checks native get serialization by ID
and prefix against the rich list fixture, missing identities, malformed inputs,
exact/universal/different/unassigned/multiple associations, shared-network guards,
pool cascades, unrelated rows and their timestamps, and native audit revisions.
Temporary test-only AFTER DELETE triggers inject a database failure after native
delete work; complete table snapshots must match after rollback. The harnesses
also exercise backend outages and reject empty or overlapping second backends.

Successful deletions are checked separately in SQL, native get/list and active
`config-get`. Runtime removal requires an explicit pull or reload; daemon restart
must also preserve absence. Packet fixtures use isolated Linux user/network
namespaces and real DISCOVER/OFFER/REQUEST/ACK exchanges. After SQL deletion they
prove that the still-active runtime can allocate. After explicit native activation
they require no DHCPOFFER and unchanged existing memfile lease bytes. This proves
lease retention for the tested memfile backend; SQL lease storage, multi-server
activation coordination and client renewal behavior are not runtime-tested here.

Run the complete gate against a matching Kea installation:

```sh
python3 -B scripts/integration.py --kea-prefix build/upstream/install --build-dir build/integration --jobs 2
python3 -B -m unittest discover -s tests -p 'test_*.py'
```

The integration runner performs a fresh Release CMake configuration with compiler
warnings treated as errors, builds the hook, runs all six CTest cases, rejects
skips and verifies cleanup. No database or DHCP host service is reconfigured.

The 2026-10-15 run passed all six tests with zero failures or skips in 395.32
seconds against Kea 3.2.1, PostgreSQL 15.19 and MariaDB 10.11.19. Cleanup passed.
Python unit discovery passed six tests; clang-format, Ruff, documentation links
and changed-file whitespace checks passed separately. The full upstream suite
and Oracle MySQL were not run.
