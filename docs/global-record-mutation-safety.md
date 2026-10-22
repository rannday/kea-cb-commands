# Global-record mutation safety: M33

Status: **PARTIAL — all-scope dependency and reconstruction qualification remains open**.
No production C++ changed and no existing-record mutation was enabled.
Production readiness remains **NO-GO**.

## Evidence boundary

This investigation inspects the extracted Kea 3.2.1 source whose provenance is
recorded in `build-repro-clean/toolchain.txt`: commit
`1737462bc79276e3269304ea8cd3d1c03400e30d`, archive SHA-256
`2aebb52859cc402ae20004f54574714045fc6366825df1b09b7845130f9f798b`.
The extracted source is not a separate Git checkout; running Git there resolves
the enclosing project and does not verify upstream provenance.

Source conclusions and disposable fixture observations are distinguished below.
See execution evidence (local report: `build/milestone33/checks.md`) for the current matrix,
quality results and remaining verification gaps.

## Applicable blockers

The M31 ledger remains A0 / B4 / C5 / D1 / E1 / F1. No category is reclassified
during this bounded investigation.

| ID | Current restriction and missing guarantee | Candidate remediation and evidence gate |
| --- | --- | --- |
| C1 | Existing scalar globals refused: selected readback cannot prove complete physical-row ownership | Complete native association inventory; compare common-only, named, multiple and mixed links against diagnostic SQL |
| C2 | Existing definitions refused: ownership and all-scope consumers unavailable | Inventory definition ownership and dependent global/network/subnet/pool/class options; prove encoding preservation |
| C3 | Existing global options refused: complete ownership and precise delete identity unproven | Exact row identity and complete links; eliminate class-pattern ambiguity; independent preservation assertions |
| D1 | Read/preflight/write is non-atomic | Atomic backend revision/dependency precondition, or technically enforced exclusion covering all writers |
| F1 | Reconstruction using ALL, server enumeration and ONE remains unqualified | Demonstrate completeness including common/mixed and unassigned rows; physical IDs alone do not recover omitted links |

The common-only versus mixed global-parameter counterexample below challenges
F1 for that family. The fixture compares native reads before and after adding
a named link to the same common row. Full cross-family reconstruction, including
unassigned records, remains unqualified; F1 is not reclassified.

## Native methods and targeting

Public backend methods examined include `getGlobalParameter4`,
`getAllGlobalParameters4`, `createUpdateGlobalParameter4`,
`deleteGlobalParameter4`, `getOptionDef4`, `getAllOptionDefs4`,
`createUpdateOptionDef4`, `deleteOptionDef4`, `getOption4`,
`getAllOptions4`, `createUpdateOption4` and `deleteOption4`.
Overloads and their SQL predicates must be distinguished.

| Family | Native update predicate | Native delete predicate | Safety implication |
| --- | --- | --- | --- |
| Global parameter | Exact joined server tag plus parameter name | Exact joined tag plus name; deletes physical parameter row | Shared-row update changes the value for every linked consumer; deletion removes the row rather than only the selected link |
| Global definition | Exact joined tag, code and space; name is replacement data | Joined tag, code and space; deletes physical definition row | Code/space is not proof of unique complete ownership or absence of consumers |
| Global option | Joined tag, scope 0, code, space and exact serialized client classes | Joined tag, scope 0, code, space and client classes using SQL LIKE | Update and delete have different class semantics; wildcard matching is not exact identity |

These global predicates retain a server-tag condition, unlike the M32 scoped
delete wrappers that substitute ANY. Retaining a tag condition still does not
make shared physical-row mutation association-local. Native upserts attach an
association on insertion; the inspected existing-row update paths do not perform
copy-on-write or split ownership.

### Source references

All links below pin the required commit.

- PostgreSQL [global reads and creation](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/hooks/dhcp/pgsql/pgsql_cb_dhcp4.cc#L195),
  [option creation](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/hooks/dhcp/pgsql/pgsql_cb_dhcp4.cc#L1662),
  [definition delete dependency check](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/hooks/dhcp/pgsql/pgsql_cb_dhcp4.cc#L2065),
  [global option delete statement](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/hooks/dhcp/pgsql/pgsql_cb_dhcp4.cc#L4494).
- PostgreSQL [row reconstruction](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/hooks/dhcp/pgsql/pgsql_cb_impl.cc#L242)
  and [query macros](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/hooks/dhcp/pgsql/pgsql_query_macros_dhcp.h#L1017).
- MariaDB/mysql [global row reconstruction](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/hooks/dhcp/mysql/mysql_cb_impl.cc#L264),
  [definition reconstruction](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/hooks/dhcp/mysql/mysql_cb_impl.cc#L399),
  [update predicates](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/hooks/dhcp/mysql/mysql_query_macros_dhcp.h#L1017),
  [delete predicates](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/hooks/dhcp/mysql/mysql_query_macros_dhcp.h#L1168)
  and [global option LIKE predicate](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/hooks/dhcp/mysql/mysql_cb_dhcp4.cc#L3684).

## Association visibility

Global readers join association tables, but queries include the selected tag
and common records. Reconstructors process a physical row once and set only the
first returned tag. They also implement common-versus-specific logical override.
A logical selected view is therefore not a database-wide association inventory.

Global parameter queries order by parameter ID and server ID. A common link
(server ID 1) comes first. Adding a named association to that same common row
does not make the additional link appear in native parameter readback, even
when querying that named server. The physical ID remains the same. This is a
source-derived indistinguishability case covered by the parameter fixture.

Global-option queries also order by option ID and server ID, so a common link
is retained first. Definition reconstruction retains one tag but orders only by
definition ID; its retained tag is not guaranteed deterministic. Repeating selected reads may recover some named-only
links; completeness for mixed links, shadowed records and orphans remains
unqualified. Project responses do not expose physical IDs as mutation handles.

## Dependencies and bounded feasibility

The inspected PostgreSQL definition delete path with force=false checks for a
selected global option. That check does not enumerate every scoped/class option
and every other selector. It is not an all-scope dependency proof. MariaDB has
the same selected-global-option precheck (`mysql_cb_dhcp4.cc`,
lines 2203–2226). Neither check establishes all-scope dependency completeness.
The schemas store options by code/space rather than a foreign key to a definition.
Definition deletion cascades its association links, not a verified inventory of
all options decoded with it. Consequently absence of a foreign-key error cannot
prove absence of affected consumers. Definition name and code/space indexes are
not a globally unique ownership key; class-local definitions add another identity
dimension. PostgreSQL's early schema contains a historical foreign-key typo that
is corrected later in the same creation script (lines 4229–4234); inspect the
final schema rather than treating its first CREATE TABLE as the resulting state.

Global options may depend on native/built-in or SQL definitions, encoding,
ordered class lists and inheritance. A successful upsert or deletion does not
prove preservation of these dependencies. Global parameter scalar parsing does
not resolve ownership; structured values remain refused.

No bounded existing-record case is qualified. Required conditions remain:
one exact physical target; complete links including common/unassigned state;
complete relevant consumers; lossless native representation; admission and no
recovery hold; and exclusion of competing writes or an atomic native guard.
No mutation is enabled by this document.

## Public alternatives examined

`getModifiedGlobalParameters4`, `getModifiedOptionDefs4` and
`getModifiedOptions4` filter by modification time; they do not expose an atomic
expected-state write. `getRecentAuditEntries` accepts a timestamp and audit ID
as read cursors, with ALL/ONE selectors; these are not mutation preconditions.
`getAllServers4` excludes the logical all server. Enumerating named servers and
repeating ONE reads does not restore links omitted by common fallback or logical
override, nor establish an unassigned inventory. Parent subnet/network and class
reads can reveal some consumers but provide no supported reverse dependency
inventory spanning every scope and selector. No examined public write accepts a
revision token or expected association set. These alternatives do not remove C1,
C2, C3 or D1. F1 remains explicitly unqualified for its full cross-family scope.

## Concurrency

The sequence is read, reconstruct links, inspect dependencies, validate/admit,
native write, then verification. Another hook, another Kea backend client, direct
SQL or writer replacement can invalidate each preflight observation before the
write. A native transaction around the write does not include prior hook reads.
Audit revisions and timestamps are observations, not established compare-and-swap
tokens. Post-write verification cannot undo a wrongly targeted committed write.

Correct identity and concurrency protection are separate requirements.
Designated-writer policy is not database-enforced fencing. Existing durable
holds, explicit activation and uncertain-outcome reconciliation remain required.
See the [proposed API contract](native-api-improvement-proposal.md).

## Fixture boundary and next qualification

The shared PostgreSQL/MariaDB fixtures exercise empty, common, named, multiple
named and mixed links, selector fallback, missing records, invalid payloads,
read-only admission and existing SET/DEL refusals. Full table snapshots include
configuration, audit, association and existing dependency rows. New mixed-link
refusals also compare active config-get responses, proving no activation in
those cases. Diagnostic SQL constructs disposable fixture links only.

These observations do not establish every definition consumer or encoding path,
unassigned/union reconstruction completeness, or family-specific durable recovery
hold behavior. The recovery journal remains test-tooling evidence rather than a
new production hold mechanism. No accepted existing-record mutation or new packet
mutation case applies. Existing packet regressions qualify supported behavior;
they do not close M22 full-state convergence or uncertain-commit recovery gaps.
Recommended M34: complete the missing read-only consumer/reconstruction evidence,
review the proposed native contracts, then reassess feasibility without enabling
writes solely to increase coverage. Defer DHCPv6 and retain production NO-GO.
