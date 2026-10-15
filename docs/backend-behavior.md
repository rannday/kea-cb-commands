# Verified Kea 3.2.1 backend behavior

This review uses the unmodified public `Kea-3.2.1` source under
`.upstream/kea-Kea-3.2.1`. Paths and line numbers below refer to that release.
Source inspection and runtime evidence are distinguished explicitly. Kea 3.0.4
has not been SQL-runtime-tested. No proprietary hook source is used.

## Pool and command selection

`src/lib/dhcpsrv/config_backend_pool_dhcp4.cc:40` delegates `getAllSubnets4` to
`getAllPropertiesConst` in `src/lib/config_backend/base_config_backend_pool.h:379`.
That helper returns the **first nonempty** matching backend collection. It does
not union databases, detect overlapping IDs or compare values. An unspecified
selector with no backends can return an empty collection; an explicit selector
with no match throws `NoSuchDatabase` (line 403).

`src/lib/database/backend_selector.h:89` exposes type, host and port selectors,
not database name or pool index. Pool enumeration and `selectBackends` are
protected (`base_config_backend_pool.h:595`). A type/host/port selector cannot
uniquely choose two database names at the same endpoint. Unspecified selection
also differs across pool helpers, so it cannot be treated as an aggregation API.

The hook uses the active `SrvConfig`'s inherited `getConfigControlInfo()`
(`src/lib/process/config_base.h:106`) and `getConfigDatabases()`
(`src/lib/process/config_ctl_info.h:189`). Its policy is:

| Configured backend state | Command behavior |
| --- | --- |
| No backend | Error: no configuration backend is configured |
| Exactly one, live | Explicitly select its native type; list matching subnets |
| Exactly one, empty/no matching rows | Success with `subnet4: []` |
| Exactly one, unavailable/removed during retry | Generic read error |
| Multiple, including empty/disjoint/overlapping | Error before reading |
| Any returned subnet belongs to a shared network | Error without partial data |

This assumes Kea's normal configured-backend lifecycle; backends injected by
other plugins outside the active configuration are not supported. Policy is
deliberately based on configured databases, so a temporarily removed backend
does not change which database a command would read. No command-level selection
arguments are exposed for listing. Explicit type selection permits the native MySQL path
without a database-specific branch in the hook.

Official schema constraints make subnet IDs and prefixes unique within each
database (`src/share/database/scripts/pgsql/dhcpdb_create.pgsql:1498` and
`src/lib/dhcpsrv/subnet.h:838`). Independent databases can reuse IDs. The
PostgreSQL integration test verifies schema rejection of duplicate IDs and
command rejection of two databases with overlapping IDs; it never invents merge
or last-writer semantics.

## Server associations and serialization

`src/hooks/dhcp/pgsql/pgsql_cb_impl.h:772` filters `ALL` to the reserved universal
`all` association. `ONE(tag)` includes that tag **and** universal objects (line
794). `UNASSIGNED` means no server associations (line 779), not a missing tag.
Both drivers reject `ANY` for `getAllSubnets4`
(`pgsql_cb_dhcp4.cc:695`, `mysql_cb_dhcp4.cc:796`).

The list command maps an empty active server tag to `ALL`, otherwise `ONE(tag)`.
Unassigned objects, arbitrary selectors and per-request tag changes are not
exposed. PostgreSQL and MariaDB fixtures verify universal/specific/missing/unassigned cases.

`src/lib/dhcpsrv/subnet.cc:723` and `:785` serialize subnet/network fields, pools
and options. They do not serialize the shared-network name loaded by
`src/hooks/dhcp/pgsql/pgsql_cb_dhcp4.cc:411`, nor the shared network's inherited
settings. The hook therefore rejects the entire result if any selected subnet
has a shared-network name. It does not return a misleading flat configuration.
Globals, option definitions and class definitions are outside this subnet-list
contract. See [verified fields](postgresql.md#reproducible-test).

## Failure, recovery and logging

`src/lib/pgsql/pgsql_connection.cc:555` marks failed connections unusable and
starts recovery. `pgsql_connection.h:496` posts recovery to the registered IO
service. `src/hooks/dhcp/pgsql/pgsql_cb_dhcp4.cc:2779` enters a multithreading
critical section; lines 2794–2810 use the active configured database list to
replace unusable backends. Success cancels the timer and reports recovery
(line 2822). Retry exhaustion invokes Kea's failure policy (line 2833).
`src/hooks/dhcp/mysql/mysql_cb_dhcp4.cc:2940` follows the same native mechanism.

The command catches native exceptions and returns a generic error without
exception text or connection parameters. Kea's own drivers may log raw database
details; secure those logs. Hook load/unload use the native logger. There is no
custom connection, background thread, retry loop or cached pool in this hook.

Both SQL tests use `serve-retry-continue`, 30 attempts and a one-second interval
(`reconnect-wait-time: 1000` in this release's configuration-backend path).
They stop the private cluster, assert repeated errors during retries, restart it
and verify a successful complex read without configuration reload in both
threading modes. MariaDB additionally tests two-try exhaustion: Kea logs
`MYSQL_CB_RECONNECT_FAILED4` and stays alive, with controlled read errors.
Restarting the database after exhaustion leaves reads failing during a two-second
observation; configuration reload restores them. Startup with an unavailable
database, PostgreSQL retry exhaustion and alternative failure policies remain
unverified. Default/on-fail policies can stop Kea; the command cannot provide
responses after the daemon stops. See [MariaDB recovery details](mysql.md#recovery-and-retry-exhaustion).

## Synchronous execution and limits

`src/bin/dhcp4/ctrl_dhcp4_srv.cc:1644` gives HTTP commands the DHCPv4 IO service;
`src/lib/config/http_command_mgr.cc:207` passes it to the listener. The main loop
polls it (`src/bin/dhcp4/dhcp4_srv.cc:1224`). HTTP response creation calls
`processCommand` synchronously (`src/lib/http/connection.cc:578`,
`src/lib/config/http_command_response_creator.cc:178`); the hook completes before
response retrieval (`src/lib/config/hooked_command_mgr.cc:52`). Unix control
dispatch likewise runs synchronously (`src/lib/config/unix_command_mgr.cc:378`).

Native backends' single connection and multithreading declaration assume calls
on the main IO thread. Packet-worker multithreading on/off passes the runtime
tests; arbitrary concurrent calls from foreign threads are unsupported. Listing
blocks command processing and has no pagination, cancellation or project size
cap. Production-scale behavior is unverified. Read success neither activates nor
changes the running DHCP configuration.

MySQL's constructor prepares write statements as well as reads
(`mysql_cb_dhcp4.cc:3779`); its read-only preparation restriction is an upstream
TODO at line 3781. MariaDB runtime probes verify SELECT-only startup rejection
and the need for SELECT/INSERT/UPDATE/DELETE grants; EXECUTE is unnecessary for
the verified reads. PostgreSQL permits the tested SELECT-only role. Table
snapshots verify MariaDB read nonmutation despite the required write grants;
see [the privilege experiments](mysql.md#experimentally-verified-privileges).

## Native subnet mutations

The following references are actual Kea 3.2.1 source inspection; the transaction,
audit, timestamp and activation observations also have real SQL runtime tests.

- `src/lib/dhcpsrv/config_backend_pool_dhcp4.h:305` exposes
  `createUpdateSubnet4`; its implementation delegates to the native single-backend
  helper (`config_backend_pool_dhcp4.cc:269`). The helper rejects zero or multiple
  live matches (`src/lib/config_backend/base_config_backend_pool.h:487–530`).
  The hook additionally requires exactly one configured database.
- `src/hooks/dhcp/pgsql/pgsql_cb_dhcp4.cc:863` and
  `src/hooks/dhcp/mysql/mysql_cb_dhcp4.cc:986` implement insert-or-update.
  PostgreSQL begins the transaction at line 966, creates a scoped audit revision
  at 970 and savepoint at 976. Duplicate insertion rolls back to that savepoint
  at 985 before updating. MySQL starts its transaction at 1103 and scoped audit
  revision at 1107; duplicate handling starts at 1119. Native transaction RAII
  rolls back uncommitted work (`src/lib/pgsql/pgsql_connection.cc:103–116` and
  `src/lib/mysql/mysql_connection.cc:41–54`). Commits occur at PostgreSQL 1040
  and MySQL 1160.
- Both update predicates match **ID OR prefix**, not ID alone
  (`pgsql_cb_dhcp4.cc:3868–3912`, `mysql_cb_dhcp4.cc:3435–3479`). Native updates
  remove pools/options and replace all server associations. The hook therefore
  checks both identities across `ANY` and rejects richer objects and retagging.
  `getSubnet4` by ID/prefix supports `ANY` (PostgreSQL 631/664, MySQL 734/766),
  unlike `getAllSubnets4`. A bare upsert without these checks is not our contract.
- SQL constraints are the final native guard, but not a substitute for that
  policy: the official PostgreSQL association FK uses ON UPDATE NO ACTION
  (`src/share/database/scripts/pgsql/dhcpdb_create.pgsql:3901–3908`), whereas
  MySQL uses ON UPDATE CASCADE (`scripts/mysql/dhcpdb_create.mysql:1935–1940`).
  A conflicting prefix must never be used to rename a different ID.
- `src/lib/dhcpsrv/subnet.cc:76` and `:242–273` enforce constructor ID, family
  and timer constraints. Construction is not complete server configuration
  validation. The hook validates exact fields, numeric bounds and canonical
  network address before construction. It creates no pools/options or inherited
  stored settings.
- Native writes reject `ANY`/`UNASSIGNED`. The hook writes with `ALL` or `ONE`
  after verifying the named server exists. `getServer4` intentionally excludes
  reserved `all` (`src/hooks/dhcp/pgsql/pgsql_query_macros_dhcp.h:685–701`), so
  universal writes rely on the official reserved association instead of that
  lookup. Existing multi-tag or unassigned objects cannot be reassociated.
- Official subnet audit triggers record insert/update (PostgreSQL schema
  3082/3095; MySQL 1663/1672). Both native scoped revisions use the description
  `subnet set`. Runtime tests observe new audit rows on create and update.
  The subnet's `StampedElement` uses local second-resolution time
  (`src/lib/cc/base_stamped_element.cc:17`), while audit revision creation uses
  native local microsecond time (`pgsql_cb_impl.cc:65`, `mysql_cb_impl.cc:42`).
  Timestamps are not optimistic-concurrency tokens.

The public pool does not expose a transaction spanning lookup and mutation,
connection locking or a compare-and-swap operation. The hook's preflight checks
are not atomic against independent writers. Coordinated exclusive configuration
writing is a prerequisite; cross-process concurrent mutation is unsupported.
The single native call is atomic on the tested failure paths: denying association
INSERT after subnet INSERT/UPDATE leaves every table, including audit, unchanged
on both engines. Native sequence/auto-increment allocation need not roll back.
Loss of the connection at commit remains an uncertain outcome and is never
automatically retried by this hook.

## Activation after persistence

`src/bin/dhcp4/ctrl_dhcp4_srv.cc:1253–1280` implements native
`config-backend-pull` on the main thread inside a multithreading critical section,
calling database configuration fetch in UPDATE mode. Backend writes do not call
this command. With periodic fetch disabled, real tests show new/updated stored
subnets through backend reads while `config-get` remains unchanged. Explicit
native pull applies creation and updates; reload and real process restart load
persisted configuration. Periodic fetching, when independently enabled, can also
activate changes. No automatic activation is added by this hook.

Tests inspect native active configuration, not DHCP packet allocation. Minimal
written subnets have no pools. Allocation, failed activation and external-writer
races are outside this verified boundary; see [the complete contract](commands.md).
