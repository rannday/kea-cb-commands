# Milestone 9 release readiness

## Assessment and changes

The focused assessment covered the four implementation modules, CMake, the
strict integration and artifact runners, the existing SQL/DHCP fixtures, CI and
the user guides. No reproducible high-severity hook defect was found. The
command interfaces and hook implementation remain unchanged.

| Gap | Severity | Resolution |
| --- | --- | --- |
| SQL tests issued commands sequentially, leaving concurrent control requests unverified | Medium, verification | Shared lifecycle assertions now submit conflicting creates, parallel reads and duplicate deletes over separate connections. Only one competing ID may persist; the rejected write must leave no audit entry. Runtime configuration must remain unchanged. |
| Outage write assertions checked only the result code | Low, verification | Both SQL harnesses now require the exact generic response without native error details or arguments, and verify that diagnostic remains connection-independent during the outage. |
| MariaDB setup described the harness but lacked a deployment configuration | Medium, documentation | Added the native hook order, `mysql` backend example, schema/grant requirements and explicit activation instructions. |
| Installation and operational safety guidance was scattered | Medium, documentation | Added [release operations](operations.md): loader environment, staged validation, controlled module replacement, control-channel security, tag authorization limits, exclusive writers and uncertain-write reconciliation. |

The existing architecture already resolves the native backend pool per command,
rejects ambiguous backends and unsafe associations, guards richer stored objects,
and contains native exceptions behind generic command errors. Native drivers own
mutation transactions and audit. Those conclusions come from source inspection;
the acceptance suite below provides runtime evidence for the exercised paths.

## Local acceptance

The validation host is Debian 12 WSL, x86-64, GCC 12.2.0, PostgreSQL 15.19 and
MariaDB 10.11.19. The retained, matching upstream prefix is
`build-repro-clean/install`; its daemon reports `3.2.1-git` and the hook framework
version is 30201. The pinned Kea toolchain was reused, not rebuilt or relocated.
All new hook/test outputs are under `build/`.

```bash
python3 -B scripts/integration.py \
  --kea-prefix build-repro-clean/install --build-dir build/m9-integration --jobs 2
PATH="$PWD/build/quality/bin:$PATH" python3 -B scripts/quality.py
python3 -B -m unittest discover -s tests -p 'test_*.py' -v
cmake --install build/m9-integration --prefix "$PWD/build/m9-stage"
python3 -B scripts/verify_artifact.py \
  --library build/m9-stage/lib/kea/hooks/libdhcp_db_commands.so \
  --kea-prefix build-repro-clean/install --forbid-path "$PWD"
LD_LIBRARY_PATH="$PWD/build-repro-clean/install/lib" python3 -B tests/smoke.py \
  --server "$PWD/build-repro-clean/install/sbin/kea-dhcp4" \
  --hook "$PWD/build/m9-stage/lib/kea/hooks/libdhcp_db_commands.so" \
  --work-dir "$PWD/build/m9-staged-lifecycle"
git diff --check
```

Local execution on 2026-10-16 passed the fresh Release build with
`-std=c++14 -Wall -Wextra -Wpedantic -Werror`. All six CTest tests passed with
no skips in 385.15 seconds:

| Test | Result | Seconds |
| --- | --- | ---: |
| `control_transport` | Passed | 0.05 |
| `hook_lifecycle` | Passed | 0.32 |
| `postgresql_read` | Passed | 69.05 |
| `postgresql_dhcp` | Passed | 82.23 |
| `mysql_read` | Passed | 112.68 |
| `mysql_dhcp` | Passed | 120.82 |

Both SQL engines ran with packet multithreading disabled and enabled. The full
test log records eight successful concurrent-request scenarios across the SQL
and packet suites. Existing native rollback/audit, tag isolation, pool semantics,
outage/recovery, activation and restart checks passed. Packet tests exercised
real DORA and lease behavior, including lease retention after deletion and
explicit runtime removal. The strict runner confirmed temporary-resource cleanup.

The combined quality runner passed C++ formatting, Python lint, whitespace,
JSON-file parsing and local documentation-link checks. All six transport unit
tests passed separately. The README and MariaDB JSON examples also passed syntax
parsing; placeholder deployment configurations were not connected to a production
database. `git diff --check` passed.

The installed staging artifact passed all four required export checks, matching
shared Kea dependency resolution, and absence of RPATH/RUNPATH and the forbidden
checkout path. The staged lifecycle test passed load/reload/unload/shutdown in
both threading modes and left its fixture directory empty.

JUnit evidence is `build/m9-integration/ctest-results.xml`; complete per-mode
output is `build/m9-integration/Testing/Temporary/LastTest.log` (JUnit output is
truncated by CTest). No system deployment or remote CI run is implied.

## Release boundary

Supported operation requires coordinated exclusive configuration writers. This
milestone does not certify independent-writer races, load/scale behavior or
every possible connection loss at commit. An uncertain mutation requires
reconciliation before retry; native reconnect exhaustion may require an explicit
reload/restart. Requests remain synchronous in both packet threading modes.
Persistence never requests activation and deletion retains leases.

CI configuration was inspected locally; no GitHub Actions execution was observed
in this milestone. Debian WSL validation does not verify Ubuntu's CI-specific
AppArmor setup, Windows binaries, Oracle MySQL or another Kea ABI. Installation
was staged locally; no system installation or deployment was performed.

**Milestone 9: GO for initial release within this documented boundary.** No
demonstrated high-severity defect or unresolved release blocker remains from
this assessment. Review is still required before committing or publishing.
