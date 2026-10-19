# kea-cb-commands

## Project boundary

Independent C++14 Linux shared-library hook for unmodified ISC Kea 3.2.1.
The artifact is `libdhcp_db_commands.so`, loaded by `kea-dhcp4` only.
PostgreSQL 18 and MariaDB 12.3 LTS are the integration targets; MariaDB uses Kea's
`mysql` backend type. Oracle MySQL is unverified. Kea 3.0.4 is source-assessed
only; build against the exact Kea installation that will load the hook.
See [README](README.md), [database support](docs/database-support.md) and
[architecture](docs/architecture.md).

## Implementation map

All sources build into one CMake `MODULE`; headers in `src/` are private.

| File | Responsibility |
| --- | --- |
| [diagnostic.cc](src/diagnostic.cc) | Lifecycle exports, registration, Kea logging and message dictionary |
| [commands.cc](src/commands.cc), [commands.h](src/commands.h) | 41 callout boundaries, response construction and exception containment |
| [arguments.cc](src/arguments.cc), [arguments.h](src/arguments.h) | Identity validation, bounded native subnet/pool preservation and `ContractError` |
| [subnet4.cc](src/subnet4.cc), [subnet4.h](src/subnet4.h) | Backend selection, server-tag policy and native subnet CRUD |
| [records4.cc](src/records4.cc), [options4.cc](src/options4.cc) | Server/scalar-global and definition/global-option handlers |
| [shared_network4.cc](src/shared_network4.cc), [scoped_options4.cc](src/scoped_options4.cc) | Network and scoped-option handlers |
| [client_classes4.cc](src/client_classes4.cc) | Ordered class reads and guarded fresh creation |
| [command_support.h](src/command_support.h), [backend_support.h](src/backend_support.h), [option_support.h](src/option_support.h) | Shared request, admission, backend and native option helpers |
| [CMakeLists.txt](CMakeLists.txt) | Kea API/link probe, shared module and opt-in CTest families |

Required C exports are `version`, `load`, `unload` and
`multi_threading_compatible`. Kea owns callout deregistration on unload.

## Command contracts

- `db-commands-diagnostic`: pool API accessibility, not database connectivity.
- `cb-subnet4-list`: absent/empty arguments; native subnet serialization.
- `cb-subnet4-get`: one ID or canonical IPv4 prefix, optional server tag.
- `cb-subnet4-set`: explicit server tag and one bounded standalone subnet, optional pools.
- `cb-subnet4-del`: one identity, explicit tag and `preserve-leases: true`.

Exact fields, response codes and failures are defined in
[command contracts](docs/commands.md) and the
[list contract](docs/postgresql.md). Keep those interfaces compatible.
The [M31 inventory](docs/dhcp4-qualification.md) enumerates all 41 commands,
including server records, scalar globals, definitions, global/scoped options,
shared networks and client classes. Fresh-only and refused mutation boundaries
are family-specific. DHCPv6 and exact commercial `cb_cmds` compatibility remain
unimplemented.

## Behavioral invariants

- Default-deny set/delete admission via the native boolean hook parameter
  `allow-mutations`. Validate strictly at load; reset before load/unload. Admission
  is local, not cross-process fencing. See [migration](docs/mutation-admission.md).

- Resolve `ConfigBackendDHCPv4Mgr::instance().getPool()` per invocation;
  retain no backend state across reloads and create no private manager.
- Use native Kea configuration backend APIs, shared core libraries and upstream
  SQL hooks. The hook issues no direct SQL and needs no paid hooks.
- Require one configured backend; the native pool's first-nonempty read behavior
  is not database aggregation. Preserve `ALL`/`ONE(tag)` visibility and `ANY`
  conflict checks; reject shared-network subnets and unsafe associations.
- Subnet set supports the bounded standalone attributes in
  [subnet capabilities](docs/subnet4-capabilities.md); refuse unsupported existing
  properties. Omitted pools preserve stored pools; supplied pools replace them
  only when dependency guards permit, and `[]` clears them under those guards.
- Native drivers own mutation transactions, rollback and audit. Preflight reads
  do not lock out independent writers; preserve the exclusive-writer contract.
- Persistence never requests activation. Pull/reload/restart is explicit;
  deletion retains leases. Uncertain writes require reconciliation before retry.
- Contain exceptions at callout boundaries. Only `ContractError` text is public;
  native failures keep the existing generic responses.
- Commands execute synchronously on the main thread, including when packet
  multithreading is enabled. Preserve both threading modes.

See [backend behavior](docs/backend-behavior.md), [pool semantics](docs/pools.md)
and [subnet lifecycle](docs/subnet-lifecycle.md) for the detailed rationale.

## Build and verification map

[Reproducible builds](docs/reproducible-builds.md) is the current build and
acceptance guide; [development](docs/development.md) covers local setup and the
canonical `build/` output layout (`quality`, `upstream`, `hook`, `integration`,
`stage`). Existing installed prefixes may be reused without relocation.
`scripts/quality.py` combines formatting, lint, whitespace and local-link checks;
`scripts/integration.py` builds and requires all six CTest tests without skips.
`scripts/verify_artifact.py` checks exports and matching shared dependencies.

Tests: `tests/test_transport.py` covers transport; `tests/smoke.py` loads real
Kea; `tests/postgresql.py` and `tests/mysql.py` exercise private SQL backends.
Shared mutation/get/delete assertions live in `tests/mutation.py` and
`tests/lifecycle.py`; `tests/dhcp.py` and `tests/packet_namespace.py` provide
real DHCP DORA and lease checks. SQL and packet suites exercise both threading
modes. See [PostgreSQL](docs/postgresql.md) and [MariaDB](docs/mysql.md) setup.

## Python diagnostics for agents

After Python changes, run both checks from the repository root:

```bash
basedpyright
ruff check tests scripts
```

Use BasedPyright (the installed Pyright-derived type checker) for type errors,
including optional values and invalid attributes; Ruff checks lint issues.
Both use [pyproject.toml](pyproject.toml). Keep its execution environments and
Python target; do not weaken diagnostic settings or add broad suppressions to
make checks pass. Report errors and remaining warnings separately; a clean Ruff
run does not establish type correctness. If a checker is unavailable, report
the missing check without installing dependencies unless authorized.

`scripts/quality.py` includes Ruff but does not run BasedPyright; run the latter
explicitly. Static checks do not run tests. Honor an explicit request to defer
tests and report that validation as deferred.

## C++ semantic tools for agents

Use the project-local `clangd` MCP (`isaacphi/mcp-language-server`) first for
C++ definitions, references, hover/type information and diagnostics. Codex uses
`.codex/config.toml` in a trusted checkout.
See [C++ tooling](docs/cpp-tooling.md#project-local-clangd-mcp-for-development-agents)
for launch settings, representative calls and `/mcp` verification.

Confirm tools are exposed in the current session before relying on them.
If unavailable, state that limitation and use the existing Serena C++ server
or bounded source inspection. Avoid a duplicate bridge for routine navigation.
Ordinary file reads/searches retain their usual tools. MCP edits and renames
must stay within the authorized task; read-only checks must not invoke them.

Use `build/integration/compile_commands.json`, with the actual C++14 flags and
matching Kea includes. Preserve `.clangd`, the configured compiler and installed
Kea prefix. Do not regenerate a correct build or suppress diagnostics for MCP.
Transport initialization alone is not semantic verification; check real symbol
results and diagnostics. The documented clangd 22 `ExtractFunction` probe
failure in `src/subnet4.cc` does not invalidate working navigation/diagnostics.
