# DHCPv4 pools: upstream review and verification

## Review before mutation changes

The pinned, unmodified Kea source is authoritative; the clean-build guide places
it under `build/upstream/source`.
Both `PgSqlConfigBackendDHCPv4Impl::createUpdateSubnet4`
(`src/hooks/dhcp/pgsql/pgsql_cb_dhcp4.cc:966–1040`) and its MySQL counterpart
(`src/hooks/dhcp/mysql/mysql_cb_dhcp4.cc:1103–1160`) start a native transaction,
open a scoped audit revision, remove old pools on update, recreate the pools
attached to the supplied subnet, and commit. Pool deletion/insertion is part of
the subnet transaction. Passing a fresh subnet without pools would remove the
stored pools; the hook must explicitly retain them when the field is omitted.
An explicit empty collection uses the same transactional replacement path.

Native reads reconstruct pools and their richer attributes, including options,
classes and context (PostgreSQL lines 571–600; MySQL lines 676–703). This command
accepts bounded ranges or canonical CIDR notation and native class lists in M28.
Omitted pools preserve supported attributes; any supplied replacement is refused
when existing pools have class restrictions. Options, context and other unsupported
attributes still refuse updates. Preservation uses a fresh backend read, never
active runtime configuration. The existing
exclusive-writer requirement still applies: the public API offers no lock or
compare-and-swap spanning preflight reads and mutation.

Native `config-backend-pull` applies backend changes separately from persistence;
reload/restart also read the backend. The hook will not activate configuration.
SQL success does not imply that an activation succeeded or that a lease exists.

For real packet tests, `src/lib/dhcpsrv/cfg_iface.cc:168–189` explicitly permits
UDP on a selected loopback address. `src/bin/dhcp4/main.cc:129–156` exposes
testing server/client ports with `-p` and `-P`. Relayed replies use `giaddr`
(`dhcp4_srv.cc:3812`), with the testing client port overriding the usual relay
port (`dhcp4_srv.cc:3682–3683`). This permits real DHCP packets over loopback
inside a disposable unprivileged Linux network namespace, without physical
interfaces, host routing changes, privileged ports, or external traffic.

Runtime test results and the final request contract are documented after
implementation and verification below and in [commands.md](commands.md).

## Implemented contract

`subnet4.pools` is optional. Each entry supplies either `start` and `end`
IPv4 address strings or canonical prefix notation in `pool`, optionally with
`client-classes` and `evaluate-additional-classes` lists. A supplied list replaces
the collection, including `[]`, only when preservation preconditions pass.
Omission preserves supported pools from a fresh native read, or creates an empty
collection for a new subnet. Prefix changes must contain preserved pools.
Existing pool class restrictions refuse replacement; scoped options, context,
unsupported attributes, shared networks and ambiguous associations remain
protected from writes. See the [M28 capability inventory](subnet4-capabilities.md)
for the complete bounded reconstruction and comparison policy.

The hook constructs `Pool4` objects and calls `Subnet4::addPool`, using native
address-family, ordering, membership and overlap checks. Duplicate ranges,
extra fields and malformed structures are rejected before the native upsert.
Kea may serialize equivalent ranges as CIDRs; tests normalize native output.
Endpoints equal to `0.0.0.0` are rejected: both pinned SQL readers treat a zero
endpoint as an absent pool. Pools externally inserted with such endpoints are
outside this contract and cannot be protected using the native read API. Repair
that unsupported SQL state before using this command.

## Packet test architecture

`tests/packet_namespace.py` captures the original network namespace identity,
creates a disposable user/network namespace, verifies only loopback exists,
and raises loopback inside it. A nested user namespace restores a nonzero UID
for PostgreSQL. No host privilege escalation or host networking change is used.
`tests/dhcp.py` refuses to send packets unless the captured and current network
namespaces differ and only loopback exists.

Unmodified Kea 3.2.1 binds `lo/127.0.0.1` UDP on testing port 1067. A relay at
`127.0.0.2:1068` sends real BOOTP/DHCP DISCOVER and REQUEST packets with `giaddr`.
The hook creates subnet 910 (`127.0.0.0/24`) and pool `.10`–`.20`; native
activation precedes OFFER/ACK and memfile lease verification. Replacement uses
`.30`–`.40`. Checks cover transaction/client identity, server identifier,
pool membership, lifetime, and recorded active lease address/client/subnet.
Each exchange uses a fresh client. No upstream in-process simulated client is
used as packet evidence.

The fixture uses the matching `kea-lfc` executable and sets
`KEA_DHCP_DATA_DIR` to its private temporary directory. Cleanup stops the Kea
and SQL processes, removes their temporary data, and releases the namespace.
Loopback UDP with relay selection proves real packet allocation; raw Ethernet,
broadcast reception and a physical relay are not covered.

## Activation and recovery findings

Persisted SQL, native backend reads, active `config-get`, and packet/lease
results are separate assertions. The command neither activates nor rolls back
configuration. A reload with an invalid interface is deliberately rejected after
a successful write; persisted pools remain and runtime configuration stays
unchanged. The failed reload can remove the live backend connection even though
the prior runtime configuration remains. Tests compare every SQL table across
that failure, then use a corrected reload to restore backend connectivity and
activate the SQL pools.
Replacement is followed by pull/reload and an actual process restart. An active
subnet with no pools must produce no offer for a fresh client.

During backend outage the first native pull fails. After Kea removes the broken
backend, a later pull may report success as a no-op. Never treat that response
alone as activation proof: confirm backend availability and inspect `config-get`
before relying on traffic behavior. Restore availability, reconcile persisted
state, then deliberately pull or reload. Do not retry an uncertain commit
without reconciling SQL. Independent external configuration writers must remain
coordinated; preflight reads and the upsert are not one public transaction.

## Milestone 5 executed results

Final verification on 2026-10-15 passed all six project CTest cases with zero
failures and zero skips in 302.73 seconds:

| Test | Result | Seconds |
| --- | --- | ---: |
| `control_transport` | Passed | 0.05 |
| `hook_lifecycle` | Passed | 0.31 |
| `postgresql_read` | Passed | 43.02 |
| `postgresql_dhcp` | Passed | 56.79 |
| `mysql_read` | Passed | 95.92 |
| `mysql_dhcp` | Passed | 106.65 |

The clean CMake build used `-Wall -Wextra -Wpedantic -Werror`. Direct Python
unit discovery passed six tests; all eight Python modules parsed. Documentation
links and whitespace checks passed. Ruff and clang-format were unavailable and
were not run; the full upstream Kea test suite was not run. All five fixture
work directories were verified empty after process and temporary-file cleanup.

The isolated suites passed against unmodified Kea 3.2.1, PostgreSQL 15.19 and
MariaDB 10.11.19 on Debian Linux, with Kea multithreading disabled and enabled.
Both SQL engines passed one/multiple pool creation, single-address and CIDR
round trips, replacement, omission preservation, explicit removal, native audit
and timestamp checks, protection of unrelated configuration, and full table-data
comparisons after invalid requests and injected late transactional failures.
PostgreSQL sequence counters are excluded from rollback comparisons because
sequence allocation is not transactional; persisted table and audit rows are
compared. Failure injection revokes fixture-only association-table privileges
after connecting, so failure occurs inside the native write transaction.

Both packet suites passed three real DORA exchanges per threading mode: initial
activation, replacement/reload, and actual server restart. Each ACK had a
matching active memfile lease record, giving twelve verified exchanges across
the two engines and threading modes. No offer was accepted before activation
or after explicitly activating an empty pool collection. Activation-failure
SQL snapshots, backend outage, recovery, and cleanup checks passed.

These are Linux namespace/loopback relay results. Oracle MySQL, other Kea
versions, installed packaging, raw Ethernet and production load are unverified.
Writer coordination and reconciliation after an uncertain commit remain
operational requirements. The next milestone should harden reproducible CI and
release packaging around these acceptance gates before expanding configuration
functionality.
