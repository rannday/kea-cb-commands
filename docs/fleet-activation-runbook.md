# Fleet activation runbook

A successful mutation persists SQL configuration. It does not activate any Kea
process. Each consumer must be verified independently; two consumers sharing
SQL do not form a qualified DHCP HA pair.

## Milestone 22 evidence boundary

The [new collector](reconciliation-evidence.md) preserves each consumer's full
subnet subtree independently and reports the M21 managed projection separately.
It retains runtime/native differences rather than stripping fields to match.
The [durable gate](operator-recovery.md) survives workflow restart and keeps all
real M22 observations held. M22 is **PARTIAL**: the bounded convergence and manual
operator verification described below do not authorize full-state resumption.
A manual acknowledgement cannot clear the new gate.

## Persistence and canary activation

1. Permit one approved mutation only when the workflow has no outstanding
   mutation, uncertain outcome, fencing issue or activation hold.
2. Record the native response, ID/prefix readback, universal association, basic
   pools and independent full SQL snapshot. On uncertain outcome, hold all
   further writes and follow the [recovery policy](transaction-recovery-policy.md).
3. Before activation, query each consumer's `config-get`. Confirm its old
   state remains active. Keep `config-fetch-wait-time: 0`; periodic fetching
   would invalidate controlled activation.
4. Send native `config-backend-pull` to consumer A. Compare its active subnet,
   prefix, lifetime and complete pool list against recorded intended SQL state.
   A successful response alone does not prove the desired object was applied.
5. Confirm consumer B still has the prior active state. This is staged
   activation, not fleet convergence.
6. Explicitly pull consumer B, verify its active state, compare both consumers
   and recheck SQL snapshot. Only then mark fleet convergence.
7. Send isolated DORA to each endpoint and verify its ACK identity, allocated
   range and recorded active lease. For a real deployment use separately
   authorized client networks; this test uses only private namespace loopback.

The qualification compares every field supported by its minimal subnet
mutation (ID, prefix, lifetime, pools). It does not qualify options, shared
networks, shared lease coordination or arbitrary rich configurations.

## Partial failure and stop policy

The test persists a second pool range, activates A, then gives B an invalid
local lifetime type. Native `config-reload` rejects parsing without interrupting
database sessions. B retains its prior active state and SQL retains the desired
new state. A and B disagree, so convergence must fail.

The shared deployment workflow catches activation errors, automatically latches
a write hold and rejects a subsequent mutation before dispatch. An explicit
convergence attempt also fails. Snapshot equality proves the blocked operation
made no SQL change. This automatic policy covers only callers using the tested
workflow. The hook itself does not track fleet state; production operators must
hold every other mutation ingress path too.

## Operator recovery

1. Keep the global write hold. Record each process's actual active state and
   SQL intent; do not overwrite SQL to disguise a failed consumer.
2. Diagnose and correct B's local configuration. In the qualification the
   operator restores a valid lifetime, saves the file and explicitly reloads B.
3. Verify both consumers' active managed fields match intended SQL state and
   verify SQL snapshot unchanged. Check admission, endpoints and process roles.
4. Perform DORA/lease checks independently for A and B.
5. Release the write hold only through explicit operator verification. A
   successful reload alone does not release it.

Stop subsequent writes for any failed/unknown command, mismatched active state,
incomplete fleet inventory, changed SQL snapshot, unverified fencing, or unknown
transaction outcome. Do not automatically retry mutation or activation, roll
back persisted state, or promote another writer to resolve activation failure.

See [deployment](designated-writer-deployment.md),
[fencing](writer-fencing-runbook.md) and the
[native activation design](runtime-activation-design.md).
