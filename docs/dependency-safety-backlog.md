# Dependency safety backlog

This backlog records what must be proved before widening existing-object mutation
support. Baseline: public ISC Kea 3.2.1 source commit
`1737462bc79276e3269304ea8cd3d1c03400e30d`. It does not authorize new commands,
production SQL, automatic activation or retries. M22 remains PARTIAL and production
readiness remains NO-GO. Current contracts are in [commands](commands.md);
[reconciliation evidence](reconciliation-evidence.md) and
[operator recovery](operator-recovery.md) define the deployment limits.

## Evidence boundaries

1. **Native evidence:** selected objects, native serialization, observed server
   tags, network membership queries and native audit observations. Capabilities
   differ by object family. Never substitute a selected view for a complete SQL
   association/dependency inventory.
2. **Diagnostic SQL evidence:** disposable test databases can expose exact row
   identities, join-table associations, options at every scope, memberships and
   before/after audit contents. Read-only SQL can support operator diagnostics,
   but it is not a production-hook dependency or a new mutation interface.
3. **Evidence not supplied by either readback alone:** fresh exclusive writer
   ownership, an atomic relationship between preflight and mutation, operator
   intent, consumer process identity and complete effective runtime equivalence.
   A SQL snapshot cannot establish these operational facts. Neither local
   admission nor a durable local hold constitutes distributed fencing.

Pinned native drivers own their transactions, but the public backend interface
provides no compare-and-swap or transaction spanning these hook preflight reads
and the subsequent native mutation. Timestamps and audit IDs are observations,
not an atomic conditional-write token. Any future permission to mutate must
retain exclusive-writer and uncertain-outcome recovery requirements.

## Family-specific work

| Operation currently limited | Evidence available through native APIs | Diagnostic SQL evidence required for qualification | Conditions needed before permitting it |
| --- | --- | --- | --- |
| Existing server deletion | Server identity/description and selected configuration reads; `deleteServer4` exists | All associations to globals, definitions, options, networks, subnets and classes; exact cascade/unassignment and audit effects in both backends | Prove no dependent association exists, or define an explicitly authorized complete dependency plan. Current hook cannot certify an unreferenced server through its existing native reads. Refuse deletion meanwhile. |
| Existing scalar-global update/delete | Selected `StampedValue`, scalar type and observed tags; native upsert/delete | Exact same-name row identities, full associations and fallback relationships; whole-row update/delete effects | An unambiguous row and complete association set plus replacement semantics preserving other selectors. Selected readback may filter/collapse associations, so a matching value alone cannot authorize mutation. |
| Existing option-definition update/delete | Selected native definitions, code/space/type and observed tags | All associations and every dependent option across global, network, subnet, pool and class scopes; stored CSV/binary representation | Prove no dependents or prove all remain correctly decoded with the new definition. Validate duplicate name/code, encapsulation and selector effects. No automatic cascade or re-encoding. |
| Existing global-option update/delete | Selected native descriptor, payload, code/space, ordered client classes and observed tags | Exact descriptor identity and associations, class variants, SQL representation and audit effects | Complete ownership and dependency evidence; preserve payload bytes, flags, class restrictions and unrelated variants. Selected equality is insufficient. |
| Existing shared-network update | Native network properties/options and reconstructed network tags; separate membership query | Complete associations, scoped options, member subnet identities and associations; round-trip of every replacement attribute | Construct a complete lossless replacement under an explicit supported contract. Pinned update replaces network options and associations; minimal creation input cannot safely stand in for an existing object. |
| Existing shared-network delete | Named network with observed tags and backend-wide member subnets | Exact members, network options and all associations; detach/cascade and audit behavior | At minimum, a demonstrably empty, option-free, exclusively associated network under verified single-writer control, with native deletion qualified on both engines. M27 still refuses even this case; complete evidence and a separately tested contract are required. |
| Add/move/remove subnet membership | Native subnet shared-network name; network membership API returns backend-wide members | Full original subnet/pools/scoped options and associations, source/destination network views and membership graph | Lossless subnet replacement, valid source/destination visibility for every affected consumer, preservation of associations/options/pools, and explicit activation/packet qualification. M28 bounded rich subnet mutations still refuse shared-network members. |

## Shared-network source findings

The pinned drivers reconstruct network tags before filtering the returned network
collection. See PostgreSQL
[`pgsql_cb_dhcp4.cc`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/hooks/dhcp/pgsql/pgsql_cb_dhcp4.cc#L1404-L1435)
and MySQL
[`mysql_cb_dhcp4.cc`](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/hooks/dhcp/mysql/mysql_cb_dhcp4.cc#L1590-L1620).
This differs from the incomplete selected association visibility encountered in
M25/M26. The M27 response preserves these observed tags; its conservative
`associations-complete: false` does not assert that network tags are absent.
It prevents treating separate observations as a complete dependency certificate.

`getSharedNetworkSubnets4` ignores its selector and delegates to an `ANY` query
in both drivers: PostgreSQL
[implementation](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/hooks/dhcp/pgsql/pgsql_cb_dhcp4.cc#L4788-L4793)
and MySQL
[implementation](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/hooks/dhcp/mysql/mysql_cb_dhcp4.cc#L3842-L3847).
M27 labels this membership `ANY`. It must not be relabeled as the selected
consumer's membership. Native activation separately fetches selected networks and
subnets, then attaches subnets by network name. Missing selected networks can
make activation fail even when backend-wide membership readback succeeds.

Existing native network updates remove network options and associations before
replacing them: PostgreSQL
[update path](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/hooks/dhcp/pgsql/pgsql_cb_dhcp4.cc#L1591-L1624)
and MySQL
[update path](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/hooks/dhcp/mysql/mysql_cb_dhcp4.cc#L1773-L1802).
Native deletion detaches member subnets and removes network-scoped options and
associations. Both final schemas explicitly detach member subnets in native
deletion triggers; PostgreSQL's final subnet foreign key uses
`ON DELETE NO ACTION`. See the pinned
[PostgreSQL schema](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/database/scripts/pgsql/dhcpdb_create.pgsql)
and [MySQL schema](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/share/database/scripts/mysql/dhcpdb_create.mysql).
These destructive paths are source-assessed here; this document does not claim
that M27 executed native network update/delete against dependent records.

The [native DHCPv4 backend interface](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/lib/dhcpsrv/config_backend_dhcp4.h)
exposes object operations, not a complete dependency graph or an atomic
read/validate/write protocol. Calling an available method does not establish
commercial command compatibility or safe whole-object replacement.

## Upstream extensions versus stricter project contracts

Potential upstream extensions are complete association/dependency enumeration
for each affected identity, a selector-honoring membership query, and atomic
conditional mutation over an expected revision. They would improve native-only
proofs. They remain proposals, not prerequisites automatically waived by SQL
inspection, and no upstream implementation is part of M27.

Narrower project contracts might qualify an empty, option-free, singly associated
network; a definition with no dependent options; or membership replacement of a
fully supported subnet with all fields preserved. Each requires evidence from
both backends, negative cases proving unchanged data/audit on refusal, verified
exclusive ownership, restart persistence and explicit per-consumer activation.
If native APIs cannot establish a required predicate, a contract assertion from
the caller alone is insufficient. Keep the operation refused or pursue an
upstream API extension. Do not add production SQL as a shortcut.

Membership support remains deferred after M28's bounded subnet extension;
M29 adds guarded fresh network/subnet/pool options, while existing-option
replacement and deletion remain deferred. Neither path should
silently unlock these cases through a richer parser alone. Consumer runtime
observability and writer recovery remain a separate qualification workstream;
M22's incomplete exact-equivalence evidence must remain visible.

## M29 scoped-option findings and remaining gates

Native scoped creation operates independently of parent replacement. The
[DHCPv4 interface](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/lib/dhcpsrv/config_backend_dhcp4.h)
has global-only `getOption4/getAllOptions4`; scoped reads require the selected
parent's `CfgOption`. Scoped create/delete overloads require `ANY()` and accept
network name, subnet ID, or pool start/end. Pool writes do not accept subnet ID.
M29 enumerates ALL, each server and UNASSIGNED parents to reject duplicated
ranges, including hidden unassigned duplicates.

The drivers reconstruct parent tags, but scoped option descriptors omit option
association joins. Native upsert can preserve hidden links on an existing row.
Delete's optional class predicate can match multiple variants; it is not a
safe project identity predicate. Consequently M29 permits fresh code/space only
under one exact parent association and refuses all existing-option set/delete.
A different class list does not authorize a new variant over an existing
code/space. Independent parent writes never bypass the M28 refusal of parent
replacement with options or network membership.

| Evidence category | Available evidence and remaining work |
| --- | --- |
| Native APIs | Selected parent identity, reconstructed parent tags, explicit option descriptors, payload/flags/classes, native timestamps/audit queries; sufficient for bounded fresh creation with an exclusive writer |
| Diagnostic SQL only | Exact option row IDs, option-server join sets, full stored encoding, range ownership, parent/dependency rows and before/after audit contents; M29 tests independently assert parent preservation and no SQL/audit changes on refusal |
| Missing from either snapshot alone | Atomic relationship between preflight and mutation, current writer ownership, operator intent and full consumer equivalence |
| Upstream extension needed for a native complete-evidence contract | Expose complete scoped-option associations/dependencies, address pools by parent plus stable identity, exact class matching and conditional mutation by expected revision |
| Stricter preconditions currently supported | Fresh code/space under a singly associated parent, selected native encoding, globally unique pool range, designated writer and existing recovery gate |
| Deferred existing mutations | Prove complete associations, class variants, definitions and safe exact SQL effects on both engines before update/delete; caller acknowledgement or a diagnostic snapshot alone cannot unlock them |

No production SQL, generic reconciliation framework, distributed fencing or
upstream API change is introduced. Direct option timestamps and audit metadata
are not added to project responses; existing audit tooling supplies separate
observations. Scoped read responses explicitly remain association-incomplete.

## M28 preservation findings and remaining gates

The bounded subnet path now preserves native timers, boot fields and supported
class lists when omitted. Full native serialization comparison rejects visible
unsupported fields. Disposable SQL snapshots independently check unrelated rows
and unchanged configuration/audit after refusals; this diagnostic evidence is
not available as a production SQL shortcut.

| Deferred operation | Evidence required before enabling |
| --- | --- |
| Replace classed pools | Explicit lossless replacement contract covering class restrictions, options and physical identity; fresh complete dependency evidence |
| Update a subnet or pool with scoped options | Native serialization plus complete option/association/dependency visibility and preservation tests; current readback alone is insufficient |
| Update a shared-network member or move/detach it | Selected network/subnet association compatibility, full inherited settings and membership preservation; current whole-subnet writes remain refused |
| Accept other SQL-backed subnet attributes | Typed validation, both-driver bindings/readback qualification and supported-field reconstruction with negative SQL/audit assertions |
| Optimistic concurrent update | An atomic expected-revision precondition in the public native mutation API; timestamps/audit reads alone do not provide it |

M28 does not unlock existing server/global/definition/global-option or network
updates/deletes. Their earlier evidence gaps remain. M29 should first establish
scope-specific option identity, association and dependency contracts, then add
safe native scoped-option operations without weakening these refusals.
