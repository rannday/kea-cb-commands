# DHCPv4 subnet lifecycle commands

## Mutation admission (current development version)

`cb-subnet4-set` and `cb-subnet4-del` require the hook-library parameter
`"allow-mutations": true`. Omission, an empty parameters map or explicit false
denies both commands before argument validation or any backend access. Commands
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
are required; `pools` is optional. Unknown fields are errors even when empty.
There are no defaults taken from active server globals or shared networks.

- `id` and `valid-lifetime` must be JSON integers in `1..4294967294`. Booleans,
  floats, numeric strings, zero and the unsigned maximum are rejected.
- `subnet` must be canonical IPv4 CIDR with length `0..32`, network bits only,
  and canonical decimal prefix length. IPv6, host bits and `/024` are rejected.
- `server-tag` is explicit, lowercase, with no surrounding whitespace; Kea's
  native `ServerTag` validates its remaining constraints (1..256 characters,
  reserved `any` rejected). A named server must already exist. Reserved `all`
  selects the native universal association. The command creates no server record.
- `pools`, when present, is a list of maps containing exactly the string fields
  `start` and `end`. Each pair must form a valid IPv4 range inside the subnet.
  Kea validates range order, subnet membership and overlap, including duplicates.
  IPv6, malformed structures, unsupported pool fields and `0.0.0.0` endpoints
  are rejected. Native SQL reads omit a range with a zero endpoint; rejecting it
  prevents silent loss on reconstruction. Options, classes, reservations,
  exclusions and allocation policies are unsupported.
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
The hook compares native serialization against a minimal `Subnet4` baseline,
with renew/rebind timers zero and basic address pools only. Pool-level options,
classes, context and other extra settings are refused along with richer subnet
settings.
An existing richer object is rejected, including when unsupported values would
otherwise be overwritten by Kea's whole-object update. This is replacement of
a supported object, not a general merge or patch command.

Omitting `pools` on an existing subnet preserves its pools from a fresh native
backend read. Omitting it on creation creates no pools. If preserved pools do not
fit a changed prefix, the request fails; supply an explicit replacement list.
An explicit nonempty list replaces the whole pool collection. An explicit `[]`
removes all pools. Rich existing objects remain protected even when a replacement
list is supplied. No pool-level mutation command is added.

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
hook explicitly copies stored basic pools when the field is omitted.
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

Options, classes, shared networks, server creation/retagging, DHCPv6,
batch writes, optimistic concurrency, automatic activation, production load and
mixed-release compatibility remain unimplemented or unverified as applicable.


Cross-process writes remain unsupported: coordinate a single writer across all
server tags and all tools using the database. Both successful responses can still
mean one request overwrote another; tags do not create independent ID/prefix
namespaces. Reconcile stored identities, associations and pools after errors or
lost responses before retrying. Activate and inspect each Kea process separately.
See [multi-process evidence and guarantees](backend-behavior.md#multi-process-validation)
and [the repeatable validation command](development.md#multi-process-sql-validation).
