# DHCPv4 qualification through Milestone 30

M31 qualifies the existing interface against ISC Kea 3.2.1 commit
`1737462bc79276e3269304ea8cd3d1c03400e30d`. It introduces no production
command, alias or mutation capability. Production readiness remains **NO-GO**.
Execution results are recorded in [M31 checks](../build/milestone31/checks.md).
The [remediation plan](dhcp4-remediation-plan.md) separates qualification from
implementation and deployment work.

## Baseline and inventory

The audited baseline is `d376d3a448c5541a9d43c87fd87a8b7a385dc165` on
`main`, with a clean staged/unstaged/untracked baseline. The native source and
installed prefix are `build-repro-clean/source` and
`build-repro-clean/install`. M22–M30 evidence is historical context; M31
execution is fresh evidence.

[Registration](../src/diagnostic.cc) contains **41 commands**: one diagnostic
and ten families of four commands. The table enumerates every name; a DEL
endpoint that only refuses existing records is not implemented deletion.

| Family | LIST | GET | SET | DEL |
| --- | --- | --- | --- | --- |
| Subnet | `cb-subnet4-list` | `cb-subnet4-get` | `cb-subnet4-set` | `cb-subnet4-del` |
| Server | `cb-server4-list` | `cb-server4-get` | `cb-server4-set` | `cb-server4-del` |
| Global parameter | `cb-global-parameter4-list` | `cb-global-parameter4-get` | `cb-global-parameter4-set` | `cb-global-parameter4-del` |
| Option definition | `cb-option-def4-list` | `cb-option-def4-get` | `cb-option-def4-set` | `cb-option-def4-del` |
| Global option | `cb-option4-global-list` | `cb-option4-global-get` | `cb-option4-global-set` | `cb-option4-global-del` |
| Shared network | `cb-shared-network4-list` | `cb-shared-network4-get` | `cb-shared-network4-set` | `cb-shared-network4-del` |
| Network option | `cb-option4-network-list` | `cb-option4-network-get` | `cb-option4-network-set` | `cb-option4-network-del` |
| Subnet option | `cb-option4-subnet-list` | `cb-option4-subnet-get` | `cb-option4-subnet-set` | `cb-option4-subnet-del` |
| Pool option | `cb-option4-pool-list` | `cb-option4-pool-get` | `cb-option4-pool-set` | `cb-option4-pool-del` |
| Client class | `cb-client-class4-list` | `cb-client-class4-get` | `cb-client-class4-set` | `cb-client-class4-del` |

The remaining command is `db-commands-diagnostic`. It accepts absent/empty
arguments, returns hook/API accessibility and admission information, and does
not test database connectivity.

### Request and response profiles

The following profiles apply to each operation in the inventory. Full literal
schemas, result text and field validation remain in [command contracts](commands.md);
[handler callouts](../src/commands.cc) own response envelopes and exception
containment. Requests are a command plus an arguments map; unknown fields are
rejected. Result 0 denotes success, 3 denotes an empty/not-found read or missing
delete, and 1 denotes refusal/error. Native exception details are not exposed.

`tag` below means `server-tag`. Except server records and the unfiltered subnet
list, reads use ALL for `all` or ONE(tag), including common fallback. Responses
retain selectors separately. No family combines independent selector views.

| Family | LIST / GET / DEL identity | SET attributes | Successful arguments / read representation |
| --- | --- | --- | --- |
| Subnet | LIST absent/empty; GET exactly one `id` or canonical IPv4 `subnet`, optional tag; DEL identity plus explicit tag and `preserve-leases:true` | Explicit tag and `subnet4` map: id, subnet, valid-lifetime; optional pools, renew-timer, rebind-timer, next-server, server-hostname, boot-file-name, client-classes, evaluate-additional-classes | LIST/GET native `subnet4` array; GET echoes selector; SET one `subnet4` map; DEL `deleted` count and selector |
| Server | LIST absent/empty; GET/DEL tag | tag and required description; reserved all/any refused | `count`, `servers` array of server-tag/description; sorted by tag; excludes logical all |
| Global parameter | LIST tag; GET/DEL tag/name | tag/name/value in supported scalar subset | `count`, `global-parameters` rows containing name/value/observed server-tags; selector |
| Definition | LIST tag; GET/DEL tag and `option-def:{code,space}` | tag and option-def: name, code, space, type; optional array, record-types, encapsulate, user-context | `count`, `option-defs`, selector, `associations-complete:false`; native definition serialization |
| Global option | LIST tag; GET/DEL tag and `option:{code,space}`, optional client-classes | tag and option: code, space, data; optional name, csv-format, always-send, never-send, client-classes, user-context | `count`, `options`, selector, `associations-complete:false`; native option serialization |
| Shared network | LIST tag; GET/DEL tag/name | tag and shared-network: name; optional valid-lifetime, renew-timer, rebind-timer | `count`, `shared-networks`, selector, incomplete-association marker and `membership-selector:"ANY"`; native properties/options/tags/member subnets |
| Network option | All require tag and `parent:{shared-network-name}`; GET/DEL add option identity | Same parent and option attributes as global option | `count`, `options`, parent, selector, parent-server-tags, `associations-complete:false` |
| Subnet option | All require tag and `parent:{subnet-id}`; GET/DEL add option identity | Same parent and option attributes as global option | Same scoped response profile |
| Pool option | All require tag and `parent:{subnet-id,start,end}`; GET/DEL add option identity | Same parent and option attributes as global option | Same scoped response profile |
| Client class | LIST tag; GET/DEL tag/name | tag, required `follow-class-name:""`, client-class with name and optional test, only-in-additional-list, option-data, next-server, server-hostname, boot-file-name, valid-lifetime, min-valid-lifetime, max-valid-lifetime, user-context | `count`, ordered `client-classes`, selector, incomplete-association marker; native fields/options/dependencies and evaluation metadata |

All successful SET/DEL replies explicitly report `activation-requested:false`.
Missing DEL replies do not call native writes. A missing scoped parent is an
error, rather than an option-not-found reply. No command silently activates SQL.

Pool inputs use start/end or a CIDR `pool`, plus optional client-classes and
evaluate-additional-classes. Omitted supported subnet fields/pools preserve
existing values. Explicit pool lists replace only when preservation checks pass.
Class-restricted existing pools, membership, options and unsupported richer
attributes prevent unsafe replacement. See [subnet capabilities](subnet4-capabilities.md).

Global writes support 15 scalar names: valid-lifetime, min-valid-lifetime,
max-valid-lifetime, renew-timer, rebind-timer, decline-probation-period,
echo-client-id, match-client-id, authoritative, calculate-tee-times, t1-percent,
t2-percent, next-server, server-hostname and boot-file-name. Native list readback
can include unsupported names; this does not authorize their mutation.

Option codes are 1–254; spaces must pass the DHCPv4 contract. Native definition
and option parsers validate types and encoding against selected SQL definitions
and native built-ins. Classes use native ClientClassDefParser/expression parsing,
require earlier visible dependencies and reject reserved/built-in names,
templates, local definitions, unsupported fields and non-append positioning.
Class names are database-wide identities; selector tags are not namespaces.

### Native APIs, operation support and proof

All APIs below are DHCPv4 native pool calls, resolved per invocation through
one configured backend. Read-only operations need no mutation admission.
Every SET/DEL, including a missing DEL, first requires explicit
`allow-mutations:true`. Admission is not fencing.

| Family / handler | Native reads | Native writes actually allowed | Proof fixtures / exclusions |
| --- | --- | --- | --- |
| Subnet / [subnet4](../src/subnet4.cc), [arguments](../src/arguments.cc) | getAllSubnets4, getSubnet4 by ID/prefix; ANY conflict/association checks | createUpdateSubnet4 for bounded create/update; deleteSubnet4 for one exact association, preserving leases | [mutation](../tests/mutation.py), [lifecycle](../tests/lifecycle.py), [DHCP](../tests/dhcp.py); SET excludes unsafe rich replacements; DEL permits rich standalone objects under exact-association/lease-preservation guards |
| Server / [records4](../src/records4.cc) | getAllServers4, getServer4 | createUpdateServer4 create or description replacement | [records4](../tests/records4.py); existing delete refused |
| Globals / records4 | getAllGlobalParameters4, getGlobalParameter4 | createUpdateGlobalParameter4 only when selected effective identity absent | records4; existing update/delete and compound values refused |
| Definitions / [options4](../src/options4.cc) | getAllOptionDefs4, getOptionDef4 | createUpdateOptionDef4 fresh selected identity only | [options4](../tests/options4.py); existing update/delete refused |
| Global options / options4 | getAllOptions4, getOption4 | createUpdateOption4 global overload, fresh selected identity only | options4; existing update/delete refused |
| Shared networks / [shared_network4](../src/shared_network4.cc) | getAllSharedNetworks4, getSharedNetwork4, getSharedNetworkSubnets4 | createUpdateSharedNetwork4 fresh database-wide name only | [shared_network4](../tests/shared_network4.py); existing update/delete/membership writes refused |
| Three scoped options / [scoped_options4](../src/scoped_options4.cc) | Native parent lookup and CfgOption readback | createUpdateOption4 network/subnet/pool overload with ANY, exact sole parent association and fresh code/space guard | [scoped_options4](../tests/scoped_options4.py); existing update/delete refused, pool range must be globally unique |
| Classes / [client_classes4](../src/client_classes4.cc) | getAllClientClasses4 ordered dictionary for LIST and GET; getClientClass4 for preflight | createUpdateClientClass4 append-only fresh class | [client_classes4](../tests/client_classes4.py), [class packets](../tests/client_class_packets.py); existing update/delete/reorder refused |

Native missing-record deletion methods exist but are deliberately not invoked
by refusal-only endpoints. SQL readback proves persistence, never packet
classification or activation. All family fixtures run under both SQL backends
and both packet-threading modes; their invocation and results are in M31 checks.

## Commercial coverage and contract confidence

All **74** M23 descriptors independently match the pinned public ARM command
declarations: **36 DHCPv4, 38 DHCPv6**. The
[74-row matrix](compatibility-matrix.md) remains the per-operation ledger with
individual source links, request/response profiles, selectors and unresolved
contract references. No proprietary implementation was inspected.

| Functional analogue | Implemented | Partial | Missing |
| --- | --- | --- | --- |
| DHCPv4 servers | 3 | 0 | 1 |
| DHCPv4 scalar globals | 0 | 3 | 1 |
| DHCPv4 definitions | 0 | 3 | 1 |
| DHCPv4 global options | 0 | 3 | 1 |
| DHCPv4 shared networks | 0 | 3 | 1 |
| DHCPv4 scoped options | 0 | 3 | 3 |
| DHCPv4 subnet operations | 0 | 6 | 0 |
| DHCPv4 classes | 0 | 3 | 1 |
| DHCPv6 | 0 | 0 | 38 |
| **Total** | **3** | **24** | **47** |

M30 counts reproduce without numerical correction. Exact compatibility remains
**0 implemented / 0 partial / 74 missing**: no remote command is registered.
The old unlabelled 3/15/56 aggregate table was stale M26 data and is corrected.
Four subnet endpoints cover six commercial operations; six scoped LIST/GET
extensions have no documented commercial counterpart. Refusal endpoints do not
increase implemented coverage.

Every operation has a public positive request and result-0 response example.
All 74 descriptors lack nonzero-result examples. Thus a positive schema can be
clear while the complete command contract is only **partially documented**.
Missing-record envelopes, error text/arguments and validation precedence are
not publicly established sufficiently to claim an exact implementation.

The authoritative baseline is the
[pinned ARM](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/doc/sphinx/arm/hooks-cb-cmds.rst)
and individual public descriptors linked in the matrix.

| Contract topic | Confidence and qualification |
| --- | --- |
| Class SET format | Contradictory: descriptor uses singular client-class with nested follow-class-name; ARM uses client-classes and arguments-level predecessor. Both v4/v6 affected. Class GET/LIST/DEL positive formats are not implicated by this SET contradiction |
| Class success metadata | Class SET success text and GET commentary incorrectly mention shared networks; GET concrete class response schema remains clear |
| Compound global GET | Contradictory: ARM scalar-only versus descriptor scalar/list/map and dotted member lookup; success text also differs by leading count |
| Definition DEL identity | Prose says name/code; concrete example uses code/space and nested force. Neither is evidence for safe all-scope dependency checking |
| Option identity | ARM explicitly distinguishes omitted class filter: GET can choose indeterminately, SET uses empty classes, DEL matches all; explicit class list is an exact commercial identity |
| Network/subnet membership | Commercial subnet replacement requires shared-network-name, nullable for standalone, and clears omitted values; project preservation is a distinct contract |
| Selectors | Positive tag profiles documented; no complete missing/error behavior. ARM explicitly limits this release to one configured backend, so sole-backend enforcement alone is not a proven incompatibility |
| Class order/dependencies | ARM specifies append on creation, retain position on update, explicit predecessor moves, references must precede consumers; native implementation findings below qualify this independently |
| Missing/error envelopes | Not publicly established completely for any of the 74 operations; no inference from naming or result-0 examples |

Potential future aliases begin with server GET-ALL, then server GET, only after
empty/missing/error envelope qualification. Definition reads also need complete
association metadata. Network/subnet/class reads need dedicated commercial
serializers and selectors. Class SET, compound global GET and destructive
operations remain deferred. **No alias is ready for registration in M31.**

## Native mutation investigation

Pinned source links below identify implementations, not conclusions inferred
from method names. Public interfaces are in
[config_backend_dhcp4.h](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/lib/dhcpsrv/config_backend_dhcp4.h);
the PostgreSQL and MariaDB implementations were both inspected.

| Family | Identity, readback and native side effects | Feasibility conclusion |
| --- | --- | --- |
| Subnets/pools | Database-wide subnet ID and canonical prefix; ANY exposes conflicts and tags. Upsert replaces children. Serialized equivalence guard preserves only the supported standalone projection; pool replacement can remove restrictions/options | Existing bounded CRUD is supported. Richer updates need lossless construction and exact child/association preconditions, rather than a blanket upstream change |
| Server records | Tag identifies server; description readback is adequate for replacement. deleteServer4 calls purgeUnassignedConfig after successful deletion, purging orphan globals, definitions and global options, including unrelated preexisting orphans | Description update works. Delete needs database-wide orphan evidence and exclusion of outside writers; demonstrated purge semantics justify refusal |
| Globals | Name plus selected effective row; tags do not create independent global identities. Selected readback filters associations and collapses common fallback. Native row update/delete can affect shared ownership | Complete stable row/association evidence required; selected-view emptiness authorizes only the existing bounded fresh contract |
| Definitions | code/space and selected row; readback includes SQL ID but filtered associations. deleteOptionDef4(force=false) checks global option lookup, not every scoped/class consumer | Force=false is useful but not sufficient. Need complete consumers/associations before existing mutation |
| Global options | code/space/client-class filter and row identity; selected tags incomplete. Native delete removes a row rather than detaching one association | Need full associations and exact class-filter semantics; no safe automatic cascade |
| Shared networks | Database-wide name; native reconstruction accumulates network tags. Member lookup ignores caller selector and uses ANY. Upsert deletes/recreates options and associations | Empty, sole-associated, losslessly reconstructable network is a bounded future candidate; rich network/member replacement is not yet proven |
| Network options | Parent name plus code/space/classes; parent exposes options and tags; ANY native write | Sole exact parent plus lossless option identity may permit bounded update/delete; option ownership evidence still needs qualification |
| Subnet options | Parent subnet ID plus code/space/classes; same ownership and ANY behavior | Same bounded candidate; never replace whole subnet merely to mutate an option |
| Pool options | Public write/delete accepts address range, without subnet ID; native query resolves by range alone | Global range uniqueness is an enforceable current precondition. Arbitrary colliding ranges require a parent-qualified upstream overload |
| Classes | Database-wide name and global order_index; ordered readback reconstructs class tags before whole-object selector filtering; template identity lost. Upsert deletes/recreates options/definitions, dependencies and links | Empty predecessor appends INSERT but preserves UPDATE position. Same-position ordinary-class update is possible in principle; child preservation and complete consumers remain unqualified |

Specific implementation evidence, relative to the pinned source:

- `src/hooks/dhcp/pgsql/pgsql_cb_dhcp4.cc:2676,2712` and
  `src/hooks/dhcp/mysql/mysql_cb_dhcp4.cc:2877`: server deletion/orphan purge.
- `src/hooks/dhcp/pgsql/pgsql_cb_impl.cc:283,293,827,876`: stable IDs and
  selected global fallback collapse; native IDs are not revision guards.
- `src/hooks/dhcp/pgsql/pgsql_cb_dhcp4.cc:2070` and
  `src/hooks/dhcp/mysql/mysql_cb_dhcp4.cc:2208`: definition dependency check.
- `src/hooks/dhcp/pgsql/pgsql_cb_dhcp4.cc:1404,1591,1612,4788`: network tags,
  destructive child replacement and ANY member enumeration.
- `src/hooks/dhcp/pgsql/pgsql_cb_impl.cc:577`: option collection iterates selector
  tags; ANY/UNASSIGNED does not provide an orphan option inventory.
- `src/hooks/dhcp/pgsql/pgsql_query_macros_dhcp.h:1315,1355`: option whole-row
  deletion and pool-range-only identity.
- `src/hooks/dhcp/pgsql/pgsql_cb_impl.cc:1162` and
  `src/hooks/dhcp/pgsql/pgsql_cb_dhcp4.cc:4505`: null class filter becomes SQL
  wildcard; deletion uses LIKE. Explicit empty classes avoids null/all behavior;
  wildcard-bearing names still require qualification.
- `src/hooks/dhcp/pgsql/pgsql_cb_dhcp4.cc:2482,2543,2564,2572,2582`:
  append-on-insert, internal transaction, replaced class children, preserved
  position on empty-predecessor update and replaced links/dependencies.

M31 corrects the blanket M30 association concern for classes: both native drivers
accumulate all class server tags before filtering whole class objects by selector.
The project's conservative `associations-complete:false` response marker does not
prove that native class tags are incomplete. PostgreSQL reconstruction/filtering
is in `pgsql_cb_dhcp4.cc:2384,2418`; MariaDB equivalents are
`mysql_cb_dhcp4.cc:2562,2593`. This does not establish complete textual consumers,
lossless template/child reconstruction or atomic preflight, so existing mutations
remain refused.

### Alternatives and finite blocker inventory

This ledger counts **12 findings**, each once by its primary category.
Cross-cutting D1 also applies to the other findings. Counts describe findings,
not command totals: **A 0, B 4, C 5, D 1, E 1, F 1**. There is no evidence that
every refusal is an upstream limitation.

| ID | Category | Restriction and evidence / next proof |
| --- | --- | --- |
| B1 | B — stricter preconditions | Rich subnet/pool replacement: native upsert exists, but require lossless serialization, exact sole ownership and child preservation; preserveSubnet4 currently enforces the smaller safe subset |
| B2 | B | Existing shared network: restrict to empty membership, sole association, supported attributes and no lost options; native tag/member reads exist |
| B3 | B | Existing scoped option: restrict parent ownership, exact class filter, lossless option representation and globally unique pool range |
| B4 | B | Ordinary existing class at same position: native empty-predecessor update preserves position; exclude templates/local definitions and prove children/dependencies unchanged |
| C1 | C — additional read-only evidence | Global existing row associations hidden by selected views; complete row ownership needed |
| C2 | C | Definition ownership and all-scope consumers missing; force=false does not prove safety |
| C3 | C | Global option associations and precise deletion identity incomplete |
| C4 | C | Server deletion can purge unrelated orphan records; full orphan/dependency inventory required |
| C5 | C | Class consumers include textual option/subnet/pool/network/additional-evaluation references beyond native class dependency edges; orphan option inventory incomplete |
| D1 | D — concurrency/fencing | All preflight mutations lack an atomic read-to-write revision condition |
| E1 | E — upstream enhancement | Unrestricted pool-option mutation cannot identify a colliding range by subnet through the public write/delete overload |
| F1 | F — unknown | Assigned association reconstruction using ALL + getAllServers4 + ONE(each tag), joined by native SQL IDs, is plausible but unqualified on both engines; it cannot establish orphan inventory |

No A finding is asserted: candidate APIs exist, but a complete safety proof for
a currently refused operation is still missing. F1 is an investigative candidate,
not authorization to mutate. C findings may be resolved by a trustworthy,
read-only evidence facility under a stable snapshot and writer exclusion;
production C++ must continue using native write APIs only.

### Transactions, revisions and race windows

The public mutation signatures accept objects/selectors but no expected
revision, compare-and-swap token or caller transaction covering preflight.
getRecentAuditEntries uses timestamp/ID cursors: audit observation bounds, not
a whole-configuration revision or lock. Modification timestamps are not unique
global revisions. Driver transactions protect their own write sequence, not
earlier hook reads.

| Window | Possible outside change | Consequence |
| --- | --- | --- |
| Initial read → dependency inspection | Insert a same identity or add a consumer | Freshness/dependency decision becomes stale |
| Dependency → association inspection | Add/remove association or membership | Wrong ownership or incomplete consumers |
| Association inspection → validation | Replace child/options/classes/order | Validated object no longer matches persisted object |
| Validation → native write | Create the identity or alter any checked dependency | Native upsert can overwrite; delete can remove a newly shared row |
| Write → post-write readback | Another writer changes configuration | Readback cannot prove which writer caused final state or repair safely |

One designated writer is sufficient only while all SQL mutation authorities
are actually excluded and this writer serializes its command sequence. Main
thread callouts serialize local commands in MT off/on; they do not serialize
other processes. A second hook process, another Kea CB client, direct SQL,
migration tool or unfenced restarted writer invalidates the assumption.
Post-write verification detects some changes but cannot undo stale preflight.

Minimum deployment prerequisites are an enforceable inventory of mutation
credentials/processes, exclusive active writer, exclusion of all restart
authorities for a replaced writer, serialized schema/administrative changes,
fresh reconciliation after uncertain outcomes and a durable mutation hold.
A policy flag or process disappearance alone is not database-enforced fencing.
No distributed lock, leader election or retry is implemented here. Native
CAS/transactional preconditions would be an upstream enhancement for unrestricted
concurrent writers; external exclusivity remains a possible architecture.

## M22 reconciliation and recovery limits

[Intended, persisted and active evidence](reconciliation-evidence.md) remain
separate. New native reads increase visibility but do not make M22 exact.

| Family | Persisted evidence now available | Activation / intended / recovery limitation |
| --- | --- | --- |
| Subnets/pools | Native serialized fields; diagnostic tags/timestamps in M22 collector | Managed projection tested; inherited globals/options/defaults and complete exact equality still unqualified |
| Servers | Native tag/description | Administrative metadata, not proof a consumer activated configuration |
| Globals/definitions/global options | Selected native values/definitions/options | Full associations, orphan rows and cross-family semantic equality absent from M22 collector |
| Networks/scoped options | Native parent/options, ANY membership and observed tags | Inheritance, complete option links and selector-specific active targets not fully reconciled |
| Classes | Ordered native dictionary, expressions/options and dependencies | Template identity/readback limits; SQL order alone is not active class order or successful evaluation |

Actual OFFER/ACK payloads and independent config-get observations establish
specific activated behavior in the private packet fixtures. A successful write
or config-backend-pull reply alone does not. Neither establishes fleet-wide
activation. Approved request fixtures are bounded intent, not a durable
production intent registry.

CONVERGED applies only to the proven managed projection; real complete M22
evidence remains `complete:false`. PENDING_ACTIVATION and PARTIAL_ACTIVATION
retain independent consumer observations. UNKNOWN_COMMIT retains the durable
hold; audit entries and selected readback cannot resolve every ambiguous outcome.
WRITER_UNFENCED, EVIDENCE_INCOMPLETE and RECOVERY_REQUIRED continue blocking
mutation/promotion. Synthetic complete observations test algorithms, not real
full-state recovery. No durable hold is relaxed.

MariaDB consumer credentials still require DML privileges for native startup;
hook read-only admission is not database-enforced read-only isolation.
Recovery/replacement must exclude old processes and their restart mechanisms.
Full real CONVERGED recovery and writerless promotion remain unqualified.

## BasedPyright baseline and reduction policy

Reproduce from the repository root with BasedPyright **1.40.2**:

```bash
basedpyright --outputjson > build/milestone31/basedpyright.json
ruff check tests scripts
```

The JSON summary is **33 files analyzed, 0 errors, 3,749 warnings, 0 information**.
All diagnostic paths belong to project-owned code: **tests 3,271; scripts 478**.
None points to external dependencies or generated/build files. External typing
and dynamic JSON can propagate unknown types into project diagnostics; that
does not reclassify those diagnostics as external files.

`pyproject.toml` includes only tests/scripts, Python 3.13, separate execution
roots for direct-script imports; Ruff retains the Python 3.10 syntax floor.
The scope is appropriate and unchanged. Config SHA-256:
`778f2d1fd133b66b64140567f70590577f0020a7567e23a6b53c8becab863991`.

| Rule | Warnings |
| --- | --- |
| reportUnknownArgumentType | 826 |
| reportAny | 625 |
| reportUnknownVariableType | 559 |
| reportUnknownMemberType | 497 |
| reportUnknownParameterType | 422 |
| reportMissingParameterType | 418 |
| reportUnusedCallResult | 187 |
| reportImplicitStringConcatenation | 112 |
| reportExplicitAny | 31 |
| reportUnknownLambdaType | 29 |
| reportUnannotatedClassAttribute | 28 |
| reportPrivateUsage | 10 |
| reportImplicitOverride | 3 |
| reportUnusedParameter | 1 |
| reportUnusedVariable | 1 |

Unknown-type rules total 2,333; Any/ExplicitAny 656; missing parameter types 418.
These dominate the baseline. Largest files: concurrency.py 466, dhcp.py 389,
designated_writer.py 313, mysql.py 261 and postgresql.py 247.

Representative risk assessment:

- scripts/analyze.py:36–69 consumes dynamically typed compilation JSON and
  command arrays. Shape validation and typed boundaries would improve correctness;
  warnings alone do not demonstrate a currently failing invocation.
- Fixture command replies, SQL callbacks and process/packet helpers carry
  Unknown/Any across modules. Prioritize response shape, optional process handles,
  cleanup paths and subprocess results; these can hide real attribute/index risks.
- Unused argparse action results and next(iterator) in analyze.py are intentional
  side effects/consumption. Adjacent literals in client_class_packets.py:124–143
  are deliberate string construction. These diagnostics are low priority style
  signals, not demonstrated bugs.
- Private helper imports in designated_writer.py are coupling concerns;
  missing override markers in three unittest setUp methods are style signals.
  Unused lifecycle save and recovery row are small cleanup candidates.
- No blanket claim that all Unknown/Any warnings are false positives is justified.
  No new correctness error was established by this bounded assessment.

Retain the raw JSON with this checkout/tool version; enumerate counts using
`generalDiagnostics[].rule`, `file` and `severity`, and
`summary.filesAnalyzed/errorCount/warningCount`. This reproduces both counts
and origin classification without parsing terminal text. The local JSON
contains absolute checkout paths and is evidence, not a portable source file.

Future warning gates should require zero errors, no new actionable diagnostics
in changed files and reviewed per-rule/file deltas against a version-pinned
baseline. Annotate shared transport/JSON boundaries first, then high-risk
process/cleanup code; reduce one module at a time with existing tests. An equal
total can hide a new warning, so compare normalized path/rule/message/location
records as well as counts. Tool upgrades require an explicit baseline review.
Do not disable diagnostic categories, lower settings or undertake a typing
rewrite merely to obtain zero warnings.

## Focused preservation verification

Existing private SQL fixtures provide diagnostic evidence without adding direct
SQL to production. Their checked helpers compare configuration, associations
and audit snapshots around each refused/missing mutation. PostgreSQL excludes
sequence counters from equality; rows/audit records remain compared. MariaDB
snapshots all fixture tables. Sequence consumption is not a configuration change.

| Required case | Executable evidence |
| --- | --- |
| Hidden/common/mixed associations | records4.py; options4.py hidden links; scoped_options4.py hidden parent/option links; client_classes4.py hidden class links |
| Existing option dependencies | options4.py definition/global-option refusals; scoped_options4.py parent options; class fixtures option consumers |
| Network membership | shared_network4.py member inventory/update/delete refusal; lifecycle.py membership guard |
| Pool identity collisions | scoped_options4.py duplicate range including unassigned subnet |
| Class ordering/consumers | client_classes4.py append/order/dependency SQL; class consumers in subnet/pool/option/additional evaluation; client_class_packets.py observable ordered dependencies |
| Rich subnet preservation | mutation.py preservation and refusal cases; lifecycle.py rich standalone reads/deletion and membership refusal; DHCP timers/boot/class restrictions |
| Refused updates/deletes/missing deletes | Each family checked helper compares snapshots; missing parent remains error; no native write on missing DEL |
| No unintended activation | Existing config-get/packet state before explicit activation; refused class mutations followed by repeated matching/nonmatching packets |

The SQL fixtures seed disposable scenarios where needed; diagnostic comparisons
are read-only. Fixture reset SQL is not a production implementation or evidence
that a prohibited mutation is safe. M31 runs no deliberate connection interruption,
outage injection or production-network DHCP traffic.

The required backend/threading results, packet assertions, cleanup and quality
tool outcomes are recorded separately in M31 checks. Unrestricted CRUD, exact
commercial parity, complete recovery and production deployment are not acceptance
claims of this qualification.
