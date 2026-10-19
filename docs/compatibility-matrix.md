# Commercial command compatibility matrix

## M29 scoped options

M29 is **PARTIAL**. Twelve project-specific scoped-option callouts provide
list/get and guarded fresh creation for shared networks, subnets and pools.
Existing update/delete remains refused; missing deletion returns result 3
without a native write. Parent objects are never replaced. Option associations
are explicitly incomplete even when parent tags are observable.

Only six commercial commands exist for these scopes: network/subnet/pool set
and delete. There are no documented scoped list/get commands in this baseline;
the six project read commands are extensions. Three create-only set analogues
move from missing to partial. Delete remains missing functionality despite its
safe refusal endpoint. Current functional coverage is **3 implemented, 21 partial,
50 missing** of 74 (DHCPv4 3/21/12; DHCPv6 0/0/38). There are 37 registered
project commands. Exact commercial compatibility remains **0 implemented,
0 partial, 74 missing**. Earlier counts below are historical.

Native scoped writes use ANY and parent identity; production guards require
one exact parent association. Pool writes use range alone, so creation also
requires backend-wide range uniqueness across common, named and unassigned
subnets. Complete option links and atomic revision preconditions remain absent.
See [contracts](commands.md), [architecture](command-architecture.md) and the
[dependency backlog](dependency-safety-backlog.md).

## M28 bounded subnet extension

M28 is **PARTIAL**: the existing subnet SET accepts native timers, boot fields,
subnet/pool classes and CIDR pools, preserving omitted supported attributes.
Membership, scoped options and unsupported existing fields still prevent updates.
Existing pool class restrictions refuse supplied-list replacement. No new commands
or aliases are registered. Functional counts remain **3 implemented, 18 partial,
53 missing** of 74; exact compatibility remains **0 implemented, 0 partial,
74 missing**. See the [capability inventory](subnet4-capabilities.md) and
[dependency backlog](dependency-safety-backlog.md).

## M27 implementation update

M27 is **PARTIAL**. Four project-specific `cb-shared-network4-list/get/set/del`
callouts add native selected-network reads and guarded fresh creation. Creation
accepts only a name and optional valid/renew/rebind timers. Existing updates and
deletes are refused; a missing delete returns result 3 without a native write.
There are 25 registered commands, with no commercial aliases.

Network rows preserve native properties, options and observed server tags.
Membership is explicitly labelled `membership-selector: "ANY"`: pinned drivers
ignore the supplied selector for member reads. These children are persisted
evidence, not the selected consumer's active configuration. The response retains
`associations-complete: false`; independent network/member reads are not an
atomic dependency snapshot. See [contracts](commands.md) and the
[dependency-safety backlog](dependency-safety-backlog.md).

Current functional counts: **3 implemented, 18 partial, 53 missing** of 74;
DHCPv4: 3/18/15, DHCPv6: 0/0/38. The three new partial analogues are network
list/get and create-only set. Network delete remains missing despite its
refusal endpoint. Exact commercial compatibility remains **0 implemented,
0 partial, 74 missing**. Earlier milestone counts below are historical.

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


## Baseline and evidence

**M23 status: PARTIAL.** The command inventory is complete; public contract
contradictions and unspecified error behavior prevent an exact compatibility
claim. The implementation updates above record functional analogues only;
no commercial runtime verification or remote registration is claimed.

The target is **ISC Kea 3.2.1**, tag `Kea-3.2.1`, commit
`1737462bc79276e3269304ea8cd3d1c03400e30d` from
[the source lock](../scripts/kea-source.json).
The existing matching build identifies itself as `3.2.1-git`.
Authoritative public references:

- [Versioned ARM hooks chapter](https://kea.readthedocs.io/en/kea-3.2.1/arm/hooks.html).
- [Versioned command API reference](https://kea.readthedocs.io/en/kea-3.2.1/api.html#commands-cb-cmds).
- [Pinned ARM cb_cmds source](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/doc/sphinx/arm/hooks-cb-cmds.rst).
- [Pinned public command descriptors](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api).
- [DHCPv4 native interface](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/lib/dhcpsrv/config_backend_dhcp4.h)
  and [DHCPv6 native interface](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/lib/dhcpsrv/config_backend_dhcp6.h).

The local ARM `isccmd::` declarations and public JSON descriptors independently
contain the same **74 commands: 36 DHCPv4 and 38 DHCPv6**. All descriptors name
`cb_cmds` as their hook. No proprietary hook source or binary was used.
Context7 returned master documentation; it is excluded from the pinned baseline.

| Counting basis | Implemented | Partial | Missing | Total |
| --- | --- | --- | --- | --- |
| Exact commercial command interface | 0 | 0 | 74 | 74 |
| Functional analogues in existing commands | 3 | 15 | 56 | 74 |
| DHCPv4 functional analogues | 3 | 15 | 18 | 36 |
| DHCPv6 functional analogues | 0 | 0 | 38 | 38 |

Six of the fifteen partial analogues are the v4 subnet list, get-by-id, get-by-prefix, set,
del-by-id and del-by-prefix operations. They share four existing `cb-subnet4-*`
commands; they are neither six registered commands nor compatible aliases.
The diagnostic is outside the commercial inventory.

## Reading the inventory

Each row is one exact command. Its name links to the **individual pinned public
descriptor**, including request syntax, success response text and explanatory
comments. Schema profiles below supply mandatory/optional fields, validation,
selector behavior, dependencies and unresolved errors. Both apply to every row.
All requests have `command` and an `arguments` map; `remote` is optional.

- **N**: no top-level `server-tags`; object identity is database-wide in that family.
- **S**: mandatory `server-tags:[tag]`, exactly one non-null string, including
  logical `all`. Read ONE falls back to common; delete targets only the explicitly
  associated row and must not delete the common fallback.
- **L**: mandatory nonempty tag list; one/many strings, or `[null]` to select
  unassigned objects. Do not mix null with strings without contract evidence.
  Named views include common objects; returned metadata retains actual associations.
- **W**: mandatory one/many non-null string tags, including `all`, assigning the
  object to those servers. Tags are associations, never separate writer namespaces.
- Every native method below is called through the corresponding family pool,
  with a per-call `BackendSelector` and command-specific `ServerSelector`.
  The native interface alone does not establish command compatibility.
- **U1 applies to every row**: error/not-found numeric results, text, empty
  argument shape and validation precedence are not fully specified per command.
  Success examples use `result:0`; do not infer empty/error results from this.
  Documented delete misses remove nothing; exact zero-count envelope remains to
  be qualified. Preserve all specified response keys and text when fixtures are
  established; do not add a universal `count` that a descriptor omits.
- **Partial** means existing restricted functional analogue only. **Missing**
  means no production equivalent. Every row still lacks a tested remote interface.

## Schema and semantic profiles

### Server (SV)

GET/DEL: `servers:[{server-tag:string}]`, exactly one. GET-ALL: no object
arguments. SET: `servers:[{server-tag:string,description:string}]`, exactly one;
the descriptor shows description but does not clearly specify omission/default
behavior (U6). User tags are case-insensitive, at most 256 characters; reserved
`all`/`any` cannot be ordinary records. No top-level tag selector.
GET returns `arguments.servers` plus count; GET-ALL excludes the logical all
record; SET returns servers; DEL returns count. Replacement changes the record.
Deleting a server removes non-shareable parameters/definitions/global options
and detaches shareable subnet/network associations; last-association removal can
leave an unassigned object. Recreating the server does not restore deleted data.
Verify child classes and all cascades against both concrete backends (U6).

### Global parameter (GP)

GET/DEL: `parameters:[string]`, exactly one. GET-ALL: no parameter names.
SET: `parameters:{name:value,...}`; multiple parameters are supported.
All use S. GET returns a parameters **map**, metadata and count; GET-ALL a
parameters **list of maps**, each with metadata, plus count. SET returns the
parameters map plus count; DEL returns count. Validate supported parameter name,
type and family; delete exposes JSON/default values only after activation.
A multi-parameter SET can partially persist before an error: reconcile all
parameters, never promise batch atomicity or automatically retry.

**U2:** ARM prose says scalar string/integer/real/boolean only, while the pinned
API descriptor comments also allow scalar lists/maps and dotted
`map-name.parameter-name` access. M25 must resolve and enumerate supported
names, map/list encoding and types; scalar-only implementation is not full parity.
Neither source permits arbitrary whole-server JSON storage.

### Shared network (NW)

GET/DEL: `shared-networks:[{name:string}]`, exactly one, N.
GET optional `subnets-include:"no"|"full"`, default no; full includes native
`subnet4`/`subnet6` child definitions. DEL optional
`subnets-action:"keep"|"delete"`, default keep; keep detaches child subnets.
LIST uses L and returns only names plus metadata and count.
SET uses W, one full network in `shared-networks`; reject embedded
`subnet4`/`subnet6`. SET replaces, omitted values become unspecified and
inherit globals/defaults; GET returns full network plus metadata and count.
SET success has no arguments in the descriptor. DEL returns count.
Child membership is changed through subnet SET, not network SET.
Validate native family fields, option dependencies, tags and child deletion.

### Option definition (OD)

GET/DEL: `option-defs:[{code:integer,space:string}]`, exactly one; DEL supports
optional boolean `force` **inside that definition map**, shown false.
GET-ALL has no object argument. SET: one full native definition
(name/code/type/space and optional array/record/encapsulation fields according
to the native parser). S for every operation. Default spaces are dhcp4/dhcp6.
Validate family code ranges, data type, record types, uniqueness and dependent
options. DEL must reject definitions in use unless force is true; native
delete alone does not supply this commercial preflight (U5).
GET/GET-ALL return option-defs and metadata, with count as in the descriptor;
SET success has no arguments; DEL returns count. Descriptor DEL prose
mentions name/code but syntax and ARM identify code/space: use the latter
documented identity and record the discrepancy (U5).

### Global option (OG)

GET/DEL: `options:[{code:integer,space:string,client-classes?:[string,...]}]`.
SET: one full native option in options (data/encoding/send controls and native
supported fields). GET-ALL has no option selector. S for all.
GET returns options with metadata, **without a count in its example**;
GET-ALL returns options and count. SET returns option identity
(code/space/client-classes); DEL returns count.
Resolve built-in/custom definitions, CSV/binary encoding, family code bounds,
encapsulation and class tags. Name-based SET is reliable only for built-ins;
prefer explicit code for custom definitions.

**Option identity rule, all option scopes:** omitting client-classes on GET can
select an indeterminate match if several exist; on SET it matches only the
empty class list; on DEL it deletes all code/space matches. Supplying a list,
including `[]`, selects that exact class-list match. Do not collapse absent
and empty or sort class lists without proving their semantics (U7).

### Scoped option (OS)

Only SET and DEL exist. Both use N, exactly one scope object and one options
object. Option identity/encoding rules are OG. Scope keys:
`shared-networks:[{name}]`, `subnets:[{id}]`,
`pools:[{pool:range-or-prefix}]`, or v6
`pd-pools:[{prefix:address,prefix-len:integer}]`.
Scope object must already exist. Validate address family, range/prefix, PD
prefix length and unambiguous native pool identity. No top-level tags.
SET replaces just that scope's option; response option identities.
DEL returns count and affects only that scope, never an inherited option in a
parent/child. GET uses the owning network/subnet full read; there is no
independent commercial scoped option GET or LIST. Pool/PD parent ambiguity and
missing-parent failure behavior need backend fixtures (U6).

### Subnet (SN)

GET/DEL-BY-ID: `subnets:[{id:integer}]`. GET/DEL-BY-PREFIX:
`subnets:[{subnet:prefix}]`. All N, exactly one.
LIST uses L and returns id, prefix, shared-network-name, metadata and count,
**not full subnet definitions**.
SET uses W and one full native subnet in subnets, including id, subnet and
mandatory `shared-network-name:string|null`. A named shared network must
already exist; null makes the subnet standalone.
GET returns full native subnet including embedded address pools, v6 PD pools,
options, shared-network-name and association metadata, plus count.
SET returns id/subnet; DEL returns count and deletes the whole subnet identity,
not a tag-local version. SET is replacement, not patch: omitted fields become
unspecified. Validate complete family syntax, inheritance, pools, prefix/ID
collisions, dependencies and association changes.
M28 cb SET preserves omitted supported attributes/pools and accepts a bounded
rich standalone model (timers, boot fields and class restrictions). Unsupported
dependencies and shared-network members remain refused. This merge contract
cannot serve as a replacement-style remote SET alias. See the
[subnet capability inventory](subnet4-capabilities.md).

### Client class (CL)

GET/DEL: `client-classes:[{name:string}]`, exactly one, N.
GET-ALL uses L and returns full classes with metadata and count, preserving
class evaluation order. SET uses W, one full class with expressions and supported
nested option-def/option-data. Dependencies must already exist under the same
server/common tag and precede their users; dependent classes block deletion.
New classes append; updating keeps position. Optional
`follow-class-name:string|null` selects a predecessor; null/omitted gives
default positioning. SET returns class name(s); DEL returns count.

**U3:** both public SET JSON descriptors use `client-class` singular, whereas
ARM examples use `client-classes`. They place follow-class-name inside the
class, whereas ARM examples place it in arguments.
**U4:** SET response text says “shared network” in the descriptors. GET comment
also mislabels a class as shared network. These are public contradictions, not
verified commercial behavior. Obtain public clarification before registering
these names; native parser/API signatures cannot resolve commercial envelopes.

## Command-by-command inventory

Response notation names the documented `arguments` fields; “none” means the
success descriptor omits arguments. Exact success text/schema and request
examples are linked per row. Profiles carry error/not-found limitations U1,
dependencies, validation and create/replace/delete semantics.

| Exact command / pinned contract | Family | Profile; request selector | Success arguments | Native API entry point | Current functional status; remaining work |
| --- | --- | --- | --- | --- | --- |
| [`remote-class4-del`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-class4-del.json) | v4 | CL; N | `count` | `deleteClientClass4` | Missing: schema, native handler and qualification; U3/U4 |
| [`remote-class4-get-all`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-class4-get-all.json) | v4 | CL; L | `client-classes`, `count` | `getAllClientClasses4` | Missing: schema, native handler and qualification; U3/U4 |
| [`remote-class4-get`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-class4-get.json) | v4 | CL; N | `client-classes`, `count` | `getClientClass4` | Missing: schema, native handler and qualification; U3/U4 |
| [`remote-class4-set`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-class4-set.json) | v4 | CL; W | `client-classes` | `createUpdateClientClass4` | Missing: schema, native handler and qualification; U3/U4 |
| [`remote-class6-del`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-class6-del.json) | v6 | CL; N | `count` | `deleteClientClass6` | Missing: schema, native handler and qualification; U3/U4 |
| [`remote-class6-get-all`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-class6-get-all.json) | v6 | CL; L | `client-classes`, `count` | `getAllClientClasses6` | Missing: schema, native handler and qualification; U3/U4 |
| [`remote-class6-get`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-class6-get.json) | v6 | CL; N | `client-classes`, `count` | `getClientClass6` | Missing: schema, native handler and qualification; U3/U4 |
| [`remote-class6-set`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-class6-set.json) | v6 | CL; W | `client-classes` | `createUpdateClientClass6` | Missing: schema, native handler and qualification; U3/U4 |
| [`remote-global-parameter4-del`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-global-parameter4-del.json) | v4 | GP; S | `count` | `deleteGlobalParameter4` | Missing: cb-global-parameter4-del refuses existing values; complete associations unobservable; U1/U2 |
| [`remote-global-parameter4-get-all`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-global-parameter4-get-all.json) | v4 | GP; S | `parameters`, `count` | `getAllGlobalParameters4` | Partial: cb-global-parameter4-list; scalar subset/different schema; U1/U2 |
| [`remote-global-parameter4-get`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-global-parameter4-get.json) | v4 | GP; S | `parameters`, `count` | `getGlobalParameter4` | Partial: cb-global-parameter4-get; scalar subset/different schema; U1/U2 |
| [`remote-global-parameter4-set`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-global-parameter4-set.json) | v4 | GP; S | `parameters`, `count` | `createUpdateGlobalParameter4` | Partial: cb-global-parameter4-set creates only; existing updates refused; scalar subset/different schema; U1/U2 |
| [`remote-global-parameter6-del`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-global-parameter6-del.json) | v6 | GP; S | `count` | `deleteGlobalParameter6` | Missing: schema, native handler and qualification; U2 |
| [`remote-global-parameter6-get-all`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-global-parameter6-get-all.json) | v6 | GP; S | `parameters`, `count` | `getAllGlobalParameters6` | Missing: schema, native handler and qualification; U2 |
| [`remote-global-parameter6-get`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-global-parameter6-get.json) | v6 | GP; S | `parameters`, `count` | `getGlobalParameter6` | Missing: schema, native handler and qualification; U2 |
| [`remote-global-parameter6-set`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-global-parameter6-set.json) | v6 | GP; S | `parameters`, `count` | `createUpdateGlobalParameter6` | Missing: schema, native handler and qualification; U2 |
| [`remote-network4-del`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-network4-del.json) | v4 | NW; N | `count` | `deleteSharedNetwork4 + deleteSharedNetworkSubnets4 (delete children)` | Missing: cb refusal endpoint only; existing deletion unsupported |
| [`remote-network4-get`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-network4-get.json) | v4 | NW; N | `shared-networks`, `count` | `getSharedNetwork4 + getSharedNetworkSubnets4 (full)` | Partial: cb-shared-network4-get; different schema; native ANY children, incomplete dependency evidence |
| [`remote-network4-list`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-network4-list.json) | v4 | NW; L | `shared-networks`, `count` | `getAllSharedNetworks4` | Partial: cb-shared-network4-list; full selected network rows rather than commercial summaries |
| [`remote-network4-set`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-network4-set.json) | v4 | NW; W | none | `createUpdateSharedNetwork4` | Partial: cb-shared-network4-set; fresh minimal creation only; existing updates refused |
| [`remote-network6-del`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-network6-del.json) | v6 | NW; N | `count` | `deleteSharedNetwork6 + deleteSharedNetworkSubnets6 (delete children)` | Missing: schema, native handler and qualification |
| [`remote-network6-get`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-network6-get.json) | v6 | NW; N | `shared-networks`, `count` | `getSharedNetwork6 + getSharedNetworkSubnets6 (full)` | Missing: schema, native handler and qualification |
| [`remote-network6-list`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-network6-list.json) | v6 | NW; L | `shared-networks`, `count` | `getAllSharedNetworks6` | Missing: schema, native handler and qualification |
| [`remote-network6-set`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-network6-set.json) | v6 | NW; W | none | `createUpdateSharedNetwork6` | Missing: schema, native handler and qualification |
| [`remote-option-def4-del`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-option-def4-del.json) | v4 | OD; S | `count` | `deleteOptionDef4` | Missing: cb refusal endpoint only; existing deletion unsupported; U5 |
| [`remote-option-def4-get-all`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-option-def4-get-all.json) | v4 | OD; S | `option-defs`, `count` | `getAllOptionDefs4` | Partial: cb selected native read; incomplete associations; project envelope; U5 |
| [`remote-option-def4-get`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-option-def4-get.json) | v4 | OD; S | `option-defs`, `count` | `getOptionDef4` | Partial: cb selected native read; incomplete associations; project envelope; U5 |
| [`remote-option-def4-set`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-option-def4-set.json) | v4 | OD; S | none | `createUpdateOptionDef4` | Partial: cb native create-only; existing update refused; project envelope; U5 |
| [`remote-option-def6-del`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-option-def6-del.json) | v6 | OD; S | `count` | `deleteOptionDef6` | Missing: schema, native handler and qualification; U5 |
| [`remote-option-def6-get-all`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-option-def6-get-all.json) | v6 | OD; S | `option-defs`, `count` | `getAllOptionDefs6` | Missing: schema, native handler and qualification; U5 |
| [`remote-option-def6-get`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-option-def6-get.json) | v6 | OD; S | `option-defs`, `count` | `getOptionDef6` | Missing: schema, native handler and qualification; U5 |
| [`remote-option-def6-set`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-option-def6-set.json) | v6 | OD; S | none | `createUpdateOptionDef6` | Missing: schema, native handler and qualification; U5 |
| [`remote-option4-global-del`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-option4-global-del.json) | v4 | OG; S | `count` | `deleteOption4 (global)` | Missing: cb refusal endpoint only; existing deletion unsupported |
| [`remote-option4-global-get-all`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-option4-global-get-all.json) | v4 | OG; S | `options`, `count` | `getAllOptions4 (global)` | Partial: cb selected native read; incomplete associations; project envelope |
| [`remote-option4-global-get`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-option4-global-get.json) | v4 | OG; S | `options` | `getOption4 (global)` | Partial: cb selected native read; incomplete associations; project envelope |
| [`remote-option4-global-set`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-option4-global-set.json) | v4 | OG; S | `options` | `createUpdateOption4 (global)` | Partial: cb native create-only; existing update refused; project envelope |
| [`remote-option4-network-del`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-option4-network-del.json) | v4 | OS; N | `count` | `deleteOption4 (network name)` | Missing: cb-option4-network-del reports absence only; existing deletion refused; U6 |
| [`remote-option4-network-set`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-option4-network-set.json) | v4 | OS; N | `options` | `createUpdateOption4 (network name)` | Partial: cb-option4-network-set guarded fresh creation; existing updates refused; U6 |
| [`remote-option4-pool-del`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-option4-pool-del.json) | v4 | OS; N | `count` | `deleteOption4 (address range)` | Missing: cb-option4-pool-del reports absence only; existing deletion refused; U6 |
| [`remote-option4-pool-set`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-option4-pool-set.json) | v4 | OS; N | `options` | `createUpdateOption4 (address range)` | Partial: cb-option4-pool-set guarded fresh creation; subnet/range uniqueness required; U6 |
| [`remote-option4-subnet-del`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-option4-subnet-del.json) | v4 | OS; N | `count` | `deleteOption4 (subnet ID)` | Missing: cb-option4-subnet-del reports absence only; existing deletion refused; U6 |
| [`remote-option4-subnet-set`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-option4-subnet-set.json) | v4 | OS; N | `options` | `createUpdateOption4 (subnet ID)` | Partial: cb-option4-subnet-set guarded fresh creation; existing updates refused; U6 |
| [`remote-option6-global-del`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-option6-global-del.json) | v6 | OG; S | `count` | `deleteOption6 (global)` | Missing: schema, native handler and qualification |
| [`remote-option6-global-get-all`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-option6-global-get-all.json) | v6 | OG; S | `options`, `count` | `getAllOptions6 (global)` | Missing: schema, native handler and qualification |
| [`remote-option6-global-get`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-option6-global-get.json) | v6 | OG; S | `options` | `getOption6 (global)` | Missing: schema, native handler and qualification |
| [`remote-option6-global-set`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-option6-global-set.json) | v6 | OG; S | `options` | `createUpdateOption6 (global)` | Missing: schema, native handler and qualification |
| [`remote-option6-network-del`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-option6-network-del.json) | v6 | OS; N | `count` | `deleteOption6 (network name)` | Missing: schema, native handler and qualification; U6 |
| [`remote-option6-network-set`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-option6-network-set.json) | v6 | OS; N | `options` | `createUpdateOption6 (network name)` | Missing: schema, native handler and qualification; U6 |
| [`remote-option6-pd-pool-del`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-option6-pd-pool-del.json) | v6 | OS; N | `count` | `deleteOption6 (PD prefix/length)` | Missing: schema, native handler and qualification; U6 |
| [`remote-option6-pd-pool-set`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-option6-pd-pool-set.json) | v6 | OS; N | `options` | `createUpdateOption6 (PD prefix/length)` | Missing: schema, native handler and qualification; U6 |
| [`remote-option6-pool-del`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-option6-pool-del.json) | v6 | OS; N | `count` | `deleteOption6 (address range)` | Missing: schema, native handler and qualification; U6 |
| [`remote-option6-pool-set`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-option6-pool-set.json) | v6 | OS; N | `options` | `createUpdateOption6 (address range)` | Missing: schema, native handler and qualification; U6 |
| [`remote-option6-subnet-del`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-option6-subnet-del.json) | v6 | OS; N | `count` | `deleteOption6 (subnet ID)` | Missing: schema, native handler and qualification; U6 |
| [`remote-option6-subnet-set`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-option6-subnet-set.json) | v6 | OS; N | `options` | `createUpdateOption6 (subnet ID)` | Missing: schema, native handler and qualification; U6 |
| [`remote-server4-del`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-server4-del.json) | v4 | SV; N | `count` | `deleteServer4` | Missing: cb-server4-del refuses existing records; native orphan purge unsafe; U6 |
| [`remote-server4-get-all`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-server4-get-all.json) | v4 | SV; N | `servers`, `count` | `getAllServers4` | Implemented functional analogue: cb-server4-list; different schema, no exact compatibility; U1/U6 |
| [`remote-server4-get`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-server4-get.json) | v4 | SV; N | `servers`, `count` | `getServer4` | Implemented functional analogue: cb-server4-get; different schema, no exact compatibility; U1/U6 |
| [`remote-server4-set`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-server4-set.json) | v4 | SV; N | `servers` | `createUpdateServer4` | Implemented functional analogue: cb-server4-set; different schema, no exact compatibility; U1/U6 |
| [`remote-server6-del`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-server6-del.json) | v6 | SV; N | `count` | `deleteServer6` | Missing: schema, native handler and qualification; U6 |
| [`remote-server6-get-all`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-server6-get-all.json) | v6 | SV; N | `servers`, `count` | `getAllServers6` | Missing: schema, native handler and qualification; U6 |
| [`remote-server6-get`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-server6-get.json) | v6 | SV; N | `servers`, `count` | `getServer6` | Missing: schema, native handler and qualification; U6 |
| [`remote-server6-set`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-server6-set.json) | v6 | SV; N | `servers` | `createUpdateServer6` | Missing: schema, native handler and qualification; U6 |
| [`remote-subnet4-del-by-id`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-subnet4-del-by-id.json) | v4 | SN; N | `count` | `deleteSubnet4 (ID)` | Partial: cb subnet analogue; full schema, metadata, selectors and U1 |
| [`remote-subnet4-del-by-prefix`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-subnet4-del-by-prefix.json) | v4 | SN; N | `count` | `deleteSubnet4 (prefix)` | Partial: cb subnet analogue; full schema, metadata, selectors and U1 |
| [`remote-subnet4-get-by-id`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-subnet4-get-by-id.json) | v4 | SN; N | `subnets`, `count` | `getSubnet4 (ID)` | Partial: cb subnet analogue; full schema, metadata, selectors and U1 |
| [`remote-subnet4-get-by-prefix`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-subnet4-get-by-prefix.json) | v4 | SN; N | `subnets`, `count` | `getSubnet4 (prefix)` | Partial: cb subnet analogue; full schema, metadata, selectors and U1 |
| [`remote-subnet4-list`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-subnet4-list.json) | v4 | SN; L | `subnets`, `count` | `getAllSubnets4` | Partial: cb subnet analogue; full schema, metadata, selectors and U1 |
| [`remote-subnet4-set`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-subnet4-set.json) | v4 | SN; W | `id`, `subnet` | `createUpdateSubnet4` | Partial: cb subnet analogue; full schema, metadata, selectors and U1 |
| [`remote-subnet6-del-by-id`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-subnet6-del-by-id.json) | v6 | SN; N | `count` | `deleteSubnet6 (ID)` | Missing: schema, native handler and qualification |
| [`remote-subnet6-del-by-prefix`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-subnet6-del-by-prefix.json) | v6 | SN; N | `count` | `deleteSubnet6 (prefix)` | Missing: schema, native handler and qualification |
| [`remote-subnet6-get-by-id`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-subnet6-get-by-id.json) | v6 | SN; N | `subnets`, `count` | `getSubnet6 (ID)` | Missing: schema, native handler and qualification |
| [`remote-subnet6-get-by-prefix`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-subnet6-get-by-prefix.json) | v6 | SN; N | `subnets`, `count` | `getSubnet6 (prefix)` | Missing: schema, native handler and qualification |
| [`remote-subnet6-list`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-subnet6-list.json) | v6 | SN; L | `subnets`, `count` | `getAllSubnets6` | Missing: schema, native handler and qualification |
| [`remote-subnet6-set`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api/remote-subnet6-set.json) | v6 | SN; W | `id`, `subnet` | `createUpdateSubnet6` | Missing: schema, native handler and qualification |


## Completeness and deliberately absent command families

| Family | v4 commands | v6 commands | Native capability / command boundary |
| --- | --- | --- | --- |
| Servers | 4 | 4 | Record CRUD; associations belong to object operations |
| Globals | 4 | 4 | Supported parameter subset; U2 must be resolved |
| Definitions | 4 | 4 | Global CRUD; class definitions nested in class SET |
| Global options | 4 | 4 | Global CRUD with class-aware identity |
| Shared networks | 4 | 4 | List summaries, get full, replace, delete with child policy |
| Subnets and embedded pools | 6 | 6 | Read/delete by ID or prefix, list, replace |
| Network/subnet/address-pool options | 6 | 6 | SET/DEL only, two per scope |
| PD-pool options | 0 | 2 | v6 SET/DEL only |
| Client classes | 4 | 4 | Ordered full objects and nested options |
| **Total** | **36** | **38** | **74** |

No standalone pool CRUD commands, class-option CRUD, association CRUD,
audit commands or modified-object commands appear in either public inventory.
Address pools and PD pools are managed through full subnet objects.
Native `getModified*` and `getRecentAuditEntries` support consumer fetch and
diagnostics, but are not additional commercial commands. Do not count core
`config-backend-pull`, `config-get`, `config-reload`, subnet_cmds, host_cmds,
lease_cmds or class_cmds as cb_cmds parity.

## Backend selection and evidence limits

Optional remote accepts optional type, host and port; port requires host.
Omit an empty remote specification. ARM describes the first configured backend
when remote is absent and notes that only one CB is supported by this release.
The native selector cannot name a database by database name. Native pools return
the first nonempty read and require exactly one backend for writes; they do not
aggregate databases. Keep the current unambiguous-single-backend safety boundary
until a separately specified routing test proves any expansion. Exact behavior
for multiple configured or unmatched backends is a contract question (U8).

Backend support does not imply that every JSON setting is stored.
Interfaces/listeners, control sockets, hooks, database credentials/topology,
MT/service startup settings and other unsupported maps remain local JSON.
Shared network, subnet, option and class native objects carry their supported
fields; globals need a versioned allowlist after U2. Reservations and leases
are distinct backends, outside this command inventory.

The matrix establishes documented names and candidate native entry points,
not observed commercial runtime behavior. U1–U8 are tracked with resolution
gates in the [gap analysis](commercial-parity-gap-analysis.md).
Implementation architecture is in [command architecture](command-architecture.md).
