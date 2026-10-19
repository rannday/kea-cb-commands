# Milestone 32 checks — scoped-option association reconstruction

Status: **PASS** as a bounded qualification milestone with zero newly enabled mutations. Production readiness: **NO-GO**.

## Baseline and scope

- Branch `main`, baseline `dc28df1a711556a3b966e7106e5809892e97da79`; initially clean, no staged or untracked changes.
- Pinned ISC Kea 3.2.1 source `1737462bc79276e3269304ea8cd3d1c03400e30d`; extracted source/install reused at `build-repro-clean/source` and `build-repro-clean/install`, provenance in `build-repro-clean/toolchain.txt`.
- No production C++ changes, aliases, new command families, commits or pushes. Zero existing-record mutations enabled.
- See [safety investigation](../../docs/scoped-option-mutation-safety.md) for native source references, separate update/delete findings and preconditions.

## Findings

M31 B3 and D1 were investigated, including F1's association-reconstruction hypothesis for scoped records. E1's pool parent-identity limitation remains unchanged. The historical 12-blocker classification remains A0/B4/C5/D1/E1/F1; the missing read-only association predicate refines B3 rather than changing that inventory.

Parent associations are observed natively. Scoped option-server links are not: ALL and ONE reads filter parents and load options without joining their association table. Option SQL IDs are observable but public scoped mutation methods do not accept them. `getAllOptions4` covers global options only. Enumerating servers cannot distinguish scoped link sets.

Updates match parent/code/space/serialized classes without an option-server predicate and can fall back to insertion. Deletes discard their selector and use a LIKE class predicate; absent classes broaden it. Neither operation has a public expected-revision/compare-and-swap guard. Transactions do not span preflight reads. Designated-writer admission is not fencing.

All four subnet/network existing SET/DEL operations remain refused. Pool existing mutations and server deletion remain refused. Missing scoped deletion retains result 3. Production native writes, recovery holds and explicit activation boundaries remain unchanged.

## Disposable association probes

The expanded `tests/scoped_options4.py` checks both subnet and network options under named and common parents, each with seven exact SQL link states: none; common; requested server; hidden server; two named servers; common plus requested; common plus both named. Native responses are compared across visible selectors. Each repeated SET/DEL refusal compares complete persisted configuration and audit snapshots; active `config-get` is unchanged. Mixed common/named parent ownership is separately observed and refused.

Fresh native scoped creation with ANY has no option-server links; fixtures assert and restore that original state. Diagnostic association writes are confined to disposable tests and do not exercise prohibited native existing-option writes. Extra option links alone do not prove extra runtime consumers.

Initial integration attempt failed a new fixture assertion that incorrectly expected parent tags to be copied to a fresh option. Native source confirmed ANY has no tags to attach. The assertion/restoration was corrected. Both initial MariaDB suites passed; both PostgreSQL suites had loaded the earlier assertion. A complete corrected six-suite rerun subsequently passed without failures or skips; the initial failure is retained in `integration-initial.log`.

## Verification

Canonical matrix command:

```bash
python3 -B scripts/integration.py --kea-prefix build-repro-clean/install --build-dir build/integration --jobs 2 --skip-outages
```

The corrected run uses PostgreSQL 18.6 and MariaDB 12.3.3. The non-interruption mode is deliberate: no destructive connection/outage injection. It does not qualify SQL outage/recovery behavior or independent-process fencing.

| Check | Result |
| --- | --- |
| Strict Release C++14/Werror build | PASS |
| Six-suite integration gate | PASS: 6/6, zero failures, zero skips; 1,338.74 seconds |
| PostgreSQL MT off / on | PASS / PASS; read and DHCP suites |
| MariaDB MT off / on | PASS / PASS; read and DHCP suites |
| Unit tests (`tests`) | 11 PASS |
| Tooling tests (`scripts`) | 28 PASS |
| Ruff `ruff check tests scripts` | PASS |
| BasedPyright | 0 errors, 3,775 warnings, 0 information; 33 files |
| Formatting / local links | PASS, 108 files |
| Clang analyzer | PASS, nine translation units |
| cppcheck | PASS, nine translation units |
| clang-tidy | Unavailable: executable not found; runner exited 1 |
| Artifact checks | PASS |
| `git diff --check` | PASS |

Final suite durations: transport 0.06 s; lifecycle 1.07 s; PostgreSQL read 222.55 s / DHCP 287.89 s; MariaDB read 416.72 s / DHCP 410.45 s. Each SQL suite exercises MT off and on. The strict runner confirmed all temporary resources removed. Detailed output is in `build/integration/Testing/Temporary/LastTest.log`, with the six-result JUnit report at `build/integration/ctest-results.xml`.

An optional command to summarize the completed JUnit XML did not execute because automatic permission review timed out. No retry or bypass was used; the completed runner result and test log establish the results above.

Other reproducible checks, run from the repository root:

```bash
python3 -B -m unittest discover -s tests -p 'test_*.py'
python3 -B -m unittest discover -s scripts -p 'test_*.py'
ruff check tests scripts
basedpyright --outputjson
python3 -B scripts/analyze.py analyzer --build-dir build/integration
python3 -B scripts/analyze.py cppcheck --build-dir build/integration
python3 -B scripts/analyze.py tidy --build-dir build/integration
python3 -B scripts/verify_artifact.py --library build/integration/libdhcp_db_commands.so --kea-prefix build-repro-clean/install
PATH="$PWD/build/quality/bin:$PATH" python3 -B scripts/quality.py
git diff --check
```

Raw local logs: `integration-initial.log`, `integration.log`, `quality.log`, `analyzer.log`, `cppcheck.log`, `tidy.log`, `artifact.log`, and BasedPyright JSON in this directory. Build artifacts/logs are unversioned evidence.

### BasedPyright comparison

BasedPyright version 1.40.2. M31: 0 errors / 3,749 warnings. M32: **0 errors / 3,775 warnings (+26)**. All diagnostics are in project-owned files: tests 3,297 (+26), scripts 478 (unchanged); none originate in generated/external files. No diagnostic settings or broad suppressions changed.

| New warning category | Delta |
| --- | ---: |
| reportAny | +1 |
| reportImplicitStringConcatenation | +3 |
| reportMissingParameterType | +3 |
| reportUnknownArgumentType | +6 |
| reportUnknownMemberType | +6 |
| reportUnknownParameterType | +3 |
| reportUnknownVariableType | +4 |

These additions concern the fixture's untyped callback/JSON boundary and SQL string construction; no new type errors were reported. The existing warning baseline is retained, not represented as zero or hidden by configuration changes.

## Files changed

- `tests/scoped_options4.py`: association probes and SQL/audit/active-state preservation assertions.
- `docs/scoped-option-mutation-safety.md`: native evidence, identity/dependency requirements, refusals and race analysis.
- `README.md`, `docs/commands.md`, `docs/compatibility-matrix.md`, `docs/commercial-parity-gap-analysis.md`: unchanged contracts and coverage, linked M32 findings.
- `docs/dependency-safety-backlog.md`, `docs/dhcp4-qualification.md`, `docs/dhcp4-remediation-plan.md`, `docs/development-roadmap.md`: blocker refinements and M33 recommendation.
- `build/milestone32/checks.md`: this local evidence report, under the existing ignored build layout.

No production source, dependency, diagnostic configuration, remote ref or unrelated file changed.

## Activation, compatibility and next milestone

No new mutation packet case applies because no existing mutation was admitted. Both backends and threading modes passed real DORA and memfile lease checks, lifetime/T1/T2/boot-file payloads, router/DNS/domain/custom options, global < network < subnet < pool precedence, matching/nonmatching class-restricted pools, class options 247/248, explicit activation and actual process restart. Persisted changes remained inactive until explicit activation; subnet deletion retained leases. Refused scoped mutations preserved complete SQL/audit snapshots and active `config-get` under all tested association states. Existing read-only admission, malformed input, dependency, parent/membership and pool-collision regressions passed.

SQL persistence alone is not activation; M22 full convergence, independent-writer fencing, sanitizers and uncertain-commit recovery are not qualified here.

Inventory remains 41 registered commands. Functional commercial coverage remains **3 implemented / 24 partial / 47 missing** of 74; exact compatibility **0/74**. No partial operation was promoted on the strength of registration or refusal.

Remaining blockers include incomplete scoped association/unique-row evidence, exact class deletion identity, preflight races and external writers, durable recovery and activation evidence, pool identity and other unchanged CRUD restrictions. Production remains NO-GO.

Recommended M33: independently qualify F1 for global records with native association readback and specify trustworthy scoped association/identity APIs, including concurrency and recovery requirements. Defer DHCPv6. Stop for review before M33.
