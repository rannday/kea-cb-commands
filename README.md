# Kea Database Commands

An independent, MPL-2.0 native C++ hook project for managing ISC Kea SQL
configuration backends through Kea commands. It targets unmodified upstream Kea
on Linux and reuses its PostgreSQL and MySQL/MariaDB backend implementations and
schema. It has no dependency on another repository, custom distribution, or Docker.

**Status: diagnostic prototype verified with Kea 3.2.1.** The native hook has been
compiled, linked, and lifecycle-tested with an unmodified upstream DHCPv4 build
in Debian WSL. No SQL mutations or commercial `cb_cmds` command replacements are
implemented. See [feasibility](docs/feasibility.md) for evidence and limits.

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
  "mutations-supported": false
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
- `src/diagnostic.cc`: hook entry points and one diagnostic command
- `tests/`: bounded JSON control client, transport tests, and real-Kea lifecycle test
- `.github/workflows/ci.yml`: Linux build and lifecycle matrix, not yet executed

Original code is licensed under [MPL-2.0](LICENSE). This project is independent of
ISC and does not use proprietary hook source or binaries.
