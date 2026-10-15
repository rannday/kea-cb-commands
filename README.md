# Kea Database Commands

An independent, MPL-2.0 native C++ hook project for managing ISC Kea SQL
configuration backends through Kea commands. It targets unmodified upstream Kea
on Linux and reuses its PostgreSQL and MySQL/MariaDB backend implementations and
schema. It has no dependency on another repository, custom distribution, or Docker.

**Status: native DHCPv4 reads and minimal subnet create/update verified on Kea
3.2.1 using PostgreSQL 15 and MariaDB 10.11.**
`cb-subnet4-list` reads through Kea's existing configuration backend interfaces
and returns native subnet configuration. `cb-subnet4-set` persists one minimal
standalone subnet through those same interfaces, without activating it.
See the [mutation command contract](docs/commands.md), including its required
exclusive-writer policy, and [PostgreSQL integration](docs/postgresql.md)
for setup, the command contract and verified complex fields;
[backend behavior](docs/backend-behavior.md) for selection, recovery and upstream
evidence; and [MySQL/MariaDB](docs/mysql.md) for reproducible native builds,
isolated tests and verified privilege requirements. MariaDB requires write grants
to prepare native statements even though listing performs no writes;
PostgreSQL supports the tested SELECT-only account. Oracle MySQL is unverified.
The list command requires one configured backend, accepts only absent or empty
arguments, and rejects shared-network subnets to avoid incomplete results.
Commercial `cb_cmds` compatibility, deletion, pools/options mutations and DHCPv6
are not implemented. DHCP allocation from written subnets is not verified.

Initial build candidates are **Kea 3.2.1** (first target) and **3.0.4 LTS**
(second target, source-assessed only). Build a separate artifact against
each exact Kea installation; even a patch release changes the hook version check.
The prototype accepts DHCPv4 only. The design includes DHCPv6 as a later milestone.

## Quick start

Use Linux or Debian WSL2. Install prerequisites and build shared-library Kea with
the exact instructions in [development](docs/development.md). Do not link against
Windows/MSYS2 Kea libraries or a static copy of Kea.

With a matching Kea installation at an isolated prefix:

```bash
export KEA_PREFIX="$PWD/.local/kea/3.2.1"
export PKG_CONFIG_PATH="$KEA_PREFIX/lib/pkgconfig${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"
export LD_LIBRARY_PATH="$KEA_PREFIX/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export PATH="$KEA_PREFIX/sbin:$KEA_PREFIX/bin:$PATH"
cmake -S . -B build -DCMAKE_BUILD_TYPE=Debug \
  -DKEA_DB_COMMANDS_RUNTIME_TESTS=ON
cmake --build build --parallel 2
ctest --test-dir build --output-on-failure
```

The output is `build/libdhcp_db_commands.so`. To load it in a test DHCPv4
configuration, add its **absolute Linux path** to the existing `Dhcp4` object:

```json
"hooks-libraries": [
  { "library": "/absolute/path/build/libdhcp_db_commands.so" }
]
```

Send `{"command":"db-commands-diagnostic"}` over the configured native control
channel. A successful response has `result: 0` and these `arguments`:

```json
{
  "configuration-backend-pool-accessible": true,
  "kea-hooks-version": 30201,
  "database-connectivity-tested": false,
  "mutations-supported": true
}
```

The hook version is `30004` when built for 3.0.4. Pool accessibility proves access
to the server's backend manager API; it does not prove a database is configured or
reachable. Arguments may be absent or an empty object. Other arguments return an
error. The command returns no credentials or configuration data.

## Project contents

- [Feasibility and upstream evidence](docs/feasibility.md)
- [Architecture and implementation roadmap](docs/architecture.md)
- [Development, prerequisites, and verification](docs/development.md)
- [PostgreSQL setup and integration tests](docs/postgresql.md)
- [Minimal subnet mutation contract and activation](docs/commands.md)
- [Verified backend selection, selectors and recovery](docs/backend-behavior.md)
- [MySQL/MariaDB prerequisites and isolated test](docs/mysql.md)
- `src/diagnostic.cc`: hook entry points, diagnostic, subnet list and set commands
- `tests/`: transport, real-Kea lifecycle, and isolated PostgreSQL/MySQL tests
- `.github/workflows/ci.yml`: Linux build and lifecycle matrix, not yet executed

Original code is licensed under [MPL-2.0](LICENSE). This project is independent of
ISC and does not use proprietary hook source or binaries.
