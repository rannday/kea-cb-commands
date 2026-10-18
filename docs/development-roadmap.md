# Development roadmap: commercial command parity

**M22 status: PARTIAL.** The [evidence collector](reconciliation-evidence.md)
and [durable recovery gate](operator-recovery.md) are implemented in test tooling.
Incomplete evidence blocks mutation and promotion across both SQL backends and
threading modes. Exact full-state equivalence, successful evidence-gated
replacement and complete operator resumption remain unqualified.

**M23 status: PARTIAL.** The commercial command inventory and architecture are
complete; public contract contradictions and unspecified errors prevent an
exact parity claim. Functional parity is the primary development sequence below.
Outstanding recovery and production qualification remain a separate workstream.
This roadmap is a plan, not implementation authorization.

## Priority and boundaries

**M21 acceptance is complete for the controlled same-host deployment.**
M20/M20.1 local admission and non-interruption SQL/DHCP acceptance remain green.
M22's partial outcome is recorded above; its original proposal below is retained
for scope and acceptance comparison. Local admission does not fence
external writers or make the project production-ready. Production restart
exclusion, durable holds and uncertain-outcome recovery remain open.

This roadmap preserves the standalone native Kea 3.2.1 architecture, PostgreSQL
and MariaDB, C++14, existing commands and persistence-only mutation behavior.
Milestones 1–22 remain historical work. Historical results remain in
[architecture](architecture.md), [release readiness](release-readiness.md),
[SQL investigation](sql-transaction-investigation.md), and
[ISC evidence](isc-report-evidence.md).

## Historical Milestones 20–22

### M20 — Explicit mutation admission (PASS)

- **Objective:** allow a consumer to load read commands while refusing mutations
  before any native backend access.
- **Implemented scope:** native boolean parameter `allow-mutations`, default
  false. Only explicit true admits set/delete. Admission is checked before
  parsing or backend access. Invalid types, non-map parameters and unknown keys
  fail initialization. Permission resets before load/unload and is granted last
  on successful load. Diagnostic adds effective `allow-mutations`; capability
  remains `mutations-supported`. This supersedes M19's proposed legacy-compatible
  `mutations-enabled` name/default in accordance with the M20 requirement.
- **Expected files:** lifecycle/registration in `src/diagnostic.cc`, admission
  access and callout checks in `src/commands.cc`/`src/commands.h`, lifecycle and
  mutation assertions in `tests/smoke.py` and `tests/mutation.py`, contracts and
  deployment documentation. Confirm the smallest state interface during design.
- **Acceptance:** absent/false refuse valid and invalid mutation requests before
  backend resolution; true preserves existing mutation behavior; reads work; diagnostic
  reflects admission; invalid parameter fails load; unload/reload has no stale
  role. Both SQL engines show unchanged data/audit for denied writes. Both packet
  threading modes and the six-test strict suite pass without skips.
- **Dependencies:** existing contracts and lifecycle machinery; no ISC fix.
- **Exclusions:** authentication, database permissions, leader election, locks,
  per-tag roles, automatic retries, activation and claims of external fencing.

#### Verification evidence and remaining boundaries

**M20.1 outcome: PASS (2026-10-16).** Both SQL fixtures use the shared admission
helper with explicit writer phases and initial read-only phases. All six strict
CTest tests pass without skips against Kea 3.2.1, PostgreSQL 15.19 and MariaDB
10.11.19 on Debian 12 WSL2. Both packet-threading modes pass omitted/empty/false
admission, exact set/delete denial, successful list/get and unchanged SQL
table/audit snapshots and active state after denied create/update/delete.
Malformed requests and lifecycle tests without a backend verify admission
precedence. See the [complete coverage matrix](mutation-admission.md).

Explicit true preserves CRUD, validation/conflicts, tags/selectors, pool
omission/replacement/removal, audit/rollback, persistence across actual process
restart and explicit pull/reload activation. Both packet tests pass DORA,
allocation, persistent memfile leases and retained leases after SQL deletion.
No automatic activation is introduced. Lifecycle tests also cover invalid
parameters, failed initialization, registration and no stale writer permission.

Release C++14 with warnings as errors, transport units (6/6), script units
(25/25), formatting, Ruff lint/static checks, whitespace/local links, artifact
exports/dependencies and clangd diagnostics pass. Exact commands and current
logs are under `build/milestone20.1/checks.md`. Earlier PARTIAL attempts and exact
policy rejections remain in the historical evidence there and under
`build/milestone20/`. Resume edits used native patches without bypassing policy.

This acceptance explicitly uses `--skip-outages`, forwarded to all four SQL and
DHCP tests. Deliberate SQL interruption/recovery, retry exhaustion and historical
crash reproductions were not run; their default test assertions are preserved.
Docker, sanitizer integration and optional independent-process suites remain
unrun. The Docker fixture requires a candidate artifact implementing admission;
published v0.1.0 is unchanged. This historical M20.1 run did not include M21.

**At the M20.1 boundary:** cross-process writer fencing, deployment enforcement,
reconciliation and activation qualification remained open; see M21 below.
Production acceptance remains open.
**Upstream dependency:** native SQL transaction exception safety remains
unresolved; ISC issue URL is pending confidential submission, not invented.

### M21 — Qualify the designated-writer deployment (PASS, bounded)

**Executed 2026-10-17:** PostgreSQL 15 and MariaDB 10.11, packet MT off/on,
each run three independent roles in the private loopback-only packet namespace.
The administrative writer is verified packetless. Consumers deny set/delete
while retaining reads; full SQL snapshots and active state remain unchanged.
Graceful supervised writer exit fences the old process before reconciliation
and replacement. Failed fencing and missing reconciliation prevent candidate
startup. Both consumers pass staged activation, partial-failure hold/recovery
and six DORA/lease checks per scenario (24 total).

See [deployment](designated-writer-deployment.md),
[fencing](writer-fencing-runbook.md) and
[fleet activation](fleet-activation-runbook.md). Implementation is isolated to
test/deployment tooling; production hook behavior is unchanged from M20.
The existing six-test Release C++14 gate passes with no skips and deliberate
outages excluded; 31 unit tests, artifact checks, clangd diagnostics and quality
checks pass. Evidence: `build/milestone21/checks.md`.

This proves fencing only under the trusted local supervisor with no retired
writer restart. Container/remote fencing, partitions, arbitrary external writers,
durable operational holds and uncertain native transaction recovery are
unqualified. This is not production readiness or Kea HA qualification.

The original milestone scope is retained below:

- **Objective:** demonstrate a non-serving writer and consumers with enforced
  mutation boundaries, including a controlled ownership handover.
- **Exact scope:** deployment/runbook examples with protected writer ingress,
  explicit roles or omitted hook, process inventory and manual fencing checklist.
  Add a separate non-faulting topology test; do not automatically run the existing
  concurrency fault suite.
- **Expected files:** `docs/operations.md`, deployment examples, a focused test
  under `tests/` and opt-in CMake registration. Production CRUD remains unchanged.
- **Acceptance:** writer has no packet listeners; only its endpoint admits
  mutations; consumers continue packet service during ordinary writer shutdown;
  replacement is admitted only after old writer shutdown and no in-flight work.
  Both engines and threading modes pass. Document that an unreachable old host
  blocks promotion, and how bypass writers are excluded operationally.
- **Dependencies:** M20 for consumers needing read commands; network/control
  access policy and database ownership inventory supplied by deployment.
- **Exclusions:** failover during partitions, deliberate DB interruption,
  automatic election, DB lock SQL, and universal read-only MariaDB grant claims.

### M22 — Native read-only reconciliation evidence (original proposal)

- **Objective:** allow operators to distinguish visible subnet state from exact
  ownership/conflict evidence after an uncertain write.
- **Exact scope:** design an opt-in extension to existing get diagnostics for
  exact server associations and ID/prefix conflict checks through native APIs.
  Preserve default replies. Define what cannot be concluded about commit history.
  Specify an external intent-record format and manual comparison procedure.
- **Expected files:** `src/subnet4.cc`/`.h`, `src/commands.cc`, argument parsing if
  an opt-in field is approved, `tests/lifecycle.py`, contracts and recovery policy.
- **Acceptance:** universal, specific, multi-tag, unassigned, absent and prefix
  conflict cases have accurate evidence on both engines. Read-only requests make
  no mutations. Default response compatibility and full strict suite pass. A
  fixture with ambiguous history never reports exactly-once or confirmed rollback.
- **Dependencies:** separately approve the response schema; M21 ownership makes
  comparison stable. Verify API serialization before implementing.
- **Exclusions:** direct SQL, transaction reconstruction, automated retry,
  automatic compensation and durable journal service inside the hook.

## Feature parity milestones

M1–22 remain historical work; see [development history](development-history.md)
and the results above. M22's original proposal differs from its implemented
test-tooling scope; its actual PARTIAL result takes precedence.

M23 replaces the former future M23/M24 activation/production proposals with the
feature sequence below. Their unfinished work is retained in the separate
hardening workstream. Feature development does not require a production GO,
but must preserve every existing admission, ownership, hold and activation rule.

Every implementation milestone inherits the eight
[acceptance gates](commercial-parity-gap-analysis.md#acceptance-evidence-for-implementation-families):
pinned build/native APIs; request/error fixtures; PostgreSQL and MariaDB with
MT off/on; associations; restart/persistence and explicit activation; applicable
real packets; alternative evidence; existing regressions and quality.
No required tests may silently skip. Unresolved public contracts prevent an
exact compatibility claim for the affected command.

### M23 — Commercial parity inventory and architecture (PARTIAL)

Deliver the 74-command [matrix](compatibility-matrix.md), uncertainty ledger,
[architecture](command-architecture.md) and this plan. The documented inventory
is complete (36 IPv4, 38 IPv6); public class examples conflict and error behavior
is incompletely specified. Resolve the affected U1–U8 questions per family
before registering commercial names. Evidence: `build/milestone23/checks.md`.

### M24 — Shared command infrastructure

M24 extracts private request/field/reply and typed backend/selector helpers,
retaining all five commands, admission precedence and one-backend behavior.
An isolated IPv6 manager/server/global compile/link probe exercises installed
native symbols without enabling IPv6 loading or remote commands. The concrete
baseline-preservation gate is in the
[architecture](command-architecture.md#m24-implementation-boundary), including
strict six-test SQL/DHCP acceptance without deliberate outages. Execution evidence
is recorded in `build/milestone24/checks.md`. M25 must freeze its own commercial
schema fixtures and resolve U2/U6 before registering its eight command names.

### M25 — DHCPv4 servers and global parameters

Depends on M24; resolve U2 compound-global encoding and U6 server lifecycle
defaults. Deliver servers first (4 commands), then globals (4 commands).
Acceptance: eight qualified names, reserved `all` behavior, association
detach/cascade evidence, scalar and each supported compound value, absent versus
empty metadata, multi-parameter partial-failure reporting and packet-observed
global behavior after explicit activation. Unsupported JSON-only settings fail
clearly; no arbitrary whole-server storage.

### M26 — DHCPv4 option definitions and global options

Depends on M25. Deliver definitions then global options (8 commands); resolve
U5 force/dependency checks and U7 class-tag identity. Acceptance includes
custom/built-in option spaces, text/binary data, record/encapsulation validation,
class-tag omission/empty distinctions, deletion dependency refusal and explicit
force policy, round trips and actual DHCP option payloads.
Class filters can be tested with local/native seeded classes; class-management
commands are not prematurely introduced.

### M27 — DHCPv4 shared networks

Depends on M26. Four commands with full fields, summary/full-child read views,
association preservation and explicit keep/delete child policy. Acceptance
covers inherited options, selector-specific children, missing parents, safe
deletion and real allocation across shared-network subnets.

### M28 — Full DHCPv4 subnets and pools

Depends on M27. Six commands, full native subnet replacement, explicit shared
network membership and embedded address pools. Acceptance covers rich-object
round trips, inherited values, association changes, identity conflicts, pool
replacement and real allocations. Existing minimal `cb-*` semantics remain
unchanged, including omitted pools and retained leases on delete.

### M29 — DHCPv4 scoped options

Depends on M28. Six set/delete commands for network, subnet and pool scopes.
Acceptance covers precise parent identity, class filters, option-definition
dependencies, inherited versus explicit deletion, overlapping-range ambiguity
and packet-observed precedence. Do not invent scoped get/list commands.

### M30 — DHCPv4 client classes

Depends on M29; resolve U3/U4 schema and response contradictions. Four commands,
native expression parsing, ordering and dependency behavior, embedded class
options/definitions. Acceptance includes insertion versus update positioning,
follow-class handling, KNOWN/UNKNOWN dependencies, invalid/dependent deletion
and packets selecting each intended class branch.

### M31 — DHCPv4 compatibility qualification

Depends on M25–30. Qualify all 36 IPv4 remote commands together, including
cross-object replacement/deletion, mixed selectors, batch failures, restarts and
activation. Freeze versioned request/success/error fixtures and report any
remaining public-contract uncertainty as PARTIAL. Existing five commands,
admission and non-interruption SQL/DHCP regressions must still pass. No claim of
commercial binary conformance without separately authorized, lawful evidence.

### M32 — DHCPv6 loading and test foundation

Depends on M24 and M31. Enable family-aware loading only after lifecycle,
manager/link and native backend tests pass in real `kea-dhcp6`. Extend shared
fixtures and the strict runner with mandatory IPv6 tests. Acceptance includes
independent IPv4/IPv6 processes, read-only admission, MT modes, clean reload and
real IPv6 allocation/PD fixture baselines. No new remote family names yet.

### M33 — DHCPv6 servers and globals

Depends on M32 and the M25 lessons. Eight commands in two deliverables.
Acceptance repeats server association lifecycle and the IPv6-specific global
allowlist, inheritance and packet effects; do not assume IPv4 settings apply.

### M34 — DHCPv6 definitions and global options

Depends on M33 and M26 design. Eight commands, with IPv6 option codes/spaces,
encapsulation, class filters and binary/text validation. Acceptance includes
native persistence and actual DHCPv6 option payloads.

### M35 — DHCPv6 shared networks

Depends on M34. Four commands with child inclusion/deletion policies,
associations, inherited values and real allocation across member subnets.

### M36 — DHCPv6 subnets, address pools and PD pools

Depends on M35. Six subnet commands. Split full subnet/address-pool support
from embedded PD-pool support within this milestone. Acceptance includes
prefix/delegated-length and exclusion validation, association round trips,
IA_NA allocation and real prefix delegation before/after explicit activation.

### M37 — DHCPv6 scoped options

Depends on M36. Eight set/delete commands for network, subnet, address pool and
PD pool. Acceptance verifies each scope's identity, class filters and inheritance,
including actual delegated-prefix option behavior where applicable.

### M38 — DHCPv6 client classes

Depends on M37 and resolved M30 contracts. Four commands, IPv6 expressions,
ordering, dependencies and embedded options. Acceptance includes packet-selected
allocation/PD branches and invalid expression/dependency rejection.

### M39 — DHCPv6 compatibility qualification

Depends on M33–38. Qualify all 38 IPv6 commands against versioned fixtures,
both SQL backends and MT modes, restarts, activation, allocation and PD.
Document remaining command-contract uncertainty independently of native API
success. IPv4 qualification remains a required regression.

### M40 — Cross-family commercial command parity qualification

Depends on M31 and M39. Reconcile the inventory against the pinned release
again: all 74 documented names have individual contract, backend, selector,
error, persistence and activation evidence; no invented CRUD names.
Run the combined strict matrix without required skips and preserve existing
commands and recovery safety. Exact parity remains PARTIAL for unresolved
contract behavior. Other Kea versions and Oracle MySQL require separate
qualification; MariaDB evidence does not establish Oracle MySQL compatibility.

## Separate deployment-hardening workstream

These are deployment/release gates, not prerequisites for every configuration
family. New object families must extend reconciliation evidence without
weakening holds while these gaps remain.

| Work | Dependencies and measurable completion |
| --- | --- |
| H1: Complete M22 evidence | Approved intent registry, complete native inventory, defaults/inheritance and consistent snapshots; distinguish exact from incomplete per consumer; prove missing/stale/contradictory evidence cannot resume writes. |
| H2: Controlled recovery and promotion | H1 plus writerless transition; successful evidence-gated replacement and operator resumption in PostgreSQL/MariaDB × MT off/on, holds surviving workflow/writer/consumer restarts and unknown outcomes. |
| H3: Deployment ownership and privileges | Explicit deployment boundary, least-effective native grants by role, ingress exclusion and restart ownership; same-host disappearance never qualifies remote/container fencing. Broader fencing requires separate design and authorization. |
| H4: Restricted production qualification | H1–H3, measured availability, artifact install/rollback, upgrade/restart rehearsals and named deployment restrictions; upstream SQL transaction cleanup remains unresolved until independently verified. Production remains NO-GO meanwhile. |

The former activation proposal is covered by H1/H2 and
[runtime activation](runtime-activation-design.md). The former restricted
production proposal is H4. No distributed election, direct hook SQL, automatic
retry/activation, new failure injection or production rollout is authorized by
this roadmap. C++14 remains sufficient; see
[C++ feasibility](cpp-standard-feasibility.md).
