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
The existing local setup uses `build-repro-clean/install` and `build-m7`.
Recheck their availability and cached paths before using these examples.

For implementation changes with that configured build:

```bash
cmake --build build-m7 --parallel 2
ctest --test-dir build-m7 --parallel 1 --output-on-failure
```

CTest registers transport by default. Real lifecycle, SQL and DHCP tests depend
on the `KEA_DB_COMMANDS_RUNTIME_TESTS`, `KEA_DB_COMMANDS_POSTGRESQL_TESTS`,
`KEA_DB_COMMANDS_MYSQL_TESTS` and `KEA_DB_COMMANDS_DHCP_TESTS` CMake options.
Use the strict runner below to configure all four and refresh Kea discovery.

## Choose validation by subsystem

- Documentation only: check Markdown, relative links and whitespace; no C++ or
  database run is needed. `scripts/quality.py` does not scan root `AGENTS.md` or
  `.agents/skills/`, so check guidance files explicitly when they change.
- Transport or Python tooling: run the relevant existing unit suite:

  ```bash
  python3 -B -m unittest discover -s tests -p 'test_*.py' -v
  python3 -B -m unittest discover -s scripts -p 'test_*.py' -v
  ```

- Lifecycle, exports or CMake: build, run `hook_lifecycle` through CTest and
  inspect the artifact with the existing verifier:

  ```bash
  python3 -B scripts/verify_artifact.py \
    --library build-m7/libdhcp_db_commands.so \
    --kea-prefix build-repro-clean/install --forbid-path "$PWD"
  ```

- Command parsing, replies, backend selection, tags or CRUD: exercise both SQL
  harnesses, including their shared mutation and lifecycle checks.
- Pool, deletion, activation or retained-lease behavior: include both DHCP
  packet suites. Use the strict gate for a refactor spanning these modules.

Run the combined quality gate with the existing private tool environment:

```bash
PATH="$PWD/build-quality-venv/bin:$PATH" python3 -B scripts/quality.py
```

For full SQL and packet acceptance with the existing local installation:

```bash
python3 -B scripts/integration.py --kea-prefix build-repro-clean/install \
  --build-dir build-m7 --jobs 2
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
