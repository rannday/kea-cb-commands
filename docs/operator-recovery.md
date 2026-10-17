# Operator recovery — Milestone 22

**Status: PARTIAL; keep production mutation ingress held.** This is a diagnostic
qualification and a fail-closed local gate, not a qualified production recovery
service. Exact full-state evidence is missing; the real workflow cannot release
its hold or promote a replacement. See [evidence](reconciliation-evidence.md)
and the [same-host fencing boundary](writer-fencing-runbook.md).

## Recovery classifications

All applicable reasons are retained. The first applicable row is the primary
state, in this precedence order:

| State | Evidence and required response |
| --- | --- |
| WRITER_UNFENCED | Current exclusive writer ownership is unverified; hold writes and establish lifecycle/fencing evidence |
| UNKNOWN_COMMIT | A prior outcome is unresolved, or journal state is missing/invalid; obtain fresh complete persisted evidence, never retry automatically |
| EVIDENCE_INCOMPLETE | Missing required consumer/target/readback or an unqualified equivalence domain; keep the hold |
| PARTIAL_ACTIVATION | Only some consumers match their own targets, or consumers with the same target have different active states |
| PENDING_ACTIVATION | Known persisted configuration awaits required consumers; no observed consumer has reached its target |
| RECOVERY_REQUIRED | Persisted and approved intended states disagree; operator decision is required |
| CONVERGED | Complete persisted/intended agreement, all required per-consumer active targets and verified ownership; no unresolved outcome |

Missing observations and ownership failures always prohibit CONVERGED.
Consumers may have different approved targets; identical fleet state is not a
general requirement. All non-CONVERGED classifications require recovery before
another mutation. Operational failures that prevent collection also hold writes.

## Durable hold and trust boundary

`RecoveryGate` journals version, deployment identity, hold, uncertainty and
reason to a mode-0600 temporary file, fsyncs it, replaces the journal atomically,
then fsyncs its directory. It stores no SQL credentials. Missing, malformed,
wrong-version or wrong-deployment state starts held and uncertain. Every
workflow restart requires fresh collection even if the saved hold was clear.

Before dispatch, the gate saves a hold and re-reads evidence; before a mutation
is dispatched it saves uncertainty. Exceptions, process restart and lost replies
therefore cannot authorize the next mutation. No uncertain operation is retried.
An endpoint/read exception cannot clear the hold. An explicit recovery attempt
saves a hold before collecting; acknowledgement alone is never a bypass.

This is not distributed fencing, a multi-process journal lock, authentication,
or a complete mutation ingress service. It assumes one trusted orchestrator,
private filesystem and supervised processes without restart policies. Hook
admission and SQL credentials remain independently usable. Other callers must
also be excluded. A local journal cannot prove remote/container ownership.

## Recovery procedure and current stop point

1. Hold every mutation ingress. Inventory writer processes, endpoints,
   credentials and restart authorities. Confirm the designated process using
   PID, boot ID, start ticks, native status and admission; verify consumers deny
   mutations.
2. Re-read persisted configuration and actual associations for every required
   selector. Preserve full compared data and fingerprints. Investigate audit
   changes; do not treat audit timestamps as complete revisions.
3. Establish operator-approved intent separately from whatever is currently in
   SQL. For an unknown outcome, compare fresh persisted state before deciding
   whether the intended write committed. Never automatically replay it.
4. Explicitly activate each required consumer and inspect its actual
   `config-get` result. A successful pull/reload response is insufficient.
   Recover an unavailable consumer through clean startup, verify its new
   process instance and explicitly activate it.
5. Compare every consumer to its own approved selector-specific target.
   Record missing/unobservable fields and independently verify DHCP and leases.
6. Record fresh reconciliation, identity and lifecycle evidence. Keep the hold
   for any mismatch, unknown outcome, missing observation or incomplete scope.
7. Release only after complete fresh CONVERGED evidence. **Current real M22
   collector stops before this step:** incomplete full-state observability is
   not repairable through manual acknowledgement.

The unit gate demonstrates release with synthetic complete observations.
The real four-cell qualification demonstrates retained holds, pending/partial
state, clean consumer recovery, unknown-outcome simulation and DHCP continuity.
It does not demonstrate complete real operator resumption.

## Writer replacement

The M21 controlled test still verifies clean shutdown, reaped exit zero,
process disappearance, closed endpoint and bounded reconciliation before serial
replacement. M22 additionally records boot/start identity and refuses promotion
with incomplete, missing or retained stale evidence.

A future complete recovery workflow must verify the old instance and every
restart authority are fenced, collect complete persisted/intent/consumer
evidence while no writer is active, and bind promotion to that fresh evidence
and the new instance. The present generic promotion gate requires CONVERGED
ownership evidence and does not implement that writerless transition. Successful
M22 promotion, subsequent mutation and real full-state resumption are therefore
**not qualified**. Do not weaken the gate or reuse M21's projection to bypass it.

Process disappearance is sufficient only for the qualified supervised same-host
child with no external restart. It does not fence a remote host, container
controller, credential holder or independent restart mechanism.

## Database privileges qualified

Disposable users and databases only; no production roles or credentials change.

| Role | PostgreSQL | MariaDB |
| --- | --- | --- |
| Administrative writer | CONNECT, schema USAGE, table SELECT/INSERT/UPDATE/DELETE, sequence USAGE/SELECT; default PUBLIC routine EXECUTE remains | SELECT/INSERT/UPDATE/DELETE plus EXECUTE for native audit routines |
| Consumer A | CONNECT, schema USAGE, table SELECT; default read-only transactions | SELECT/INSERT/UPDATE/DELETE |
| Consumer B | Separate account with the same read grants and read-only transactions | Separate account with the same CRUD grants |
| Diagnostic reconciler | CONNECT, schema USAGE, table SELECT; read-only transactions | SELECT |

These are tested effective schema-level privileges, not proven per-object
absolute minima. Existing M21 grant-ladder tests show MariaDB SELECT-only native
backend initialization fails because Kea prepares write statements; CRUD permits
initialization and writer audit mutation additionally needs EXECUTE. M22 uses
distinct consumer accounts and verifies actual native read/pull/DHCP operations.
Its diagnostic SELECT-only CLI account reads associations and rejects a no-row
DELETE. PostgreSQL still permits default PUBLIC routine execution, so this is
not a complete privilege-hardening proof.

Hook-level read-only admission is a local defense. In particular MariaDB
consumers retain DML credentials; bypassing the hook can mutate SQL. Do not claim
database-enforced read-only consumers on MariaDB. Authentication, per-object
grants, routine revocation and production credential lifecycle need separate
qualification.

## Qualification gaps and next milestone

M22 remains PARTIAL for exact equivalence, real CONVERGED state, successful
evidence-gated replacement and full operator resumption. Selector read views
are tested, but distinct selector-specific runtime targets are unit-tested only.
Administrative replacement/restart evidence comes from the retained M21
regression, not a completed M22 promotion. Durable hold restart tests cover the
local workflow; they do not establish cross-host restart exclusion.

Proposed M23: complete an auditable read-only backend inventory and approved
intent model, qualify defaults/inheritance/options and consistent snapshot
semantics, then implement the writerless replacement transition and prove real
full-state recovery in all four cells. Preserve NO-GO until those tests and
deployment-specific restart exclusion pass. No distributed lock, automatic
retry or production hook expansion is implied by this recommendation.
