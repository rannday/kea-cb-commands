# DHCPv4 configuration commands

## M29: scoped DHCPv4 options

Twelve project-specific commands use pinned Kea 3.2.1 native APIs. For each
scope `network`, `subnet`, and `pool`, commands are
`cb-option4-<scope>-list`, `cb-option4-<scope>-get`,
`cb-option4-<scope>-set`, and `cb-option4-<scope>-del`.
They are not commercial aliases. The documented commercial inventory contains
only `remote-option4-{network,subnet,pool}-{set,del}`; the six project read
commands add functionality without inventing commercial inventory entries.

Every request requires `server-tag` and a `parent` map. Non-list requests also
require one `option` map. Unknown fields and wrong types fail. Exactly one
configured SQL backend is required. Tags use native `ALL()` for `all` and
`ONE(tag)` otherwise; a named server must exist. `any` is not a request tag.

| Scope | Exact parent fields |
| --- | --- |
| network | `shared-network-name`: nonempty string, at most 128 bytes, no NUL or leading/trailing whitespace |
| subnet | `subnet-id`: integer 1..4294967294 |
| pool | `subnet-id`, `start`, `end`: exact existing range, canonical IPv4 strings with start <= end |

List takes no option. Get/delete require `code` (integer 1..254), `space`
(valid explicit DHCPv4 option space, at most 128 bytes), and optionally
`client-classes` (distinct nonempty strings). Omitted classes and `[]` select
the unclassified option; supplied classes match the native serialized list
exactly, including ordering. Code alone never identifies an option across scopes.
Reads stay within the selected parent view and do not combine selectors.

Set requires `code`, `space`, and string `data`. Optional fields are
`name`, `csv-format`, `always-send`, `never-send`, `client-classes`, and
map `user-context`. M26's selected-definition native parser is shared:
CSV defaults to true and requires a selected or native built-in definition;
false accepts native hexadecimal encoding. Strings, integers, addresses,
arrays, records, binary and valid empty payloads use Kea's encoder. Invalid
encoding, conflicting flags, unknown attributes and unsupported representations
are rejected. There is no additional `persistent` JSON field: Kea's
`always-send` representation controls the native persistent descriptor flag.

For example, fresh subnet option creation:

```json
{
  "command": "cb-option4-subnet-set",
  "arguments": {
    "server-tag": "test-server",
    "parent": { "subnet-id": 980 },
    "option": { "code": 15, "space": "dhcp4", "data": "example.test" }
  }
}
```

Reads reconstruct explicit options from the parent object's native `CfgOption`;
they do not return inherited effective options. Results contain `count`,
`options` (native serialization ordered by space/code/class identity),
`parent`, `server-tag`, `parent-server-tags`, and
`associations-complete: false`. Option association joins are not reconstructed
by native readback. Parent tags are observations, not a complete dependency
certificate. Missing parents are validation errors; empty list/missing get or
delete return result 3 with zero count. Successful reads/fresh creates return
result 0. Validation/refusal/backend failure returns result 1 through the
existing safe exception boundary. Only contract errors disclose detail.

Set/delete first require mutation admission. Mutating parent reads use
`ANY()` and require exactly the requested parent association. Existing
code/space at that scope refuses set and delete across all class variants:
`Existing scoped option mutations are unsupported: complete associations and dependencies cannot be verified.`
A missing delete is a read-only result 3. No native delete is invoked.

Fresh set calls the native scoped `createUpdateOption4` overload with
`ANY()`, without replacing its parent. Native audit triggers update the owning
network or subnet modification timestamp (including for pool options) and record
audit history. Parent configuration and association rows otherwise remain intact. Pool writes additionally enumerate
ALL, each named server and UNASSIGNED subnets and require the exact range to
occur once in the whole backend: native pool writes have no subnet key.
Parent ownership, fresh identity and global range checks are preflight evidence,
not an atomic compare-and-swap. The designated exclusive writer remains required.
Post-write readback must find the new identity; uncertainty requires
reconciliation before another attempt, never an automatic retry.

Mutation responses include `activation-requested: false`. No command activates
consumers or clears an M22 hold. Persisted state, selected parent serialization,
active `config-get` and actual packets remain separate evidence. Existing
M28 subnet updates still refuse scoped options and shared-network membership.
See the [dependency backlog](dependency-safety-backlog.md) for remaining gates,
and the pinned [native interface](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/lib/dhcpsrv/config_backend_dhcp4.h)
and [public command descriptions](https://github.com/isc-projects/kea/tree/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/api)
for the baseline.

## M27: shared networks

These four project-specific commands target pinned Kea 3.2.1 commit
`1737462bc79276e3269304ea8cd3d1c03400e30d`. They are not aliases for the
commercial `remote-network4-list/get/set/del` contracts.

| Command | Exact arguments |
| --- | --- |
| `cb-shared-network4-list` | `server-tag` |
| `cb-shared-network4-get` | `server-tag`, `name` |
| `cb-shared-network4-set` | `server-tag`, one `shared-network` map |
| `cb-shared-network4-del` | `server-tag`, `name` |

Every request requires an arguments map. Unknown fields, incorrect types,
per-request backend selectors and multiple server tags are rejected. Exactly one
configured PostgreSQL or MySQL backend is required. An explicit `server-tag`
must be `all` or an existing named server; native tag validation applies and
`any` and NUL are forbidden. The selector is native `ALL()` for `all`, otherwise
`ONE(tag)`, which can include common fallback configuration. Results from
different selectors are never merged.

`name` must be a nonempty string of at most 128 bytes, without NUL or surrounding
whitespace. Set accepts exactly `name` and optional integer `valid-lifetime`,
`renew-timer`, `rebind-timer`. Timers must be in `1..2147483647` (the common SQL
integer range); supplied pairs must satisfy renew < rebind < valid. Omitted timers remain unspecified in the
native object. Embedded subnets, network options, inheritance switches, context
and all other fields are rejected, including empty values.

```json
{"command":"cb-shared-network4-set","arguments":{"server-tag":"test-server","shared-network":{"name":"example-network","valid-lifetime":900,"renew-timer":300,"rebind-timer":600}}}
```

**Set creates only a fresh, empty network.** Before either mutating command,
`getSharedNetwork4(..., ANY(), name)` checks the globally unique name, including
networks hidden from the requested selector. Any existing network is refused,
including an identical request, an empty network, and a differently associated
network. Existing deletion is always refused; no native deletion API is called.
The deterministic public refusal text is:

```text
Existing shared-network mutations are unsupported: complete associations and dependencies cannot be verified.
```

This conservative policy preserves existing attributes, options, associations
and membership. It does not mean native network reads omit all associations:
the pinned drivers reconstruct network tags, which the response preserves.
A selected read and separate membership query still do not establish a complete,
atomic dependency snapshot authorizing replacement or deletion. See the
[dependency-safety backlog](dependency-safety-backlog.md).

Replies use result 0 for a nonempty read or successful create, result 3 for an
empty list or missing get/delete, and result 1 for admission, validation or native
failures. Empty/missing deletion performs no native write. Non-error replies use
`DHCPv4 shared-network operation completed.` and these arguments:

```json
{"count":1,"shared-networks":[{"name":"example-network","server-tags":["test-server"],"subnet4":[]}],"server-tag":"test-server","associations-complete":false,"membership-selector":"ANY"}
```

The example abbreviates native network fields; actual rows preserve native
`SharedNetwork4::toElement()` properties and add observed `server-tags`. Network
rows sort by name. Each `subnet4` row preserves native subnet serialization and
observed tags, sorted by subnet ID. Duplicate identities fail closed. Native
properties and options are returned without inferring omitted fields.

**Membership is backend-wide evidence, not the requested consumer view.** Both
pinned SQL drivers implement `getSharedNetworkSubnets4` using `ANY` regardless of
the selector argument. The hook explicitly reports `membership-selector: "ANY"`;
a listed member can belong to another server selector. Do not treat this list as
proof that a particular consumer loaded that member, or as an effective inherited
configuration. `associations-complete: false` prohibits treating these observations
as complete ownership/dependency evidence. Independent `config-get` and packet
observations remain necessary after explicit activation.

Set/delete check mutation admission before parsing or backend access. Their
non-error replies also include `activation-requested: false`. Contract failures
return public validation text and no arguments; native failures return
`Configuration backend operation failed; reconcile persisted state before retrying.`
A create whose selected readback is incomplete returns an error requiring
reconciliation; that error does not establish rollback. No automatic retry or
activation occurs.

Reads and refused requests leave SQL and audit state unchanged. Fresh creation
uses native `createUpdateSharedNetwork4`, with native transaction/audit behavior.
The absence check is not atomic with that upsert: verified exclusive writer
ownership remains mandatory. Admission alone is not fencing. Unknown outcomes
and the existing M22 mutation holds require [operator recovery](operator-recovery.md).
M22 remains PARTIAL; this command does not establish exact deployment convergence.

## M26: option definitions and global options

These are project-specific contracts for pinned Kea 3.2.1, **not commercial
aliases**. Eight registrations:

| Family | Commands |
| --- | --- |
| Definitions | `cb-option-def4-list`, `cb-option-def4-get`, `cb-option-def4-set`, `cb-option-def4-del` |
| Global options | `cb-option4-global-list`, `cb-option4-global-get`, `cb-option4-global-set`, `cb-option4-global-del` |

All requests require an arguments map with `server-tag`: either `all` or an
existing named server. No `any`, multiple tags, backend overrides or unknown
fields are accepted. Exactly one configured PostgreSQL/MySQL backend is required.
Native ONE reads prefer a specific row over the common fallback; ALL selects
common configuration. Views are never combined.

List accepts only `server-tag`. Other operations also require one `option-def`
or `option` map. Identity is explicit `code` (integer 1..254) and `space`
(valid native name, at most 128 bytes, excluding `dhcp6`). Global get/delete
also accept `client-classes`; omission means exactly the empty class list,
not every variant. Class order is retained, never normalized into another identity.

Definition set requires `name`, `code`, `space`, `type`; optional `array`
(boolean, default false), `record-types` (string, default empty), `encapsulate`
(string, default empty) and `user-context` (map). Native OptionDefParser and
CfgOptionDef validation enforce type/record/encapsulation and name/code constraints.
Get/delete accept identity fields only. Text must contain no NUL.

Global set requires `code`, `space`, `data` (string); optional `name`,
`csv-format`, `always-send`, `never-send`, `client-classes`, `user-context`.
Flags must be native booleans; classes must be distinct nonempty strings and
context a map. `persistent` is not a request field: use native `always-send`.
Unknown fields are rejected. Text is bounded to 65535 bytes and cannot contain NUL.

Native OptionDataParser supplies CSV and binary encoding. CSV requires a
selected SQL definition or native built-in/vendor/last-resort definition;
process-global runtime definitions are deliberately excluded to prevent
cross-selector/stale decoding. Supported examples include strings, integers,
IPv4 addresses, address arrays, record values, hexadecimal and valid empty
binary payloads. Binary readback may uppercase hexadecimal; payload bytes,
rather than textual letter case, establish encoding equivalence.

Example creation (requires explicit mutation admission):

```json
{"command":"cb-option-def4-set","arguments":{"server-tag":"all","option-def":{"name":"example-text","code":224,"space":"dhcp4","type":"string"}}}
```

```json
{"command":"cb-option4-global-set","arguments":{"server-tag":"all","option":{"code":224,"space":"dhcp4","data":"example","always-send":true}}}
```

**Set is create-only.** A visible existing identity is refused even when its
payload matches. Existing delete is also refused. Native reads hide other
associations; whole-row mutation and limited native dependency checks cannot
prove safe update/delete. No force or cascade is exposed. Missing delete returns
an empty result without invoking native delete. These are essential functional
exclusions, so M26 remains PARTIAL.

Every write checks admission before parsing/backend access. Reads and refused
requests leave native data/audit unchanged. Successful persistence does not
activate runtime configuration; pull/reload/restart remains an explicit operator
action. Existing exclusive-writer, uncertain-outcome and M22 recovery rules apply.

Responses use result 0 for a nonempty successful view/create, 3 for empty
list/get/missing delete, 1 for contract/admission/backend failure. Successful/empty
arguments contain `count`, `option-defs` or `options`, `server-tag` and
`associations-complete: false`. Mutation replies also contain
`activation-requested: false`. Each row preserves native serialization and
observed `server-tags`; these are incomplete selector metadata, not complete
association ownership. Stable ordering uses space/code and native class identity.
Safe contract errors are public; other exceptions return the generic backend
failure asking for reconciliation before retry. No automatic retries occur.


## M25 server records and scalar globals

These eight project-specific commands are not commercial aliases. All use the
sole configured native SQL backend; no request chooses another backend. Writes
require explicit mutation admission before parsing and never request activation.
Apply the [recovery procedure](operator-recovery.md) before further writes after
an uncertain outcome. Native exceptions return result 1 and the generic text
`Configuration backend operation failed; reconcile persisted state before retrying.`
Validation errors use result 1 and public contract text; no SQL error is exposed.
Successful nonempty results use 0; empty/missing results use 3. Unknown fields
and incorrect types are rejected. Each admitted mutation invokes one native
write operation; refused and missing-delete requests perform none.

### Server records

| Command | Exact arguments |
| --- | --- |
| `cb-server4-list` | absent or empty map |
| `cb-server4-get` | `{"server-tag":"example"}` |
| `cb-server4-set` | `{"server-tag":"example","description":"operator description"}` |
| `cb-server4-del` | `{"server-tag":"example"}` |

Tags must already be canonical lowercase, without surrounding whitespace, at
most 256 characters, nonempty and without NUL. Reserved `all` and `any` cannot
identify records. Description is required, string, at most 65536 bytes and
without NUL; an empty description is allowed. Set creates or updates the
identified record, preserving other records and existing associations.

Arguments in replies contain `count` and `servers`, a list of native
`{"server-tag":...,"description":...}` objects sorted by tag. Set/delete add
`"activation-requested":false`. Native list excludes the logical all record.
Success text is `DHCPv4 server records retrieved.`; empty text is
`DHCPv4 server record not found.`

**Existing-record deletion is excluded.** It returns result 1 with exactly
`Server deletion is unsupported: native orphan cleanup cannot be verified safe.`
A missing record returns result 3, count 0 and an empty servers list.
No native delete is invoked. Native deletion in both pinned drivers purges
unassigned global parameters, option definitions and global options, including
orphans unrelated to the requested server. Native read APIs cannot enumerate
all those orphan sets to prove cleanup harmless. Association detachment and
client-class restrictions also need wider qualification. Use no manual
acknowledgement to bypass this refusal.

### Global parameters

| Command | Exact arguments |
| --- | --- |
| `cb-global-parameter4-list` | `{"server-tag":"example"}` |
| `cb-global-parameter4-get` | `{"server-tag":"example","name":"authoritative"}` |
| `cb-global-parameter4-set` | `{"server-tag":"example","name":"authoritative","value":false}` |
| `cb-global-parameter4-del` | `{"server-tag":"example","name":"authoritative"}` |

A named server must exist; logical `all` selects common configuration. Other
tag validation matches server commands. Named reads include common fallback.
No ANY, UNASSIGNED, multiple-tag or batch-write interface is provided. Tags
remain associations, not independent mutation namespaces.

**Set currently creates only when the selected native view is empty. Existing
global update/delete is excluded.** Both return result 1 with exactly
`Global mutation is unsupported for existing values: native readback cannot verify complete associations.`
This includes common fallback. Missing delete returns result 3 and performs no
native write. Native reads filter associations and collapse common/explicit
rows; a single returned tag cannot prove exclusive ownership. Native SQL
update/delete affects whole rows and could change other associations. Even
an apparently single-association existing value is therefore refused. Repeated
set is also refused; no idempotent update claim is made.

Get/set/delete accept this bounded name/type table:

| Names | Native JSON type and limits |
| --- | --- |
| valid-lifetime, min-valid-lifetime, max-valid-lifetime | Integer, 1..4294967295 |
| renew-timer, rebind-timer, decline-probation-period | Integer, 0..4294967295 |
| echo-client-id, match-client-id, authoritative, calculate-tee-times | Boolean |
| t1-percent, t2-percent | Real, finite and strictly between 0 and 1 |
| next-server | String containing an IPv4 address, at most 63 bytes |
| server-hostname | String, at most 63 bytes |
| boot-file-name | String, at most 127 bytes |

Strings reject NUL. Integer and real types are distinct: use `0.4`, not `1`,
for a percentage. No map, list, null, dotted name or arbitrary JSON setting is
accepted. Cross-parameter relationships and consumer inheritance still require
explicit activation validation; a successful SQL write does not prove an
activatable or converged consumer configuration.

Reply arguments contain `count`, `parameters` and the requested `server-tag`.
Each row is `{"name":...,"value":...,"server-tags":[...]}`; tags are the
associations observable in the selected native view, including `all` on
fallback. **They are not a complete association inventory.** Native filtering
can hide additional associations and collapse same-name rows before the hook
receives them. Rows are sorted by name; any duplicate names still exposed fail
closed. List preserves native observed names/values, including names unsupported
by get/set/delete. Missing delete returns an empty parameters list and count 0.
Set/delete add `"activation-requested":false`. All non-error replies use
`DHCPv4 global parameter operation completed.` as text.

This representation preserves native scalar JSON types. The pinned
`StampedValue` serializer does not support arbitrary compound values: maps
accepted by its constructor fail string serialization; list/null are rejected.
The controller reconstructs some dotted globals and specially encoded lists,
but this is not a general JSON round trip. Compound support remains unresolved,
as recorded in the [matrix](compatibility-matrix.md). No flattening is attempted.


## Mutation admission (current development version)

All set/delete commands, including the M25 server/global families, require the hook-library parameter
`"allow-mutations": true`. Omission, an empty parameters map or explicit false
denies these commands before argument validation or any backend access. Commands
remain registered. Denial returns exactly:

```json
{
  "result": 1,
  "text": "Mutations are disabled; configure allow-mutations: true on the designated administrative writer."
}
```

This rejection makes no SQL mutation, audit change or activation request.
Diagnostic/list/get remain available subject to their normal backend contracts.
For an admitted writer, validation, generic native failures, transactions and
persistence/activation behavior below remain unchanged.

Use Kea's native `hooks-libraries` entry with a `parameters` map. Only the
`allow-mutations` key and native boolean values are accepted. Unknown keys,
strings, numbers, null, lists and maps as its value fail initialization;
non-map parameters also fail. Admission resets to false before load and before
unload; it becomes true only after successful initialization. Kea owns command
deregistration, including failed-load cleanup. Main-thread command/lifecycle
serialization requires no new synchronization.

`db-commands-diagnostic` reports `allow-mutations` separately from the unchanged
`mutations-supported` capability flag. Admission cannot be switched through a
hook command. A privileged native configuration reload can change parameters;
protect that control channel and configuration ownership.

This is a breaking default change from published v0.1.0. It is not cross-process
fencing or database authorization; external writers can bypass it. See
[migration guidance](mutation-admission.md) and the
[qualification status](development-roadmap.md).

## Retrieve one subnet: `cb-subnet4-get`

```json
{"command":"cb-subnet4-get","arguments":{"id":900,"server-tag":"test-server"}}
```

Alternatively use `"subnet":"198.18.0.0/24"` instead of `id`. Exactly one
identity is required. The only optional field is `server-tag`, defaulting to
the active server tag, or `all` if empty. IDs, prefixes and tag strings obey the
syntactic set validation rules below. Unknown fields, both identities, malformed identities,
multiple tags, `any` and per-request backend selectors are rejected. Exactly one
configured native PostgreSQL/MySQL backend is required.

The response has `result: 0`, `text: "DHCPv4 subnet retrieved."` and
`arguments: {"server-tag": "test-server", "subnet4": [SUBNET]}` where `SUBNET`
is the complete native `Subnet4::toElement()` serialization, with the same shape
and defaults as `cb-subnet4-list`. This is stored configuration, not an effective
runtime configuration or a lease report. Shared-network members are rejected
because flat serialization omits their inherited context.

No matching visible subnet returns exactly:

```json
{
  "result": 3,
  "text": "DHCPv4 subnet not found.",
  "arguments": {"server-tag": "test-server", "subnet4": []}
}
```

`ONE(tag)` includes universal `all` objects. `all` selects only universal objects.
Reads do not require a named server record; universal objects can still match.
Other tags and unassigned rows are invisible. Reads do not change SQL, audit,
timestamps, runtime or leases. Native read errors have `result: 1`, generic text
`Configuration backend read failed or unavailable.` and no `arguments`.

## Delete one subnet: `cb-subnet4-del`

```json
{
  "command": "cb-subnet4-del",
  "arguments": {"id": 900, "server-tag": "test-server", "preserve-leases": true}
}
```

Use `subnet` instead of `id` to delete by canonical IPv4 prefix. Exactly one
identity, an explicit `server-tag`, and the boolean `preserve-leases: true` are
required; these are the only allowed fields. The acknowledgement records the
caller's acceptance of retained leases and separate activation; it never scans
or changes leases. Missing, false, string or numeric acknowledgements are errors.
Backend count/type and identity validation match get. A named server must exist.

The subnet must have exactly one association matching the requested tag.
Universal deletion requires explicit `"server-tag":"all"`. Unlike get, a
specific tag cannot delete a universal subnet. Differently tagged, unassigned,
multiply associated and shared-network subnets are rejected before mutation.
Deletion removes the whole subnet and native dependent pools/options/associations;
it does not remove the server record or detach just one association.

Success is exactly:

```json
{
  "result": 0,
  "text": "DHCPv4 subnet deleted; leases retained; activation required.",
  "arguments": {
    "server-tag": "test-server",
    "deleted": 1,
    "leases-deleted": false,
    "activation-requested": false
  }
}
```

A missing identity returns the same arguments with `deleted: 0`, `result: 3`,
and `text: "DHCPv4 subnet not found."`; this path does not create an audit revision.
Contract violations return `result: 1`, explanatory text and no `arguments`.
Native exceptions use `Configuration backend deletion failed or unavailable;
reconcile backend state before retrying.` Connection loss can make commit outcome
uncertain; inspect backend state before retrying. No automatic retry is performed.

The native delete owns one transaction including child removal, audit entry and
revision timestamp. Failed transactions roll back their table changes;
nontransactional sequence/auto-increment counters can advance. Validation reads
are outside that transaction: **serialize independent configuration writers**.
The hook cannot atomically compare a preflight object and delete it.

SQL deletion is immediately visible to backend reads. Active runtime configuration
can continue allocating until a separately requested `config-backend-pull`, reload
or restart succeeds on every affected server. Check `config-get` and packet
behavior; command success alone does not establish activation. Retained leases
are not revoked, and clients can continue using them until expiry. Do not reuse
subnet IDs, prefixes or address space while retained leases could conflict.
See [upstream findings and operational limits](subnet-lifecycle.md).

## Create/update: `cb-subnet4-set`

`cb-subnet4-set` creates or updates one standalone subnet in one configured SQL
configuration backend. Verified against unmodified Kea 3.2.1, PostgreSQL 15.19
and MariaDB 10.11.19 through the native MySQL backend for Milestone 4.
Milestone 5 pool and packet results are recorded separately in
[pools](pools.md) after verification. Kea 3.0.4 and Oracle
MySQL writes are unverified. This is an independent command contract.

## Request and response

Send through Kea's native control channel:

```json
{
  "command": "cb-subnet4-set",
  "arguments": {
    "server-tag": "test-server",
    "subnet4": {
      "id": 900,
      "subnet": "198.18.0.0/24",
      "valid-lifetime": 600,
      "pools": [
        {"start": "198.18.0.10", "end": "198.18.0.20"}
      ]
    }
  }
}
```

`server-tag` and `subnet4` are required and are the only top-level argument
fields. `subnet4` is one map, not an array: `id`, `subnet`, and `valid-lifetime`
are required. Optional fields are `pools`, `renew-timer`, `rebind-timer`,
`next-server`, `server-hostname`, `boot-file-name`, `client-classes` and
`evaluate-additional-classes`. Unknown fields are errors even when empty.
There are no defaults taken from active server globals or shared networks.

- `id` and `valid-lifetime` must be JSON integers in `1..4294967294`. Booleans,
  floats, numeric strings, zero and the unsigned maximum are rejected.
- `subnet` must be canonical IPv4 CIDR with length `0..32`, network bits only,
  and canonical decimal prefix length. IPv6, host bits and `/024` are rejected.
- `server-tag` is explicit, lowercase, with no surrounding whitespace; Kea's
  native `ServerTag` validates its remaining constraints (1..256 characters,
  reserved `any` rejected). A named server must already exist. Reserved `all`
  selects the native universal association. The command creates no server record.
- `renew-timer` and `rebind-timer` are integers in `0..2147483647` (the
  cross-backend signed SQL limit). Nonzero values must be below valid lifetime;
  when both are nonzero renewal must not exceed rebinding. Zero is unspecified.
- `next-server` is an IPv4 string. `server-hostname` and `boot-file-name` are
  strings without NUL, limited to 63 and 127 bytes respectively. Empty strings
  clear boot strings; `0.0.0.0` clears next-server.
- `client-classes` and `evaluate-additional-classes` are lists of distinct,
  nonempty strings without NUL. Empty lists clear these restrictions. Defining
  or ordering client classes is outside this command.
- `pools`, when present, is a list of maps. Use either string `start` and `end`
  or one canonical IPv4 CIDR string `pool`; do not mix the forms. Each range
  must lie inside the subnet. Kea validates order, containment and overlap,
  including duplicates. Each pool may also contain `client-classes` and
  `evaluate-additional-classes` under the same list rules. Prefix notation
  normalizes to an address range; notation and SQL pool IDs are not preserved.
  IPv6, unknown fields and zero endpoints are rejected: native SQL reads omit
  zero-endpoint pools. Pool options, context and other pool attributes remain
  unsupported for writes.
- Exactly one SQL backend must appear in active `config-control`; its native
  type must be `postgresql` or `mysql`. No per-command backend selector exists.

Success means the native backend call committed:

```json
{
  "result": 0,
  "text": "DHCPv4 subnet persisted.",
  "arguments": {
    "server-tag": "test-server",
    "subnet4": {
      "id": 900,
      "subnet": "198.18.0.0/24",
      "valid-lifetime": 600,
      "pools": [
        {"start": "198.18.0.10", "end": "198.18.0.20"}
      ]
    },
    "persisted": true,
    "activation-requested": false
  }
}
```

The response echoes the validated request object, including `pools` only when
supplied. It does not expand preserved pools into an omitted field. It is not
effective runtime configuration. Errors have `result: 1`, explanatory `text`, and no `arguments`.
Validation errors identify the failed contract. Native exceptions return:
`Configuration backend write failed or unavailable; reconcile backend state before retrying.`
Raw exception text and connection details are not returned. Kea's own logs may
contain database details and must be protected.

## Create, update and conflict rules

The ID identifies the object. An absent ID creates it; an existing ID updates
its prefix, lifetime and pool collection only when its stored configuration has
exactly the supported native representation and exactly the requested server
association.
The hook reconstructs the supported native subnet and pool attributes from a
fresh read and compares the complete native serialization with that bounded
reconstruction. Any difference refuses the write. Subnet/pool options, context,
unsupported lifetimes, relay and other attributes therefore remain protected;
shared-network membership is refused before reconstruction. This check does not
claim native serialization exposes every SQL dependency.

Required ID, prefix and lifetime come from the request. Omitted supported optional
attributes preserve stored values; supplied values replace them after validation.
On creation omitted values use native constructor defaults. Null is rejected for
all accepted fields. This is a typed, bounded merge, not a generic JSON patch.
The legacy unknown-subnet-field error text remains unchanged for compatibility.
See the [capability inventory](subnet4-capabilities.md) for the SQL/readback limits.

Omitting `pools` on an existing subnet preserves its pools from a fresh native
backend read. Omitting it on creation creates no pools. If preserved pools do not
fit a changed prefix, the request fails; supply an explicit replacement list.
An explicit nonempty list replaces the whole pool collection. An explicit `[]`
removes all pools only when safe. Any existing pool with class restrictions
refuses a supplied replacement list, even an identical list or `[]`; omission
preserves these classes. Existing scoped options or unsupported attributes refuse
the entire update, including omitted pools. No pool-level command is added.

A prefix owned by another ID is rejected, even if that object is associated
with another server or unassigned. Unassigned and multiply associated existing
objects cannot be updated; server retagging is unsupported. Two different
prefixes that overlap as IP ranges are not prohibited by this minimal contract;
this hook does not implement full server-wide configuration validation.

Input validation and native object construction finish before any mutation API
is invoked. Native ID/prefix lookups use `ServerSelector::ANY()` so other tags
cannot hide a conflict. The write uses `ALL()` for `all`, otherwise `ONE(tag)`.
The active daemon tag does not override this explicit write tag. Listing still
follows the active tag, so a successfully written subnet may be hidden from that
daemon's `cb-subnet4-list` result until the active tag matches.

## Integrity boundary

The hook calls `ConfigBackendPoolDHCPv4::createUpdateSubnet4` once. Both native
drivers wrap the subnet, its pools, associations and audit records in one
transaction.
The drivers delete old pools on update and insert the supplied collection; the
hook explicitly reconstructs supported stored pools when the field is omitted.
Physical pool IDs and pool modification timestamps are regenerated by native
replacement; they are not stable identities or optimistic concurrency tokens.
Tests force an association INSERT failure after a subnet INSERT or UPDATE and
compare every official table before/after: both engines roll back the subnet,
association changes and audit records. Sequence/auto-increment counters can
advance despite rollback; gap-free identifiers are not guaranteed.

**Coordinate exclusive configuration writers.** The native API provides no public
transaction or compare-and-swap spanning preflight reads and the upsert. Those
reads cannot lock out another Kea process, administrator or backend client.
Commands handled on this daemon's main command loop are synchronous, including
with packet multithreading enabled; that does not serialize independent writers.
Concurrent external writers are unsupported. If that coordination cannot be
provided, do not use this command: its conflict and preservation checks cannot
provide a cross-process consistency guarantee. See [upstream evidence](backend-behavior.md#native-subnet-mutations).

A connection failure during commit or response delivery may have an uncertain
outcome. No automatic write retry is performed. Reconcile stored ID, prefix and
associations after recovery before retrying. Tests prove controlled outage
errors and late-statement rollback; they do not prove a deterministic outcome
for network loss at the exact commit boundary. Kea owns reconnection.

Native audit entries and modification timestamps are created on successful
writes, including updates. Subnet timestamps use the server's local clock with
second precision; audit revisions have their own native timestamps. These are
not revision tokens. Updates in the same second need not change the subnet
timestamp. No custom audit schema is introduced.

## Runtime activation

The command does not reload, pull, restart, or alter `CfgMgr`. In tests,
`config-fetch-wait-time` is zero: create/update is immediately visible through
backend reads while `config-get` retains the prior active subnet configuration.
An explicit native `config-backend-pull` activates new and changed subnets;
`config-reload` and a real daemon restart also load persisted data. The active
server tag and native inheritance rules still apply. Independently configured
periodic backend fetching can activate data later without a manual command.

For controlled activation, inspect persisted data, then issue the native pull
or reload separately and inspect its result and `config-get`. A failed pull is
separate from a committed write. Inspect the native activation response and
active configuration before assuming traffic uses the new pools. Restore backend
availability or repair the separate runtime configuration, reconcile SQL with
`cb-subnet4-list`, and retry native activation deliberately. No two-phase
persistence/activation guarantee or automatic rollback is implemented.

Kea can remove its live backend connection after a failed reload or backend
outage. A later pull can then succeed without applying data. Confirm connectivity
and inspect active `config-get`; a corrected reload can restore the connection.
The packet tests compare all SQL table contents across failed activation before
performing this explicit recovery.

The ordinary SQL suites use no DHCP interfaces. The opt-in packet suites start
unmodified Kea in a disposable Linux user/network namespace with loopback only.
A relay sends real DHCPDISCOVER and DHCPREQUEST datagrams on test UDP ports
1067/1068. Checks distinguish SQL persistence, backend reconstruction, native
active configuration, OFFER/ACK and a persisted memfile lease. These suites also
exercise empty pools, replacement/reload, restart and failed activation without
rolling back SQL. See [packet architecture and results](pools.md). Effective
inherited runtime defaults may differ from the stored object.

## Test coverage and limits

`tests/mutation.py` is shared by both disposable SQL harnesses. It covers create,
update, explicit universal/specific association, strict field validation,
identity/prefix conflicts, richer-object and retagging refusal, unrelated-subnet
preservation, all-table rollback, audit/timestamp changes, explicit pull/reload
activation and daemon restart persistence, with threading disabled and enabled.
Existing read/recovery tests remain, including disconnected write failures and
multiple-backend rejection. The historical CTest names `postgresql_read` and
`mysql_read` now run both read and mutation phases. See [PostgreSQL](postgresql.md)
and [MariaDB](mysql.md) for isolated setup and privilege requirements.

Milestone 5 extends this shared suite with pool creation, replacement, omission,
empty lists, validation and late-failure rollback. Opt-in `postgresql_dhcp` and
`mysql_dhcp` add real packet checks in both threading modes. Both engines passed
these checks; see [the verification record](pools.md) for scope and limitations.

Options, classes, shared networks, server retagging, DHCPv6,
batch writes, optimistic concurrency, automatic activation, production load and
mixed-release compatibility remain unimplemented or unverified as applicable.


Cross-process writes remain unsupported: coordinate a single writer across all
server tags and all tools using the database. Both successful responses can still
mean one request overwrote another; tags do not create independent ID/prefix
namespaces. Reconcile stored identities, associations and pools after errors or
lost responses before retrying. Activate and inspect each Kea process separately.
See [multi-process evidence and guarantees](backend-behavior.md#multi-process-validation)
and [the repeatable validation command](development.md#multi-process-sql-validation).
