# Writer fencing runbook

Admission decides whether this hook accepts a command. Fencing removes a former
writer's ability to execute database mutations. Changing another process's
`allow-mutations` or server tag does not fence the old process.

## Milestone 22 evidence boundary

Use the [recovery procedure](operator-recovery.md) and
[evidence model](reconciliation-evidence.md) before resumption. M22 records
Linux boot ID and process start ticks as well as PID, endpoint and admission.
Fresh collection is mandatory; missing, stale or incomplete evidence cannot
authorize promotion. The real M22 gate remains held because exact equivalence
and the writerless promotion transition are incomplete. Planned replacement
steps below describe the bounded M21 qualification, not completed M22 recovery.

## Selected mechanism and qualification boundary

Milestone 21 selects orderly process termination under one trusted local
supervisor with no restart policy. After all acknowledged writes finish, native
`shutdown`, clean child exit, process disappearance and closed old control
endpoint establish that the old process cannot execute another mutation.
A post-fence command attempt must fail and a full SQL data snapshot must remain
unchanged. The supervisor verifies this before starting the replacement.

This is actual process fencing within that deployment boundary. SQL credentials
are not revoked. An administrator, independent supervisor or remote host able
to recreate the retired writer is outside that boundary. Do not use endpoint
failure alone as fencing: a partitioned writer could still reach SQL.

| Mechanism | Assessment |
| --- | --- |
| Hook admission | Local defense only; no cross-process fencing |
| SQL grants | PostgreSQL consumers can use SELECT-only; native MariaDB preparation needs CRUD; portable live-session revocation unqualified |
| SQL session termination | Not executed; prohibited by the milestone's safety boundary |
| Network isolation | Potential defense but endpoint loss alone proves no SQL isolation; existing connections and partitions unqualified |
| Graceful supervised exit | Selected and tested without interrupted writes or killed SQL sessions |
| Container/orchestrator removal | Requires verified stop, no restart/reschedule, host identity and reconciliation; design only here |
| Automatic election/failover | Outside scope |

## Initial designation

1. Keep mutation ingress held. Inventory every process and restart authority
   able to use writer credentials across every server tag.
2. Designate one supervisor and one administrative writer. Disable independent
   restart/reschedule of retired writers. Consumers must be false or omitted.
3. Confirm a single intended backend per role, SQL identity and universal tag
   visibility. Record full SQL snapshot and native subnet readbacks.
4. Start exactly one true writer. Verify admission on all roles. Release the
   ingress hold only for an approved, recorded mutation window.

The test supervisor starts roles serially, tracks child process identities,
never restarts retired children and checks exactly one live admitted writer
after replacement. Host-wide inventory and durable restart policy are operator
responsibilities outside this disposable qualification.

## Planned replacement

1. Hold new configuration mutations globally, across all tags and callers.
2. Drain the serialized workflow. Every outstanding write must have a known
   outcome. Record acknowledged intent, ID/prefix, complete basic pools,
   association and SQL snapshot. Do not retry an ambiguous command.
3. Suppress restart/reschedule of the old writer. Verify no other owner can
   launch it. A deployment that cannot establish this must stop here.
4. Send native `shutdown` to the old writer. Wait for clean process exit;
   a successful shutdown response alone is insufficient.
5. Verify the supervised child was reaped with exit zero, its process is gone,
   its control endpoint is closed and a subsequent mutation cannot reach it.
   Compare SQL snapshot to the last acknowledged state.
6. Reconcile SQL through native ID/prefix reads and independent full-data
   snapshots. Check intended pools and exact association; resolve any unexpected
   audit or configuration change. Keep the hold if any result is uncertain.
   Public get/list do not expose full exact-association evidence: this fixture
   uses known universal associations plus full SQL snapshots. Arbitrary recovery
   still needs operator SQL inspection or the proposed M22 native read-only path.
7. Only after recorded fencing and reconciliation, start the replacement
   with true admission. Verify a distinct PID, packetless role and exactly one
   live admitted writer; verify both consumers remain false.
8. Perform one approved mutation. Verify SQL persistence separately from runtime.
   Follow the [fleet activation runbook](fleet-activation-runbook.md).
9. Keep the retired writer disabled permanently. Record the transfer evidence.

The reproducible test denies promotion while the old child is live, then denies
it again after exit when the reconciliation record is absent. The candidate
factory is unreachable on either failure path. Correct fencing and reconciliation
permit the subsequent replacement.

## Failed replacement and uncertain outcome

If fencing fails, do not start the replacement. Keep ingress held; consumers may
continue serving their last verified configuration. The test exercises a live
old writer with an unfulfilled fence and unchanged SQL. Consumer DORA succeeds
before and after the subsequent orderly writer shutdown.
It does not kill an in-flight write or deliberately disrupt a SQL session.

If graceful shutdown fails or an outcome is uncertain, retain the hold and use
the [transaction recovery policy](transaction-recovery-policy.md). Investigate
process identity, transaction outcome and all possible restart owners. Reconcile
persisted state before considering any further command. Never convert a timeout,
connection loss or missing endpoint into proof of rollback or fencing.

Promotion is prohibited by unknown write outcomes, unverified old-process exit,
unknown host/restart state, unexpected SQL changes, missing reconciliation,
another admitted writer, or an unresolved fleet activation failure. If a new
writer cannot start after a verified fence, remain writerless and held while
diagnosing; consumers retain their active configuration. Recovery requires
explicit operator verification, not automatic retries.
