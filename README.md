# Kea Database Commands

An independent MPL-2.0 C++14 hook for managing DHCPv4 subnets, server records,
selected global parameters, option definitions, global/scoped options, shared networks
and client classes in ISC Kea's
SQL configuration backend. It targets
**unmodified Kea 3.2.1 on Linux** and uses Kea's native PostgreSQL and
MySQL/MariaDB backend APIs and schema. It requires
no custom Kea distribution, proprietary hooks or Docker.

PostgreSQL 18 and MariaDB 12.3 LTS are the current
[acceptance targets](docs/database-support.md), including real DHCP allocation
with packet multithreading enabled and disabled. Oracle MySQL is
unverified. Build against the exact Kea installation that will load the hook;
compatibility with other Kea versions is not established.

## Commercial parity plan

The long-term target is independent DHCPv4/DHCPv6 command-interface parity with
ISC's commercial configuration-backend hook. The Kea 3.2.1
[command matrix](docs/compatibility-matrix.md) inventories 74 documented commands
(36 IPv4, 38 IPv6); none of those remote commands is implemented today.
M23 is **PARTIAL** because public contract contradictions and unspecified errors
remain. M25 adds three functional server operations and three partial scalar-global
analogues alongside the six partial subnet analogues. Existing-server deletion
is refused because native orphan cleanup cannot be verified safe. Existing
global updates/deletes are refused because native readback hides associations;
global set currently creates only when the selected native view is empty.

M26 adds eight project-specific option commands: list/get and create-only
native definitions/global options. Existing updates/deletes remain refused
because complete associations and dependency safety cannot be verified.
M27 adds four shared-network callouts: native reads and guarded fresh creation;
existing updates/deletes and membership writes remain refused. Member readback
uses native ANY scope, explicitly separated from consumer activation. See the
[dependency-safety backlog](docs/dependency-safety-backlog.md).
M29 adds twelve scoped-option callouts: list/get and guarded fresh creation for
network, subnet and pool scopes. Parent objects remain intact; existing option
updates/deletes remain refused. Pool creation requires a globally unique range.
M30 adds four client-class callouts: native ordered reads and guarded append-only
fresh creation with native expression/dependency validation, class options,
boot/lifetime fields and additional evaluation. Existing mutations and reordering
remain refused. Activation is explicit; packet tests verify classification.
Functional coverage is 3 implemented, 24 partial, 47 missing of 74; exact
commercial compatibility remains zero. There are 41 project commands.
Production readiness remains NO-GO.

See the [gap analysis](docs/commercial-parity-gap-analysis.md),
[shared architecture](docs/command-architecture.md) and
[feature roadmap](docs/development-roadmap.md). M24 extracts shared request,
response and typed backend helpers and adds an isolated DHCPv6 API compile/link
probe. M25 adds eight project-specific callouts using those helpers; existing
contracts are unchanged. DHCPv6 daemon loading and operations remain unimplemented.

## Reconciliation and recovery

Milestone 22 is **PARTIAL**; production readiness remains **NO-GO**.
[Read-only evidence](docs/reconciliation-evidence.md) distinguishes persisted
SQL, approved intent and independently observed consumer runtime state.
The [recovery gate](docs/operator-recovery.md) retains durable holds and refuses
incomplete/stale evidence. Exact full-configuration equivalence and real
evidence-gated resumption are not yet qualified. Production hook behavior is
unchanged.

## Commands

| Command | Purpose |
| --- | --- |
| `cb-client-class4-list/get/set/del` | Read ordered classes; append fresh classes; refuse existing writes |
| `cb-option4-network/subnet/pool-list/get/set/del` | Read scoped options; create absent identities; refuse existing writes |
| `cb-shared-network4-list/get/set/del` | Read native networks/membership; create minimal new networks; refuse existing writes |
| `cb-option-def4-list/get/set/del` | Read/create native definitions; refuse existing update/delete |
| `cb-option4-global-list/get/set/del` | Read/create native global options; refuse existing update/delete |
| `cb-server4-list`, `cb-server4-get` | Read native server records |
| `cb-server4-set` | Create/update a server description |
| `cb-server4-del` | Report missing records; refuse existing-record deletion |
| `cb-global-parameter4-list/get/set/del` | Read selected globals; create bounded scalars; refuse existing update/delete |
| `cb-subnet4-list` | List native subnet configuration; accepts absent or empty arguments |
| `cb-subnet4-get` | Retrieve one subnet by ID or canonical IPv4 prefix |
| `cb-subnet4-set` | Persist a bounded rich standalone subnet; preserve omitted attributes and pools |
| `cb-subnet4-del` | Delete one subnet with an explicit tag and `preserve-leases: true` |
| `db-commands-diagnostic` | Check backend pool API accessibility without testing database connectivity |

See the exact [get/set/delete contracts](docs/commands.md) and
[list contract](docs/postgresql.md#command-contract) before using them.
The hook requires one configured backend. It does not implement commercial
`cb_cmds` compatibility, shared-network replacement/deletion or membership mutation,
existing option replacement/deletion
or DHCPv6.

## Obtain a release

The initial release version is **v0.1.0**. Once published, archives and SHA-256
checksums are available from [GitHub Releases](https://github.com/rannday/kea-cb-commands/releases).
Follow the [release installation guide](docs/release-install.md) to verify,
stage and load the hook. The archive includes the library, license, install
instructions, release notes and a native dependency manifest; it bundles no Kea
or SQL/system libraries.

Local verification covers **Debian 12 WSL2, Linux x86_64**, with PostgreSQL 18
and MariaDB 12.3 LTS. Ubuntu 24.04 CI verification is pending. Choose a matching
platform/runtime and Kea C++ ABI; the archives are not portable across arbitrary
Linux installations. See [release notes](docs/release-notes.md) for limitations.
Public release publication remains pending maintainer approval.

## Build and install from source

Use native Linux or Debian WSL2 with a C++14 compiler, CMake/CTest, pkg-config
and matching shared Kea libraries and development headers. SQL integration also
requires Kea's upstream SQL hooks and schemas. The
[build guide](docs/reproducible-builds.md) lists exact prerequisites and commands
for a verified-source Kea build with both backends.

For an existing matching installed prefix (the clean-build guide uses
`build/upstream/install`):

```bash
export KEA_PREFIX="$PWD/build/upstream/install"
export PKG_CONFIG_PATH="$KEA_PREFIX/lib/pkgconfig"
export LD_LIBRARY_PATH="$KEA_PREFIX/lib"
export PATH="$KEA_PREFIX/sbin:$KEA_PREFIX/bin:$PATH"
cmake -S . -B build/hook -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX="$KEA_PREFIX" \
  -DCMAKE_INSTALL_LIBDIR=lib -DKEA_DB_COMMANDS_RUNTIME_TESTS=ON
cmake --build build/hook --parallel 2
ctest --test-dir build/hook --output-on-failure
cmake --install build/hook
```

This produces `build/hook/libdhcp_db_commands.so` and installs it under
`$KEA_PREFIX/lib/kea/hooks/`. Choose an installation prefix writable by your
installation process. Do not mix Windows/MSYS2 libraries or statically embedded
Kea with a Linux daemon. The build guide covers full SQL/DHCP acceptance and
export/dependency verification; the commands above run lifecycle coverage only.

## Configure and use

Configure Kea's native SQL backend as described in
[PostgreSQL setup](docs/postgresql.md#configure-kea) or
[MariaDB setup](docs/mysql.md#configure-kea). Load the matching upstream SQL hook
before this hook. For example, add these entries to the existing `Dhcp4`
configuration, using absolute paths inside Kea's permitted hook directory:

```json
"hooks-libraries": [
  { "library": "/absolute/kea/lib/kea/hooks/libdhcp_pgsql.so" },
  {
    "library": "/absolute/kea/lib/kea/hooks/libdhcp_db_commands.so",
    "parameters": { "allow-mutations": true }
  }
]
```

Use `libdhcp_mysql.so` for MariaDB. The native hook registers the backend;
Kea's `config-control` settings establish the connection. This hook does not
create a backend or read credentials. Both modules must match the daemon's ABI.

The example grants local mutation admission to the **designated administrative
writer**. Current development builds deny `cb-subnet4-set` and `cb-subnet4-del`
by default. Configure a read-only consumer with:

```json
"parameters": { "allow-mutations": false }
```

Omitting `parameters` or `allow-mutations` also denies mutations. Only a native
JSON boolean is accepted; strings, numbers, null and unknown parameter names
fail hook initialization. Diagnostic/list/get remain available. Permission is
fixed until hook reload and cannot be changed through a hook command.

**Breaking upgrade change:** existing writers must explicitly configure
`"allow-mutations": true` before adopting this development version. Published
v0.1.0 artifacts are unchanged. Milestone 20 SQL/DHCP acceptance now passes;
Milestone 21 qualifies a controlled same-host designated-writer deployment;
production qualification remains separate. See the
[roadmap](docs/development-roadmap.md) before deployment.

This guard is local admission, not fencing, locking or leader election. Multiple
enabled writers against one database are unsupported unless external enforcement
guarantees exclusive ownership. Server tags do not isolate writers. Prefer a
non-serving administrative writer; see [operations](docs/operations.md).

Send requests through Kea's configured native control channel:

```json
{"command": "cb-subnet4-get", "arguments": {"id": 123}}
```

For a connection-independent load check, send
`{"command":"db-commands-diagnostic"}`. A successful response has `result: 0`
and these arguments:

```json
{
  "configuration-backend-pool-accessible": true,
  "kea-hooks-version": 30201,
  "database-connectivity-tested": false,
  "mutations-supported": true,
  "allow-mutations": true
}
```

Diagnostic arguments may be absent or empty; other arguments return an error.
It returns no credentials or configuration data. Success establishes access to
the backend manager API, not a configured or reachable database.
`mutations-supported` describes command capability; `allow-mutations` reports
effective local admission (false on an omitted/consumer configuration).

## Operational limits

Persistence and activation are separate. Writes never pull configuration,
reload or restart Kea; use explicit native activation afterward. Deletion retains
leases, so avoid ID/prefix reuse while retained leases could conflict.
Follow the required exclusive-writer policy and reconcile uncertain write outcomes
before retrying. See [lifecycle safety](docs/subnet-lifecycle.md) and
[mutation consistency](docs/commands.md).

M28 adds renew/rebind timers, boot parameters, client-class restrictions and
prefix-style pools. Omitted optional attributes and pools preserve supported
stored values. Supplied pools replace the list only when existing pools have no
class restrictions; `[]` has the same safety gate. Scoped options, shared-network
members, unsupported attributes and unsafe associations still prevent updates.
See the [subnet capability inventory](docs/subnet4-capabilities.md).
List rejects shared-network subnets to avoid incomplete results.
MariaDB needs write grants to prepare native statements even for list operations;
PostgreSQL supports the tested SELECT-only account.

## Documentation

- [Current production-readiness review](docs/production-readiness-review.md)
  and [prioritized development roadmap](docs/development-roadmap.md)
- [Exclusive-writer architecture](docs/multi-writer-architecture.md),
  [transaction recovery policy](docs/transaction-recovery-policy.md) and
  [runtime activation design](docs/runtime-activation-design.md)
- [Designated-writer deployment](docs/designated-writer-deployment.md),
  [writer fencing runbook](docs/writer-fencing-runbook.md) and
  [fleet activation runbook](docs/fleet-activation-runbook.md)
- [Command contracts and explicit activation](docs/commands.md)
- [PostgreSQL setup and coverage](docs/postgresql.md) and [MariaDB setup and coverage](docs/mysql.md)
- [Backend selection, tags and recovery](docs/backend-behavior.md)
- [Installation checks, security and troubleshooting](docs/operations.md)
- [Milestone 9 release assessment and validation](docs/release-readiness.md)
- [Pool semantics and packet verification](docs/pools.md)
- [Architecture](docs/architecture.md) and [upstream feasibility evidence](docs/feasibility.md)
- [Development and output layout](docs/development.md)
- [Reproducible builds, quality, CI and acceptance](docs/reproducible-builds.md)
- [Docker validation of the published Ubuntu release](tests/docker/README.md)
- [Release installation](docs/release-install.md), [notes](docs/release-notes.md)
  and [maintainer release procedure](docs/releases.md)

Original code is licensed under [MPL-2.0](LICENSE). This project is independent
of ISC and does not use proprietary hook source or binaries.
