# Minimal DHCPv4 subnet mutation

`cb-subnet4-set` creates or updates one standalone subnet in one configured SQL
configuration backend. Verified against unmodified Kea 3.2.1, PostgreSQL 15.19
and MariaDB 10.11.19 through the native MySQL backend. Kea 3.0.4 and Oracle
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
      "valid-lifetime": 600
    }
  }
}
```

All five fields shown inside `arguments` are required. Only `server-tag` and
`subnet4` are allowed at its top level; `subnet4` is one map, not an array, with
exactly `id`, `subnet`, and `valid-lifetime`. Unknown fields are errors even when
empty. There are no defaults taken from active server globals or shared networks.

- `id` and `valid-lifetime` must be JSON integers in `1..4294967294`. Booleans,
  floats, numeric strings, zero and the unsigned maximum are rejected.
- `subnet` must be canonical IPv4 CIDR with length `0..32`, network bits only,
  and canonical decimal prefix length. IPv6, host bits and `/024` are rejected.
- `server-tag` is explicit, lowercase, with no surrounding whitespace; Kea's
  native `ServerTag` validates its remaining constraints (1..256 characters,
  reserved `any` rejected). A named server must already exist. Reserved `all`
  selects the native universal association. The command creates no server record.
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
      "valid-lifetime": 600
    },
    "persisted": true,
    "activation-requested": false
  }
}
```

The response echoes the validated minimal object; it is not effective runtime
configuration. Errors have `result: 1`, explanatory `text`, and no `arguments`.
Validation errors identify the failed contract. Native exceptions return:
`Configuration backend write failed or unavailable; reconcile backend state before retrying.`
Raw exception text and connection details are not returned. Kea's own logs may
contain database details and must be protected.

## Create, update and conflict rules

The ID identifies the object. An absent ID creates it; an existing ID updates
its prefix and lifetime only when its stored configuration has exactly the
minimal native representation and exactly the requested server association.
The hook compares native serialization against a minimal `Subnet4` baseline,
with renew/rebind timers zero and no pools, options or other extra settings.
An existing richer object is rejected, including when unsupported values would
otherwise be overwritten by Kea's whole-object update. This is replacement of
a minimal object, not a general merge or patch command.

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
drivers wrap the subnet, its associations and audit records in one transaction.
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
separate from a committed write. No two-phase persistence/activation guarantee
or activation-failure recovery is implemented.

The tests use no DHCP interfaces or packet sockets. They verify active runtime
configuration through native `config-get`, not successful DHCP allocation.
This milestone forbids pools; the created standalone subnets have no dynamic
allocation pool. Positive packet/allocation proof remains a later milestone
with an explicit pool contract. Effective inherited runtime defaults may differ
from the minimal stored object.

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

Deletion, pools, options, classes, shared networks, server creation/retagging,
DHCPv6, batch writes, optimistic concurrency, automatic activation, production
load, allocation proof and mixed-release compatibility remain unimplemented or
unverified as applicable.
