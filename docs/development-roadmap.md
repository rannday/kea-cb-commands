# Development roadmap after Milestone 21 qualification

## Priority and boundaries

**M21 acceptance is complete for the controlled same-host deployment.**
M20/M20.1 local admission and non-interruption SQL/DHCP acceptance remain green.
The next proposed milestone is **M22: native read-only reconciliation evidence**,
subject to separate review and authorization. Local admission does not fence
external writers or make the project production-ready. Production restart
exclusion, durable holds and uncertain-outcome recovery remain open.

This roadmap preserves the standalone native Kea 3.2.1 architecture, PostgreSQL
and MariaDB, C++14, existing commands and persistence-only mutation behavior.
No implementation is part of Milestone 19. Historical results remain in
[architecture](architecture.md), [release readiness](release-readiness.md),
[SQL investigation](sql-transaction-investigation.md), and
[ISC evidence](isc-report-evidence.md).

## Proposed small milestones

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

### M22 — Native read-only reconciliation evidence

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

### M23 — Qualify explicit multi-instance activation

- **Objective:** turn the [activation design](runtime-activation-design.md) into
  an executable operator workflow.
- **Exact scope:** a small external administrative helper or documented scripted
  sequence using existing control commands; one change window, canary, normalized
  active-state comparisons and partial-failure records. Select one form before
  implementation to avoid building a controller service prematurely.
- **Expected files:** an administrative script under `scripts/` if justified,
  focused multi-instance tests, operations and activation docs. No new callouts.
- **Acceptance:** two consumers on each SQL engine and threading mode remain
  unchanged before activation; canary-only change is visible; invalid local
  configuration produces a recorded partial failure; corrected reload converges;
  restart during a pending window is detected; leases survive deletion. A no-op
  pull never counts as convergence.
- **Dependencies:** M21 fencing and M22 reconciliation; node configuration and
  service probe definitions.
- **Exclusions:** atomic fan-out, automatic SQL rollback, periodic uncontrolled
  fetch, HA/lease synchronization and DB fault injection.

### M24 — Restricted production qualification

- **Objective:** make a deployment-specific readiness decision with explicit
  residual native SQL risk.
- **Exact scope:** documented startup/reload/reconnect matrix and supervised
  administrative restart, measured availability objectives, exact-build artifact
  installation/rollback and an upgrade rehearsal. Add established non-faulting
  admission/activation checks to CI; use existing strict acceptance for artifacts.
- **Expected files:** CI workflow, operations/release documentation, focused
  lifecycle fixtures and packaging checks only where gaps are demonstrated.
- **Acceptance:** evidence names target Kea/runtime libraries and deployment;
  six strict tests pass without skips; write hold survives writer restart at the
  ingress layer; artifact rollback is rehearsed; consumers' actual availability
  is measured. PostgreSQL startup/recovery unknowns are either resolved in an
  approved safe test or recorded as a deployment restriction. Native abort risk
  and restart limits are explicitly accepted by the operator.
- **Dependencies:** M20–23 and deployment-specific SLOs; no dependency on an ISC
  fix. Approval of any new failure testing is separate from this roadmap.
- **Exclusions:** automatic crash reproduction, broad platform certification,
  release/version changes by implication and security exploitability claims.

## Future DHCPv4 command coverage

These API families were checked against the pinned installed public pool header
and its [versioned upstream source](https://github.com/isc-projects/kea/blob/Kea-3.2.1/src/lib/dhcpsrv/config_backend_pool_dhcp4.h).
They identify native capabilities, not existing hook features or permission to
implement them. Current list/get/set/delete cover only minimal standalone subnets.

| Candidate | Native API surface | Dependencies, validation and tests | Next safety release? |
| --- | --- | --- | --- |
| Richer subnet fields | `getSubnet4`, `createUpdateSubnet4` | Preserve full object semantics; define replace/patch rules, cross-field validation and round-trip tests. Existing rich-object rejection must remain until supported. | No |
| Shared networks | `getSharedNetwork4`, `getAllSharedNetworks4`, `getSharedNetworkSubnets4`, `createUpdateSharedNetwork4`, `deleteSharedNetwork4` | Parent/child associations and inherited values make this high complexity; require safe deletion, selectors, audit, rollback and packet activation tests. | No |
| Option definitions | `getOptionDef4`, `getAllOptionDefs4`, `createUpdateOptionDef4`, `deleteOptionDef4` | Code/space/type/record validation and dependency protection; test built-in/custom collisions and force-delete semantics before exposing them. | No |
| Options | `getOption4`, `getAllOptions4`, `createUpdateOption4` overloads for global/network/subnet/pool scopes | Depends on definitions, binary/text encoding and class selection. Test inheritance, scope identity, dependencies and actual packet options. High complexity. | No |
| Client classes | `getClientClass4`, `getAllClientClasses4`, `createUpdateClientClass4` with `follow_class_name` | Ordered definitions and expressions require dependency/order validation and packet matching tests; empty follow name appends. | No |
| Global parameters | `getGlobalParameter4`, `getAllGlobalParameters4`, `createUpdateGlobalParameter4` | Stamped native values, types, local override precedence and fleet-wide effects; test merged configuration and invalid activation. Not arbitrary whole-server configuration storage. | No |
| Server records | `getServer4`, `getAllServers4`, `createUpdateServer4` | Identity/association lifecycle and universal-server rules; prevent orphaning or accidental visibility changes. Server records do not create writer isolation. | No |
| Audit/read diagnostics | `getRecentAuditEntries`, modified-object getters | Cursor uses time plus ID; test ordering, selectors and retention assumptions. Useful follow-up observability, never a CAS or exactly-once API. | Only narrowly justified reconciliation work |

Feature families should each receive a separate scoped design after safety gates.
Do not implement shared networks, options, classes and globals as one milestone.
No newer C++ standard is required by this plan; see
[C++ feasibility](cpp-standard-feasibility.md).
