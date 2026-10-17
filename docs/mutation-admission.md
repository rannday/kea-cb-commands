# Mutation admission and migration

Current development builds default to read-only mutation admission. Published
v0.1.0 artifacts and their behavior have not changed. Milestone 20 acceptance is
complete following Milestone 20.1 fixture migration and SQL/DHCP verification.

## Milestone 20.1 verification status — PASS

The resumed verification on Debian 12 WSL2 uses Kea 3.2.1, PostgreSQL 15.19 and
MariaDB 10.11.19. All six strict CTest tests passed with zero skips. Earlier
blocked attempts and their exact diagnostics remain under `build/milestone20/`
and `build/milestone20.1/`; the resume used inspectable native patches without
executable heredocs or policy changes. Current commands, logs and matrix are
recorded in `build/milestone20.1/checks.md`.

Both fixtures use the shared `tests/mutation.py` admission helper while
preserving native SQL hooks. Initial read-only phases omit the parameter;
native mutation/backend-guard checks and permitted CRUD explicitly enable true.
Writer-capable connections then exercise omitted, empty and false roles: both
mutation commands return the exact documented admission response for valid and
malformed input. Denied creates, updates and deletes leave all table/audit
contents, active configuration and list output unchanged; get succeeds.
PostgreSQL snapshot normalization excludes nontransactional sequence counters.
Lifecycle assertions without a configured backend and callout source ordering
also establish admission before validation/backend resolution.

Permitted regressions pass creation/update/deletion, persistence across reads
and process restarts, validation/conflicts, tags/selectors, pool preservation,
replacement and removal. Persistence leaves runtime unchanged until explicit
pull/reload. Packet tests pass sixteen real DORA exchanges overall, allocation,
persistent memfile lease records and lease retention after SQL subnet deletion.
SQL configuration persistence and lease persistence remain separate.

| Backend | Packet threading off | Packet threading on |
| --- | --- | --- |
| PostgreSQL | Admission PASS; SQL invariants PASS; CRUD/pools/selectors PASS; persistence/explicit activation PASS; DORA/leases PASS | Admission PASS; SQL invariants PASS; CRUD/pools/selectors PASS; persistence/explicit activation PASS; DORA/leases PASS |
| MariaDB | Admission PASS; SQL invariants PASS; CRUD/pools/selectors PASS; persistence/explicit activation PASS; DORA/leases PASS | Admission PASS; SQL invariants PASS; CRUD/pools/selectors PASS; persistence/explicit activation PASS; DORA/leases PASS |

Release C++14 build with warnings as errors, real lifecycle in both threading
modes, transport unit tests (6/6), script unit tests (25/25), artifact checks,
clangd diagnostics and formatting/lint/documentation checks pass. This run uses
the documented [`--skip-outages`](reproducible-builds.md) option in all four
SQL/DHCP entries: deliberate SQL interruption/recovery and historical abort
reproductions were not run. Default test coverage remains available. Docker,
sanitizer integration and independent-process deployment qualification remain
unrun. Production readiness and cross-process fencing are not granted.

## Configuration

Administrative writer (one designated owner per configuration database):

```json
{
  "library": "/absolute/kea/lib/kea/hooks/libdhcp_db_commands.so",
  "parameters": { "allow-mutations": true }
}
```

Read-only consumer:

```json
{
  "library": "/absolute/kea/lib/kea/hooks/libdhcp_db_commands.so",
  "parameters": { "allow-mutations": false }
}
```

These entries belong in `Dhcp4.hooks-libraries`, after the matching native SQL
hook. Omitting parameters, using `{}`, or omitting `allow-mutations` is equivalent
to false. A non-map parameters value, unknown key or non-boolean admission value
fails loading. `"true"`, `1` and null never grant permission. No environment
variable or ordinary hook command changes this state.

The implementation uses Kea 3.2.1's supported
[`LibraryHandle::getParameters()`](https://github.com/isc-projects/kea/blob/Kea-3.2.1/src/lib/hooks/library_handle.h).
The load callback resets permission before validation and grants it only after
registration and successful initialization. Unload resets it before logging.
Kea's [library manager](https://github.com/isc-projects/kea/blob/Kea-3.2.1/src/lib/hooks/library_manager.cc)
removes callouts during teardown and failed-load cleanup. Existing synchronous
main-thread command execution applies in both packet-threading modes.

## Upgrade procedure

1. Inventory every writer, consumer, external administrative tool and credential
   holder for the physical configuration database. Tags are not isolation.
2. Fence all alternate writers externally. Select one administrative owner,
   preferably a Kea process serving no DHCP packets.
3. Explicitly configure true only on that owner. Consumers use false or omit
   this hook if read commands are unnecessary. Protect configuration and control
   access: native reload is privileged and can change the role.
4. Validate with the matching daemon's `-t` and `-T`. Follow the existing
   [controlled module replacement procedure](operations.md); do not overwrite
   a loaded library in place. Retain the previous module and configuration.
5. Verify all five commands remain registered and diagnostic `allow-mutations`
   matches each node's intended role. Check read commands. A denied mutation has
   the fixed [admission error](commands.md); do not automatically retry it.
6. Run the established SQL/DHCP acceptance against the exact candidate build
   before release or production qualification. A successful load alone is
   insufficient; qualify deployment ownership separately.

Admission precedes set/delete argument validation and backend access. It does
not change SQL permissions, intercept other hooks, fence other processes, elect
leaders, retry writes or activate configuration. Multiple true instances sharing
a database are unsupported unless an external mechanism guarantees exclusive
ownership. An operator restoring a backup must recheck ownership before start.

An admitted command retains the existing [transaction recovery policy](transaction-recovery-policy.md)
and [explicit activation workflow](runtime-activation-design.md). Local denial
occurs before native mutation; transport loss without a received response still
requires determining which configuration/process actually handled the request.
Admission does not resolve the ISC native SQL transaction exception-safety issue.
