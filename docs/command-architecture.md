# Command architecture for commercial parity

This records the M23 design and M24 shared infrastructure for unmodified
Kea 3.2.1, C++14 and the existing standalone shared-library hook. Future command
families remain proposals until their implementation milestones. The
[command inventory](compatibility-matrix.md) defines the target; the
[gap analysis](commercial-parity-gap-analysis.md) records unresolved contracts.

## Current architecture

One CMake MODULE exports the Kea lifecycle functions. `src/diagnostic.cc`
registers forty-one IPv4-only commands; `commands.cc` retains command-specific replies
and explicit mutation admission. Header-only `command_support.h` shares request
extraction, required/optional field checks, safe errors and response publication.
`backend_support.h` shares typed per-invocation manager access, single-backend
selection and server selectors. `arguments.cc` validates bounded native subnet/pool
requests; `subnet4.cc` retains native CRUD and subnet safety policy.
`records4.cc` contains the M25 server/scalar-global handlers using the same
request, exception and backend helpers. Mutation admission is explicit at each
family's set/delete boundary. The native manager is resolved per invocation,
with exactly one backend. Global set only creates an absent selected value;
existing update/delete is refused because native readback cannot enumerate
complete associations. Existing-server deletion is also refused because native
cleanup can purge unrelated orphans. These are explicit coverage gaps.
Exceptions are contained, mutations default to denied, and persistence does
not activate consumers. These are useful foundations, but the minimal object
builder and common replies cannot implement the full commercial interface.

Keep this architecture. Add small shared command support and typed,
family-specific handlers as their milestones arrive. Do not build a generic
SQL layer, configuration store, controller service or universal CRUD framework.

## M30 client-class handler

`client_classes4.cc` owns four callouts, reusing M24 request/response/backend
helpers and the selected native option encoder. It constructs native classes
through ClientClassDefParser and derives member references with ExpressionParser.
Reads retain the dictionary's ordered vector. One explicit empty predecessor
appends a fresh globally absent name. Runtime/native consumer inspection precedes
the sole native write. This is an exclusive-writer preflight, not an atomic
dependency snapshot. Existing upsert/delete and insertion never reach a native
mutation. No generic store, direct SQL, retries or activation is added.

## M29 scoped-option handlers

`scoped_options4.cc` contains twelve explicit callouts and one small scope-aware
handler. Shared request/response/backend helpers remain authoritative. M26
encoding helpers move unchanged into private inline `option_support.h`, used by
global and scoped options: selected native definitions, native CSV/binary
construction and native serialization. No second codec or SQL layer is added.

Scoped reads come from the selected parent's `CfgOption`; public native
`getOption4/getAllOptions4` are global-only. Writes use the native independent
network-name, subnet-ID or pool-range overload, with ANY as required by pinned
drivers. They never replace the parent. Parent ANY tags must contain exactly
the requested tag. Pool creation enumerates ALL, every named server and
UNASSIGNED subnet views, deduplicates subnet IDs, then checks physical ranges
through ANY reads. A nonunique range is refused before the native range-only
write. Existing code/space at any class variant prevents creation/deletion;
native option association visibility is insufficient to authorize replacement.

The guards are preflight reads, not atomic compare-and-swap. The exclusive
designated-writer boundary remains necessary. M28 whole-subnet mutation guards,
M22 tooling holds and uncertain-outcome recovery remain unchanged.

## M26 option handlers

`options4.cc` uses the existing command boundary and typed backend helpers.
Eight explicit callouts dispatch to small option-family operations; each write
checks admission before parsing or backend access. Only absent selected
identities may be created; existing update/delete is refused. Native read
metadata is explicitly incomplete, never used as complete ownership evidence.

Individual `OptionDefParser` objects validate definitions without invoking the
list parser that changes runtime definitions. A small `OptionDataParser`
subclass resolves selected SQL definitions and native built-in/vendor/last-resort
definitions, excluding process-global runtime fallback. Native encoding and
serialization remain authoritative; no SQL or independent codec is introduced.
Native collections serialize definitions/options, with deterministic identity
ordering and observed association metadata. Binary serialization may normalize
hexadecimal letter case; payload bytes define encoding equivalence.

M22 recovery tooling is unchanged. These callouts do not implement durable holds
inside the hook or qualify evidence-gated resumption.

## M27 shared-network handlers

`shared_network4.cc` adds four explicit callouts using the existing request,
response, admission and typed backend helpers. Reads serialize native networks
and separately fetched native member subnets in deterministic name/ID order.
Observed tags are preserved. Pinned drivers fetch members with ANY independently
of the selected network view, so the response labels that scope and does not
claim an active consumer view or complete atomic dependency evidence.

Set checks the global native ANY name view before allowing fresh creation of
a validated name and optional timers. Every existing-network write is refused,
including selector-invisible records. Delete only reports missing names; it
never invokes a native delete. No option/membership mutation path, direct SQL,
activation or retry is added. Preflight is safe only within the established
exclusive-writer boundary, not a cross-process lock.
See the [dependency backlog](dependency-safety-backlog.md).

## Registration and lifecycle

M24 retained five explicit registrations. M25 adds eight explicit project-specific
registrations in the same lifecycle boundary. M26 adds eight option callouts;
all thirteen earlier contracts remain unchanged. M27 adds four shared-network
callouts while retaining all 21 earlier contracts. When additional families justify
it, use a small static descriptor table containing command name, DHCP family,
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
bounded `cb-subnet4-set` attribute/pool-preservation behavior. Preserve explicit shared
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

M24 implements two private header-only helpers rather than a new framework.
`CommandRequest`, `optionalField` and `requireFields` preserve command-specific
schema checks, omitted/null distinctions and error messages. `respond` uses
Kea's exact `ConstElementPtr` argument type. `commandBoundary` shares the
get/set/delete exception envelope; list/diagnostic retain their distinct outer
publication handling. Admission remains explicit before request parsing in
each mutating callout.

`backendPool<Manager>` preserves native family types without casts or cached
state. `singleBackendSelector` retains separate list and mutation/lookup error
policies. Tag validation and ALL/ONE construction are shared; association
conflict checks and richer-object rejection remain in the IPv4 implementation.

The opt-in `KEA_DB_COMMANDS_DHCP6_PROBE` builds
`tests/native_dhcp6_probe.cc` as an isolated executable. It instantiates the
shared helper with `ConfigBackendDHCPv6Mgr`, constructs native selectors and
forces link references to server/global read, create/update and delete methods.
Those references are in a retained function that is never called. Strict C++14,
`-z defs` and eager `-z now` linking plus executable startup verify installed
headers and shared symbols. Startup constructs an empty manager only: no SQL
backend, persistent operation, command registration or DHCPv6 daemon loading.

The opt-in `KEA_DB_COMMANDS_CALLOUT_TESTS` target links actual production
callouts against deterministic failing backend fixtures and native Kea callout
handles. It verifies private native errors, public contract errors, response
envelopes, admission before backend access and absence of retries without SQL
interruption. The regular lifecycle test checks request validation through
real daemon command dispatch in both threading modes.

Acceptance remains unchanged five-command registration and replies, admission
precedence, exception containment, exactly-one-backend behavior, clean lifecycle,
pinned Release C++14 warnings-as-errors, unit/lifecycle and all six strict
SQL/DHCP tests without skips in explicit non-interruption mode, both engines
and MT modes, quality and artifact checks. Exact execution results belong in
`build/milestone24/checks.md`.

M25 can use these helpers for four DHCPv4 server and four global-parameter
commands without another infrastructure extraction. First freeze per-command
request/reply fixtures from the M23 matrix; resolve U6 server lifecycle and U2
compound-global encoding using pinned native APIs and disposable SQL tests.
Fixtures and commercial envelopes remain family-specific. M24 creates no
commercial registrations, activates no configuration and does not establish
DHCPv6 runtime or database compatibility.

## M28 bounded subnet preservation

`arguments.cc` owns typed native construction and `preserveSubnet4`. The latter
reconstructs the whitelisted stored fields, compares the complete native
serialization, then applies only explicitly supplied optional fields and
revalidates. This is deliberately not a general JSON merge or a complete SQL
reconciliation mechanism. `subnet4.cc` retains fresh ANY conflict reads,
association and membership checks and the sole native write. Mutation admission
remains in the existing callout boundary; no registration or response envelope
changes.

Supported extensions are timers, boot parameters, native class lists and pool
CIDR notation. Omitted supported fields survive updates. Unsupported options,
context and shared-network membership refuse the write; replacing a classed pool
list is refused. Native replacement recreates physical pool IDs and timestamps.
There is no public atomic revision guard, so exclusive designated ownership
remains necessary. See the [capability and preservation inventory](subnet4-capabilities.md)
and [dependency backlog](dependency-safety-backlog.md). Scoped option handlers
in M29 must establish their own dependency evidence and cannot bypass these
whole-subnet safeguards.
