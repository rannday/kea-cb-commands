# Native MySQL/MariaDB integration

Milestone 3.5 uses Debian 12 WSL2, MariaDB 10.11.19, Connector/C 3.3.20 and
unmodified Kea 3.2.1 with its official MySQL schema (35.0). Oracle MySQL has not
been runtime-tested. No packages, persistent services or system databases were
changed; the required MariaDB packages were already installed.

The hook reads the native Kea DHCPv4 configuration backend interface. It adds no
MySQL SQL or database-specific branch. List arguments remain absent or `{}`;
there is no command-level backend selector. Multiple configured backends are
rejected rather than implicitly selecting one or merging overlapping subnet IDs.
Milestone 4 adds the same native minimal subnet mutation as PostgreSQL; see
[the exact command contract](commands.md).

## Prerequisites and invocation

Provide an unmodified Kea 3.2.1 build with MySQL support, its matching
`libdhcp_mysql.so`, this project's hook built against that same Kea, the
official `src/share/database/scripts/mysql/dhcpdb_create.mysql` schema, a MySQL
or MariaDB command-line client, a MariaDB `mariadb-install-db` installer
(`mysql_install_db` alias also works), and its matching server executable.
The installer must support `--auth-root-authentication-method=normal` and
`--skip-test-db`; Oracle MySQL's `mysqld --initialize` is not currently supported.
Run as an ordinary non-root user. Do not point at a production database.

### Build the matching native backend

On Debian 12 the required database packages are `mariadb-server`,
`mariadb-client`, and `libmariadb-dev-compat` (which depends on `libmariadb-dev`).
Inspect installed packages before installing anything. Package installation must
not start or enable a persistent database service; the harness starts its own
unprivileged server. No package installation was needed for Milestone 3.5.

Reuse the existing unmodified source and build directories. With this checkout's
local Meson 1.12.1 runner:

```sh
python3 .upstream/meson-1.12.1/meson.py configure build-kea-3.2.1 -Dmysql=enabled
ninja -C build-kea-3.2.1 -j 2 \
  src/hooks/dhcp/mysql/libdhcp_mysql.so \
  src/bin/dhcp4/kea-dhcp4 \
  src/hooks/dhcp/pgsql/libdhcp_pgsql.so \
  src/lib/d2srv/libkea-d2srv.so
```

This uses Kea's supported Meson option, without modifying upstream source or
installing Kea. Enabling MySQL changes generated headers, so Ninja may rebuild
required core dependencies. Keep the daemon, both native hooks and this hook on
the same source tag, compiler ABI and shared-library build. Build-tree pkg-config
reports `3.2.1-git`; the exact hook framework version is `30201`. Neither Kea
3.0.4 nor a mixed installed/build-tree ABI is covered.

Enable the opt-in CMake test with explicit matching paths:

```sh
cmake -S . -B build \
  -DKEA_DB_COMMANDS_MYSQL_TESTS=ON \
  -DKEA_DHCP4_EXECUTABLE=/path/to/kea-dhcp4 \
  -DKEA_MYSQL_CLIENT=/usr/bin/mariadb \
  -DKEA_MYSQL_SERVER=/usr/sbin/mariadbd \
  -DKEA_MYSQL_INSTALL_DB=/usr/bin/mariadb-install-db \
  -DKEA_MYSQL_HOOK=/path/to/libdhcp_mysql.so \
  -DKEA_MYSQL_SCHEMA=/path/to/kea-3.2.1/src/share/database/scripts/mysql/dhcpdb_create.mysql
cmake --build build
ctest --test-dir build -R mysql --output-on-failure
```

For an uninstalled Kea build, prefix the configure command with
`PKG_CONFIG_PATH="$PWD/build-kea-3.2.1/meson-uninstalled"`. If MySQL was enabled
after this project's first configure, add `-U__pkg_config_checked_KEA` to refresh
CMake's cached pkg-config metadata. Otherwise the staged native hook may fail to
find `libkea-mysql.so`. CTest supplies the matching library directories through
its process-local `LD_LIBRARY_PATH`; no system loader configuration is changed.
Direct Python invocation needs those same matching library directories.

`KEA_DB_COMMANDS_MYSQL_TESTS=ON` registers the test with CTest's `MySQL` label;
`ctest --test-dir build -L MySQL --output-on-failure` selects that label.

The harness can also run directly:

```sh
python3 tests/mysql.py \
  --server /path/to/kea-dhcp4 \
  --hook /path/to/libdhcp_db_commands.so \
  --mysql-hook /path/to/libdhcp_mysql.so \
  --schema /path/to/kea-3.2.1/src/share/database/scripts/mysql/dhcpdb_create.mysql \
  --mysql-bin /usr/bin/mariadb \
  --mysql-install-db /usr/bin/mariadb-install-db \
  --mysql-server /usr/sbin/mariadbd \
  --work-dir /tmp/kea-mysql-tests
```

`--mysql-bin` names the client executable, not its directory. Missing files or
running as root produce a prerequisite message with exact missing paths and exit
77 (CTest skip), never a passing integration result.

## Isolation and verified coverage

Each threading mode uses a fresh private data directory and Unix socket. The
database server uses `--skip-networking` and `--no-defaults`; clients likewise
ignore default option files. The test clears inherited MySQL environment
variables and uses a private MySQL option directory and login-file path. Kea's
native connection passes a null socket argument to `mysql_real_connect`; the harness sets
`MYSQL_UNIX_PORT` and `host=localhost` to select its private socket. This works
with the verified Connector/C build; no TCP listener or default database socket
is used.
The database client always receives the explicit private socket. Kea receives a
random account name created only inside the fixture, so an incorrectly selected
default socket cannot authenticate as an existing application account.

Fixture SQL runs only in the disposable official schema under its administrator.
It uses the official audit procedure. By default, Kea uses a separate account
granted `SELECT, INSERT, UPDATE, DELETE` only on the disposable schema.
These grants allow native statement preparation; no DDL or global privileges are
granted. Full table-content snapshots before and after reads verify that commands
make no database changes. This tests nonmutating commands, not a database-enforced
read-only account. No SQL enters the hook.

The harness verifies command registration, empty and known-subnet reads,
multiple subnets and pools, subnet and pool DHCP options (including always-send),
subnet timers, client-class references, additional class evaluation and user
context. It shares PostgreSQL's semantic JSON validator. Universal, tagged,
missing-tag and unassigned associations are checked. Missing matches return an
empty list. Invalid arguments, including backend/tag overrides, are rejected.
Two databases at the same endpoint are rejected both when the second is empty
and when it contains an overlapping subnet ID. Reads leave runtime subnets empty
and all database table contents unchanged. Both threading modes are exercised.
Shared-network rejection is runtime-tested by the PostgreSQL fixture; MariaDB
does not add coverage of that unsupported serialization case.

Processes stop on failures as well as success. Private credentials, data,
sockets and logs are removed with each fixture. Failure output never prints
their contents. Fixture creation and deliberate test changes use SQL only in
the test administrator, never in the hook.

## Experimentally verified privileges

Kea 3.2.1's native constructor prepares all statements, including writes; its
upstream TODO defers restricting preparation for read-only access. The harness
tests this ladder with fresh schema-scoped accounts and snapshots:

| Grants | Native initialization |
| --- | --- |
| SELECT | Rejected: INSERT permission required |
| SELECT, INSERT | Rejected: UPDATE permission required |
| SELECT, INSERT, UPDATE | Rejected: DELETE permission required |
| SELECT, INSERT, UPDATE, DELETE | Accepted |
| Above plus EXECUTE | Accepted; EXECUTE unnecessary for these reads |

Functional reads use the four-grant account, without DDL or global grants.
This is nonmutating command verification, not database-enforced read-only
access. PostgreSQL's SELECT-only, read-only-transaction fixture still passes.
The default MariaDB test treats the expected restricted-account failures as
assertions. Optional `--select-only` instead runs the functional path with only
SELECT: native startup fails, which remains a test failure rather than a skip.
These read-initialization observations are separate from the mutation privilege
test below.

## Recovery and retry exhaustion

With `on-fail: serve-retry-continue`, 30 attempts and
`reconnect-wait-time: 1000`, repeated outage reads return the controlled generic
error. Restarting the private server before exhaustion restores complex reads
through Kea's native recovery without configuration reload. A separate two-try
case waits for `MYSQL_CB_RECONNECT_FAILED4`: Kea remains alive and reads fail.
Restoring MariaDB alone does not restart exhausted retries during the observed
two-second window; `config-reload` restores the backend and successful reads.

In this release's configuration-backend path, `DatabaseConnection::makeReconnectCtl`
passes the interval unchanged to `TimerMgr`, whose unit is milliseconds.
Use `1000` for the tested one-second interval. The earlier fixture's value `1`
could exhaust retries before restart, notably with threading enabled. This is
a test configuration correction, not custom recovery logic or a Kea patch.
Startup with an unavailable database and alternative failure policies remain
unverified. The hook adds no MySQL-specific code or connection handling.

## Milestone 4 mutation verification

After proving nonmutating reads with the four-grant account, the harness attempts
a valid native subnet write without EXECUTE and requires a controlled error with
unchanged table contents. It then grants schema-scoped EXECUTE for the native
audit procedure and runs the shared mutation tests successfully. A verified
working mutation grant set is SELECT, INSERT, UPDATE, DELETE, EXECUTE on the
private official schema; no DDL or global grants are used. For an already created
disposable test account, the additional test grant is:

```sql
GRANT EXECUTE ON kea_test.* TO 'kea_writer'@'localhost';
```

Replace the account with the one in your private fixture; production credentials
do not belong in source. This establishes the tested grant requirement, not a
claim to the smallest possible per-routine/table grant set. PostgreSQL tests
retain the official function execution defaults and use a separate writer role.

Both threading modes cover create/update with exact ID/prefix/lifetime and
association, validation and conflicts, rejection of richer objects and retagging,
unchanged unrelated subnets, native audit records and modification timestamps.
Snapshots cover every table, including audit; identity counters are not compared.
For a late native failure, the harness gives INSERT through table grants, then
revokes association-table INSERT on the live connection. Both a new-subnet INSERT
and existing-subnet UPDATE fail with all table contents restored. Schema-level
grant changes alone did not revoke access on an already open connection in the
experiment; table-level revocation is used to test the intended late failure.

The same hook code handles both engines. No MySQL-specific mutation branch,
schema or reconnect loop is added. Native pull/reload activates persisted writes,
and actual process restart reloads them. Writes alone do not change `config-get`
when periodic fetching is disabled. DHCP allocation, concurrent external writers
and commit-boundary connection loss are not proved safe by these tests; see
[the integrity and activation boundary](commands.md).
