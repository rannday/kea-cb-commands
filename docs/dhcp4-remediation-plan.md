# DHCPv4 remediation plan after M31

Production readiness remains **NO-GO**. Complete selected DHCPv4 remediation
before starting DHCPv6. The [qualification](dhcp4-qualification.md) inventories
41 endpoints, reconciles 74 commercial operations and classifies twelve safety
findings. This plan does not authorize any new mutation or alias.

Priorities reflect safety and operator value. Complexity is relative:
small means bounded tooling/docs; medium means one family with both-engine
fixtures; large means cross-family semantics, recovery or external coordination.
All implementation milestones need their own review and acceptance.

## M32 result and recommended M33

M32's [scoped-option qualification](scoped-option-mutation-safety.md) resolves
the scoped reconstruction question negatively: parent reads cannot reveal child
option-server links. No existing mutations are enabled. Its authorized acceptance
allows PASS with a conclusive negative result and passing regressions; the older
recommendation to report PARTIAL merely because no mutation is unlocked is
superseded. See [execution evidence](../build/milestone32/checks.md).

M33 should qualify F1 for global records separately and design a supported scoped
association read facility, unique target identity and exact class predicates.
Retain D1's exclusion/recovery requirements. A read facility or upstream proposal
is a prerequisite to reconsidering B3; sole parent ownership alone is insufficient.
Do not begin DHCPv6 or authorize implementation from this recommendation.

## Historical M31 recommendation for M32

Keep the production command surface unchanged. First qualify read-only assigned
association reconstruction and exact scoped-option identity; then implement
only the narrowly proven existing-record operations. If evidence is insufficient,
retain refusal and report PARTIAL. Do not make unrestricted class deletion,
server deletion, aliases or DHCPv6 prerequisites for M32 PASS.

| Order / finding | Commands and current restriction | Evidence and implementation needed | Concurrency / safety | Tests and expected compatibility | Complexity / upstream |
| --- | --- | --- | --- | --- | --- |
| 1 — F1, C1–C3 | Global, definition and global-option SET/DEL refuse existing rows | Probe ALL + getAllServers4 + ONE(each tag), join native SQL IDs, compare independently queried links; test overridden common, mixed, hidden, multi-tag and unassigned cases. Document where reconstruction fails; do not merge values merely by name | Stable inventory under exclusive writer; no orphan completeness claim from assigned rows | Both engines/MT modes, unchanged SQL/audit for refusal, row-level association proof. Evidence work alone changes no functional counts | Medium; public APIs available, no upstream dependency for the probe |
| 2 — B3 | Scoped option SET/DEL fresh only | Prove lossless descriptor round-trip and exact code/space/class identity; qualify SQL LIKE wildcard behavior. Permit only sole-associated parent and globally unique pool range; retain ANY native overload with explicit preflight | Exclude external writers; refuse uncertain option links, wildcard identities and range collisions; preserve parent membership/children | Hidden/common links, multiple class identities, empty filter, wildcard names, unrelated options, missing parent/option, packet precedence, restart, SQL/audit equality on refusals. At most three commercial SET partials improve; three DELs move from missing to partial only when real deletes work | Medium/large; no upstream change for bounded unique ranges |
| 3 — B2 | Shared-network SET/DEL fresh only | Prove empty ANY membership, sole exact association, lossless supported native fields and no lost children; construct existing native object rather than minimal replacement | Exclusive writer and stable child inventory; reject membership/rich unsupported objects | Empty network update/delete, member/common/hidden refusal, unrelated network/options preserved, missing delete, restart. Could improve network SET and move DEL missing to partial | Medium; existing APIs, no mandatory upstream change |
| 4 — B1 | Subnet SET supports bounded standalone projection | Expand only a field whose native parsing, serialization, inherited semantics and pool preservation can be established; keep omitted-value preservation contract | Exact sole association; no membership or destructive child replacement; all preflight assumptions retained | Rich round-trip/omission/explicit-empty, class/options restrictions, DORA/leases/boot/timers and restart. Improves existing partial subnet analogue without a new command | Medium per bounded field group; public APIs available |
| 5 — warning policy | Python tests/tooling contain 3,749 warnings | Pin baseline tool/config and compare normalized diagnostics for changed files; annotate shared transport/JSON and process boundaries first | Preserve checks and cleanup behavior; no broad suppressions | Zero type errors, no new actionable warnings, unit/tooling and affected private integration tests. No compatibility-count change | Small for policy, gradual medium cleanup; no upstream dependency |

M32 should start with orders 1–2. Orders 3–4 are separately reviewable follow-on
work; do not expand the milestone merely to unlock counts. Registration stays
at 41 unless a later explicitly approved feature requires otherwise.

## Work requiring stronger local safeguards

| Finding / commands | Current restriction | Required evidence and implementation | Safety and concurrency assumptions | Tests / compatibility effect | Complexity / upstream |
| --- | --- | --- | --- | --- | --- |
| B4, C5 — client-class SET/DEL | Existing changes, deletes and reorder refused | Lossless ordinary-class readback; exclude templates/local definitions; preserve options, links, order and dependencies. Enumerate textual consumers in every scope. Start same-position update using empty predecessor; postpone deletion/reorder until complete consumers are proven | Exclusive writer plus fresh complete consumer inventory; no activation/retry; reject orphan-option evidence gaps | Multiple selectors/common/hidden/unassigned, required/additional classes, classes in options/subnets/pools/networks, wildcard identities, rich child preservation, order after restart, real matching/nonmatching OFFER/ACK. Could improve SET; DEL moves missing to partial only after safe removal works | Large; public same-position API exists, orphan evidence may need added facility |
| C1 — global SET/DEL | Existing selected row refused; 15 scalar creation subset | Complete links and selected fallback identity; per-name type/range and cross-parameter validation; native whole-row mutation only under exclusive row ownership | Strong local serialized inventory; no shared-row detachment inference | Common override, mixed tags, compound rejection, conflicting timers, explicit activation, SQL/audit preservation. Improves partial SET, may unlock bounded DEL | Medium/large; no proven mandatory upstream change |
| C2 — definition SET/DEL | Existing mutation refused despite native force=false | Complete all-scope users, option encoding compatibility and links. Do not treat global-only dependency check as complete; do not cascade | Stable dependency graph under one excluded-writer regime | Global/network/subnet/pool/class users, dependent payload decoding and packet evidence. Could unlock bounded DEL and improve SET | Large; native check incomplete, additional read-only facility may suffice |
| C3 — global-option SET/DEL | Existing mutation refused | Complete links, exact class-list identity, descriptor preservation and selected-definition consistency | Stable row/definition inventory; reject LIKE wildcard ambiguity | Multiple class filters, hidden/common/unassigned links, all option types and precedence. Could improve SET and unlock bounded DEL | Medium/large; no proven mandatory upstream change |
| C4 — server DEL | Existing deletion refused | Database-wide orphan inventory covering globals, definitions, options and affected dependencies; prove purge cannot remove unrelated configuration, or obtain targeted native deletion without global purge | Exclude every mutation authority throughout evidence/write; complete no-orphan precondition must remain true | Preexisting unrelated orphans, shared/common links, unknown tag, no audit change on refusal. Only a real safe deletion improves coverage | Large; native current purge is demonstrated; targeted API desirable but not yet proven necessary for a restricted no-orphan case |

Diagnostic SQL belongs only in disposable/read-only tooling. Any deployment
evidence facility requires explicit design for snapshot consistency, permissions,
provenance, secret handling and validity. It must never become direct SQL writes
inside the hook or an old evidence file that authorizes mutation indefinitely.

## Work requiring architectural safeguards

| Finding | Required work | Acceptance / compatibility | Complexity / upstream |
| --- | --- | --- | --- |
| D1 — all supported/preflight mutations | Enforce exclusive writer ownership over every process, credential and restart authority; serialize administrative/schema changes. Define failover fencing and uncertain-write hold before broader deployment | Competing writer prevented, stale replacement cannot restart, fresh reconciliation required before resuming; do not infer fencing from allow-mutations. Functional counts unchanged | Large; deployment architecture or upstream atomic revisions, no distributed control plane in M31 |
| M22 exactness | Approved per-selector intent, complete persisted inventory, normalized defaults/inheritance/options/classes with meaningful list order, independently observed consumer configuration | Prove real full-state CONVERGED, distinguish pending/partial activation, preserve UNKNOWN_COMMIT and durable recovery holds; prove writerless promotion/resumption | Large; consistent read facility and deployment-specific ownership needed |
| Activation evidence | Bind explicit activation to consumer instance/selector and compare active semantic state and packet behavior | Partial fleet activation cannot be reported as convergence; retain lease separation and no automatic retry | Large; no new production command assumed |
| Native failure recovery | Qualify upstream SQL transaction cleanup and controlled recovery after ambiguous failures in a separately authorized milestone | Demonstrate safe reconciliation and operator resumption; no destructive outage injection in M31/M32 | Large; upstream cooperation may be needed |

## Work requiring upstream support

E1 is the demonstrated API identity limitation: arbitrary pool-option writes and
deletes need a public overload carrying parent subnet ID or an unambiguous pool
ID, with equivalent PostgreSQL/MariaDB semantics. Existing range-only APIs can
remain usable under backend-wide uniqueness. Test identical ranges in separate
subnets and associations; never bypass the limitation with production SQL.
This is medium/large upstream work and would broaden safe scoped-option
coverage rather than automatically establish exact commercial compatibility.

Native compare-and-swap revisions or a transaction API spanning native reads and
writes would support multiple independent writers. Audit cursors/timestamps do
not provide this. This is a desirable large upstream enhancement for concurrent
deployment, while externally enforced exclusivity is a different viable design.
Do not count every current D1 restriction as proof that upstream change is the
only solution.

Template-preserving class readback and complete unassigned option/dependency
enumeration are upstream enhancement candidates. First prove whether supported
public alternatives or a trustworthy read-only evidence facility suffice; retain
C/F classifications until then.

## Commercial contract work and production hardening

Read-only server GET-ALL is the first exact-alias research candidate, followed
by server GET. Establish empty/missing/error result envelopes, reserved tags,
response text and validation behavior from authoritative evidence. Option and
class read aliases additionally require commercial selector/metadata serializers.
Class SET requires correction of contradictory public schemas; compound global
GET requires a per-name representation decision and success-text clarification.
No alias should simply forward a project handler with a different contract.

Before production, complete credential/privilege hardening (especially MariaDB
consumer DML), authenticated control channels, operational packaging/upgrade
qualification, upstream failure recovery, full reconciliation and enforceable
writer replacement. Qualification PASS does not waive any blocker.

Start DHCPv6 only after the selected M32 evidence work, bounded mutation policy
and recovery ownership design have been reviewed. Reusing an unresolved IPv4
association/concurrency model in a second protocol would multiply the same
uncertainty without improving deployment safety.
