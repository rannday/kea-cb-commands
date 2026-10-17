# Development migration — mutation admission (not released)

Set/delete now require a native boolean hook-library parameter
`"allow-mutations": true`. Omitted/false means read-only. Invalid types or unknown
parameter names fail initialization. Diagnostic/list/get remain available;
diagnostic adds effective `allow-mutations` alongside capability. Existing
writers must opt in explicitly. See [migration](mutation-admission.md).

Milestone 20 is partial pending SQL/DHCP acceptance and fixture completion. This
is local admission, not distributed fencing; one externally enforced writer per
database is still required. It does not fix native SQL transaction cleanup.
There is no version bump or alteration of published v0.1.0 artifacts.

# Development database targets (not released)

Acceptance now targets PostgreSQL 18 and MariaDB 12.3 LTS, with exact server
version evidence, explicit CI repositories and updated Docker image pins.
See [database support and verification](database-support.md). Kea remains 3.2.1;
no hook command or native database schema migration is introduced.

# v0.1.0 — initial release

Independent MPL-2.0 DHCPv4 configuration-backend hook for **unmodified ISC Kea
3.2.1**, using native PostgreSQL and MySQL/MariaDB backend APIs. No paid hooks
are required. Kea's hook ABI exports remain unchanged (ABI 30201).

Includes `cb-subnet4-list`, `cb-subnet4-get`, `cb-subnet4-set`,
`cb-subnet4-del` and `db-commands-diagnostic`. Set handles minimal standalone
subnets and basic IPv4 pools; omitted pools preserve existing basic pools,
supplied pools replace them, and an empty list clears them.

Local verification: Debian 12 WSL2, Linux x86_64, GCC 12.2/libstdc++, glibc 2.36,
PostgreSQL 15 and MariaDB 10.11. SQL mutation, rollback, audit, real DHCP DORA
and retained-lease checks cover packet multithreading enabled and disabled.
Oracle MySQL, other Kea versions, other architectures and portable binary
compatibility across distributions are unverified. Ubuntu 24.04 is the CI
target; its own acceptance gates must pass before publication.
Each archive identifies its build distribution and records native dependencies
and required runtime symbol versions in `manifest.json`.

Install only with the matching Kea shared libraries, C++ ABI, upstream SQL hook
and initialized schema. Dependencies are not bundled. Follow the included
`INSTALL.md` before loading. The archive and its adjacent `.sha256` checksum
are published together; source is available from the corresponding Git tag.

Operational limits:

- Exactly one native configuration backend; explicit server-tag safety checks.
- Persistence does not activate configuration. Pull/reload/restart explicitly.
- Delete retains leases and requires `preserve-leases: true`; avoid unsafe
  subnet ID/prefix reuse while leases remain.
- Require an exclusive configuration writer. Preflight reads do not lock out
  other processes; reconcile an uncertain write before retrying.
- No shared-network management, richer subnet/option mutations or DHCPv6.
- Commands run synchronously on the main thread; protect the control channel
  and expect SQL latency to delay command processing.
- Diagnostic success checks API accessibility, not database connectivity.

Local verification does not establish remote CI success or production readiness
for a different installation. Publication and deployment are separate decisions.
