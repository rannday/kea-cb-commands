# Milestone 25 verification

**Status: PARTIAL.** Final strict integration run passed all six tests with zero
skips and verified fixture cleanup. Existing server deletion, existing-global
update/delete and compound/full global support are excluded. No commercial
interface compatibility is claimed. Production readiness remains NO-GO.
Date: 2026-10-18.

## Baseline and scope

Initial worktree clean at M24 commit
`2fd4605655970a945cf5d9fec0821715d6849a6f`.
Pinned public Kea 3.2.1 commit:
`1737462bc79276e3269304ea8cd3d1c03400e30d`.
Matching existing source/install: `build-repro-clean/source` and
`build-repro-clean/install` (`3.2.1-git`). Linux x86_64 Debian WSL2,
GNU C++ 12.2.0, Release, C++14, extensions disabled, warnings as errors.
PostgreSQL 18.6 and MariaDB 12.3.3 LTS; MariaDB uses the native mysql backend.
Version metadata is in `build/integration/database-versions.json` and
`build/integration/release-build.json`.

Reviewed project instructions/skills, M23/M24 checks, public command descriptors,
pinned native sources, production code, recovery contracts and existing fixtures.
No proprietary code/binaries, direct production SQL, automatic activation/retries,
new environment dependencies, destructive connection interruption, commits,
pushes, tags or releases.

## Implementation and exact registered names

New registrations:

- `cb-server4-list`, `cb-server4-get`, `cb-server4-set`, `cb-server4-del`.
- `cb-global-parameter4-list`, `cb-global-parameter4-get`,
  `cb-global-parameter4-set`, `cb-global-parameter4-del`.

All five pre-existing commands remain registered with their existing contracts.
No `remote-*` alias or command was registered. M24 shared command, backend,
selector, mutation-admission and safe exception helpers are reused. `records4.cc`
contains the family-specific logic; the hook remains one standalone MODULE.

Public baseline operations: `remote-server4-get-all/get/set/del` and
`remote-global-parameter4-get-all/get/set/del`. Public requests use object lists,
server-tags lists and parameter maps/batches; the new cb interfaces deliberately
use single-object schemas. Public error behavior, description omission (U6),
compound encoding (U2) and response metadata are insufficient for an exact
compatibility claim. See `docs/commands.md` and `docs/compatibility-matrix.md`.

Native APIs used through the current DHCPv4 pool:
`getAllServers4`, `getServer4`, `createUpdateServer4`,
`getAllGlobalParameters4`, `getGlobalParameter4`,
`createUpdateGlobalParameter4` (creation only).
There is no call to `deleteServer4` or `deleteGlobalParameter4`.

### Server deletion exclusion and associations

Both pinned SQL drivers' `deleteServer4` call `purgeUnassignedConfig`, which
purges orphan globals/options/definitions beyond the requested server record.
See PostgreSQL cb4.cc lines 2676/2688 and MySQL cb4.cc line 2852, plus native
backend tests for associated global/option/definition deletion. Native tagged
collection reads cannot prove the complete orphan sets empty. Existing-record
deletion therefore fails closed before mutation; missing records return result 3.
Runtime destructive cascade testing was not executed. Tests instead compare all
SQL tables/audit before and after refusal and inspect surviving associations.
There is no claim that server deletion is implemented.

### Global representation and safety

Fifteen supported names retain native JSON boolean, integer, real and string
types. All scalar types are round-tripped. Names/types/ranges/string bounds and
canonical server tags are validated; unknown names, dotted names, structured
maps/lists and null are rejected unchanged. Native StampedValue map construction
is not proof of SQL serialization: scalar getValue rejects maps; list/null are
not valid native values. Compound expansion and special list encodings need
separate per-name contracts. Cross-parameter lifetime/timer consistency and
inheritance are not fully validated; activation can still reject a persisted
combination. Full scalar/compound support remains incomplete.

List preserves the native selected view and deterministic name ordering,
rejecting exposed duplicate names. Returned server-tags describe that selected
observation, not a complete association inventory. Named reads may fall back to
common values. Pinned PostgreSQL query macros (GET lines 29–43, UPDATE 1017–1028,
DELETE 1184–1192) filter reads but update/delete whole rows. Native cb implementation
getGlobalParameters also collapses rows/tags; the MySQL driver has equivalent
whole-row semantics. Native readback cannot prove an existing value exclusive.

Consequently all existing-global updates/deletes fail closed. Creation is allowed
only when the selected native view is empty, excluding both an exact row and
common fallback. Missing delete is read-only and returns result 3. Diagnostic SQL
in disposable fixtures constructs shared named and mixed common/named association
rows; reads show the filtered view and every mutation refusal preserves SQL/audit.
No direct SQL is present in the hook. Preflight is not cross-process fencing;
the exclusive designated-writer assumption remains.

## Exact commands executed

Commands from repository root; no host installation changed:

```sh
cmake --build build/integration --parallel 2
python3 -B scripts/integration.py --kea-prefix build-repro-clean/install --build-dir build/integration --jobs 2 --skip-outages
python3 -B -m unittest discover -s tests -p 'test_*.py' -v
python3 -B -m unittest discover -s scripts -p 'test_*.py' -v
PATH="$PWD/build/quality/bin:$PATH" python3 -B scripts/quality.py
python3 -B scripts/analyze.py all
python3 -B scripts/analyze.py analyzer
python3 -B scripts/analyze.py cppcheck
python3 -B scripts/verify_artifact.py --library build/integration/libdhcp_db_commands.so --kea-prefix build-repro-clean/install
ctest --test-dir build/integration -N
git diff --check
git diff --no-index --check /dev/null src/records4.cc
git diff --no-index --check /dev/null tests/records4.py
git diff --no-index --check /dev/null build/milestone25/checks.md
```

C++ formatting used `build/quality/bin/clang-format -i src/records4.cc src/commands.h src/diagnostic.cc`.
Final tracked and new-file whitespace checks are clean. The no-index comparisons
return 1 because the files differ from /dev/null, with no whitespace diagnostics.
The strict runner was executed four times: initial audit-no-op failure, a passing
superseded binary, final guard verification with fixture failures, and the corrected
final fixture run.
The integration runner configures Release/Werror, enables SQL/runtime/DHCP test
families and executes serial CTest with JUnit output. `--skip-outages` explicitly
excludes deliberate SQL interruption/retry exhaustion. Multiprocess fault/fencing
qualification is not rerun; no destructive scenario was used.

## Executed checks

- Release C++14 strict build and native API link probe: PASS.
- Python tests: PASS, 11 tests (including five M22 model tests).
- Script tests: PASS, 28 tests.
- Hook lifecycle and transport: PASS in final strict run.
- Formatting, Ruff lint, whitespace and local links: PASS, 93 files before this
  evidence file; ignored evidence checked separately.
- Clang static analyzer: PASS, all five production translation units.
- cppcheck: PASS, all five production translation units.
- clang-tidy: UNAVAILABLE (`scripts/analyze.py all` reached missing executable
  and failed; analyzer/cppcheck were then run separately). No dependency installed.
- Artifact exports/shared Kea resolution/path checks: PASS.

## SQL and packet matrix

Final strict run: PASS, six tests, zero failures and zero skips, 727.68 seconds.
Each SQL/packet suite executes both threading modes. JUnit evidence:
`build/integration/ctest-results.xml`.

| Backend | MT off | MT on |
| --- | --- | --- |
| PostgreSQL 18.6 | PASS (read + DHCP) | PASS (read + DHCP) |
| MariaDB 12.3.3 LTS | PASS (read + DHCP) | PASS (read + DHCP) |

| CTest | Result | Seconds |
| --- | --- | --- |
| control_transport | PASS | 0.09 |
| hook_lifecycle | PASS | 0.91 |
| postgresql_read | PASS | 115.73 |
| postgresql_dhcp | PASS | 129.38 |
| mysql_read | PASS | 232.81 |
| mysql_dhcp | PASS | 248.77 |

The strict runner reported: `PASS: all six integration tests ran successfully;
temporary resources removed`. Its cleanup gate verified that the five runtime/SQL/
packet work directories were absent or empty. Fixtures perform graceful process
shutdown and packet-namespace teardown; the gate itself checks directories, not a
separate host-wide process/namespace inventory. This is final-source and final-fixture
evidence; earlier failed/superseded runs are recorded below.

Shared fixture assertions cover create/update/list/get, missing records, malformed
input, deterministic output, native scalar types, common/named selectors,
fallback and existing-value mutation refusal, shared/mixed associations,
preservation of unrelated rows/associations,
read-only mutation denial before parsing, clean process restart and explicit
activation independently observed via config-get. Packet fixtures additionally
verify BOOTP boot-file-name before persistence, unchanged before activation,
changed after explicit reload, retained after refused deletion, and persisted
after clean restart. Fixture-only SQL removes temporary scalar test data before
packet scenarios; that cleanup is not claimed as hook deletion functionality.
Existing subnet/pool/lease and DORA assertions remain enabled.

## Failures and corrections

1. Initial compilation tried std::sort on a bidirectional native server
   collection. Replaced with a deterministic std::map view; strict build passes.
2. First full strict run: transport/lifecycle passed, all four SQL suites failed
   at the first missing-global delete assertion. Native delete created an audit
   revision despite affecting no parameter. Added native read preflight to avoid
   no-op mutation. A second six-test run passed with cleanup, but was superseded
   by the final association guard and is not final-source acceptance evidence.
3. Source review showed selected global tags do not expose complete associations.
   Replaced apparent-exclusivity updates/deletes with unconditional existing-value
   refusal. Added diagnostic shared/mixed-row regressions and adjusted packet
   checks to verify refused deletion preserves the active field. The third run
   passed transport/lifecycle but all four SQL suites failed in diagnostic fixture
   setup/cleanup: PostgreSQL cleanup lacked a native audit revision; MariaDB
   association inserts omitted mandatory modification_ts (SQL 1364). Added explicit
   association timestamps for both schemas and backend-specific native audit
   revision setup inside the cleanup transaction. Fourth strict run passed all six
   tests with zero skips and verified cleanup.
4. Combined analysis command failed because clang-tidy is not installed. Clang
   analyzer and cppcheck were run separately and passed; tidy is not marked PASS.

## Files changed

- `CMakeLists.txt`, `src/commands.h`, `src/diagnostic.cc`.
- New `src/records4.cc`, new `tests/records4.py`.
- `tests/smoke.py`, `tests/postgresql.py`, `tests/mysql.py`, `tests/dhcp.py`.
- `README.md`, `docs/commands.md`, `docs/compatibility-matrix.md`,
  `docs/commercial-parity-gap-analysis.md`, `docs/command-architecture.md`,
  `docs/development-roadmap.md`.
- This explicitly requested generated evidence file.

## Limitations, counts and next scope

Functional M23 matrix: 3 implemented, 9 partial, 62 missing of 74; v4 3/9/24,
v6 0/0/38. Three server operations are functional; server/global delete are missing;
three bounded-global operations and six old subnet analogues are partial.
Exact commercial interface: 0 implemented, 0 partial, 74 missing.

M22 remains PARTIAL. Its existing durable hold and fail-closed incomplete-evidence
behavior are unchanged; the collector has not been expanded to establish full
server/global convergence. Model tests are not full deployment recovery proof.
No manual acknowledgement may turn incomplete evidence into permission to resume.
External fencing, complete reconciliation and the upstream native SQL transaction
cleanup exception remain production blockers. Local admission is not ownership.
No production readiness or distributed-fencing claim is made.

Recommended M26: native DHCPv4 option definitions and global options using these
helpers, public per-command contracts, code/space/type validation, dependency and
force-delete policy, PostgreSQL/MariaDB × MT, restart, admission, activation and
packet option checks. Server deletion and full global representation remain
explicit independent follow-ups, not silently completed milestones.
