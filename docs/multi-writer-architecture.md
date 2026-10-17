# Exclusive-writer architecture

## Decision

Use **one designated administrative Kea DHCPv4 process per physical configuration
database**, with enforced ingress and deployment fencing. Prefer a process that
serves no DHCP packets. Serving instances consume configuration and omit this
hook unless they need its read commands. Current development code implements
default-deny local admission with `allow-mutations`; Milestone 20.1 qualified
SQL/DHCP admission on both backends and threading modes. See
[migration](mutation-admission.md), the [roadmap](development-roadmap.md), and the
[controlled deployment](designated-writer-deployment.md).

This is static ownership with controlled manual handover, not distributed leader
election. All clients submit mutations to that process, whose synchronous main
thread serializes command execution. Serialize the whole change window through
activation too, so later writes do not invalidate verification of earlier intent.
One writer is a necessary control; it does not provide exactly-once requests.

Evidence: [subnet4.cc](../src/subnet4.cc) performs separate native preflight and
write calls; [concurrency tests](../tests/concurrency.py) demonstrate lost updates
and collisions across tags. A mutex inside one hook or a tag per daemon does not
coordinate independent processes.

## Alternatives

| Approach | Correctness / external writers / tags | Backend, crash and disconnect behavior | Complexity, tests and native-API fit |
| --- | --- | --- | --- |
| A. Designated writer, documentation alone | Safe only if every writer follows policy; cannot prevent a second deployment. Tags do not fence. | Backend-neutral; a replacement can overlap an old process unless explicitly fenced. | Simple but insufficient enforcement. Native APIs preserved. |
| A. Enforced static designated writer (**recommended**) | One reachable mutation endpoint, restricted ownership of configurations/credentials and explicit exclusion of other writers. Consumers omit mutations. | Same policy for both engines. Stop/fence old owner and finish reconciliation before promotion; no automatic lease expiry. Administrative process death still leaves outcome uncertainty. | Moderate operational work, small hook admission change. Test denied mutations, two-process role topology, fenced handover and active consumers without DB fault injection. |
| B. DB advisory lock | Cooperative only: every writer must acquire the same lock regardless of tag. Ordinary native writes do not automatically honor it. | PostgreSQL and MariaDB have different connection-owned advisory APIs. Losing a separate coordination connection can release ownership while a native backend write continues. A DB failover requires new fencing analysis. | No suitable public coordination primitive was found in the inspected native pool interface. Direct lock SQL in this hook violates scope. A separate connection is not a demonstrated safe workaround. High maintenance and disconnect testing burden. |
| C. External configuration controller | A single fenced controller can serialize requests, retain intent and coordinate activation. Multiple controllers still require fencing; unmanaged native writers bypass it. | Backend-neutral when it calls this hook. Controller timeout/death does not cancel a Kea request. Needs reconciliation and durable workflow state. | Useful later; adds a service, journal, deployment and recovery duties. Fits native/no-direct-SQL architecture, but is not required as a new product dependency now. |
| D. Host lock / distributed lease | A host lock covers cooperating processes on one host only. A lease without fencing can expire while an old writer continues. Neither creates tag namespaces. | Host locks release on process death; distributed partitions and stale owners require stronger guarantees. | A host lock may assist single-host deployment admission, but is not a portable multi-host solution. Do not add custom distributed locking. |
| D. Separate databases | Truly separate stores remove shared write contention; tags in one store do not. Synchronizing related content becomes a new responsibility. | Both engines possible, but backup, audit, rollout and recovery multiply. | Appropriate only for genuinely independent administrative domains. Not a transparent fix for one shared configuration. |

## Why advisory locks are not an immediate solution

PostgreSQL offers session and transaction advisory locks. Session ownership ends
with the owning session; transaction locks end with that transaction. MariaDB
`GET_LOCK` is connection-owned and is not released by commit. These are
application-cooperative mechanisms, not locks automatically taken by Kea's CRUD.
See the official [PostgreSQL 15 locking documentation](https://www.postgresql.org/docs/15/explicit-locking.html#ADVISORY-LOCKS)
and [MariaDB GET_LOCK documentation](https://github.com/mariadb-corporation/mariadb-docs/blob/main/server/reference/sql-functions/secondary-functions/miscellaneous-functions/get_lock.md).
This milestone did not execute either locking API.

The inspected [Kea 3.2.1 public pool API](https://github.com/isc-projects/kea/blob/Kea-3.2.1/src/lib/dhcpsrv/config_backend_pool_dhcp4.h)
provides CRUD and audit access, not a hook-owned transaction spanning preflight,
lock and mutation. Native backend transactions are internal. A lock on an
unrelated session cannot establish that the actual native writer has stopped
when that session disappears. Solving that requires verified fencing, not just
catching an error or retaining a local mutex. No lock implementation is proposed.

## Enforcing the recommended boundary

1. Inventory the physical database, credentials, Kea processes, management
   endpoints and every other tool able to mutate configuration. Treat server tags
   as data visibility, never as ownership boundaries.
2. Assign one administrative writer identity. Restrict its control endpoint to
   the authorized management path and protect its configuration. Avoid multiple
   client requests in flight at the workflow layer even though native commands
   execute serially.
3. Omit this hook on consumers that do not need it. For consumers needing reads,
   omit `allow-mutations` or set false; set/delete reject before native access.
   Explicit true is reserved for the designated externally fenced owner. This
   guard cannot stop another instance configured true or any bypass writer.
4. Restrict SQL privileges where compatible, but do not claim uniform read-only
   grants: MariaDB prepares write statements even for tested read operations.
   Revoking writes is not yet a qualified consumer configuration. A role switch
   does not constrain other hooks, direct SQL clients or administrators.
5. Do not automatically promote a replacement. Block new requests, fence the old
   endpoint/process, establish no old write remains in flight, reconcile SQL,
   then explicitly enable the replacement. If fencing cannot be established,
   leave mutations unavailable. An inaccessible host is not proof of termination.

The dedicated non-serving topology follows existing test use of administrative
Kea instances, but has not been production-qualified. Test that it has no packet
listeners and that its failure leaves consumer processes and existing lease
service available. It reduces the observed mutation-path blast radius; consumers
still use native SQL on fetch/startup and are not proven immune to SQL failures.

## Failure boundaries and implementation limits

| Event | Required response |
| --- | --- |
| Writer exits or caller loses response | Hold all writes for that database; follow [recovery policy](transaction-recovery-policy.md). Restart is not a retry. |
| Database unavailable | Reject/record failures; monitoring cannot guarantee the next write succeeds. Do not move ownership merely because a connection failed. |
| Unauthorized second writer discovered | Stop the change window, fence it and reconcile. Serialized requests through the designated endpoint do not protect against bypass writers. |
| Activation succeeds on only some consumers | Keep writer ownership; stop subsequent changes and resolve the rollout. See [activation design](runtime-activation-design.md). |
| Writer configuration restored from backup | Verify role and ownership before admitting requests; do not boot multiple enabled copies. |

The hook remains a native API adapter. It should not acquire direct SQL locks,
implement a custom transaction manager, become a lease-based leader, or perform
automatic activation. Admission is a local policy guard; deployment fencing and
operator/controller workflow provide the cross-process boundary. Both packet
threading modes must obey the same policy.
