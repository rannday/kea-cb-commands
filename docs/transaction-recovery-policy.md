# Transaction failure and recovery policy

## Status and evidence

This is the proposed operator/caller policy for existing command semantics.
It adds no retry, transaction manager or new response fields. Read
[command contracts](commands.md), [backend behavior](backend-behavior.md), and
[retained crash evidence](isc-report-evidence.md) alongside it.

Native SQL owns atomicity. The historical blocked-precommit interruption cases
verified rollback and successful operation after restart. They do not establish
rollback for every timeout or lost response. A separate historical case lost the
HTTP caller and subsequently committed; it did not simulate losing a SQL COMMIT
acknowledgement. No debugger stack or hook-free reproducer establishes the causal
chain for the observed aborts.

## Outcome classification

| Outcome | Safe statement | Retry rule |
| --- | --- | --- |
| Rejected before mutation | A known validation/admission branch made no mutation attempt for this request. A caller cannot infer this from every generic result 1. | Correct the request/policy and submit a new request under writer ownership. |
| Set/delete success acknowledged | The native mutation returned successfully; the reply describes persistence, not activation, CAS or exactly-once execution. | Do not retry a successful operation. Verify stored state and activate explicitly. |
| Delete absent (result 3) | No selected object was deleted by that invocation. This is not proof a prior timed-out request never ran. | Reconcile prior uncertainty separately. |
| Confirmed rollback | Independent evidence establishes that the relevant transaction failed before commit and its changes are absent. | An explicitly authorized new attempt may follow after connection health and ownership are restored. |
| Unknown | Transport timeout/disconnect, process death, generic native mutation failure, or lost commit acknowledgement may leave an uncertain outcome. | Prohibit automatic mutation retry until reconciliation. |
| State reconciled | Stored state is compared with intended and previous state under exclusive ownership. Equality can establish convergence, not exactly-once authorship. | Record the decision; any compensating write is a new reviewed operation. |

The existing generic write/delete failures in [commands.cc](../src/commands.cc)
already instruct reconciliation. Preserve these error semantics. A command
timeout does not cancel synchronous work inside Kea. Monitoring success, process
survival or a response from another instance is not transaction evidence.

## Before submitting a change

The management workflow should retain a sanitized, access-controlled record of
target database identity, writer, tag, ID and prefix, previous canonical state,
complete intended state (including effective pools), request time and observed
response. Do not use the set reply's request echo as full stored state when pools
were omitted. The record is external operational intent, not a native idempotency
token or commit log. This journal is a proposed follow-up, not currently supplied.

Permit one change window per database and exclude bypass writers. An operation ID
in an external record does not make Kea deduplicate commands.

## Reconciliation procedure

1. Hold new mutations for the entire database, regardless of tag. Retain the
   failed request and response/transport evidence. Do not repeat the command.
2. Establish exclusive ownership and that the previous request is no longer in
   flight. Fence an old writer before using a replacement. Coordinate with the
   database operator when session/transaction status cannot otherwise be proven.
3. Restore access and read through native APIs. Compare both ID and prefix,
   effective pools, exact associations and any richer object fields relevant to
   the change. Public get/list select visible objects; their tag field represents
   the requested selector, not a complete association inventory. They cannot
   prove the absence of an unassigned/conflicting row in every case.
4. If existing commands cannot resolve ownership or hidden-state ambiguity, stop
   for authorized native-API inspection. A future read-only reconciliation path
   is needed; do not bypass the architecture with SQL in this hook.
5. If state equals the desired state, record convergence and validate before
   activation. If baseline plus independent failure evidence confirms rollback,
   record failure. If baseline alone is observed, do not infer an exact history.
   Divergent or ambiguous state requires operator review before any new write.
6. Inspect audit evidence as supporting history where available. Timestamps,
   subnet fields and audit entries alone are not an operation-specific CAS token
   or proof that this request committed exactly once.
7. Resume writes only after recording the resolution and checking active state on
   every serving instance. A compensation is a separate mutation with its own
   uncertainty and activation window.

Do not delete leases or reuse a subnet identity automatically during recovery.
Native subnet deletion intentionally preserves leases; pool/subnet changes must
account for outstanding leases and allocation compatibility.

## Process termination and restart

Source inspection confirms that native PostgreSQL/MySQL transaction destructors
can let rollback exceptions escape implicitly nonthrowing destructors. Such an
escape invokes `std::terminate()`; it does not require another active exception.
Throwing during unwinding adds a second termination condition. Hook callout
handlers cannot catch termination inside that cleanup path. See
[investigation and versioned source references](sql-transaction-investigation.md).

Supervise the administrative writer with bounded restart/backoff and preserve
diagnostics. After restart, retain a write hold until ownership, hook registration,
a real native read and reconciliation have been checked. The current hook does
not persist this hold itself; deployment must enforce it. A diagnostic pool check
is insufficient. Do not automatically resubmit interrupted mutations.

Historical restart commands restored functionality, but did not measure supervised
RTO or prove uninterrupted DHCP. Other processes are independent; their ongoing
packet availability requires deployment-specific testing. Restarting a consumer
can read current SQL and activate pending configuration, so coordinate recovery
with the [activation policy](runtime-activation-design.md). Restart alone is not
a guarantee that an old active configuration will be preserved.

## What can improve locally

The hook can enforce a local mutation role, reject unsafe input, keep explicit
persistence-only responses, and provide carefully designed read-only evidence.
An operator/controller can serialize, journal, reconcile and verify activation.
Neither can guarantee recovery from a native destructor termination, turn a lost
acknowledgement into a known failure, or provide exactly-once writes without an
appropriate underlying protocol. No validated native cleanup fix is claimed.
