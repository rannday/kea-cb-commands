# DHCPv4 subnet and pool capabilities after M28

Baseline: ISC Kea 3.2.1, commit
`1737462bc79276e3269304ea8cd3d1c03400e30d`. M28 extends the existing
project contract; it adds no command registrations or commercial aliases.
Production readiness remains **NO-GO**. Complete native subnet replacement and
exact persisted/active equivalence remain unqualified.

## Native versus SQL-backed fields

The source of truth for SQL persistence is the pinned driver binding and
readback code, not the set of keys accepted by Kea's JSON parser. Relevant
sources are the [PostgreSQL DHCPv4 driver](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/hooks/dhcp/pgsql/pgsql_cb_dhcp4.cc),
[MySQL DHCPv4 driver](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/hooks/dhcp/mysql/mysql_cb_dhcp4.cc),
[native pool model](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/lib/dhcpsrv/pool.cc)
and [DHCPv4 backend interface](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/lib/dhcpsrv/config_backend_dhcp4.h).

| Attribute group | Native object and SQL persistence/readback | M28 writes | Independent runtime evidence |
| --- | --- | --- | --- |
| Subnet ID, IPv4 prefix, valid lifetime | Native and SQL-backed | Required; existing identity/association checks retained | Active configuration, allocation and lease lifetime |
| Minimum/maximum lifetime | Native and SQL-backed | No separate bounds accepted; nontrivial existing bounds refuse update | Outside M28 packet qualification |
| Renewal/rebinding timers | Native and SQL-backed | Optional integers 0..2147483647, validated against lifetime | Active configuration and OFFER/ACK T1/T2 |
| Next-server, server hostname, boot file | Native and SQL-backed | Optional validated IPv4/string fields | Active configuration; boot file in actual OFFER/ACK |
| Client classes, evaluate-additional-classes | Native and SQL-backed on subnet and pool | Optional distinct string lists; omitted values preserved | SQL/native round-trip; basic allocation restriction tested; evaluation ordering not qualified |
| Pool range | Native and SQL-backed | Start/end or canonical CIDR; containment/overlap validation | Actual allocation inside configured range |
| Pool order, SQL ID and timestamps | Native collection and SQL row metadata; drivers reconstruct collections | No ordering or stable physical-ID contract; replacement recreates IDs | Allocation does not establish stable identity/order |
| Server associations | Native subnet tags reconstructed before selector filtering | Exactly one existing association matching explicit request; no retagging | SQL association assertions; runtime selector alone is insufficient |
| Shared-network membership | Native and SQL-backed; absent replacement binds NULL | All member subnet updates and membership changes refused | Existing M27 runtime/packet inheritance fixture retained |
| Subnet/pool options | Native and SQL-backed; scoped association metadata incomplete | Existing options refuse entire subnet update; no option fields accepted | Existing scoped-option precedence fixture retained |
| Relay addresses, interface | Native and SQL-backed | Unsupported; existing nondefault values refuse update | Not qualified by M28 |
| DHCPv4-over-DHCPv6 interface/interface-ID/subnet | Native and SQL-backed | Unsupported | Not qualified by M28 |
| Match-client-id, authoritative, reservation-related flags | Native and SQL-backed | Unsupported | Not qualified by M28 |
| Calculate-tee-times, T1/T2 percentages | Native and SQL-backed | Unsupported | Not qualified by M28 |
| DDNS controls/name/TTL fields, cache controls, offer lifetime, allocator | Native subnet and SQL-backed | Unsupported | Not qualified by M28 |
| User context | Native subnet/pool and SQL-backed | Unsupported; existing context refuses update | SQL/native evidence, not a packet property |
| Pool DDNS/hostname overrides and explicit JSON pool identity | Native model has attributes beyond the SQL pool binding set | Unsupported; do not infer SQL support from object setters | Not qualified |
| Host reservation records and daemon/network configuration | Separate backend or JSON concerns, not embedded subnet CRUD | Outside this command's scope | Existing leases are retained; no host-reservation management |

PostgreSQL binding code around lines 876–1075 and the corresponding MySQL
upsert show full replacement behavior: old pools, subnet options and server
links are removed and recreated. A pool stores range, subnet, classes, context
and modification time, with options separately stored. The SQL pool reader
ignores physical row identity when reconstructing the runtime pool. Pool JSON
fields therefore do not all have matching persistent columns.

Commercial subnet SET is full replacement and requires explicit membership
representation. M28's preserve-on-omission contract differs deliberately. See
the [commercial matrix](compatibility-matrix.md); functionality is partial and
exact commercial compatibility remains zero.

## Preservation algorithm and invariants

1. Validate the request and enforce mutation admission at the existing boundary.
2. Resolve the sole configured native SQL backend for this invocation.
3. Read ID and prefix conflicts through ANY. Require one exact server association
   and an existing named server when applicable.
4. Refuse shared-network members. Reconstruct only the explicitly supported
   native fields, including all supported pool classes.
5. Compare the entire reconstructed native serialization with the existing
   native serialization. Any difference refuses the write. This is a guard
   against dropping visible unsupported configuration, not proof that native
   readback exposes every database property.
6. Merge only the whitelisted typed attributes: required ID/prefix/lifetime from
   the request; optional fields from the request when supplied, otherwise from
   the fresh stored object. Validate the complete merged native object.
7. Invoke native create/update once. Never retry or activate automatically.

Omission preserves supported optional fields. Null is invalid. Empty boot strings
and class lists clear those properties; zero clears timers and next-server.
Omitted pools preserve ranges/classes. A supplied pool list replaces the list;
an empty list removes it only when the same safety preconditions pass.
Existing pool class restrictions refuse any supplied pool list, even identical
input. Options/context/unsupported fields refuse the entire update, including
when pools were omitted. Prefix changes must still contain preserved pools.

SQL pool row IDs and timestamps may change on an accepted update, and native
audit entries record the mutation. Audit history is preserved, not byte-identical
after a successful write. Refused operations must leave all configuration and
audit tables unchanged. Diagnostic SQL in tests verifies those assertions and
checks unrelated configuration; no production SQL is introduced.

## Concurrency, associations and observability limits

There is no public compare-and-swap or revision precondition on native
create/update. Modification timestamps and audit revisions provide observations,
not a transaction covering our preflight and write. The exclusive designated
writer remains mandatory; external writers can race these checks.

Native scoped-option reads omit association information needed for lossless
reconstruction. A shared-network name alone cannot establish safe membership
mutation. These gaps keep options and member subnet updates refused.
M22's durable workflow holds, fresh reconciliation requirements and incomplete
exact-equivalence findings remain unchanged. A successful write or reload is
not convergence evidence.

Runtime tests inspect each applicable active configuration and actual DHCP
OFFER/ACK fields. This verifies selected fields, not every SQL-backed attribute,
class evaluation order, inherited configuration or arbitrary consumer views.
The [dependency backlog](dependency-safety-backlog.md) tracks remaining work.
