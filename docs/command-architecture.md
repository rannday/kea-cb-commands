# Command architecture for commercial parity

This is the M23 design for unmodified Kea 3.2.1, C++14 and the existing
standalone shared-library hook. It authorizes no implementation. The
[command inventory](compatibility-matrix.md) defines the target; the
[gap analysis](commercial-parity-gap-analysis.md) records unresolved contracts.

## Current architecture

One CMake MODULE exports the Kea lifecycle functions. `src/diagnostic.cc`
registers five IPv4-only commands; `commands.cc` contains callout boundaries,
admission and replies; `arguments.cc` validates minimal subnet/pool requests;
`subnet4.cc` resolves the native pool and applies subnet safety policy.
The native manager is resolved per invocation, with exactly one backend.
Exceptions are contained, mutations default to denied, and persistence does
not activate consumers. These are useful foundations, but the minimal object
builder and common replies cannot implement the full commercial interface.

Keep this architecture. Add small shared command support and typed,
family-specific handlers as their milestones arrive. Do not build a generic
SQL layer, configuration store, controller service or universal CRUD framework.

## Registration and lifecycle

Use a small static descriptor table containing command name, DHCP family,
read/mutation classification and callout pointer. Register only implemented,
qualified commands. Keep the existing five names and request/response behavior.
Do not make a `remote-*` alias for a `cb-*` handler with a narrower contract.

Lifecycle remains responsible for family/process validation, strict hook
parameter validation, registration cleanup and resetting mutation admission.
Detect an already registered command provider and fail initialization cleanly;
never silently override ISC's hook or another provider. Test partial
registration failure and unload/reload explicitly.

The future IPv6 milestone must validate AF_INET6 and `kea-dhcp6`, add matching
native manager/link probes and exercise real loading. Current IPv4-only load
restrictions remain until that milestone. The upstream PostgreSQL/MySQL hooks
register both native families; that alone does not qualify this hook for IPv6.

## Request handling and backend selection

Share only envelope extraction, typed required/optional fields, unknown-key
checks, cardinality helpers and result-envelope construction. Keep operation
schemas explicit: selectors, null, empty arrays and omitted values have different
meanings across commands. Do not infer a request schema from a native overload.

A per-call typed context resolves either
`ConfigBackendDHCPv4Mgr::instance().getPool()` or
`ConfigBackendDHCPv6Mgr::instance().getPool()`. It retains no backend across
reloads and creates no private manager. Small family adapters can share
plumbing; native object types and family-specific operations remain explicit.

Retain the project's one-configured-backend safety boundary. Parse commercial
`remote` selection (type, host, port) independently of server selectors.
Validate port/host dependencies and reject unmatched or ambiguous selection.
The public ARM's single-backend routing is the initial compatibility scope.
Any broader multi-backend routing needs a separately reviewed contract and
qualification; no fallback to arbitrary first-nonempty reads or aggregation.

Use explicit selector policies from the matrix: database-wide identity,
single-tag fallback reads, multi-tag association writes and list views.
Preserve actual associations in results rather than echoing requested tags.
Tags never confer independent writer namespaces. A read selector and an active
consumer's configured selector are separate evidence.

## Parsing, dependencies and serialization

Construct full native objects using the pinned public parsers where suitable:
`Subnet4ConfigParser`, `Subnet6ConfigParser`, `PdPoolParser`,
`OptionDataParser` and `ClientClassDefParser`. Validate complete object
semantics, option spaces/definitions, expression dependencies, address/prefix
ranges and inherited values. Parse in an isolated context: some native parsers
consult or modify staging configuration and runtime option definitions.
Prove that command parsing leaves unrelated staging and active configuration
unchanged, including on exceptions, before reuse.

Keep full-object commercial replacement semantics separate from the existing
minimal `cb-subnet4-set` pool-preservation behavior. Preserve explicit shared
network membership, class order/dependencies and all meaningful option fields.
Parent deletion and option-definition force deletion need operation-specific
dependency checks. Native method availability is insufficient proof of those
commercial policies.

Native `toElement()` is the starting point for object serialization, with
explicit command-specific wrappers, association metadata, counts and summary
versus full views. Verify omitted/default/empty behavior by field. Do not
discard fields to obtain round-trip equality. Ordered classes remain ordered;
tag sets can be normalized without merging selectors.

Global parameters need an explicit versioned allowlist and encoding map.
Native StampedValue restrictions, controller dotted-name reconstruction and
limited JSON-list decoding do not support arbitrary JSON server settings.
Resolve U2 in the gap analysis before claiming compound-global compatibility.

## Replies and failure boundaries

Preserve existing `cb-*` replies. Give commercial commands their own documented
success payloads and text; not all commands return a count or the same wrapper.
Freeze request/reply fixtures before registering each name. Resolve conflicting
public examples explicitly, especially class commands (U3/U4).

Every callout contains exceptions. Keep current public ContractError versus
generic native failure behavior for existing commands. Establish commercial
error/result/not-found contracts separately; the public descriptors do not
fully specify these. Do not claim exact compatibility where error behavior is
unverified, and never expose SQL diagnostics, credentials or backend exceptions.

## Mutation and recovery invariants

Check effective mutation admission before parsing or backend access for every
mutating handler. It remains a strict native boolean, default false, reset
before load/unload and granted only after successful initialization.
Commands execute synchronously on Kea's main thread, including packet MT mode;
do not add worker queues or cross-thread backend ownership.

Native drivers own transactions and audit records. A preflight check followed
by an update is not a cross-process atomic operation. Some multi-object commands
can partially succeed: define batch boundaries and report uncertainty without
automatic retry or compensation. Audit cursors are evidence, not CAS tokens.
The unresolved upstream SQL transaction-cleanup issue is unchanged.

The designated writer and external recovery gate remain required operational
boundaries. Hook admission does not itself enforce a durable workflow hold.
Extend evidence inventory and intended/active comparison for each new object
family; insufficient observations continue to hold recovery. Do not label a
deployment converged merely because a new CRUD command succeeds.

No handler activates runtime configuration. Pull/reload/startup remain explicit,
followed by independent per-consumer observations and packet checks.
No local state file constitutes distributed fencing. M22 remains PARTIAL:
writerless promotion, exact inventory and successful real resumption need
further qualification in the separate hardening workstream.

## Test organization and native references

Reuse SQL fixtures, transport, admission, lifecycle and packet namespace tools.
Add command-family assertion modules and data fixtures rather than duplicate
database provisioning. Extend the strict runner's required test set explicitly
when IPv6 is introduced; the existing six-test gate cannot prove IPv6.

Use real IPv6 allocation and PD exchanges for applicable commands, alongside
native object readback, persisted associations and ordering/audit evidence.
Packet tests do not prove stored descriptions, associations or deletion counts;
the gap analysis specifies alternative evidence and the common acceptance gates.

Public native source at commit
`1737462bc79276e3269304ea8cd3d1c03400e30d`:

- [IPv4 pool](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/lib/dhcpsrv/config_backend_pool_dhcp4.h)
  and [IPv6 pool](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/lib/dhcpsrv/config_backend_pool_dhcp6.h):
  typed operations and selector constraints.
- [Base pool](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/lib/config_backend/base_config_backend_pool.h):
  first-nonempty reads versus exactly-one-backend writes.
- [DHCP parsers](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/lib/dhcpsrv/parsers/dhcp_parsers.h)
  and [class parser](https://github.com/isc-projects/kea/blob/1737462bc79276e3269304ea8cd3d1c03400e30d/src/lib/dhcpsrv/parsers/client_class_def_parser.h):
  construction interfaces, not commercial command contracts.

## M24 implementation boundary

M24 should extract the smallest reusable request/context/reply helpers from
existing plumbing, retain typed subnet behavior, and add explicit schema fixture
support for later families. A small `command_support` module is sufficient if
extraction is justified; avoid pre-building all future handlers or templates.
Compile-probe the IPv6 manager interface without enabling IPv6 loading.

Acceptance: unchanged five-command registration and replies, same admission
precedence and failure containment, exactly-one-backend behavior, clean
load/unload/failure cleanup, pinned Release C++14 warnings-as-errors build,
existing unit/lifecycle and six strict SQL/DHCP tests with zero skips in the
explicit non-interruption mode, both SQL engines and MT modes, quality and
artifact checks. Add focused tests for extracted helpers only where behavior
needs independent proof.

M24 registers no `remote-*` names, changes no production contracts, adds no
activation and implements no feature-family CRUD. Its handoff includes concrete
server/global schemas and U2/U6 resolution tasks for M25. Unresolved compatibility
questions remain explicit rather than being hidden by a common response helper.
