# SQL transaction crash investigation — Milestone 16

Status: investigation stopped at the user's request on 2026-10-16. No
independent reproducer was executed. No production mitigation was implemented.
The supported Kea version remains 3.2.1.

## Preserved source findings

The hook delegates persistence to the native backend pool's
`createUpdateSubnet4` in `src/subnet4.cc`. It does not construct a SQL
transaction. The native PostgreSQL backend constructs `PgSqlTransaction`
inside `createUpdateSubnet4`, creates a scoped audit revision and savepoint,
updates the subnet and associations, and commits at the end. Hook callout
exception handlers surround the native call in `src/commands.cc`.

Kea 3.2.1 contains the following cleanup path:

- `src/lib/pgsql/pgsql_connection.cc:108–113`:
  `PgSqlTransaction::~PgSqlTransaction()` calls `conn_.rollback()` if commit
  was not completed. There is no catch around rollback.
- `src/lib/pgsql/pgsql_connection.cc:630–647`: rollback decrements transaction
  nesting state, checks connection usability and executes SQL rollback.
  An unusable connection or a failed rollback can throw.
- `src/lib/mysql/mysql_connection.cc:46–52`:
  `MySqlTransaction::~MySqlTransaction()` likewise calls rollback without
  containing exceptions.
- `src/lib/mysql/mysql_connection.cc:674–687`: the corresponding rollback
  path checks connection usability after updating nesting state.
- Destructor declarations in `src/lib/pgsql/pgsql_connection.h:169` and
  `src/lib/mysql/mysql_connection.h:208` have no `noexcept(false)` declaration.
  Their reference and Boolean members do not make destruction potentially
  throwing. Under C++14 these destructors are implicitly nonthrowing.

An exception escaping either nonthrowing destructor invokes `std::terminate`.
A rollback exception during unwinding is additionally a double-exception
termination condition. An outer hook catch cannot recover from termination.
This establishes a source-level upstream cleanup defect mechanism; it does
not independently demonstrate that mechanism as the cause of a particular
observed process abort.

Sources: [PostgreSQL implementation](https://github.com/isc-projects/kea/blob/Kea-3.2.1/src/lib/pgsql/pgsql_connection.cc#L108),
[PostgreSQL declaration](https://github.com/isc-projects/kea/blob/Kea-3.2.1/src/lib/pgsql/pgsql_connection.h#L169),
[MySQL implementation](https://github.com/isc-projects/kea/blob/Kea-3.2.1/src/lib/mysql/mysql_connection.cc#L46),
[MySQL declaration](https://github.com/isc-projects/kea/blob/Kea-3.2.1/src/lib/mysql/mysql_connection.h#L208).

## Existing evidence inspected

The Milestone 15 test in `tests/concurrency.py` locks the existing subnet-server
association for subnet 1500 using an administrative fixture connection. Native
writes block on that lock. The test then terminates the active database
connections used by two peer daemons, leaving the primary connection alive.
It checks database snapshots, transport failure, SIGABRT (`-6`), termination
and `DbConnectionUnusable` log text, and operations after restarting peers.

Those assertions and the existing explanation in
[backend behavior](backend-behavior.md#multi-process-validation) were inspected.
They were not rerun in this session. Existing diagnostic logs remain under
`build/concurrency/`; this session did not independently validate their contents
or produce a new stack trace. The prior documentation's upstream attribution
must therefore be distinguished from a completed independent reproduction.

## Upstream comparison

Read-only upstream source comparison found the same unguarded cleanup behavior
in 3.3.1, 3.3.2 and master at commit
`9fbe6be7b884f9a8e60b88c050c5b6799187312d`. In 3.3.2 the PostgreSQL destructor
is at line 133 and rollback at line 673; the MySQL destructor is at line 46
and rollback at line 692. No relevant fix was found in the compared sources.
These versions were not built or executed.

The [ISC Kea page](https://www.isc.org/kea/) listed 3.2.1 as current stable,
3.0.4 as stable LTS, and 3.3.2 as development when checked on 2026-10-16.
No newer maintained stable release containing a fix was identified.
Issue searches did not confirm an associated upstream issue. GitLab API and
some release-note access were blocked, so absence of an issue or patch is not
established.

Comparison sources:
[3.3.2 PostgreSQL](https://github.com/isc-projects/kea/blob/Kea-3.3.2/src/lib/pgsql/pgsql_connection.cc#L133),
[3.3.2 MySQL](https://github.com/isc-projects/kea/blob/Kea-3.3.2/src/lib/mysql/mysql_connection.cc#L46),
[master PostgreSQL snapshot](https://github.com/isc-projects/kea/blob/9fbe6be7b884f9a8e60b88c050c5b6799187312d/src/lib/pgsql/pgsql_connection.cc#L133),
[master MySQL snapshot](https://github.com/isc-projects/kea/blob/9fbe6be7b884f9a8e60b88c050c5b6799187312d/src/lib/mysql/mysql_connection.cc#L46).

## Unverified work and availability limits

Independent reproduction without this hook, the original exception's stack,
the active unwinding state at termination, repeatability, both threading modes,
and recovery behavior were not verified in Milestone 16. No safe hook-level
mitigation was demonstrated. No outer exception catch is proposed as a fix.
No newer-version runtime comparison, Release rebuild, quality gate, SQL/DHCP
regression suite or sanitizer run was performed before the stop request.

Operational supervision and database monitoring remain possible containment
measures, not a proven correction. A restart can interrupt DHCP service and
does not establish transaction outcome. A controlled connection termination
before commit can establish rollback; loss of a commit acknowledgement remains
uncertain. Reconcile persisted identities, associations and pools before retry.

A delegated reproducer task was rejected by a cybersecurity restriction. It
was not retried. No reproducer, database fixture, daemon or debugger was started
by the main session. The final process check found no PostgreSQL, MariaDB,
Kea DHCPv4, debugger or reproducer processes. The worktree was clean before
this findings document was added. No upstream issue was submitted, and no
commit or push was performed.

Assessment: **PARTIAL investigation; production readiness remains unresolved.**
The upstream source mechanism is confirmed. Independent causal attribution
and tested availability mitigation remain incomplete.
