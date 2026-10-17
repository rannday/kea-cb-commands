# Designated-writer deployment

Milestone 21 qualifies a controlled, same-host deployment with unmodified Kea
3.2.1 and the Milestone 20 hook. It does not qualify unrestricted independent
writers or production readiness. See the [fencing runbook](writer-fencing-runbook.md)
and [fleet activation runbook](fleet-activation-runbook.md).

## Milestone 22 qualification

M22 adds [reconciliation evidence](reconciliation-evidence.md) and a
[durable recovery gate](operator-recovery.md) to the same isolated role harness.
Its safety qualification runs on both SQL engines and both threading modes.
It is **PARTIAL**: associations and selector views are retained, but full
backend/runtime equivalence is incomplete. Every real M22 recovery attempt
keeps its hold. Successful M21 bounded replacement below is not proof of M22
exact-state resumption. No remote or distributed fencing is qualified.

## Topology and isolation

| Role | Hook admission | Interfaces | Control | Configuration backend |
| --- | --- | --- | --- | --- |
| Administrative writer | true | none | private loopback HTTP | one shared SQL database |
| Consumer A | false | namespace loopback UDP 1067 | separate loopback HTTP | same SQL database |
| Consumer B | false | namespace loopback UDP 1167 | separate loopback HTTP | same SQL database |

Each role has an independent process, PID/lock/data directory, configuration and
authenticated control endpoint. The old and replacement writer are never live
together. Role-specific server tags identify processes; writes use the universal
`all` association. Tags are visibility selectors, not ownership or fencing domains.
Consumer denials are checked with universal, administrative and consumer tags.

The existing packet namespace runner creates a disposable network namespace
containing only loopback. Real relayed unicast DHCP uses relay
`127.0.0.2:1068`; there are no LAN broadcasts or externally reachable DHCP
interfaces. Each consumer has its own memfile leases. They deliberately use
different UDP server ports: this tests independent packet handling, not a
shared-link HA pair or conflict-free shared lease allocation.

The administrative configuration uses `"interfaces-config": {"interfaces": []}`.
Pinned upstream source permits this configuration; a warning about no sockets
does not prevent the control server running. Qualification checks the active
interface list, the writer's file descriptors against UDP/raw/packet socket
tables, exclusive binding of its reserved probe port and silence to a DHCP probe.
The replacement is checked again. This is a verified packetless administrative
role, not merely an expectation from admission settings.

## Configuration examples

Merge these fragments into separate complete Kea configurations. Native SQL hook
comes first, followed by this hook; paths must match the installed Kea build.

```json
{
  "interfaces-config": {"interfaces": []},
  "server-tag": "admin-old",
  "hooks-libraries": [
    {"library": "/opt/kea/lib/kea/hooks/libdhcp_pgsql.so"},
    {"library": "/opt/kea/lib/kea/hooks/libdhcp_db_commands.so",
     "parameters": {"allow-mutations": true}}
  ],
  "config-control": {
    "config-fetch-wait-time": 0,
    "config-databases": [
      {"type": "postgresql", "name": "kea_config", "user": "kea_writer",
       "host": "/run/private-postgresql", "port": 5432}
    ]
  }
}
```

Consumers set `allow-mutations: false`, distinct role tags, and their own
interfaces, lease store and authenticated control endpoint. Omission also
defaults to false; explicit false is used in this qualification. MariaDB uses
native `libdhcp_mysql.so` and backend type `mysql`. Set fetch interval zero on
every role. SQL persistence never requests runtime activation.

## Database permissions and trust

PostgreSQL's disposable writer has CONNECT, schema USAGE, SELECT/INSERT/UPDATE/
DELETE on configuration tables and USAGE/SELECT on sequences. Consumers use
SELECT-only `kea_reader` with `default_transaction_read_only=on`. The native
MariaDB driver prepares write statements at startup, including on consumers;
its schema-scoped consumer account therefore needs SELECT/INSERT/UPDATE/DELETE.
The distinct MariaDB writer also needs EXECUTE for native audit routines; the
consumers do not receive EXECUTE. Provision the writer's required grants before
starting it.
Neither backend's application account receives DDL or administrative grants.
Schema creation and snapshots use the private fixture's administrative account.

MariaDB consumers are read-only through hook admission, not through their SQL
credentials. These grants and a trusted local supervisor are assumptions, not a
security boundary against arbitrary code, stolen credentials or an administrator
starting an additional writer. No database privilege revocation or session
termination is claimed. All test identities, authentication files and databases
are disposable.

## Reproduction

Use native Linux or Debian WSL with the existing integration prerequisites.
Run from the repository root, using the unchanged matching Kea installation:

```sh
python3 -B scripts/integration.py --kea-prefix build-repro-clean/install \
  --build-dir build/integration --jobs 2 --skip-outages
PKG_CONFIG_PATH="$PWD/build-repro-clean/install/lib/pkgconfig" \
  cmake -S . -B build/integration -DKEA_DB_COMMANDS_DESIGNATED_WRITER_TESTS=ON
ctest --test-dir build/integration -R '_designated_writer$' \
  --parallel 1 --output-on-failure \
  --output-junit "$PWD/build/milestone21/deployment-results.xml"
```

The first command runs the existing six-test Release C++14 gate. Deliberate
database outages are excluded; no session interruption is needed for this
milestone. The new opt-in CTest tests each loop over packet MT off/on, sharing
the existing private PostgreSQL/MariaDB provisioning and packet helpers. Both
SQL and DHCP CMake families must be enabled. Missing prerequisites/skips are
not qualification passes.

Each scenario removes its daemons, temporary SQL state and namespace. Sanitized
event journals survive in `build/integration/designated-writer-results/`;
JUnit and CTest logs record backend cleanup. A failed prerequisite or assertion
returns nonzero. The existing Docker harness installs the published v0.1.0
artifact, which lacks this development hook's admission gate; reusing that
artifact would test the wrong functionality. This milestone extends the native
integration infrastructure rather than rebuilding the release-only Docker image.
Docker/container fencing and remote-host fencing remain unverified.

## Executed qualification

**PASS (2026-10-17), within the controlled same-host boundary.**

| Backend | Packet MT off | Packet MT on |
| --- | --- | --- |
| PostgreSQL 15 | PASS; six DORA/lease checks | PASS; six DORA/lease checks |
| MariaDB 10.11 | PASS; six DORA/lease checks | PASS; six DORA/lease checks |

Every scenario verifies consumer mutation denial with unchanged SQL/runtime,
native writer set/delete, packetless old/replacement writers, actual graceful
process fencing, blocked unsafe promotion, reconciliation, replacement, staged
activation and partial-failure write hold. The six existing regression tests
also pass without skips, with deliberate SQL outages excluded. Exact commands,
initial fixture failure and final evidence are in `build/milestone21/checks.md`.
The two opt-in CTest tests each execute both threading modes; neither skipped.

## Supported lifecycle and limits

The only qualified transfer is planned: hold new mutations, finish all known
writes, gracefully shut down and reap the old writer, prove endpoint closure,
reconcile SQL, then start one replacement. No process manager restarts the old
writer in this test. Restart suppression must remain enforced by the deployment
owner throughout the writer's retired lifetime.

The tested workflow automatically holds further mutations after partial
activation. Direct control calls or another tool can bypass that workflow;
production access controls and a durable operator-owned hold are still required.
A process crash, uncertain transaction outcome, unobservable host, lost
supervisor state or unknown restart authority prohibits promotion. No automatic
retry, failover, election, distributed lock or hook change is introduced.
