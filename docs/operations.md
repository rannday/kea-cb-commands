# Release operations

Use unmodified Kea 3.2.1 and a hook built against that exact shared-library
installation. PostgreSQL 15 and MariaDB 10.11 are runtime-tested; Oracle MySQL,
other Kea versions and portable binary distribution are unverified. Follow
[reproducible builds](reproducible-builds.md) for build and acceptance commands,
and [development](development.md) when reusing an existing installed prefix.
For a versioned archive, follow [release installation](release-install.md),
including its platform/runtime manifest and checksum checks.

## Install and check

1. Run the strict integration and quality gates before installing. Stage with
   `cmake --install build/integration --prefix "$PWD/build/stage"`; verify the
   staged artifact and run its lifecycle smoke test as documented in the build
   guide. Set the paths to the actual build and matching Kea prefix.
2. Install `libdhcp_db_commands.so` in the intended Kea hook directory. The
   installation process needs directory write access; the daemon needs read
   access to the module and its dependencies. Retain the previous module and
   configuration for rollback. Replace a loaded module only during a controlled
   service stop; do not overwrite a mapped shared object in place.
3. Resolve all Kea dependencies to the same installation. There is no embedded
   RPATH. A private prefix needs its library directory in the daemon's loader
   environment, including when a service manager starts it. An interactive
   shell's `LD_LIBRARY_PATH` alone does not configure a service.
4. Configure the matching upstream SQL hook first, then this hook, and exactly
   one native configuration database. See the [PostgreSQL](postgresql.md#configure-kea)
   or [MariaDB](mysql.md#configure-kea) example. Use the official matching schema;
   back up existing configuration, schema and leases before planned changes.
5. Validate the intended configuration with the matching daemon's
   `kea-dhcp4 -t /absolute/path/kea.json`, then `-T` to exercise hook loading.
   These checks do not prove command behavior or DHCP service. During a planned
   service start, check `list-commands`, `db-commands-diagnostic`, and an actual
   `cb-subnet4-list` through the secured control channel. Diagnostic success
   checks the pool API, not database connectivity. No startup mutation is needed.

Persistence does not request activation. Inspect the stored object with get/list,
then explicitly use native `config-backend-pull`, reload or restart when ready.
Verify `config-get` and DHCP behavior afterward. Independently enabled periodic
fetching can activate persisted changes; keep `config-fetch-wait-time: 0` when
manual activation is required. Deletion preserves leases; avoid conflicting
subnet ID or prefix reuse until lease handling is resolved.

## Security and writer ownership

Current development builds deny set/delete unless the designated writer's hook
entry has `"parameters": {"allow-mutations": true}`. Consumers use false or
omit the parameter; diagnostic/list/get remain available. Invalid types and
unknown parameter names fail load. See [migration and role examples](mutation-admission.md).
This is a breaking default change from v0.1.0 and is pending SQL/DHCP acceptance.
Protect native reload/configuration access because it can replace admission
parameters. No ordinary hook command changes the role.

Treat access to Kea's control channel as configuration-administrator access.
This hook adds no authentication or per-command/per-tag authorization. A caller
can explicitly select another tag in get/set/delete; tags are selection and
association rules, not tenant access controls. Restrict the channel to trusted
administrators using Kea's supported authentication and transport controls.
HTTP Basic authentication alone does not encrypt credentials: use protected
local access or a secured TLS transport for remote administration.

Protect Kea configuration, database credentials, control credentials and logs
with appropriate file permissions. The hook returns generic native failure
messages; upstream Kea/connector logs and configuration output still need
sensitive-data handling. Do not publish those logs or configuration unredacted.
Scope SQL grants to the intended database; do not grant administrator privileges.

Use one coordinated writer across all Kea processes, tools and administrators
sharing the database. Requests reaching this daemon are synchronous on its main
thread in both packet threading modes. That serialization does not lock out
external writers between preflight reads and mutation. SQL calls can also delay
other control work; account for native backend timeouts in operational monitoring.
There is no cross-process concurrency guarantee or performance/scale certification.

## Troubleshooting and recovery

| Symptom | Action |
| --- | --- |
| Module fails to load or has undefined symbols | Check exact daemon/hook ABI, required exports, dependency resolution and allowed hook directory. Use the artifact verifier against the deployed Kea prefix. |
| Command is unsupported | Check that this hook loaded and appears in the effective configuration; inspect native startup logs. |
| Mutations are disabled | Verify designated writer ownership and effective diagnostic `allow-mutations`; enable true only on the externally fenced owner. Consumers should continue rejecting. |
| Diagnostic succeeds but list fails | Check `config-control`, the upstream SQL hook, schema, credentials and database reachability. Diagnostic does not open a database connection. |
| Multiple-backend or tag error | Configure exactly one backend; check the command's exact tag and association rules. `all` is the universal association, not every server's objects. |
| Rich-object or shared-network rejection | Use a management path that preserves those attributes. This hook supports only its documented standalone subnet contract. |
| Backend unavailable | Restore database reachability and monitor native reconnect logs. Reads fail rather than reporting an empty database. After retry exhaustion, recovery can require an explicit configuration reload or restart. |
| Write/delete fails or a response is lost | Reconcile stored ID, prefix, pools, associations and audit state before retrying. Connection loss at commit has an uncertain outcome; the hook does not automatically retry a mutation. |
| Persistence succeeds but DHCP is unchanged | Perform explicit activation and inspect active configuration. During outages even a successful native pull can be a no-op after the backend was removed. |

Use get/list again after recovery and compare against the intended state before
allowing another write. Existing SQL tests inject late mutation failures and
verify transactional rollback, but they do not establish the outcome of every
possible connection loss at commit. Hook unload/reload does not repair SQL
connectivity itself; backend recovery belongs to upstream Kea.
