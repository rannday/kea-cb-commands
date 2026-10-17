## Describe the bug

Kea 3.2.1's native `PgSqlTransaction` and `MySqlTransaction` destructors invoke
potentially throwing rollback operations without exception containment. Both
destructors are implicitly nonthrowing. An escaping rollback exception
therefore invokes `std::terminate()`, potentially terminating DHCP service.
This is a confirmed source-level exception-safety defect.

Historical isolated configuration-backend tests recorded six SIGABRT process
exits after administrative database-session interruption during blocked writes.
The causal connection between those aborts and the destructors is **unverified
without a debugger stack**. The tests loaded a third-party native-API hook;
there is no hook-free reproduction or standalone reproducer. Security
exploitability is unknown; no security vulnerability has been demonstrated.
The scenario did not involve a malicious DHCP packet.

## To Reproduce

Existing test evidence, not a newly executed or independently minimized
reproducer:

1. Three unmodified Kea 3.2.1 DHCPv4 daemons share a private SQL configuration
   backend. Load the native PostgreSQL or MySQL hook plus
   `libdhcp_db_commands.so`, a third-party hook calling native
   `createUpdateSubnet4`. The native backend owns transactions; the hook
   issues no SQL and creates no transaction object.
2. A test-only administrative transaction locks an existing subnet-server
   association. Start two peer writes and wait until both block on that lock.
3. The fixture administratively interrupts those two database sessions and
   releases the gate, leaving the primary daemon's SQL session intact.
4. Record process exits and compare SQL snapshots/native reads with baseline.
   Restart aborted peers, verify hook registration, then read and write again.

Source at public commit
[`26b48ca6dd81237fa9090f5ed66a90d7388aca17`](https://github.com/rannday/kea-cb-commands/commit/26b48ca6dd81237fa9090f5ed66a90d7388aca17):
[`verify_multiprocess`, failure/recovery assertions](https://github.com/rannday/kea-cb-commands/blob/26b48ca6dd81237fa9090f5ed66a90d7388aca17/tests/concurrency.py#L327-L374),
[`row_gate`](https://github.com/rannday/kea-cb-commands/blob/26b48ca6dd81237fa9090f5ed66a90d7388aca17/tests/concurrency.py#L89-L125),
[PostgreSQL snapshots](https://github.com/rannday/kea-cb-commands/blob/26b48ca6dd81237fa9090f5ed66a90d7388aca17/tests/postgresql.py#L94-L103),
[MariaDB snapshots](https://github.com/rannday/kea-cb-commands/blob/26b48ca6dd81237fa9090f5ed66a90d7388aca17/tests/mysql.py#L77-L93).

| Backend | Packet multithreading | Peer exits: writer-b, observer | Persisted-state check | After restart/recovery |
| --- | --- | --- | --- | --- |
| PostgreSQL | Off | `-6, -6` | Rollback confirmed | Read and write succeed |
| PostgreSQL | On | `-6, -6` | Rollback confirmed | Read and write succeed |
| MariaDB (`mysql`) | Off | `null, -6` | Rollback confirmed | Read and write succeed |
| MariaDB (`mysql`) | On | `null, -6` | Rollback confirmed | Read and write succeed |

`-6` is Python's subprocess status for SIGABRT. `null` denotes no exit recorded
for a surviving writer; it returned a generic command error (`result: 1`).
Aborted requests lost the HTTP connection. All four pre-commit cases passed
snapshot/native-read rollback assertions; subsequent recovery records show
`valid-lifetime: 1600`. Four retained scenarios do not establish a failure rate
or deterministic repeatability.

## Expected behavior

Database operation failures should be reported through the native API with
exception-safe cleanup and accurate connection/transaction state. Failed
rollback must not imply a successful write or a confirmed rollback. A cleanup
exception should not terminate the daemon. No particular patch is proposed
as a validated fix.

## Environment

Pinned, unmodified Kea 3.2.1 tarball installation. Exact retained
`kea-dhcp4 -V` output:

```text
3.2.1-git (tarball)
premium: no
linked with:
- log4cplus 2.0.8
- OpenSSL 3.0.22 25 Aug 2026
lease backends:
- Memfile backend 3.0
```

- Kea build: Meson 1.7.2, Release, C++14, OpenSSL; PostgreSQL/MySQL enabled;
  NETCONF, Kerberos, upstream tests and fuzz disabled. The no-hook version
  query's Memfile listing does not exclude dynamically loaded SQL support.
- Native SQL hook locations, with installation paths sanitized:
  `<KEA_PREFIX>/lib/kea/hooks/libdhcp_pgsql.so` and
  `<KEA_PREFIX>/lib/kea/hooks/libdhcp_mysql.so`.
- Third-party hook: `<HOOK_BUILD>/libdhcp_db_commands.so`; historical build
  Release/C++14, GNU 12.2.0, warnings treated as errors.
- Debian 12 WSL, x86_64/amd64. Current point version 12.15; exact historical
  point version/kernel unverified. Current compiler package:
  GCC 12.2.0 (`12.2.0-14+deb12u1`). Historical metadata records GNU 12.2.0.
- Historical SQL families: PostgreSQL 15.x, MariaDB 10.11.x. Exact historical
  server patch versions are unavailable. Current installed server binaries
  report PostgreSQL `15.19 (Debian 15.19-0+deb12u1)` and MariaDB
  `10.11.19-MariaDB-0+deb12u1`; these do not establish historical versions.
  Kea's current report lists client versions PostgreSQL 15.19 and
  MySQL-compatible 3.3.20. No running server was queried for this report.
- Oracle MySQL is untested. Both packet-threading modes appear in retained
  tests; commands execute on the main thread in either mode.

## Additional Information

Kea 3.2.1 source references:

| Native component | Versioned source | Behavior |
| --- | --- | --- |
| PostgreSQL destructor | [pgsql_connection.cc:108–113](https://github.com/isc-projects/kea/blob/Kea-3.2.1/src/lib/pgsql/pgsql_connection.cc#L108-L113) | Unguarded rollback if uncommitted |
| PostgreSQL declaration | [pgsql_connection.h:169](https://github.com/isc-projects/kea/blob/Kea-3.2.1/src/lib/pgsql/pgsql_connection.h#L169) | Implicit nonthrowing specification |
| PostgreSQL rollback | [pgsql_connection.cc:630–647](https://github.com/isc-projects/kea/blob/Kea-3.2.1/src/lib/pgsql/pgsql_connection.cc#L630-L647) | Changes nesting count, checks usability, executes rollback; can throw |
| MySQL destructor | [mysql_connection.cc:46–52](https://github.com/isc-projects/kea/blob/Kea-3.2.1/src/lib/mysql/mysql_connection.cc#L46-L52) | Same unguarded cleanup |
| MySQL declaration | [mysql_connection.h:208](https://github.com/isc-projects/kea/blob/Kea-3.2.1/src/lib/mysql/mysql_connection.h#L208) | Implicit nonthrowing specification |
| MySQL rollback | [mysql_connection.cc:674–689](https://github.com/isc-projects/kea/blob/Kea-3.2.1/src/lib/mysql/mysql_connection.cc#L674-L689) | Changes nesting count, checks usability, calls `mysql_rollback`; can throw |
| Shared usability check | [database_connection.h:266–270](https://github.com/isc-projects/kea/blob/Kea-3.2.1/src/lib/database/database_connection.h#L266-L270) | Throws `DbConnectionUnusable` |

Native mutation transaction scopes:
[PostgreSQL](https://github.com/isc-projects/kea/blob/Kea-3.2.1/src/hooks/dhcp/pgsql/pgsql_cb_dhcp4.cc#L966-L1040),
[MySQL](https://github.com/isc-projects/kea/blob/Kea-3.2.1/src/hooks/dhcp/mysql/mysql_cb_dhcp4.cc#L1103-L1160).
Candidate initial error paths:
[PostgreSQL checkStatementError](https://github.com/isc-projects/kea/blob/Kea-3.2.1/src/lib/pgsql/pgsql_connection.cc#L534-L564),
[MySQL checkError](https://github.com/isc-projects/kea/blob/Kea-3.2.1/src/lib/mysql/mysql_connection.h#L696-L726).

Under C++14, the implicit destructor exception specification depends on bases
and members, not calls in the body. These transaction objects' bases/members
do not make destruction potentially throwing. Escaping rollback invokes
`std::terminate()` even without active unwinding. A second escaping exception
during unwinding is an additional termination condition; `noexcept(false)`
alone would not solve it. Outer hook catches cannot intercept termination
inside a nonthrowing native destructor.

Historical logs contain PostgreSQL administrative-termination diagnostics,
MariaDB lost-connection error 2013, and this pair in all six aborted processes:

```text
terminate called after throwing an instance of 'isc::db::DbConnectionUnusable'
  what():  Attempt to use an invalid connection
```

These messages do not capture destructor frames, the original exception or
active unwinding. Please independently establish the causal stack and native
transaction nesting, ideally without this hook. Review cleanup exception
containment, preservation of the original error, unusable-connection recovery
and transaction-state handling. These are investigation considerations, not
verified fixes. Hook lifecycle interactions remain unexcluded.

Source-only comparison found the same unguarded cleanup in:

- Kea 3.3.1: [PostgreSQL](https://github.com/isc-projects/kea/blob/Kea-3.3.1/src/lib/pgsql/pgsql_connection.cc#L133-L138), [MySQL](https://github.com/isc-projects/kea/blob/Kea-3.3.1/src/lib/mysql/mysql_connection.cc#L46-L52).
- Kea 3.3.2: [PostgreSQL](https://github.com/isc-projects/kea/blob/Kea-3.3.2/src/lib/pgsql/pgsql_connection.cc#L133-L138), [MySQL](https://github.com/isc-projects/kea/blob/Kea-3.3.2/src/lib/mysql/mysql_connection.cc#L46-L52).
- Master snapshot `9fbe6be7b884f9a8e60b88c050c5b6799187312d`:
  [PostgreSQL](https://github.com/isc-projects/kea/blob/9fbe6be7b884f9a8e60b88c050c5b6799187312d/src/lib/pgsql/pgsql_connection.cc#L133-L138), [MySQL](https://github.com/isc-projects/kea/blob/9fbe6be7b884f9a8e60b88c050c5b6799187312d/src/lib/mysql/mysql_connection.cc#L46-L52).

No fix was identified in those inspected snapshots. They were not built or
run; this is not an exhaustive issue/history search or a regression range.

Potential impact is loss of the affected daemon's DHCP and control service.
The primary peer remained usable for native reads; packet availability, HA,
supervised restart and outage duration were not measured. Explicit restart
restored commands in the fixture, but does not guarantee uninterrupted DHCP.
Rollback was checked before commit in these cases. Loss of a commit
acknowledgement can instead leave an uncertain outcome: reconcile persisted
state before retry. Runtime configuration activation is separate from SQL
persistence. No hook workaround or upstream fix has been validated.

Curated diagnostic evidence can be attached separately; full configurations
and raw logs are excluded. Independent reproduction and a causal stack remain
outstanding, and exact historical SQL patch versions may be unavailable.

## Contacting you

Please reply through this GitLab issue. Confidential reporting is requested
initially because of potential daemon termination; exploitability is unknown.
