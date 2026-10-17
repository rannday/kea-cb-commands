# Native PostgreSQL integration

This milestone targets unmodified Kea 3.2.1 with shared libraries and its
open-source `libdhcp_pgsql.so`. It implements native DHCPv4 listing and a minimal
subnet mutation, not a complete replacement for ISC's commercial Configuration
Backend Commands hook. No proprietary module, direct SQL client or custom schema
is used by our hook. The following list contract is unchanged; see
[the set command](commands.md) for writes and consistency limits.

## Command contract

Send through Kea's configured native command channel:

```json
{"command":"cb-subnet4-list","arguments":{}}
```

`arguments` may be absent or an empty map. All other arguments are rejected.
Success is `result: 0`, including an empty backend:

```json
{
  "result": 0,
  "text": "DHCPv4 subnets retrieved.",
  "arguments": {"server-tag": "all", "subnet4": []}
}
```

Each entry in `subnet4` is Kea's native `Subnet4::toElement()` representation:
the normal configuration fields, such as `id`, `subnet`, `valid-lifetime`, pools
and options. Native serialization may emit default or empty fields. No parallel
subnet schema is defined. Missing or failed backends produce `result: 1` and a
generic error; exception text and database connection parameters are never
included by this hook. Responses are synchronous.

The selector follows the active Kea configuration's `server-tag`. An absent or
empty tag uses `ServerSelector::ALL()`, which selects objects associated with
the universal `all` tag. It does **not** mean every server's objects. A configured
tag uses `ONE(tag)`, including objects associated with that tag and universal
objects. The response reports the effective tag. Arbitrary selectors, `ANY`,
unassigned objects and per-request tag overrides are not exposed.

The command requires exactly one configured backend and selects its native type
(PostgreSQL or MySQL). No backend is an error. Multiple configured backends are
an error even if some are empty or their data is disjoint. An explicit selector
without a matching live backend throws upstream and returns an error, including
during recovery. A connected database with no matching subnets returns an empty
list successfully. No backend index, host, database name or server-tag override
is accepted in command arguments. See [verified backend behavior](backend-behavior.md).

Shared-network subnets cause the entire command to return an error without a
partial list: native flat subnet serialization omits shared-network membership
and inherited settings. The response is stored subnet configuration, not a full
effective server configuration: shared networks, globals, class definitions and
option definitions are not exported by this command.

All command errors use `result: 1` and omit `arguments`. Stable error texts are:

| Condition | `text` |
| --- | --- |
| Invalid arguments | `cb-subnet4-list accepts only absent or empty arguments.` |
| No configured backend | `No configuration backend is configured.` |
| Multiple configured backends | `cb-subnet4-list requires exactly one configured backend; multiple backends cannot be listed without ambiguity.` |
| Shared-network subnet | `Shared-network subnets cannot be represented completely by cb-subnet4-list.` |
| Native read/connection failure | `Configuration backend read failed or unavailable.` |

## Configure Kea

Initialize a disposable database with the official Kea 3.2.1 schema. The normal
installed administration procedure is `kea-admin db-init pgsql` with your test
host, port, user and database. The integration harness instead executes the
unchanged release's `src/share/database/scripts/pgsql/dhcpdb_create.pgsql` using
`psql -X -v ON_ERROR_STOP=1 -f`; this procedure is documented in that script's
header. Kea validates the schema version when it opens the backend. Do not use
a schema copied from a different release or initialize an existing database.

Add these fields to your test `Dhcp4` configuration, substituting isolated paths
and test connection values:

```json
"hooks-libraries": [
  {"library": "/absolute/hooks/libdhcp_pgsql.so"},
  {"library": "/absolute/hooks/libdhcp_db_commands.so",
   "parameters": {"allow-mutations": true}}
],
"config-control": {
  "config-fetch-wait-time": 0,
  "config-databases": [
    {"type": "postgresql", "host": "/private/test/socket",
     "port": 5432, "name": "kea_test", "user": "kea_reader",
     "on-fail": "serve-retry-continue",
     "max-reconnect-tries": 30, "reconnect-wait-time": 1000}
  ]
}
```

Both modules must match the daemon's exact build/ABI and reside in Kea's allowed
hook directory. For an isolated test directory set `KEA_HOOKS_PATH` accordingly.
The native PostgreSQL module registers the backend factory; Kea's startup
configuration initializes the connection. Our hook neither initializes a backend
nor reads credentials. Use your normal secured Kea configuration mechanism for
password-authenticated connections; do not put real credentials in tracked files.

## Reproducible test

The current target is PostgreSQL 18, including its latest maintenance patch;
see [database support](database-support.md). Required packages are
`postgresql-18`, `postgresql-client-18` and `libpq-dev` from the official
PostgreSQL repository for your distribution. The latter is also required when
building Kea. Ensure `pg_config --bindir` selects the PostgreSQL 18 tools.
Install missing packages yourself; tests never install packages, change system
configuration, start persistent services, or touch the distribution's cluster.

Build the matching installed Kea prefix with both SQL backends as described in
[reproducible builds](reproducible-builds.md). From this Linux checkout, run the
strict full gate, then select PostgreSQL tests for focused reruns:

```bash
python3 -B scripts/integration.py --kea-prefix build/upstream/install \
  --build-dir build/integration --jobs 2
ctest --test-dir build/integration -L PostgreSQL --output-on-failure
```

For an existing local prefix, follow the incremental migration example in
[development](development.md#generated-output-layout). Earlier uninstalled
build-tree commands are retained in [development history](development-history.md).

CTest supplies `LD_LIBRARY_PATH` from the matching `kea.pc` library directories
for the SQL test only. This preserves dependency lookup when upstream's module,
whose build-tree RUNPATH uses relative `$ORIGIN` paths, is staged into the private
hook directory. A standalone script invocation needs equivalent library lookup.

SQL tests are opt-in and separately labeled. Missing binaries, hook or schema,
or execution as root, exits with CTest's explicit skip code 77. A failing
dependency or assertion is a failure, not a skip. Tests require no Docker.

`tests/postgresql.py` starts a new `initdb` cluster for each threading mode,
with no TCP listener and a private mode-0700 Unix socket directory. Local trust
authentication is confined to this disposable instance. It uses a reader role
with SELECT grants and `default_transaction_read_only=on`; administrative
connections alone initialize the schema and insert the tracked test fixture.
HTTP credentials are freshly generated, stored privately and removed on cleanup.
Logs are captured privately and not echoed because upstream errors can contain
connection details.

The test validates parsed JSON semantically, using typed IP addresses, exact
ID sets, field values and counts while ignoring native defaults and ordering:

- Empty database and populated database with no matching associations.
- Multiple subnets; two pools in one subnet; subnet router and DNS options;
  pool domain-name option; CSV representation and always-send behavior.
- Subnet valid/renew/rebind timers, client classes, additional evaluated classes,
  pool client classes and user context.
- Universal, specific, missing and unassigned server associations. `ONE` includes
  universal rows; neither exposed selector includes unassigned rows.
- Multiple configured databases, including an empty second database and
  overlapping subnet IDs, rejected before listing. The official schema rejects
  duplicate IDs inside one database with a unique-constraint violation.
- Shared-network membership with inherited lifetime, rejected without partial
  results because native flat serialization cannot preserve that configuration.
- Invalid arguments; fresh database reads while runtime `subnet4` stays empty;
  unchanged complete data/sequence dumps across successful and rejected reads.
- Database stop, repeated errors while native retry callbacks run, restart of
  the same private cluster, and automatic recovery without configuration reload.

Both multithreading modes use fresh clusters and clean shutdown. In the read
phase, fixture writes are administrative setup only. The reader has SELECT grants and read-only
transactions. The fixture uses `serve-retry-continue`, 30 attempts and a one-second
retry interval. Kea owns retries and connection replacement; the hook adds none.
The default failure policy may stop the daemon. Initial connection failures and
retry exhaustion are not runtime-tested here. See [recovery details](backend-behavior.md).

## Architectural limits

- Exactly one configured backend is required. Multiple databases are explicitly
  rejected; the native pool is not an aggregate and offers no database-name/index
  selector. Shared-network subnets are explicitly rejected.
- Kea owns the live backend connection and schema checks. This command requires
  an already initialized backend. A failed initial connection may prevent the
  daemon starting, before a command can be sent.
- Native SQL configuration backends hold a single connection. Their own
  multithreading declaration assumes calls occur on the main thread. The hook
  executes synchronously on Kea's main command IO loop, creates no worker, and
  keeps no backend pointers across reloads. Concurrent external invocation from
  arbitrary threads is not supported.
- The hook suppresses raw exception text. Upstream PostgreSQL code can log
  database error details itself; secure the daemon's logging as usual.
- Listing has no pagination or project-side size cap. Large configurations may
  block command processing and exceed a client's response limit (the test client
  caps responses at 1 MiB). Production scale/load testing remains open.
- Reads do not activate or change runtime configuration. Schema mismatch,
  initial failure/retry exhaustion, production load, DHCPv6, installed packaging
  and Kea 3.0.4 SQL behavior remain unverified. MySQL/MariaDB has an
  [verified native MariaDB integration](mysql.md).
- No `cb-subnet4-list` occurrence was found in the pinned public Kea source or
  its documentation, including commercial-hook command documentation. This is
  an independent command contract; proprietary implementations were not inspected.

## Milestone 4 mutation phase

The same opt-in harness now runs `tests/mutation.py` after proving the unchanged
SELECT-only read behavior. A separate disposable `kea_writer` role receives
CONNECT on its private database, USAGE on public schema, SELECT/INSERT/UPDATE/DELETE
on official tables, and USAGE/SELECT on official sequences. This is a verified
working grant set, not a claim of least possible per-table privileges. Official
schema function execution defaults are retained; no superuser or DDL is granted
to the backend role. Do not grant these permissions to the SELECT-only reader.

For a freshly initialized disposable `kea_test` database, equivalent fixture
setup is:

```sql
CREATE ROLE kea_writer LOGIN;
GRANT CONNECT ON DATABASE kea_test TO kea_writer;
GRANT USAGE ON SCHEMA public TO kea_writer;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO kea_writer;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO kea_writer;
```

This password-free example is confined to the private local-trust test instance.
Use your existing secure authentication mechanism elsewhere. Configure the
writer role and explicitly reload before issuing writes; changing files alone
does not replace a live backend connection.

Both threading modes verify create and update, exact ID/prefix/lifetime and
association persistence, conflict and unsupported-field errors, unchanged other
subnets, native audit entries and changing timestamps. Revoking association-table
INSERT forces failures after native subnet INSERT and UPDATE. All table contents,
including audit, match their pre-operation snapshots after rollback. Sequence
states are deliberately excluded from that rollback assertion: PostgreSQL
sequence allocation is nontransactional. Existing read nonmutation checks still
compare sequences as well as data.

With periodic fetch disabled, backend reads see writes immediately while active
`config-get` retains prior data. Explicit `config-backend-pull`, `config-reload`
and real Kea restart load the expected data. DHCP allocation is unverified:
minimal written subnets have no pools and the harness opens no DHCP interface.
See [activation and exclusive-writer requirements](commands.md).

## Milestone 5 pool and packet extension

The existing SQL test now shares the pool mutation cases in `tests/mutation.py`.
The contract accepts only explicit IPv4 start/end ranges. An omitted `pools`
field preserves freshly read basic pools; an explicit list replaces the complete
collection, including `[]` to remove all pools. Rich existing subnet/pool settings
remain protected. Native transactions include pool changes and audit records;
the late-failure checks compare complete table contents after rollback. See
[the contract](commands.md) and [upstream pool evidence](pools.md).

Enable `KEA_DB_COMMANDS_DHCP_TESTS=ON` alongside this engine's existing SQL test
option to add `postgresql_dhcp`. Both threading modes use fresh private databases
and an unmodified Kea 3.2.1 server in a disposable unprivileged user/network
namespace. Loopback relay packets on test UDP ports 1067/1068 exercise real
DISCOVER/OFFER/REQUEST/ACK and persisted memfile leases. The test does not use a
SQL lease backend; SQL manages the subnet/pools and Kea records the lease in
its own memfile. Native pull, replacement/reload, restart and empty-pool checks
separate persistence from activation and allocation. Failed activation does not
roll back SQL. See [build and namespace prerequisites](development-history.md#milestone-5-pool-and-packet-verification).

Milestone 5 pool mutations and real DHCP packet checks passed against PostgreSQL
15.19 in both threading modes; [the pool verification record](pools.md)
identifies coverage and skipped checks. Earlier milestone
results above establish the previous contract only. Concurrent external writers
and connection loss exactly at commit remain unsupported/uncertain respectively.
