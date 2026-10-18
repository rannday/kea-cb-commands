# Commercial parity gap analysis

## M26 implementation update

M26 is **PARTIAL**. Eight project-specific option callouts add selected-view
list/get and create-only definitions/global options. Existing option updates
and deletes are refused: native readback hides other associations, and native
definition dependency checks do not establish safety across all scopes. Missing
deletes return an empty result without invoking native deletion. No force or
cascade is offered. See [contracts](commands.md) for exact schemas.

Native option parsers and serializers preserve CSV, binary, numeric, string,
address, array and record payloads. Encoding consults selected SQL definitions
and native built-ins, excluding stale process-global runtime definitions.
Returned server tags are observed selector metadata, with
`associations-complete: false`; they never authorize an existing mutation.

Current functional counts: **3 implemented, 15 partial, 56 missing** of 74;
DHCPv4: 3/15/18, DHCPv6: 0/0/38. The six new partial analogues are two lists,
two gets and two create-only sets. Both option delete operations remain missing
functional equivalents despite their safe refusal endpoints. Exact commercial
compatibility remains **0 implemented, 0 partial, 74 missing**; no remote names
are registered. The M25 counts below are historical.


## M25 implementation update

M25 is **PARTIAL**: native server list/get/create-update and a 15-name scalar
global read/create subset are implemented under eight project-specific callouts,
including fail-closed existing-server/global delete endpoints. See [exact contracts](commands.md).
No commercial command is registered. Commercial object envelopes, batches,
metadata, description omission and unspecified errors remain unverified.

Native `getAllServers4/getServer4/createUpdateServer4` and
`getAllGlobalParameters4/getGlobalParameter4/createUpdateGlobalParameter4`
operate through the existing pool and selector helpers. No private manager or
SQL abstraction was added. Existing-server delete is excluded: both native
drivers' `deleteServer4` call `purgeUnassignedConfig`, which can delete
unrelated orphan globals/options/definitions. Native read views cannot prove
those sets empty. Tests verify refusal preserves SQL and associations; native
destructive cascade execution is not claimed.

Existing global update/delete is also excluded. Native global queries filter
associations and collapse rows: a shared row can appear to belong to just one
tag, and a mixed all/named association can appear common-only. Native mutations
affect whole rows. Without complete association evidence, set only creates when
the selected view is empty; delete only reports a missing value. Disposable SQL
tests construct both shared cases and verify refusal without SQL/audit changes.
Returned tags describe the selected view, not complete row ownership.

Compound globals remain unresolved (U2). `StampedValue::getValue` supports
scalars; map serialization fails, while null/list construction fails. Native
controller dotted-name expansion and special list decoding need separate
per-name contracts. M25 rejects these inputs rather than changing their types.
Full scalar coverage and cross-parameter activation validation also remain open.

Functional counts are 3 implemented, 9 partial, 62 missing out of 74;
exact commercial counts remain 0 implemented, 0 partial, 74 missing.
Six partials are historical subnet analogues; three are restricted globals.
Server/global delete remain missing despite their refusal endpoints. M22 remains PARTIAL;
durable recovery tooling, external fencing and upstream SQL cleanup are unchanged.


## Decision

**M23 is PARTIAL.** All 74 documented cb_cmds command names are inventoried
against Kea 3.2.1. None is implemented under its commercial name. Public
documentation conflicts and incomplete error contracts prevent complete
behavioral specification; they must remain visible implementation gates.

Long-term direction: implement the documented `remote-*` interface independently
using public native APIs, alongside existing `cb-*` contracts. Deliver family
features in the [revised roadmap](development-roadmap.md), while deployment
hardening continues independently. No production command, registration,
transaction behavior or safety check changes in this milestone.

## M23 starting point (historical)

The following inventory records the pre-M24/M25 baseline. The M25 update above
supersedes its server/global and registration counts.

Reviewed production files: `src/diagnostic.cc`, `commands.cc/.h`,
`arguments.cc/.h`, `subnet4.cc/.h` and CMake registration/build probes.
The current artifact is one C++14 MODULE loaded only into `kea-dhcp4`.
`diagnostic.cc:52` checks AF_INET and executable identity; lines 71 onward
register exactly five commands.

| Implemented area | Actual scope | Commercial gap |
| --- | --- | --- |
| Diagnostic | Pool API accessibility and local mutation admission | No commercial analogue; not connectivity/ownership evidence |
| cb-subnet4-list | Native full subnet serialization from sole backend; rejects shared-network subnets | Commercial list is a summary with association metadata and explicit selectors |
| cb-subnet4-get | One ID or canonical v4 prefix, optional tag | Different request/response; no full shared-network/inheritance contract |
| cb-subnet4-set | One minimal standalone subnet, optional basic address pools | Full replacement, richer fields, associations and commercial envelopes absent |
| cb-subnet4-del | Explicit tag, single exact association, preserve-leases true | Commercial deletion has database-wide identity and no tag selector |
| Pools | Basic ranges inside subnet SET; omission preserves, supplied list replaces, empty clears | No standalone commercial pool CRUD; full subnet and scoped option functionality missing |
| DHCPv6 | No load support, manager access, handlers or packet fixture | All 38 commands missing |
| Other v4 families | No handlers | Servers/globals/definitions/options/networks/classes missing |

These limits are intentional safety boundaries, not accidentally omitted parsing.
`subnet4.cc:92` requires one backend; :117 guards exact delete association;
:188 refuses association changes; :192 rejects richer objects; :219 calls
native createUpdateSubnet4. Listing rejects shared-network objects at :48.
Do not remove these restrictions from the old commands to implement parity.

Existing fixtures to extend: `tests/postgresql.py`, `mysql.py`,
`mutation.py`, `lifecycle.py`, `dhcp.py`, `packet_namespace.py`,
`designated_writer.py`, `recovery.py`, `reconciliation.py`.
They already distinguish persisted SQL, active runtime and leases; reuse
process/database/transport/isolation machinery instead of a parallel harness.

Reviewed architectural/contract/history material includes architecture,
commands, development history/roadmap, production readiness, multi-writer,
transaction recovery, activation, admission, designated-writer, fencing, fleet
activation, reconciliation and operator recovery documents, plus M20.1–M22 checks.
Historical results are evidence of those runs, not newly executed M23 tests.

## M20–M22: qualified safety and remaining gaps

- M20.1: default-deny admission and strict six-test non-interruption acceptance.
- M21: PASS **within supervised same-host/no-retired-writer-restart boundary**;
  24 recorded DHCP DORA exchanges. Consumer admission is not external fencing.
- M22: **PARTIAL / production NO-GO** per `build/milestone22/checks.md:3`.
  PostgreSQL 18.6 and MariaDB 12.3.3 LTS, each packet MT off/on, passed bounded
  safety checks; all four exact-recovery cells remain PARTIAL. Sixteen DORA
  exchanges were recorded in that run, not rerun here.
- M22 canonical SHA-256 retains underlying evidence; selector associations and
  independent consumer config-get/status observations exist. SQL/native/active
  snapshots are not atomic and do not cover the entire meaningful configuration.
- The real collector always marks evidence incomplete; it cannot authorize
  mutation resumption or promotion. Synthetic complete unit observations exercise
  gate logic, not real deployment completeness.
- Durable local holds fail closed for missing/invalid journals and workflow
  restart, invalidate prior convergence, and require fresh evidence. They are
  not cross-process locks, hook enforcement, or distributed fencing.
- Successful complete-evidence replacement and full operator resumption remain
  unqualified; a writerless reconciliation-to-promotion transition is missing.
  M21's controlled replacement does not close these M22 gaps.
- PostgreSQL consumers used SELECT/read-only transactions. Native MariaDB
  consumers needed CRUD for statement preparation; writers additionally needed
  audit EXECUTE. Diagnostic SELECT-only access differs from daemon privileges.
  Absolute per-object minimum privileges remain unqualified.

The full gap cannot be cleared by new CRUD commands or a manual acknowledgement.
Feature fixtures may exercise isolated controlled writes under their existing
authorization; operational tooling must retain holds when evidence is incomplete.

## Public contract uncertainties

Each ID applies to matching rows in the [74-command matrix](compatibility-matrix.md).
“Documented” means public source says so; “source-verified” refers only to open
native Kea behavior; “unresolved” means no commercial behavior established.

| ID | Evidence and unresolved behavior | Resolution before compatibility claim |
| --- | --- | --- |
| U1 | Public descriptors show success examples, but do not enumerate per-command malformed/not-found/backend-error numeric result, text, arguments, validation precedence or all serialization defaults. No commercial runtime was inspected. | Build a per-command negative contract ledger; seek public ISC clarification for unspecified envelopes. Test chosen documented behavior without claiming unverified byte-for-byte equivalence. |
| U2 | ARM global GET says scalar only; API comments also describe scalar lists/maps and dotted names. Native code supports bounded reconstruction, which does not settle command encoding/output. | Enumerate versioned supported globals/types, map flattening/list encoding, GET/GET-ALL representation, errors and partial SET semantics; resolve public contract discrepancy. |
| U3 | Class SET API syntax uses client-class singular and nested follow-class-name; ARM uses client-classes plural and top-level follow-class-name. | Obtain public authoritative correction. Preserve both sources in fixtures; do not silently choose an alias or register the commercial name while unresolved. |
| U4 | Class SET descriptor success text refers to a shared network; class GET comment similarly mislabels the object. | Clarify exact success text and response schema independently of native serialization. |
| U5 | Option-definition DEL comments mention name/code, syntax/ARM use code/space; force is shown inside the definition map. Native delete does not itself establish the commercial dependency scan. | Qualify code/space identity and force placement, enumerate dependent options across all scopes/classes and verify force behavior on both backends. |
| U6 | Some required/default fields and secondary effects are incomplete in examples: server description omission, class cascades, missing scope objects and pool-parent ambiguity. | Negative/native fixtures and public clarification for commercial responses; explicit dependency/deletion ledger per family. |
| U7 | Option class tags are identity in 3.2.1; omission has different GET/SET/DEL meaning. Exact ordering/normalization and indeterminate multi-match behavior must not be invented. | Test omitted, empty, multiple lists, permutations and multiple matching options; preserve documented indeterminacy rather than claim unique GET. |
| U8 | ARM absent remote defaults to first backend; project rejects multiple; native pool reads first nonempty and writes require exactly one. Multi-backend and unmatched selection errors are not a complete commercial contract. | Qualify unambiguous one-backend requests first. Publish the supported safety restriction and defer expanded routing; no database aggregation. |

Supporting native evidence for U2:
[StampedValue](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/lib/cc/stamped_value.cc#L160)
accepts scalar or a map with at most one scalar member, not direct list/nested map.
[Controller translation](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/lib/dhcpsrv/cb_ctl_dhcp.h#L46)
splits dotted names, rebuilds maps and JSON-decodes recognized global list strings.
[IPv4 list names](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/lib/dhcpsrv/parsers/simple_parser4.cc#L153)
and [IPv6 list names](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/lib/dhcpsrv/parsers/simple_parser6.cc#L150)
enable host-reservation-identifiers; interfaces-config.interfaces is explicitly
not yet supported there. Therefore arbitrary maps/lists are not native CB support.

No commercial source/binary is needed or authorized to resolve these questions.
Until a public resolution exists, the affected commands remain qualified as
documented subsets or deferred, and final complete parity remains PARTIAL.

## Native API capability versus compatibility

Public family headers provide native reads, bulk reads, modified reads, updates,
deletes, server records and recent audit entries for both families. DHCPv6 adds
PD pools and PD-option overloads. Candidate calls are listed for every command
in the matrix; these are source mappings, not runtime-tested new handlers.

Native transactions/audit belong to each driver. There is no public transaction
covering arbitrary command preflight plus mutation or a multi-global batch.
Second-precision timestamps and audit cursors are not CAS/revision ownership
tokens; audit is not proof that a timed-out caller rolled back.

[Server-selector documentation](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/lib/dhcpsrv/config_backend_dhcp6.h#L35)
distinguishes ANY, ALL, ONE, MULTIPLE and UNASSIGNED. Method restrictions vary:
singleton globals/definitions/options allow ALL/ONE; bulk readers allow
ALL/ONE/MULTIPLE; scoped options use ANY.
Concrete [PostgreSQL subnet writes](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/hooks/dhcp/pgsql/pgsql_cb_dhcp6.cc#L1054)
reject ANY/UNASSIGNED despite wider abstract selector vocabulary.
Verify concrete PostgreSQL and MariaDB methods rather than relying only on headers.

Shared subnets/networks and class identities cannot be isolated by tag into
independent mutation namespaces. Current ANY conflict checks and explicit
writer ownership remain required. Full serialization needs relationship metadata
and omitted/default/inherited distinctions; toElement alone is insufficient.

Native class ordering also needs care: the PostgreSQL v6 update path keeps an
existing class position when follow_class_name is empty, although a nearby
comment describes appending. Dependency checks and nested definition/option
recreation are concrete backend behavior, not a commercial response contract.

SQL CB support excludes arbitrary local service configuration. Listeners,
control endpoints, hook loading, credentials/backend connections and MT startup
remain local JSON. Reservations/leases belong to other native backend surfaces.
Audit/modified APIs are useful tooling capabilities but have no documented
remote command in the baseline inventory.

## Compatibility policy

Expose remote names **only after each documented command contract is implemented
and qualified**, starting with unambiguous read-only operations where practical.
Keep cb commands as independent compatibility endpoints. Do not alias restricted
cb handlers to remote names, change their errors or silently reinterpret their
replace/preserve rules. Never load both command providers together: duplicate
name registration must fail safely.

Compatibility claims must name Kea version, family, backend, command and any
documented safety restriction. Require request/response schemas and text, object
serialization, absence/defaults, selector metadata, create/replace/delete,
dependency effects, error/not-found behavior and explicit persistence/activation
separation. Default-deny admission remains an intentional policy layer; tests
must distinguish admission denial from an admitted command's contract.

Where contract evidence remains incomplete, document the subset and limitation.
Do not advertise full cb_cmds replacement because native calls compile or
positive-path SQL tests pass.

## Acceptance evidence for implementation families

Every feature milestone in the roadmap inherits this gate:

1. Release C++14 build against the exact pinned installation, warnings as errors,
   native API compile/link probes and matching artifact exports/dependencies.
2. Shared request/response contract fixtures including unknown/wrong fields,
   empty/multiple objects, types/bounds, omitted/null/empty distinctions, result
   codes/text, not-found, native exceptions and admission-before-backend behavior.
3. Real PostgreSQL and MariaDB integration with packet MT off/on: selector
   ALL/ONE/multiple/unassigned where allowed, unexpected associations, same or
   overlapping object attributes under distinct associations, unchanged unrelated
   data, native audit, expected transaction boundaries and ordinary restart.
4. Persisted reconstruction, independent active config-get and explicit pull/
   reload/restart observations. Successful activation response alone is insufficient.
   Test persistence without activation, partial activation and retained leases.
5. Packet evidence where runtime behavior changes allocation or replies:
   v4 DORA/options/classes/shared-network selection; v6 Solicit/Advertise/Request/
   Reply, IA_NA allocation and IA_PD delegation/excluded-prefix behavior as applicable.
   Use private namespaces and ports only; extend existing isolation machinery.
6. For non-packet properties use native readback, diagnostic SQL snapshots only
   in fixtures, relationship metadata, database privilege probes, ordered class
   lists, audit evidence and denied-write immutability. No claim that packets
   prove all persistence/association/dependency behavior.
7. Reuse six-test strict regression, lifecycle, units, packet and admission tests;
   extend test registration deliberately when v6 cases are added (do not retain
   a fixed six-test assertion while adding mandatory tests). Zero required skips.
8. Quality/link checks, relevant static diagnostics and git diff --check, with
   commands/results recorded. Broader upstream suite, sanitizers and production
   load remain explicit unverified areas when not run.

No destructive connection interruption, automatic retry or historical abort
reproduction is required by these gates. Unknown mutation outcomes retain the
hold and require fresh reconciliation before another attempted mutation.

## Remaining production blockers

The upstream SQL transaction cleanup/abort risk remains unresolved; this audit
does not fix or re-test it. Exclusive ownership beyond a trusted same-host
supervisor, remote/container fencing, approved intent, full consistent persisted
and active-state observability, writerless promotion and real evidence-complete
recovery remain open. Credentials/control ingress, least privilege, scale,
availability objectives, packaging/rollback and deployment-specific production
qualification remain separate work.

See [production review](production-readiness-review.md),
[recovery](operator-recovery.md), [fencing](writer-fencing-runbook.md) and
[architecture proposal](command-architecture.md). Production remains NO-GO.
