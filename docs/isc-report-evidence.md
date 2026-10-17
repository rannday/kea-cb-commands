# Sanitized ISC report evidence

Prepared 2026-10-16 from retained Milestone 15–18 evidence. No new SQL test,
connection interruption or crash reproduction was performed. The
[issue body](isc-sql-transaction-issue.md) and
[submission instructions](isc-report-submission.md) distinguish observations
from source analysis and missing causal evidence.

## Environment and provenance

The reused Kea installation was built from the project's pinned, unmodified
Kea 3.2.1 tarball. Retained `build/milestone18/kea-version.txt` contains the
following exact `kea-dhcp4 -V` output:

```text
3.2.1-git (tarball)
premium: no
linked with:
- log4cplus 2.0.8
- OpenSSL 3.0.22 25 Aug 2026
lease backends:
- Memfile backend 3.0
```

The no-hook version query lists Memfile; it does not mean SQL support was
absent. The retained build report records PostgreSQL and MySQL enabled.
Native SQL hooks were loaded in the historical SQL fixtures.

| Item | Verified metadata | Qualification |
| --- | --- | --- |
| Kea | 3.2.1-git, tarball, non-premium | Historical logs also identify 3.2.1-git |
| Kea build | Meson 1.7.2, Release, C++14, OpenSSL; PostgreSQL/MySQL enabled; NETCONF/Kerberos/tests/fuzz disabled | Retained installation report, not a fresh rebuild |
| Compiler | GCC 12.2.0, Debian `12.2.0-14+deb12u1` | Historical hook metadata records GNU 12.2.0, not its Debian package revision |
| OS / architecture | Debian 12 WSL; current Debian point version 12.15; amd64 / x86_64 | Exact historical point version and kernel not retained |
| PostgreSQL | Current installed server binary: `15.19 (Debian 15.19-0+deb12u1)` | Historical test family 15.x; historical patch unverified |
| MariaDB | Current installed server binary: `10.11.19-MariaDB-0+deb12u1` | Historical test family 10.11.x; historical patch unverified; backend type `mysql` |
| SQL clients in Kea report | PostgreSQL 15.19; MySQL-compatible client 3.3.20 | Client versions are not historical server versions |
| Historical hook build | Release, C++14, GNU 12.2.0, Linux x86_64; warnings treated as errors | `build/concurrency/release-build.json` and build flags |

The version-only server commands inspected installed binaries; they did not
query a running database. Oracle MySQL runtime behavior is unverified.

Sanitized library locations replace identifying absolute installation paths.
`<KEA_PREFIX>` means the reused pinned Kea installation and `<HOOK_BUILD>`
the historical concurrency build directory:

```text
<KEA_PREFIX>/lib/kea/hooks/libdhcp_pgsql.so
<KEA_PREFIX>/lib/kea/hooks/libdhcp_mysql.so
<HOOK_BUILD>/libdhcp_db_commands.so
```

The third-party hook delegates to native configuration-backend APIs; it does
not issue SQL or construct the native transaction objects. Packet threading
was off/on; commands execute on Kea's main thread in either mode.

## Four retained scenarios

Artifacts are local, ignored files under
`build/concurrency/concurrency-results/`. Each scenario retains
`outcomes.json`, `writer-b.log` and `observer.log`.

| Scenario directory | Packet MT | Peer exits: writer-b, observer | Rollback | After recovery |
| --- | --- | --- | --- | --- |
| `postgresql-mt-0` | Off | `-6, -6` | Confirmed | Baseline read and write/read of lifetime 1600 succeed |
| `postgresql-mt-1` | On | `-6, -6` | Confirmed | Same |
| `mysql-mt-0` | Off | `null, -6` | Confirmed | Same |
| `mysql-mt-1` | On | `null, -6` | Confirmed | Same |

Python subprocess status `-6` denotes SIGABRT. `null` means no exit was
recorded for the surviving writer, not exit status zero. Six process aborts
are recorded across these four scenarios. This is not a repeatability study
or a measured failure rate.

The `sql-interruption-upstream-abort` records contain
`rollback-confirmed: true` and recovery text
`restart aborted peers; reconcile before retry`. Aborted requests recorded
transport errors (`RemoteDisconnected`). The surviving MariaDB writer
returned `result: 1` with:

```text
Configuration backend write failed or unavailable; reconcile backend state before retrying.
```

The `sql-interruption-recovery` records show persisted `valid-lifetime: 1600`.
Before restart the harness asserts both unchanged database snapshots and a
native read equal to the baseline. This confirms rollback in these controlled
blocked, pre-commit cases, not in every possible connection-loss case.

## Selected diagnostic excerpts

Only message portions are included; timestamps, logger process identifiers
and unrelated lines are omitted. No configuration files or full logs are
attachments. The following message appears in PostgreSQL writer logs
(`postgresql-mt-0/writer-b.log:9`, `postgresql-mt-1/writer-b.log:13`):

```text
DATABASE_PGSQL_FATAL_ERROR Unrecoverable PostgreSQL error occurred: Statement: <DELETE_SUBNET4_SERVER>, reason: FATAL:  terminating connection due to administrator command
```

Those logs also contain `server closed the connection unexpectedly` at lines
11 and 15 respectively. PostgreSQL observer diagnostics identify
`INSERT_SUBNET4` with MT off and `DELETE_POOLS4` with MT on.

MariaDB observer logs (`mysql-mt-0/observer.log:5`,
`mysql-mt-1/observer.log:7`) contain:

```text
DATABASE_MYSQL_FATAL_ERROR Unrecoverable MySQL error occurred: unable to execute for <DELETE FROM dhcp4_subnet_server WHERE subnet_id = ?>, reason: Lost connection to server during query (error code: 2013).
```

The `?` is the native prepared-statement placeholder. All six aborted-process
logs contain this exact pair of lines:

```text
terminate called after throwing an instance of 'isc::db::DbConnectionUnusable'
  what():  Attempt to use an invalid connection
```

Locations: PostgreSQL MT off writer 15–16 and observer 11–12; MT on writer
19–20 and observer 13–14; MariaDB observer MT off 6–7 and MT on 8–9.
These are termination diagnostics, **not a stack trace**.

## Test references and verification boundaries

Public test revision:
[`26b48ca6dd81237fa9090f5ed66a90d7388aca17`](https://github.com/rannday/kea-cb-commands/commit/26b48ca6dd81237fa9090f5ed66a90d7388aca17).
The tests are available at that revision; ignored historical logs are not.

- [Concurrency source](https://github.com/rannday/kea-cb-commands/blob/26b48ca6dd81237fa9090f5ed66a90d7388aca17/tests/concurrency.py#L327-L374):
  `verify_multiprocess` interrupts blocked peer sessions, checks snapshots,
  records aborts, restarts peers and checks recovery. `row_gate` at lines
  89–125 supplies the test-only administrative lock. `Peer.start` at lines
  48–67 waits for the endpoint and verifies hook command registration.
- [PostgreSQL snapshot](https://github.com/rannday/kea-cb-commands/blob/26b48ca6dd81237fa9090f5ed66a90d7388aca17/tests/postgresql.py#L94-L103):
  data-only dump comparison, excluding random dump restriction markers.
- [MariaDB snapshot](https://github.com/rannday/kea-cb-commands/blob/26b48ca6dd81237fa9090f5ed66a90d7388aca17/tests/mysql.py#L77-L93):
  table-content comparison, including audit tables.
- Local source: [concurrency](../tests/concurrency.py),
  [PostgreSQL](../tests/postgresql.py), [MariaDB](../tests/mysql.py).

The scenario used three daemons sharing an isolated configuration database.
Administrative fixture code locked an existing association, waited for two
native writes to block, then interrupted those two SQL sessions. It left the
primary daemon's session available. This was **administrative database-session
interruption, not a malicious DHCP packet**.

## Source conclusions and limitations

Kea 3.2.1's native transaction destructors call potentially throwing rollback
without containment. Their implicit nonthrowing exception specifications make
an escaping exception invoke `std::terminate()`. The
[issue body](isc-sql-transaction-issue.md) contains versioned source links.
This source-level exception-safety defect is confirmed. Connecting it to each
recorded abort remains unverified: no causal debugger stack, original exception
frame, unwinding-state capture, standalone reproducer or hook-free reproduction
exists. Hook lifecycle interactions have not been independently excluded.

Source-only comparisons found the same cleanup pattern in 3.3.1, 3.3.2 and
master snapshot `9fbe6be7b884f9a8e60b88c050c5b6799187312d`. No fix was identified
in those snapshots; none was run. This is not an exhaustive current fix or
duplicate-issue search. Previously restricted operations were not retried.

The primary daemon remained usable for native reads. Packet availability, HA,
supervised restart and outage duration were not measured. Explicit restart
restored hook registration and subsequent commands in the fixture. Restart
does not establish a transaction's outcome. Lost commit acknowledgement can
leave an uncertain result requiring persisted-state reconciliation before retry.
Security exploitability is unknown; no security vulnerability is established.

## Sanitization and review status

Excerpts and outcome assertions were verified against retained files during
the earlier Milestone 18 collection. On resume, a fresh read-only extraction
command was rejected by PreToolUse with:
`Protected .env or PEM path. Use a redacted example file.` It targeted named
metadata files and `*/outcomes.json` under the two retained evidence directories.
It did not execute and was not retried. The selected results above reuse the
earlier verified collection; a fresh automated artifact cross-check remains
unavailable from that operation.

The package excludes credentials, tokens, personal contact information,
identifying home paths, private hostnames, addresses and full configurations.
The public repository URL is intentional provenance. Raw build reports and
logs remain local and are **not approved attachments**. Attach this curated
document only after human review and confirmation of confidential visibility.
Historical exact database patch versions remain unavailable; supplying them
is optional and must not be inferred from current binaries.
