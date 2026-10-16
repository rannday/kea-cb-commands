# Kea Database Commands

An independent MPL-2.0 C++14 hook for managing DHCPv4 subnets in ISC Kea's
SQL configuration backend. It targets **unmodified Kea 3.2.1 on Linux** and uses
Kea's native PostgreSQL and MySQL/MariaDB backend APIs and schema. It requires
no custom Kea distribution, proprietary hooks or Docker.

PostgreSQL 15 and MariaDB 10.11 are integration-tested, including real DHCP
allocation with packet multithreading enabled and disabled. Oracle MySQL is
unverified. Build against the exact Kea installation that will load the hook;
compatibility with other Kea versions is not established.

## Commands

| Command | Purpose |
| --- | --- |
| `cb-subnet4-list` | List native subnet configuration; accepts absent or empty arguments |
| `cb-subnet4-get` | Retrieve one subnet by ID or canonical IPv4 prefix |
| `cb-subnet4-set` | Persist one minimal standalone subnet and optional basic address pools |
| `cb-subnet4-del` | Delete one subnet with an explicit tag and `preserve-leases: true` |
| `db-commands-diagnostic` | Check backend pool API accessibility without testing database connectivity |

See the exact [get/set/delete contracts](docs/commands.md) and
[list contract](docs/postgresql.md#command-contract) before using them.
The hook requires one configured backend. It does not implement commercial
`cb_cmds` compatibility, shared-network management, option mutations or DHCPv6.

## Obtain a release

The initial release version is **v0.1.0**. Once published, archives and SHA-256
checksums are available from [GitHub Releases](https://github.com/rannday/kea-cb-commands/releases).
Follow the [release installation guide](docs/release-install.md) to verify,
stage and load the hook. The archive includes the library, license, install
instructions, release notes and a native dependency manifest; it bundles no Kea
or SQL/system libraries.

Local verification covers **Debian 12 WSL2, Linux x86_64**, with PostgreSQL 15
and MariaDB 10.11. Ubuntu 24.04 CI verification is pending. Choose a matching
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
  { "library": "/absolute/kea/lib/kea/hooks/libdhcp_db_commands.so" }
]
```

Use `libdhcp_mysql.so` for MariaDB. The native hook registers the backend;
Kea's `config-control` settings establish the connection. This hook does not
create a backend or read credentials. Both modules must match the daemon's ABI.

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
  "mutations-supported": true
}
```

Diagnostic arguments may be absent or empty; other arguments return an error.
It returns no credentials or configuration data. Success establishes access to
the backend manager API, not a configured or reachable database.

## Operational limits

Persistence and activation are separate. Writes never pull configuration,
reload or restart Kea; use explicit native activation afterward. Deletion retains
leases, so avoid ID/prefix reuse while retained leases could conflict.
Follow the required exclusive-writer policy and reconcile uncertain write outcomes
before retrying. See [lifecycle safety](docs/subnet-lifecycle.md) and
[mutation consistency](docs/commands.md).

Set supports minimal standalone subnets and basic IPv4 ranges. Omitted pools
preserve stored basic pools; supplied pools replace them, and an empty list
clears them. Richer existing objects and unsafe server associations are rejected.
List rejects shared-network subnets to avoid incomplete results.
MariaDB needs write grants to prepare native statements even for list operations;
PostgreSQL supports the tested SELECT-only account.

## Documentation

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
