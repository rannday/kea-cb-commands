---
name: kea-cb-commands
description: Develop and validate the kea-cb-commands Kea hook, command handlers, native PostgreSQL/MariaDB configuration backend integration, CMake build, and SQL/DHCP integration tests. Use for repository-specific implementation or verification work in kea-cb-commands.
---

# Work on kea-cb-commands

## Locate the change

Read [AGENTS.md](../../../AGENTS.md) for the module map and project invariants.
Follow the call path from registration in `src/diagnostic.cc`, through responses
in `src/commands.cc`, to validation in `src/arguments.cc` and native operations
in `src/subnet4.cc`. Keep new logic with its existing owner and private header.

Before changing behavior, locate the matching contract and assertions:

| Area | Contract/reference | Tests |
| --- | --- | --- |
| Diagnostic and registration | [README](../../../README.md), [architecture](../../../docs/architecture.md) | `tests/smoke.py` |
| List, selection and recovery | [PostgreSQL](../../../docs/postgresql.md), [backend behavior](../../../docs/backend-behavior.md), [MariaDB](../../../docs/mysql.md) | `tests/postgresql.py`, `tests/mysql.py` |
| Set validation, persistence and pools | [commands](../../../docs/commands.md), [pools](../../../docs/pools.md) | `tests/mutation.py`, both SQL harnesses |
| Get/delete and retained leases | [commands](../../../docs/commands.md), [lifecycle](../../../docs/subnet-lifecycle.md) | `tests/lifecycle.py`, `tests/dhcp.py` |
| Build and artifact | [build guide](../../../docs/reproducible-builds.md), `CMakeLists.txt` | `scripts/test_*.py`, `scripts/verify_artifact.py` |

Inspect exact request/reply assertions, rejected-write snapshots and activation
checks before editing. Helpers in `tests/mutation.py`, `tests/lifecycle.py` and
`tests/dhcp.py` run through the SQL harnesses, not as standalone unit tests.

## Select the existing environment

Run commands from the repository root. Follow the build guide for a fresh
environment. For reuse, inspect the chosen `CMakeCache.txt`: headers, libraries,
daemon, SQL hooks and schemas must all belong to the same Kea installation.
Use `build/quality` for pinned tools, `build/upstream/install` for a fresh Kea
installation and `build/integration` for the full gate. For an existing prefix,
follow the [incremental migration](../../../docs/development.md#generated-output-layout)
example; do not relocate installed metadata or cached builds.

For implementation changes with that configured build:

```bash
cmake --build build/integration --parallel 2
ctest --test-dir build/integration --parallel 1 --output-on-failure
```

CTest registers transport by default. Real lifecycle, SQL and DHCP tests depend
on the `KEA_DB_COMMANDS_RUNTIME_TESTS`, `KEA_DB_COMMANDS_POSTGRESQL_TESTS`,
`KEA_DB_COMMANDS_MYSQL_TESTS` and `KEA_DB_COMMANDS_DHCP_TESTS` CMake options.
Use the strict runner below to configure all four and refresh Kea discovery.

## Python static checks

For Python edits, run both the type checker and linter from the repository root:

```bash
basedpyright
ruff check tests scripts
```

BasedPyright supplies Pyright type diagnostics, including optional-value and
attribute errors. Ruff supplies lint diagnostics. Use the repository's
[pyproject.toml](../../../pyproject.toml) configuration and execution environments.
Do not weaken checking or add broad suppressions to clear diagnostics. Report
error and warning counts separately, and report unavailable tools rather than
installing them without authorization. Ruff success alone is insufficient.

The quality gate below includes Ruff but does not invoke BasedPyright; run
BasedPyright explicitly. These commands are static checks, separate from unit
and integration tests. When the user defers tests, perform the static checks and
report tests as deferred instead of running the suites below.

## Choose validation by subsystem

- Documentation only: run the quality gate for Markdown, relative links and
  whitespace, including `AGENTS.md` and `.agents/skills/`; no C++ or database
  run is needed.
- Transport or Python tooling: run the relevant existing unit suite:

  ```bash
  python3 -B -m unittest discover -s tests -p 'test_*.py' -v
  python3 -B -m unittest discover -s scripts -p 'test_*.py' -v
  ```

- Lifecycle, exports or CMake: build, run `hook_lifecycle` through CTest and
  inspect the artifact with the existing verifier:

  ```bash
  python3 -B scripts/verify_artifact.py \
    --library build/integration/libdhcp_db_commands.so \
    --kea-prefix build/upstream/install --forbid-path "$PWD"
  ```

- Command parsing, replies, backend selection, tags or CRUD: exercise both SQL
  harnesses, including their shared mutation and lifecycle checks.
- Pool, deletion, activation or retained-lease behavior: include both DHCP
  packet suites. Use the strict gate for a refactor spanning these modules.

Run the combined quality gate with the existing private tool environment:

```bash
PATH="$PWD/build/quality/bin:$PATH" python3 -B scripts/quality.py
```

For full SQL and packet acceptance with the selected installation:

```bash
python3 -B scripts/integration.py --kea-prefix build/upstream/install \
  --build-dir build/integration --jobs 2
```

This configures and builds the hook, runs CTest serially, validates JUnit results
and checks fixture cleanup. It requires exactly `control_transport`,
`hook_lifecycle`, `postgresql_read`, `postgresql_dhcp`, `mysql_read` and
`mysql_dhcp` to pass. The SQL harnesses start disposable real PostgreSQL/MariaDB
servers; DHCP tests use `tests/packet_namespace.py` for private Linux namespaces.
They run with threading disabled and enabled. Prerequisites and alternative
documented build paths are in the build guide.

## Interpret the evidence

Formatting, lint, Python units, CMake probes and ELF inspection establish their
specific source/build properties. `hook_lifecycle` proves real Kea loading and
commands without a SQL server; the diagnostic does not test connectivity.
`postgresql_read` and `mysql_read` prove native SQL command behavior, despite
their historical names also covering mutations. `postgresql_dhcp` and
`mysql_dhcp` add actual DORA packets and recorded leases. A skipped optional
CTest is unavailable coverage; the strict runner rejects skips.
