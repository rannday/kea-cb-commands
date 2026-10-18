# Milestone 26 verification

**Status: PARTIAL.** Native selected-view reads and fresh creation are implemented
for DHCPv4 option definitions and global options. Existing updates/deletes are
excluded because complete association and dependency safety cannot be established.
Integration qualification is recorded below. No commercial interface compatibility
or production readiness is claimed; production remains NO-GO.
Date: 2026-10-18.

## Baseline and scope

Initial worktree clean on main at M25 commit
`4e717bfd86d54cc3b049d5626f74c85d3c3edfc8`.
Pinned public Kea 3.2.1 commit:
`1737462bc79276e3269304ea8cd3d1c03400e30d`.
Existing matching source/install: `build-repro-clean/source` and
`build-repro-clean/install` (3.2.1-git). Source lock:
`scripts/kea-source.json`, archive SHA-256
`2aebb52859cc402ae20004f54574714045fc6366825df1b09b7845130f9f798b`.
GNU C++ 12.2.0, Release, C++14, extensions disabled, warnings as errors;
Linux x86_64 Debian WSL2. PostgreSQL 18.6 and MariaDB 12.3.3 LTS (native mysql
backend). Metadata: `build/integration/database-versions.json` and
`build/integration/release-build.json`.

Reviewed repository instructions/skills, M24/M25 evidence, M23 inventory,
production code, pinned native parsers/drivers/interfaces, recovery contracts
and existing SQL/packet fixtures. No proprietary implementation, direct SQL in
the hook, dependency installation, automatic activation/retry, destructive SQL
connection interruption, production-network DHCP, commits, pushes or releases.

## Commands and contract decisions

Eight new project-specific registrations:

- `cb-option-def4-list`, `cb-option-def4-get`, `cb-option-def4-set`,
  `cb-option-def4-del`.
- `cb-option4-global-list`, `cb-option4-global-get`, `cb-option4-global-set`,
  `cb-option4-global-del`.

All thirteen earlier contracts remain unchanged. One standalone MODULE now has
twenty-one registrations; no remote-* command is registered.
Public commercial targets: remote-option-def4-get-all/get/set/del and
remote-option4-global-get-all/get/set/del. The pinned ARM and eight public JSON
descriptors establish this inventory; they do not establish every error/empty
result or resolve U5 force/delete and U7 class identity questions. Commercial
batches, backend overrides, server-tags arrays, envelopes and force are not
reproduced. The cb contracts require one explicit tag, one object, code/space
identity and deterministic project responses. See `docs/commands.md` and the
per-command public references in `docs/compatibility-matrix.md`.

## Implementation and native APIs

New `src/options4.cc` reuses command_support.h/backend_support.h, current native
ConfigBackendDHCPv4Mgr pool access, single-SQL-backend checks, selector helpers,
explicit admission and safe exceptions. No backend/manager is cached.
Both write operations check admission before parsing or backend access.

Pool methods actually used: getServer4, getAllOptionDefs4, getAllOptions4,
createUpdateOptionDef4 and createUpdateOption4 (fresh selected identities only).
Read-all plus exact identity filtering retains class-qualified views.
Native getOptionDef4/getOption4/deleteOptionDef4/deleteOption4 exist but are not
called. Native drivers own transactions and audit.

Definitions use OptionDefParser(AF_INET), CfgOptionDef validation and collection
serialization. Required name/code/space/type; optional array, record-types,
encapsulate and user-context. Native constraints validate combinations; unknown
fields/wrong types are rejected. Project code subset 1..254; native-valid space
at most 128 bytes, excluding dhcp6. Text contains no NUL and is bounded to 65535
bytes.

Global options use native OptionDataParser, OptionDescriptor and CfgOption
serialization. A small parser specialization resolves selected SQL and native
built-in/vendor/last-resort definitions while excluding process-global runtime
fallback that may belong to a different selector or older activation.
CSV is the project default and requires a definition; explicit csv-format:false
allows native hex/binary parsing. There is no independent codec.
Supported flags: always-send and never-send; persistent is rejected as an input
alias. Distinct nonempty client-classes and map user-context use native objects.
Omitted get/delete classes mean exactly [], not every variant. Native class
sequence is retained as identity.

## Association and dependency safety

Native ONE reads hide other associations and prefer a specific row over common
fallback. ALL is common-only. Responses expose observed server-tags and
associations-complete:false, never complete ownership claims. Views are never
merged; exposed duplicate identities fail closed.

An existing selected identity causes set/delete refusal, including identical
set. Missing delete returns result 3 without native mutation/no-op audit revision.
Fresh creation requires an existing named server (or all) and native selectors.

Pinned native definition deletion without force checks selected global options;
it cannot establish all-scope/cross-association safety. Force bypasses safeguards.
Definition replacement can change decoding; whole-row option mutations can affect
hidden associations. No force/cascade or existing update/delete is exposed.
Destructive native deletion was not executed. Disposable fixture SQL constructs
hidden associations; all-table/audit snapshots establish refusal preservation.

## Exact verification commands

From repository root:

```sh
build/quality/bin/clang-format -i src/options4.cc src/commands.h src/diagnostic.cc
python3 -B scripts/integration.py --kea-prefix build-repro-clean/install --build-dir build/integration --jobs 2 --skip-outages
python3 -B -m unittest discover -s tests -p 'test_*.py' -v
python3 -B -m unittest discover -s scripts -p 'test_*.py' -v
PATH="$PWD/build/quality/bin:$PATH" python3 -B scripts/quality.py
python3 -B scripts/analyze.py analyzer
python3 -B scripts/analyze.py cppcheck
python3 -B scripts/analyze.py tidy
python3 -B scripts/verify_artifact.py --library build/integration/libdhcp_db_commands.so --kea-prefix build-repro-clean/install --forbid-path build-repro-clean/source
git diff --check
```

Additional read-only evidence check: Python pathlib reads this file, asserts a
final newline and no trailing whitespace, and checks local Markdown link targets
with the same target rule as scripts/quality.py.

Strict runner configures Release, warnings-as-errors, all runtime/SQL/DHCP suites
enabled, sanitizers/multiprocess fault scenarios disabled; builds then runs six
serial CTests with JUnit. Deliberate outage/retry exhaustion is explicitly excluded
by --skip-outages. No connection-loss recovery, multiprocess writer qualification
or M22 deployment scenario PASS follows from this run.

Executed results: strict C++14 build PASS; unit tests PASS (11 transport/
reconciliation, 28 tooling); Clang analyzer PASS (six translation units);
cppcheck PASS (six); artifact exports/shared dependency/runtime path checks PASS.
clangd: no diagnostics for options4.cc. Standalone clang-tidy UNAVAILABLE
(missing executable; command failed); nothing installed.
Formatting/Ruff/local-link/whitespace PASS (95 files).
Final strict integration PASS: six required tests, zero failures, zero skips.
Final git diff --check PASS. This evidence file's newline/whitespace and local
Markdown links were checked separately because build/ is excluded by quality.py.

## SQL, threading, persistence and packet results

Final strict run: control_transport PASS (0.05 s), hook_lifecycle PASS
(0.75 s), postgresql_read PASS (140.12 s), postgresql_dhcp PASS (152.03 s),
mysql_read PASS (302.96 s), mysql_dhcp PASS (249.29 s). Total 845.20 s;
six required tests, zero failures, zero skips. JUnit:
build/integration/ctest-results.xml. Each SQL/packet family covers MT off and MT on.

| Backend | MT off | MT on |
| --- | --- | --- |
| PostgreSQL 18.6 | PASS | PASS |
| MariaDB 12.3.3 LTS | PASS | PASS |

Each cell verifies selected reads/fresh creates, mutation admission, hidden and
common/specific associations, rejected updates/deletes, SQL/audit preservation,
clean restart persistence, independent runtime observation, explicit activation,
actual OFFER/ACK option payloads and existing subnet/pool/lease/boot-file commands.
These are qualified operations, not a claim that the excluded updates/deletes work.

The runner's six-test/no-skip report and temporary-resource cleanup gates passed.
Disposable database/work directories and fixture-owned processes/namespaces use
the existing fixture teardown; no hostwide process inventory or distributed
fencing qualification is claimed.

Assertions cover empty list/get/missing-delete; native creation; duplicate
identity/name refusal; invalid type/record/space/code/fields; malformed CSV/hex,
missing definitions/wrong types; common/specific views; hidden shared associations;
all-table/audit equality for reads/refusals; denial before parsing; independent
config-get observations and clean restart.

Encodings: strings, uint16, IPv4 addresses/address arrays, records, integer arrays,
hex, valid empty binary and class-restricted binary. Native hex case normalizes;
tests compare decoded bytes. Encapsulation metadata is supported by native
parsing/serialization but not independently asserted or packet-qualified.
Never-send/arbitrary user-context are parser-supported but not independently
round-trip or packet-qualified.

Packet assertions inspect actual OFFER and ACK router (3), DNS (6), domain (15)
and custom string (224) bytes. Newly persisted custom definition/option 246 must
stay absent before reload, appear after explicit reload and survive restart.
Existing DORA, SQL/CSV lease, boot-file-name, pool replacement, subnet deletion/
retained lease and unrelated subnet regressions remain enabled. This does not
establish full M22 convergence or multi-consumer equivalence.

## Failures and corrections

1. Initial compilation tried OptionDefinition::toElement (absent in pinned Kea)
   and modifying ConstElement. Use native singleton collection serialization and
   a mutable parsed JSON copy. Strict build passes.
2. First strict run: transport/lifecycle passed; four SQL suites failed.
   Tests assumed identical hex letter case; native readback uppercases. Compare
   decoded bytes. Another suite exposed native binary fallback with omitted CSV
   and no definition; added explicit CSV-definition guard. Malformed fixture uses
   ab:z rather than assuming odd-width hex invalid. Diagnostic SQL uses
   options.option_id versus option_def.id.
3. Diagnostics prompted uint8_t enum storage and a const-reference native shared
   pointer parameter. Final clangd clean.
4. Standalone tidy missing; analyzer/cppcheck passed separately.
5. PreToolUse rejected a bounded shell source search as a protected path.
   It was not retried or bypassed; specific allowed file reads supplied evidence.
   No protected files or safety hooks changed.

## Files changed

- CMakeLists.txt, src/commands.h, src/diagnostic.cc.
- New src/options4.cc and tests/options4.py.
- tests/smoke.py, tests/postgresql.py, tests/mysql.py, tests/dhcp.py.
- README.md, docs/commands.md, docs/compatibility-matrix.md,
  docs/commercial-parity-gap-analysis.md, docs/command-architecture.md,
  docs/development-roadmap.md.
- This explicitly requested generated evidence file.

## Limits, counts and next scope

Functional: 3 implemented, 15 partial, 56 missing of 74 (v4 3/15/18; v6 0/0/38).
Six new partial analogues: two selected lists, two gets, two create-only sets.
Both deletes remain missing functional equivalents despite safe refusal endpoints.
Exact commercial compatibility: 0 implemented, 0 partial, 74 missing.

Existing update/delete, complete associations, all-scope definition references,
commercial schemas and packet-qualified encapsulation/class behavior remain open.
Default-deny admission is local, not fencing. M22 remains PARTIAL: durable holds/
recovery tooling unchanged, not expanded for exact option convergence. Unit model
tests passed; full same-host recovery was not rerun. Unknown outcomes require
fresh reconciliation, never automatic retry. Upstream transaction cleanup,
external fencing and full reconciliation remain production blockers.

Recommended M27: DHCPv4 shared-network reads/create through native APIs, explicit
child membership/inherited-option contracts, association/update/delete safety,
both backends/threading modes, restart, explicit activation and packet allocation.
Carry option gaps explicitly; no remote registration or weaker safeguards.
