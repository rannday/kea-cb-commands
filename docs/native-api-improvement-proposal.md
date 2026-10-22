# Native API improvement proposal

**Proposed contract; not implemented or accepted upstream.** This is a project
proposal, not an ISC commitment or an implemented API. Kea source is unchanged.
The [source investigation](global-record-mutation-safety.md) distinguishes
global predicates from M32 scoped selector-discarding behavior.

## Complete association enumeration

Propose a public read accepting backend identity, record family and either a
stable physical record ID or an exact family identity. Return every matching
physical record, its stable ID, complete identity and payload, common and
named-server links, modification metadata and a revision token.

| Family | Complete identity and returned payload |
| --- | --- |
| Global parameter | Parameter name and physical ID; native value type and lossless scalar or structured value representation |
| Option definition | Physical ID, code, space and global/class scope identity; name, type, array, record types, encapsulation and complete native definition attributes |
| Global/scoped option | Physical ID, scope/parent identity, code, space and ordered class list; complete native option descriptor and payload encoding |

An empty association set means unassigned, not unknown. Common is an explicit
link, not an expansion to the current server list.

This read must not apply selected-consumer override, common fallback, deduplicate
different physical rows, or infer child links from parent links. It must return
an explicit completeness flag and reject unsupported backend implementations.
Not found and ambiguous identity must be distinct. Parent association evidence
must be returned separately.

Implementation belongs in public interfaces and both SQL backends, with a
consistent snapshot contract. Tests must cover empty/common/named/multiple/mixed/
unassigned links, shadowed records and equal identities. Compare against read-only
SQL, including an association change that leaves parent serialization unchanged.

## Exact update and delete

Propose additive exact mutation methods accepting:

- Backend and stable record ID, with expected full identity.
- Parent kind and identity: global, network name, subnet ID, pool stable ID plus
  subnet ID, or class identity as applicable.
- Family-specific identity from the table above: parameter name, definition
  scope/code/space, or option scope/code/space/exact ordered class list.
- Expected complete association set and revision token.
- For update, a complete validated family descriptor and explicit field semantics.
  Parameter name is immutable; a value replacement preserves the native type
  unless an explicit validated type change is requested. Omitted fields never
  imply deletion. Structured-value support requires a separately qualified
  lossless roundtrip and does not expand the project's current scalar contract.
  Definition renaming or encoding changes require consumer validation; option
  updates must preserve every attribute not explicitly changed.

The method must affect exactly one intended physical record or fail atomically.
Server selection must never broaden to ANY. Class strings must use equality,
not SQL LIKE or wildcard interpretation. A pool address range alone is
insufficient. Common/named association ownership must not change implicitly.

Row replacement and association-local copy-on-write are distinct contracts.
The initial proposal supports whole-row mutation only when the caller's expected
ownership set is authorized. If association-local mutation is added, require an
explicit mode, documented identity allocation and preservation of every other
consumer; never infer that mode from ONE(tag).

Do not implement exact methods by wrapping existing broader mutation overloads.
Both backends need exact predicates and affected-row validation inside the same
transaction. Tests must include identical codes in different spaces/scopes/
parents, duplicate candidates, literal percent/underscore class names, multiple
links, missing records and unrelated-record preservation.

## Dependency inventory

Propose a public dependency read for exact option/definition identity, returning
typed consumer identities across global, shared-network, subnet, pool and class
scopes, selectors/associations, encoding/encapsulation relationships and the
revision covered. Report unsupported or incomplete evidence explicitly.

Definition changes can alter decoding without deleting an option. The inventory
must explain affected serialized/formatted values and reject an encoding change
unless the caller supplies a separately defined safe migration contract.
Deletion must not silently cascade, orphan consumers or use force as proof.

Public APIs and both SQL implementations are required. Tests must include
hidden-selector consumers, scoped/class consumers, missing custom definitions,
built-in definitions, encapsulation, and a consumer added after dependency read.

## Atomic concurrency preconditions

A revision token must cover the target, links, parent identity and relevant
dependency set, or an explicitly documented backend-wide configuration revision.
Require an atomic check-and-write transaction shared by every mutation path.
A timestamp copied into a WHERE clause alone does not meet this contract.

If direct SQL and other native writers can bypass the revision protocol,
document that exclusion and require technical access controls before claiming
protection. A database-wide revision is valid only if all covered changes
advance it atomically. PostgreSQL and MariaDB must implement equivalent conflict
behavior despite different isolation/locking mechanics.

Tests must interleave a target edit, association edit, parent edit and dependency
insertion between read and write. Stale evidence must fail without configuration,
association or audit mutation. Backend failure after an uncertain commit remains
a reconciliation event, not an automatic retry.

## Errors, audit and compatibility

| Result | Required contract |
| --- | --- |
| Not found | No target; no configuration/audit mutation |
| Ambiguous identity | Multiple candidates; no mutation |
| Dependency conflict | Identified affected consumers or explicit incomplete evidence; no mutation |
| Revision conflict | Expected evidence stale; no mutation |
| Unsupported association | Backend cannot honor requested ownership semantics; no mutation |
| Backend failure | Preserve rollback where known; expose uncertain outcome distinctly for recovery |

Successful updates/deletes must produce the documented native audit event.
Refusals must not create an empty audit revision. Runtime activation remains a
separate explicit action.

Prefer new versioned capabilities and overloads; retain old behavior for existing
callers without claiming it provides the stronger contract. Capability discovery
must identify unsupported drivers before writes. Schema migrations, indexes and
revision triggers require PostgreSQL and MariaDB upgrade/rollback planning.
No proposed API removes the deployment's independent recovery and fencing needs.

## Family preservation tests and remaining design decisions

For parameters, test equal names on different physical rows, mixed ownership,
scalar type changes and lossless structured roundtrip; reject unsupported values
without audit changes. For definitions, test equal code/space in global and
class scope, renamed definitions and consumers in every option scope. For options,
test payload encoding, exact classes and parent/link preservation. Run each
contract on PostgreSQL and MariaDB with independent SQL assertions.

Independent M33 review identified shadowed mixed-link fixtures and omitted scalar
identity semantics; the fixtures and this specification were corrected. Complete
schema/trigger and all-scope dependency qualification remains open. Stable-ID
lifetime, revision scope and native error representation require upstream design
review. These are proposed requirements and tests, not evidence that Kea already
provides them. No upstream changes are authorized here.
