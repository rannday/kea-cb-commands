# Milestone 24 verification

**Status: PASS.** Implementation and required available checks complete.
The final strict regression gate passed all six tests with zero skips and verified
cleanup. Production readiness remains NO-GO.
Date: 2026-10-17.

## Baseline and scope

Initial worktree clean on main at
`de4d9742e9a5fed65f2d263e2b47f819fff9d2fc`, synchronized with origin/main.
No unrelated changes discarded; no staging, commits, pushes, tags or releases.

Pinned public ISC Kea 3.2.1 source commit:
`1737462bc79276e3269304ea8cd3d1c03400e30d`.
Existing source: `build-repro-clean/source`; matching installation:
`build-repro-clean/install`, reporting `3.2.1-git`.
M23 records archive SHA-256
`2aebb52859cc402ae20004f54574714045fc6366825df1b09b7845130f9f798b`.
No newer upstream API or proprietary hook code/binary used.

Release metadata: Linux x86_64, GNU 12.2.0, C++14, extensions disabled.
Integration database executables report PostgreSQL 18.6 and MariaDB 12.3.3 LTS;
MariaDB uses Kea's native mysql backend. See
`build/integration/database-versions.json` and `release-build.json`.

Reviewed applicable instructions/skills, all production C++ and headers,
contracts, architecture/parity/roadmap/recovery documentation, M22/M23 checks and
existing unit/SQL fixtures. M22 remains PARTIAL: real evidence is incomplete and
cannot authorize hold release or replacement promotion. M23 remains PARTIAL
for unresolved commercial contracts U1–U8. Neither result was promoted by M24.

## Files changed

- `CMakeLists.txt`
- `src/command_support.h` (new)
- `src/backend_support.h` (new)
- `src/commands.cc`
- `src/arguments.cc`, `src/arguments.h`
- `src/subnet4.cc`
- `tests/smoke.py`
- `tests/callout_boundary.cc` (new)
- `tests/native_dhcp6_probe.cc` (new)
- `README.md`
- `docs/architecture.md`
- `docs/command-architecture.md`
- `docs/development-roadmap.md`
- This explicitly requested generated evidence file.

## Architecture before and after

Before: five callouts repeated request extraction, response publication and
get/set/delete nested exception envelopes; subnet operations repeated native
manager/backend selection and tag construction.

After: the same four production translation units build into the same MODULE.
Two small private header-only helpers share only existing plumbing:

- `CommandRequest`, `commandRequest`, `acceptsEmptyArguments`.
- `requireFields` and `optionalField`, retaining command-specific schemas,
  messages and validation ordering. Omission remains distinct from explicit
  null, empty maps and empty lists.
- `ContractError`, `respond` and `commandBoundary`: only explicitly safe
  contract text is public; native failures use existing generic envelopes;
  response publication uses Kea's exact ConstElementPtr type.
- `requireMutationAdmission`, called explicitly before parsing/backend access
  at each mutating command boundary.
- `backendPool<Manager>`, resolving the current native pool per invocation
  without casting, caching, private manager or family erasure.
- `singleBackendSelector`, preserving separate list versus SQL mutation/lookup
  policy and messages.
- `validatedServerTag` and `serverSelector`, preserving canonical tag checks
  and ALL/ONE semantics.

DHCPv4 association checks, ANY conflict checks, native CRUD/transactions,
richer-object refusals and pool replacement/preservation stay in subnet4.cc.
Diagnostic/list retain their distinct outer exception/publication handling.
Lifecycle exports, daemon/family restrictions, logging, five registrations and
MT declaration in diagnostic.cc are unchanged. No remote commands, SQL,
activation, retries, distributed ownership or new production feature families.

## Exact commands executed

Commands run from the repository root. Environment assignments select this
existing installation or project quality binaries; no host configuration changed.

### Before-refactor baseline and final regression gate

The following commands were run before production edits and again after the
refactor (results below distinguish baseline from final):

```sh
python3 -B -m unittest discover -s tests -p 'test_*.py' -v
python3 -B -m unittest discover -s scripts -p 'test_*.py' -v
python3 -B scripts/integration.py --kea-prefix build-repro-clean/install --build-dir build/integration --jobs 2 --skip-outages
```

Baseline: 11 test units and 28 script units passed; all six integration tests
passed with zero skips (595.78 s). This was the original module, not proof of
the refactor. Final unit run: the same 39 tests passed, zero skips.

The strict runner configures/builds Release C++14 with warnings as errors,
validates database series, enables both SQL engines and DHCP suites, runs the
six named CTest cases, rejects skipped/missing/unexpected cases and checks
fixture cleanup. Both threading modes are exercised inside each SQL/packet
suite. Deliberate SQL stop/recovery paths are explicitly excluded.

### DHCPv6 compile/link/startup probe

```sh
PKG_CONFIG_PATH="$PWD/build-repro-clean/install/lib/pkgconfig" cmake -S . -B build/milestone24/probe -DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_STANDARD=14 -DBUILD_TESTING=OFF -DKEA_DB_COMMANDS_WARNINGS_AS_ERRORS=ON -DKEA_DB_COMMANDS_DHCP6_PROBE=ON
cmake --build build/milestone24/probe --parallel 2
cmake --build build/milestone24/probe --target native_dhcp6_probe --parallel 2 --verbose
LD_LIBRARY_PATH="$PWD/build-repro-clean/install/lib" build/milestone24/probe/native_dhcp6_probe
nm -C -u build/milestone24/probe/native_dhcp6_probe
readelf -d build/milestone24/probe/native_dhcp6_probe
```

PASS: strict C++14 compilation, real executable linking and startup with eager
symbol resolution (-z defs, -z now/BIND_NOW). Shared dependencies include the
matching libkea-dhcpsrv.so.150, libkea-database.so.88 and libkea-cc.so.98.
No private static Kea copy or runtime path was introduced.

Source: `tests/native_dhcp6_probe.cc`. Compile-time checks require
KEA_HOOKS_VERSION 30201 and C++14. It instantiates the actual shared typed helper
with ConfigBackendDHCPv6Mgr, obtains the native pool, constructs PostgreSQL/mysql
backend selectors and ALL/ONE/ANY/UNASSIGNED/MULTIPLE server selectors.

Qualified pool calls in a retained, never-invoked function force ten native
shared symbols, confirmed by nm:
getAllServers6, getServer6, getAllGlobalParameters6, getGlobalParameter6,
createUpdateServer6, createUpdateGlobalParameter6, deleteServer6,
deleteAllServers6, deleteGlobalParameter6, deleteAllGlobalParameters6.
Signatures use native BackendSelector, ServerSelector, ServerTag, ServerPtr,
StampedValuePtr/collections and uint64_t delete counts from the pinned headers.

No configured database, SQL operation, production command registration,
kea-dhcp6 loading, IPv6 allocation or PD verification. API/link availability
does not establish runtime backend behavior or commercial command compatibility.

### Focused lifecycle and exception containment

```sh
LD_LIBRARY_PATH="$PWD/build-repro-clean/install/lib" python3 -B tests/smoke.py --server "$PWD/build-repro-clean/install/sbin/kea-dhcp4" --hook "$PWD/build/milestone24/probe/libdhcp_db_commands.so" --work-dir "$PWD/build/milestone24/lifecycle"
PKG_CONFIG_PATH="$PWD/build-repro-clean/install/lib/pkgconfig" cmake -S . -B build/milestone24/boundary -DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_STANDARD=14 -DBUILD_TESTING=ON -DKEA_DB_COMMANDS_CALLOUT_TESTS=ON -DKEA_DB_COMMANDS_WARNINGS_AS_ERRORS=ON
cmake --build build/milestone24/boundary --target callout_boundary --parallel 2
ctest --test-dir build/milestone24/boundary -R '^callout_boundary$' --output-on-failure
```

PASS: expanded real-daemon smoke/lifecycle suite in MT off/on. Sixteen new exact
validation envelopes plus optional tags, omitted/empty pools, scalar arguments,
missing backend, admission precedence and absence of remote registrations.
Existing load/unload/reload/admission cases retained.

PASS: isolated callout_boundary CTest, 1/1, zero skips (0.01 s).
Links actual production commands.cc against deterministic failing operation
fixtures and native CalloutHandle/CalloutManager. Verifies list/get/set/delete
native exceptions remain generic, explicit contract messages remain public,
all five callout exception paths contain malformed handle argument types,
ConstElementPtr response type/envelope, denied writes never reach operation
fixtures, and exactly one invocation per failed operation (no retry).
This is boundary evidence, not a native SQL-driver outage test.

### Quality, static analysis and artifact checks

```sh
build/quality/bin/clang-format -i src/command_support.h src/backend_support.h src/commands.cc src/arguments.cc src/arguments.h src/subnet4.cc tests/native_dhcp6_probe.cc
build/quality/bin/clang-format -i tests/callout_boundary.cc
PATH="$PWD/build/quality/bin:$PATH" python3 -B scripts/quality.py
PATH="$PWD/build/quality/bin:$PATH" python3 -B scripts/analyze.py all
python3 -B scripts/analyze.py analyzer
python3 -B scripts/analyze.py cppcheck
python3 -B scripts/verify_artifact.py --library build/integration/libdhcp_db_commands.so --kea-prefix build-repro-clean/install
git diff --check
```

PASS: formatting, ruff, whitespace and local documentation links (91 files).
PASS: Clang static analyzer and cppcheck on all four refactored production
translation units. The aggregate analyze.py all command stopped because
clang-tidy is unavailable; clang-tidy was NOT run. No dependency installed.
PASS: artifact exports, matching shared Kea dependencies and absence of RPATH.
PASS: git diff --check.

## Final SQL, threading and DHCP results

PASS: final strict six-test gate, zero failures and zero skips, 545.58 s.
The runner confirmed all six expected tests ran and temporary resources were
removed. CTest output is preserved under build/integration/Testing/Temporary.

| Backend | MT off | MT on |
| --- | --- | --- |
| PostgreSQL 18.6 | Command integration and DHCP passed | Command integration and DHCP passed |
| MariaDB 12.3.3 LTS | Command integration and DHCP passed | Command integration and DHCP passed |

Completed final cases: control_transport 0.07 s; hook_lifecycle 0.58 s;
postgresql_read 57.83 s; postgresql_dhcp 70.81 s; mysql_read 221.02 s;
mysql_dhcp 195.25 s. These results are from the final refactored module.

Coverage retained by the existing suites includes native persistence/readback,
create/update/get/delete and not-found results, pool omission/replacement/clear,
tag associations/conflicts, shared-network/rich-object rejection, ambiguous
backend rejection, admission, explicit activation, process restart persistence
and actual isolated DHCP DORA/lease behavior. No claim of exact persisted versus
active whole-configuration reconciliation is made.

## Corrections, exclusions and remaining limitations

- Corrected ServerTag's namespace to isc::data while extracting the helper;
  final compile/link/integration builds use the corrected type.
- One boundary build was invoked before asynchronous CMake configuration had
  finished and reported "could not load cache"; reran after configuration
  completed, then compilation and CTest passed.
- No deliberate SQL connection interruption, historical SIGABRT reproduction,
  destructive fault injection or production-network packet tests.
- No new sanitizer-instrumented production run; sanitizer fixture unit tests
  do not imply a fresh ASan/UBSan integration run.
- M21 designated-writer and M22 live reconciliation suites were not rerun.
  Their code, durable holds and incomplete-evidence policy were not changed.
- clang-tidy unavailable; other available static analysis passed.
- M22 observability/recovery/privilege gaps and the upstream transaction-cleanup
  exception issue remain. Same-host process evidence is not distributed fencing.
- No DHCPv6 runtime or commercial remote command qualification.

## M25 handoff

Implement four DHCPv4 server commands, then four global-parameter commands using
the shared helpers and existing native manager/pool. Freeze each documented
request/reply contract first. Resolve U6 reserved-all/description/default and
association detach/cascade semantics; resolve U2 scalar/compound global encoding
and supported-versus-JSON-only settings. Keep commercial envelopes separate from
the existing cb-* contracts. Test per-command errors, batch partial results,
selectors/associations, restart persistence, both SQL engines/MT modes and
packet-visible global behavior after explicit activation. Register only qualified
names. Extend evidence without weakening M22 holds. No further shared-framework
redesign is required before this family work.

Stop after M24 verification and review; M25 has not begun.
