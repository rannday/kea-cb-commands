# Production readiness review — Milestone 19 with M22 addendum

**Milestone 22: PARTIAL; production readiness remains NO-GO.**
[Read-only reconciliation](reconciliation-evidence.md) preserves native subnet
data, diagnostic SQL associations/timestamps and independent runtime subtrees.
[Recovery tooling](operator-recovery.md) adds a durable fail-closed hold, fresh
observation requirements, process-instance identity and refusal of incomplete
promotion. It does not prove exact full-state equivalence, successful M22
replacement or real operator resumption. Native omissions, runtime defaults/
inheritance and the writerless promotion transition remain open. MariaDB
consumers still require native CRUD credentials; hook admission is not SQL
read-only enforcement. M21 results below retain their original bounded scope.

**Milestone 21 addendum (2026-10-17):** the controlled same-host
[designated-writer deployment](designated-writer-deployment.md) passes on
PostgreSQL/MariaDB with packet threading off/on. Three independent roles,
packetless administration, consumer denial with SQL/runtime preservation,
graceful process fencing, gated replacement/reconciliation, staged activation,
partial-failure write hold and both consumers' DORA/leases are verified.
Existing six-test regressions and quality checks pass; deliberate SQL outages
are excluded. See `build/milestone21/checks.md`.

R1 is controlled only within the trusted local supervisor/no-restart boundary;
R4 and R9 now have focused non-faulting deployment evidence. SQL credentials
remain usable by other processes; remote/container fencing, durable holds and
external writer exclusion require deployment-specific qualification. R2's
native SQL failure risk and R3's arbitrary uncertain-outcome/exact-association
recovery remain open. No production approval or HA qualification follows.
M22 should provide separately approved native read-only reconciliation evidence.

The M19 review and M20/M20.1 addenda below retain their historical scope.

Milestone 20 addendum: local default-deny admission is now implemented in the
development worktree and lifecycle-tested in both packet-threading modes.
Milestone 20.1 SQL/DHCP acceptance now passes for both backends and threading
modes, excluding deliberate SQL interruptions; see the [roadmap](development-roadmap.md).
This addressed R5's missing local role only. At that milestone, R1 cross-process
fencing, native SQL failure risk, reconciliation and activation remained open. The
Milestone 19 baseline and findings below are retained as historical evidence.

## Decision and evidence boundary

**NO-GO for unrestricted production use with independent writers sharing a
configuration database.** A restricted deployment can progress without waiting
for ISC, but must demonstrate writer fencing, uncertain-outcome reconciliation,
and activation verification before receiving a deployment-specific approval.
Passing existing integration tests does not establish those controls.

This is a source and retained-evidence review, not a new runtime qualification.
No SQL, DHCP, crash, or concurrency tests were executed for this milestone.
Historical results remain historical; proposed controls below are not implemented.
The previous release-readiness decision predates the multi-process findings.

## Implemented baseline

| Area | Verified implementation and evidence |
| --- | --- |
| Artifact | One Linux C++14 module, `libdhcp_db_commands.so`, for `kea-dhcp4`; four lifecycle exports. See [CMake](../CMakeLists.txt) and [diagnostic.cc](../src/diagnostic.cc). |
| Diagnostic | `db-commands-diagnostic` accesses the native manager/pool API; explicitly does not test database connectivity. It reports mutation capability, not writer authorization or health. |
| Read commands | `cb-subnet4-list` serializes native subnets; `cb-subnet4-get` selects ID or canonical prefix and returns result 3 when absent. Shared-network subnets are rejected. |
| Write commands | `cb-subnet4-set` accepts a minimal standalone subnet and optional basic pools. Omitted pools preserve existing basic pools; supplied pools replace them. `cb-subnet4-del` requires explicit tag and `preserve-leases: true`; absence returns result 3. See [commands](commands.md). |
| Native APIs | [subnet4.cc](../src/subnet4.cc) resolves `ConfigBackendDHCPv4Mgr::instance().getPool()` per invocation, then uses native `getSubnet4`, `getAllSubnets4`, `getServer4`, `createUpdateSubnet4`, and `deleteSubnet4`. No private manager, cached backend, or direct SQL. |
| Backend selection | Exactly one configured backend is required. CRUD requires `postgresql` or `mysql`; list uses the configured backend type. A type selector does not identify an independent database within multiple same-type backends. |
| Server selection | `ALL` selects universal objects; `ONE(tag)` also sees universal objects. `ANY` supports internal conflict/ownership preflight. Set/delete require one exact existing association. Tags are neither authorization nor independent write namespaces. |
| Validation | [arguments.cc](../src/arguments.cc) checks exact keys, types, numeric bounds, canonical prefixes/tags and pool ranges/overlap. Mutation refuses richer existing objects rather than losing fields. This is not validation of a complete future server configuration. |
| Transactions | Native backends own mutation transactions and audit. Hook preflight and mutation are separate calls. There is no cross-process lock, CAS, operation ID, or exactly-once guarantee. |
| Responses | [commands.cc](../src/commands.cc) contains ordinary exceptions; only contract failures expose their text. Native mutation errors explicitly require reconciliation. A successful set echoes the request, so omitted pools are not a complete stored-state receipt. |
| Activation | Write responses state `activation-requested: false`. Persistence does not update live DHCP state. Native pull/reload/restart is a separate operation. |
| Threading/lifecycle | Commands run synchronously on Kea's main thread in both packet threading modes. `load` registers five commands; Kea owns deregistration on unload. No writer role is currently enforced. |

Implementation references: [source](../src/subnet4.cc),
[contracts](commands.md), [backend behavior](backend-behavior.md),
[architecture](architecture.md).

## Prioritized findings

Severity describes the stated deployment condition; it does not imply every
deployment has every failure. BLOCKER prevents the proposed unrestricted
deployment, HIGH requires a reliability control, MEDIUM is a bounded improvement.

| ID / severity | Evidence and impact | Recommended resolution |
| --- | --- | --- |
| R1 **BLOCKER** | `setSubnet` preflight and native mutation in [subnet4.cc](../src/subnet4.cc) have no common cross-process guard. [verify_multiprocess](../tests/concurrency.py) retained lost-update/tag-collision evidence. Independent writers can overwrite each other's state, including preserved pools. | Enforce one writer per physical configuration database, including external tools. Start with the [designated-writer architecture](multi-writer-architecture.md); prohibit automatic promotion without fencing. |
| R2 **HIGH** | [M18 evidence](isc-report-evidence.md) records six SIGABRT exits during administrative SQL-session interruption. Native rollback destructors are source-confirmed exception-unsafe; their causal stack in those exits remains unverified. A packet-serving writer can disappear with its control connection. | Isolate mutations on a dedicated administrative Kea process, supervise it, hold writes after uncertain failure, and accept residual native SQL risk explicitly. No outer catch or language-standard change fixes this path. |
| R3 **HIGH** | Generic mutation errors, process death and transport loss do not establish rollback. [verify_multiprocess](../tests/concurrency.py) also demonstrates a caller disconnect followed by persistence. Public get/list do not expose complete exact-association evidence. | Adopt the [recovery policy](transaction-recovery-policy.md), retain intent/preimage externally, and add a tested native read-only reconciliation path before automatic operational recovery. No automatic write retries. |
| R4 **HIGH** | [verify_dhcp](../tests/dhcp.py) distinguishes persisted and active state; [verify_multiprocess](../tests/concurrency.py) shows separate instance activation. Pull success can be a no-op after backend removal. Restart can load pending SQL. | Require per-instance active-state verification, explicit activation windows and partial-failure handling in the [activation design](runtime-activation-design.md). Do not promise atomic fan-out. |
| R5 **HIGH** | [load](../src/diagnostic.cc) registers mutations without a role parameter. Tags only select data. MariaDB native preparation requires write-capable privileges even for tested reads; see [backend behavior](backend-behavior.md). | Fence command ingress and configuration ownership. Consumers should omit this hook if unnecessary; propose explicit mutation admission for consumers needing reads. A hook role is defense in depth, not database authorization against other software. |
| R6 **MEDIUM** | Local subnet validation cannot establish interface, class, option, lease or merged-server validity. [verify_dhcp](../tests/dhcp.py) includes invalid-interface activation failure. Delete deliberately retains leases. | Validate the candidate against each node's complete configuration; gate lease-sensitive pool/subnet changes and identity reuse. Preserve current fail-closed scope. |
| R7 **MEDIUM** | [commands.cc](../src/commands.cc) diagnostic is pool accessibility only; lifecycle logs do not provide an operation journal or per-instance activation inventory. Synchronous SQL can delay main-thread command handling. | Add external request/outcome and active-state records first. Measure latency and DB timeout behavior before defining service SLOs; do not label diagnostic success as SQL health. |
| R8 **MEDIUM** | [backend behavior](backend-behavior.md) records MariaDB retry exhaustion requiring reload; PostgreSQL exhaustion/startup-unavailable behavior is not fully qualified. Restart evidence is functional, not an RTO or HA measurement. | Qualify startup, reload, consumer reconnect and supervised administrative restart separately, using ordinary availability tests where possible. Leave historical interruption experiments out of routine gates. |
| R9 **MEDIUM** | [CI](../.github/workflows/ci.yml) covers quality, strict integration and packaging; it does not establish multi-process writer fencing, activation orchestration, or deployment SLOs. The optional concurrency suite includes deliberate faults. | Add non-faulting admission/fencing/activation tests as separate gates. Do not enable the entire historical fault suite automatically. |
| R10 **MEDIUM** | [release tooling](../scripts/package_release.py) verifies pinned Release C++14 artifacts and acceptance evidence; shared Kea/libstdc++ dependencies remain external. Tested release scope is Linux x86_64, not arbitrary distributions. | Qualify exact deployment Kea builds and runtime dependencies; document configuration/DB backup, rollback and hook upgrade order. A matching hook ABI integer alone is insufficient. |
| R11 **LOW** | Native APIs exceed the deliberately minimal subnet interface. Adding richer objects before safety controls would expand validation and recovery obligations. | Defer feature families to the [roadmap](development-roadmap.md). Retain C++14; [modernization experiments](cpp-standard-feasibility.md) do not justify a baseline change. |

## Coverage and its limits

The strict [integration runner](../scripts/integration.py) requires all six tests
without skips: transport, hook lifecycle, PostgreSQL SQL and DHCP, MariaDB SQL and
DHCP. [Mutation](../tests/mutation.py) and [lifecycle](../tests/lifecycle.py)
assertions cover validation, pools, association guards, audit, rollback, get/delete,
and retained leases. Packet tests cover both threading modes, activation and
restart with real DORA in isolated namespaces. Existing release/sanitizer results
are recorded in [release readiness](release-readiness.md); none were rerun here.

Historical concurrency coverage is evidence of limits, not a coordination feature.
It includes blocked precommit failures and six aborts across four backend/threading
scenarios. It does not prove commit-acknowledgement-loss behavior, hook-free crash
reproduction, a causal debugger stack, seamless failover, or production throughput.
See [investigation](sql-transaction-investigation.md) and
[sanitized evidence](isc-report-evidence.md).

## Native defect status and decision gates

Kea 3.2.1 PostgreSQL/MySQL transaction destructors call potentially throwing
rollback without containment. An exception escaping those implicitly nonthrowing
destructors invokes `std::terminate()`. Inspected 3.3.1, 3.3.2 and master snapshot
retain the pattern; no validated fix was identified in that comparison. This is
not a claim about all subsequent upstream revisions or runtime behavior there.
**ISC issue: not submitted; URL pending confidential submission.** See the
[draft](isc-sql-transaction-issue.md) for versioned source links and limitations.

A restricted deployment review should require: one fenced administrative writer;
no uncoordinated external writer; recovery and reconciliation exercises; verified
activation on every serving node; exact-build artifact acceptance; supervised
restart with write hold; and an accepted availability objective for remaining
native SQL failure paths. These gates allow development without depending on an
ISC fix, but do not establish crash immunity for SQL-consuming daemons.

## Review verification

The existing quality runner passed formatting, Python lint, whitespace and local
document-link checks. `git diff --check` passed. Only documentation was changed;
no runtime qualification, DB interruption or historical fault suite was run.

A read-only shell command inspecting named upstream C++ files was rejected by
PreToolUse as protected-file access and was not retried. Public installed pool
header inspection and existing versioned source evidence support the API inventory;
activation conclusions also rely on existing tests and documentation. No new
inspection of the rejected native activation-handler bodies is claimed. The
historical raw-log extraction limitation recorded in the M18 evidence also remains.

A supplemental sanitization scan was also rejected with
`Protected .env or PEM path. Use a redacted example file.` The command named only
the five new Markdown deliverables and searched for home-path, private-key-header
and SQL credential-URL markers. It did not execute and was not retried. Automated
sanitization verification is therefore incomplete. These documents introduce no
raw log/configuration excerpts; prior sanitized evidence is linked instead.
