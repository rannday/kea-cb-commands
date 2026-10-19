# M32: DHCPv4 scoped-option mutation safety

Production readiness remains **NO-GO**. M32 enables **zero existing-record
mutations**. Subnet and shared-network option updates and deletes remain refused.
This is a bounded negative qualification: supported native reads cannot establish
the necessary option ownership, even under a sole-associated parent. Existing
fresh creation, reads and missing-record deletion contracts are unchanged.
See [execution evidence](../build/milestone32/checks.md), the
[M31 inventory](dhcp4-qualification.md) and [remediation plan](dhcp4-remediation-plan.md).

## Selected blockers and operations

The smallest candidate was an existing subnet option under one named-server
parent, with explicit empty class filters. Update and deletion were investigated
separately; shared-network candidates were independently checked against both
driver implementations. No production guard was changed.

| Candidate | M31 findings | Native read | Native mutation | Required identity and missing evidence |
| --- | --- | --- | --- | --- |
| `cb-option4-subnet-set` existing | B3, D1; F1 reconstruction hypothesis | `getSubnet4` then parent `CfgOption` | `createUpdateOption4(ANY, subnet_id, descriptor)` | Parent subnet ID, code, space, exact ordered class representation; complete option links and unique matching row unavailable |
| `cb-option4-subnet-del` existing | B3, D1; F1 hypothesis | Same | `deleteOption4(selector, subnet_id, code, space, classes)` | Same parent/code/space; SQL classes use LIKE and selector is discarded; unknown links prevent admission |
| `cb-option4-network-set` existing | B3, D1; F1 hypothesis | `getSharedNetwork4` then parent `CfgOption` | `createUpdateOption4(ANY, network_name, descriptor)` | Network name replaces subnet ID; same missing option ownership and row uniqueness evidence |
| `cb-option4-network-del` existing | B3, D1; F1 hypothesis | Same | `deleteOption4(selector, network_name, code, space, classes)` | Whole matching option row, not one server association; same missing evidence |

B3's proposed bounded case is therefore insufficient for these existing records.
The unresolved predicate is additional read-only association evidence (category
C in the M31 taxonomy); this refines B3 rather than recounting the historical
12 blockers. F1's global/definition/global-option reconstruction proposal is
**not** resolved by a scoped-parent counterexample. D1 remains independently
applicable. E1's range-only pool identity limitation remains unchanged and pool
existing-record mutations stay refused. Server deletion was not investigated
or enabled here.

## Native association visibility

All source references below use ISC Kea commit
`1737462bc79276e3269304ea8cd3d1c03400e30d`, not a newer API. Local extracted
source provenance is recorded in `build-repro-clean/toolchain.txt`.

| Evidence | What can actually be established |
| --- | --- |
| Parent object server tags | Native subnet/network reads reconstruct parent associations; a mixed common/named parent is observable |
| Scoped option payload, flags, classes, context and SQL ID | Native option descriptors expose properties and inherit database ID, but scoped row processing does not populate option server tags |
| ALL, ONE(tag), all enumerated server tags | Change parent visibility; each visible parent loads its options independently of those options' association links |
| Diagnostic SQL in disposable fixtures | Exact `dhcp4_options_server` links, including absent, hidden, multi-server and mixed common/named records |
| Production native evidence | Complete scoped-option association set remains unknown; `associations-complete: false` remains accurate |

The PostgreSQL [subnet join](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/hooks/dhcp/pgsql/pgsql_query_macros_dhcp.h#L132)
and [network join](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/hooks/dhcp/pgsql/pgsql_query_macros_dhcp.h#L492)
load options through parent identity, without `dhcp4_options_server`.
The [MariaDB/MySQL joins](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/hooks/dhcp/mysql/mysql_query_macros_dhcp.h#L136)
have the same omission (network join at line 495). Parent selector filtering
occurs after loading options: PostgreSQL `getSubnets4` at line 616 and
`getSharedNetworks4` at line 1428 of `pgsql_cb_dhcp4.cc`.

[OptionDescriptor](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/lib/dhcpsrv/cfg_option.h#L49)
inherits tags/ID, but PostgreSQL `processOptionRow` in `pgsql_cb_impl.cc:806`
and MariaDB `mysql_cb_impl.cc:873` do not populate tags. This differs from
standalone global reads, which explicitly reconstruct them. Public
[getAllOptions4](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/lib/dhcpsrv/config_backend_dhcp4.h#L241)
is global-only. An observable SQL option ID does not supply an API to read its
scoped links or target these scoped mutations by that ID.

Thus even enumerating ALL plus `getAllServers4` plus ONE(each tag) cannot
reconstruct scoped links. Absence of tags in serialization is not evidence of
an unassociated option. Parent tags are not child tags.

## Identity and independent mutation findings

PostgreSQL update statements in `pgsql_cb_dhcp4.cc:4078,4136`, and MariaDB
statements in `mysql_cb_dhcp4.cc:3540,3552`, match parent identity, code, space
and exact serialized client classes. They do not restrict by option server
association or a caller-provided SQL option ID. Matching records are updated;
no match falls back to insertion. Association rows are mechanically preserved
on update, but their complete ownership cannot be checked. Parent-based reads
also mean that extra option links alone do not demonstrate extra effective
runtime consumers. Preserving links does not establish operator intent.

PostgreSQL `deleteOption4` at lines 5231/5249 and MariaDB at 4284/4302 discard
the public selector and invoke the ANY path. Subnet/network deletes target
whole option rows, with parent/code/space and a LIKE class predicate
(PostgreSQL statement definitions at 4522/4554). Absent classes become `%`
(`pgsql_cb_impl.cc:1162`); a nonnull empty class list avoids that wildcard.
Class strings containing LIKE metacharacters still need an exact-identity
policy. No deletion was attempted against an existing option in M32.

Parent subnet ID and network name distinguish their respective scope; option
space and ordered classes are part of identity alongside code. Neither a
selected parent nor a successful get proves one physical option row, complete
links, or that a native mutation will affect only the intended consumer.
Pool range ambiguity is not solved by these findings.

## Dependencies and admission requirements

An existing update would need lossless supported encoding and flags/context,
exact classes, complete links, one target row, selected option definitions,
stable definition semantics, and preservation of other options, parent fields,
membership and associations. Native updates operate on options rather than
replacing parents or definitions, but their hidden ownership cannot be checked.
A delete additionally needs proof of exact whole-row targeting and intentional
removal for every affected consumer; removing a scoped option can expose an
inherited value and change packet payloads. No automatic cascade is authorized.

The candidate preconditions were one explicit parent association, one physical
option, an exact class predicate, complete option links, selected definitions,
mutation admission, no recovery hold and exclusive writer ownership. Complete
option links cannot be proven through the supported reads. Caller assertions,
unchanged parent tags, cached SQL evidence and an apparently simple payload do
not satisfy that missing predicate. Consequently no bounded existing-record
contract is admitted.

The existing deterministic refusal remains:

> Existing scoped option mutations are unsupported: complete associations and dependencies cannot be verified.

Admission rejection precedes mutation processing; missing-option deletion keeps
result 3 without a write. Fresh code/space creation remains bounded by sole
parent association, selected native parsing and the existing pool uniqueness
guard. No broader selector fallback or parent replacement is introduced.
Durable holds remain an external recovery-tooling control; M32 does not add or
claim a new hook-level recovery gate.

## Race windows and operational exclusion

The sequence remains read parent/options; inspect associations/dependencies;
validate; invoke native mutation; verify persisted result. A second writer can
change links, parent, definitions or target existence at any boundary before
the write, or before verification. An upsert may become an update after a
freshness check; a post-write read cannot undo that race.

Native transactions begin inside the write implementation. No public atomic
expected-revision predicate spans these preflight reads and mutation. Audit
entries and modification timestamps are observations, not compare-and-swap.
Even complete future association readback would leave D1 unresolved.

The designated-writer policy is an assumption, not database-enforced fencing.
Deployment must exclude other Kea backend clients, administrative/direct SQL
writers, stale processes and restart/failover authorities throughout the
operation. A local admission flag cannot enforce that exclusion. Preserve
uncertain-write reconciliation, durable holds and deliberate operator recovery;
no automatic retry or activation. M22 full convergence and recovery qualification
remain incomplete.

## Disposable verification and limits

`tests/scoped_options4.py` changes only test fixtures. For both subnet and
network scopes, under separately named and common parents, it cycles option
links through seven states: no option links; common; requested named server; hidden
named server; two named servers; common plus requested; common plus both named.
Independent SQL checks each exact link set. Native get results remain identical
across those states for every tested visible selector (including common fallback
through both named selectors). Each repeated SET/DEL refusal compares the full
configuration/audit snapshot; active `config-get` remains identical. Mixed
common/named parent ownership is separately observable and refused.

Native fresh scoped creation with ANY initially creates no option-server links;
the tests assert and restore that state. Parent association is independently
visible and controls parent-based option loading. These fixtures deliberately
change associations in disposable SQL transactions only. They never authorize
production SQL, and they never execute a prohibited existing-option native write.
Existing tests retain different scopes/parents, class-filter conflicts,
malformed/unsupported encoding, definition resolution, missing parents/options, read-only admission, range collisions, membership,
parent/other-option preservation, explicit activation and restart checks.

With zero newly permitted mutations there is no new update/delete packet case.
The established DHCP tests still prove DORA/leases, boot/timers, classification,
global/network/subnet/pool precedence, explicit activation and restart. Packet
success is not inferred from SQL readback. Exact results and unavailable checks
are recorded in the execution evidence.

## Next work

Keep 41 commands, functional coverage 3 implemented / 24 partial / 47 missing
and exact compatibility 0/74. Do not claim complete scoped CRUD.
Recommended M33: separately qualify F1 for global records whose native readers
actually reconstruct links, and design a trustworthy scoped association read
facility or upstream API proposal before revisiting these four mutations.
Include unique row identity, exact class matching and concurrency/recovery
requirements. Defer DHCPv6 and deployment until those designs are reviewed.
