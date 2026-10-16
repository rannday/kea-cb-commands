# Development history

This archive preserves earlier setup commands and execution records. Paths and
version-specific instructions below describe those runs; use the current
[development guide](development.md) and [build guide](reproducible-builds.md)
for new work.

For the current clean-build procedure, pinned quality tools, strict acceptance
gate, CI design and artifact checks, start with
[reproducible builds](reproducible-builds.md). The milestone records below retain
their historical commands and execution evidence.

## Recommended environment

Use Debian WSL2 for local Linux builds from Windows, or native Linux for an
equivalent development environment. Prefer a checkout on the WSL Linux filesystem
for large upstream builds; a checkout under `/mnt/c` also works but can be slower
and has longer paths. Windows C++/MSYS2 tools are useful for editing and formatting;
they do not produce a Linux Kea-compatible hook. There is no supported Windows
native build path in this project.

Use the same compiler, standard library ABI, Boost, architecture, and relevant
build flags as the target Kea installation. Keep each Kea release in a separate
prefix and use a separate hook build directory. Containers are optional future
packaging tools, not a dependency. No Docker setup is included.

### Keep the checkout on Debian's filesystem

After you finish the repository rename and save/push the initial files yourself,
open Debian WSL and clone the repository under your Linux home directory:

```bash
mkdir -p ~/src
git clone <your-repository-url> ~/src/kea-db-commands
cd ~/src/kea-db-commands
```

Use your final repository/directory name in place of `kea-db-commands`. Nothing
in this setup requires the current Windows directory name. Do not clone an empty
remote and expect uncommitted files from the Windows checkout to appear there;
save them in Git first, or explicitly transfer your working files separately.

Run the prerequisite checks and local Meson/upstream/hook build steps below from
that Linux checkout. Recreate the venv and build outputs there: virtual environments,
CMake caches, Meson builds, and installed pkg-config files contain absolute paths
and should not be copied from `/mnt/c` or reused after a directory rename.

If you use VS Code with its WSL extension, run `code .` from this Debian directory
and check that the window reports a WSL connection. Its terminal and compiler
should run in Debian. Windows Explorer can also reach the files at
`\\wsl.localhost\Debian\home\rann\src\kea-db-commands` (adjust the username/name).
Keep the active source, upstream source, venv, and build trees together on the
Linux filesystem. Use Git to synchronize checkouts; avoid editing two independent
copies without synchronizing their changes.

## Debian prerequisites (manual installation)

Run these yourself only when you intend to install packages. They are not run by
the repository build. Database client headers are needed to build upstream SQL
backends; database servers are unnecessary for the initial diagnostic.

```bash
sudo apt update
sudo apt install --no-install-recommends \
  build-essential cmake ninja-build pkg-config \
  python3 python3-venv bison flex curl ca-certificates \
  libboost-dev libboost-system-dev liblog4cplus-dev libssl-dev \
  libpq-dev default-libmysqlclient-dev
```

Upstream requires Meson >=1.3.0. Debian 12's packaged Meson is older. A virtual
environment inside this checkout avoids modifying system Python:

```bash
python3 -m venv .local/build-tools
.local/build-tools/bin/pip install 'meson>=1.3'
export PATH="$PWD/.local/build-tools/bin:$PATH"
meson --version
cmake --version
pkg-config --modversion log4cplus openssl libpq mysqlclient
```

Use a distribution package instead if it already supplies a sufficiently recent
Meson. CMake must be >=3.20. Upstream public documentation is available in the
[installation chapter](https://kea.readthedocs.io/en/kea-3.2.1/arm/install.html);
the pinned source build remains authoritative for optional dependency checks.

## Build an isolated upstream dependency

The commands below download public tagged source and install build outputs only
under this repository. They are manual setup instructions, not automatic CMake
steps. Review the dependency setup before running it locally. Tags
are named explicitly; no moving development branch or premium source is used.
The source archive URL uses GitHub because ISC's download directory blocked
automated fetching during the investigation.

```bash
export KEA_VERSION=3.2.1
export KEA_PREFIX="$PWD/.local/kea/$KEA_VERSION"
mkdir -p .upstream
curl --fail --location --retry 2 \
  "https://github.com/isc-projects/kea/archive/refs/tags/Kea-$KEA_VERSION.tar.gz" \
  --output ".upstream/kea-$KEA_VERSION.tar.gz"
tar -xzf ".upstream/kea-$KEA_VERSION.tar.gz" -C .upstream
meson setup "build-kea-$KEA_VERSION" ".upstream/kea-Kea-$KEA_VERSION" \
  --prefix="$KEA_PREFIX" --libdir=lib --buildtype=debugoptimized \
  -Dcpp_std=c++14 -Dcrypto=openssl \
  -Dmysql=disabled -Dpostgresql=enabled -Dkrb5=disabled -Dnetconf=disabled
meson compile -C "build-kea-$KEA_VERSION" -j 2
meson install -C "build-kea-$KEA_VERSION"
```

No `sudo` is used for the source install. Upstream defaults disable unit tests;
this dependency build does not claim to run Kea's own complete test suite. Bison
and Flex allow generated parsers to be built from the Git archive. Limit build
parallelism on memory-constrained WSL installations. For 3.0.4, repeat with
`KEA_VERSION=3.0.4` and a distinct prefix/build directory. Inspect the actual
archive root if upstream archive naming changes.

Use an existing development package installation instead if it supplies the
**exact** selected release's daemon, installed `config.h`, headers, shared core
libraries, SQL hooks, and `kea.pc`. `kea-dev` from an older distribution release
does not satisfy that requirement. Do not mix an installed daemon with unrelated
source headers. The tag's pkg-config version may include a `-git` suffix; the hook
header version and the actual build identity matter more than that suffix.

## Build and exercise the hook

An upstream Meson build can also be used without installing it. After building
the DHCPv4 target and its dependencies, use its generated uninstalled pkg-config
metadata and the daemon from the same build tree:

```bash
ninja -C "build-kea-$KEA_VERSION" -j 2 src/bin/dhcp4/kea-dhcp4 \
  src/hooks/dhcp/pgsql/libdhcp_pgsql.so src/lib/d2srv/libkea-d2srv.so
export PKG_CONFIG_PATH="$PWD/build-kea-$KEA_VERSION/meson-uninstalled"
cmake -S . -B build -DCMAKE_BUILD_TYPE=Debug \
  -DKEA_DB_COMMANDS_RUNTIME_TESTS=ON \
  -DKEA_DHCP4_EXECUTABLE="$PWD/build-kea-$KEA_VERSION/src/bin/dhcp4/kea-dhcp4"
cmake --build build --parallel 2
ctest --test-dir build --output-on-failure
```

This exercises the upstream build tree, not installed-package completeness.
Meson's runtime library paths must remain intact. Do not reuse this hook build
directory when switching to an installed prefix. For the installed-prefix path:

```bash
export PKG_CONFIG_PATH="$KEA_PREFIX/lib/pkgconfig${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"
export LD_LIBRARY_PATH="$KEA_PREFIX/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export PATH="$KEA_PREFIX/sbin:$KEA_PREFIX/bin:$PATH"
pkg-config --modversion kea
cmake -S . -B build -DCMAKE_BUILD_TYPE=Debug \
  -DKEA_DB_COMMANDS_RUNTIME_TESTS=ON
cmake --build build --parallel 2
ctest --test-dir build --output-on-failure
nm -D --defined-only build/libdhcp_db_commands.so
ldd build/libdhcp_db_commands.so
```

The configure probe must compile and link `ConfigBackendDHCPv4Mgr::instance` and
`getPool`. Check the dynamic symbol output for `version`, `load`, `unload`, and
`multi_threading_compatible`; check that Kea dependencies resolve to the intended
prefix and no private static Kea copy is included. The shared-library link uses
`-z defs` to reject unresolved symbols. Do not deploy the result merely because
these static checks pass: run the lifecycle test against the matching daemon.

For an existing Kea build requiring a different C++ standard, add
`-DCMAKE_CXX_STANDARD=20` (or the actual standard) and match its remaining ABI
settings. A nonstandard daemon location can be specified with
`-DKEA_DHCP4_EXECUTABLE=/absolute/path/kea-dhcp4`. CMake caches probe results: use a
fresh build directory after switching the Kea prefix or toolchain.

CTest registers the Python transport tests by default. Real daemon tests are
enabled explicitly with `KEA_DB_COMMANDS_RUNTIME_TESTS=ON`. To run without CMake:

```bash
python3 -B -m unittest discover -s tests -p test_transport.py -v
python3 -B tests/smoke.py --server "$KEA_PREFIX/sbin/kea-dhcp4" \
  --hook "$PWD/build/libdhcp_db_commands.so" --work-dir "$PWD/build/runtime"
```

The latter requires Linux, the actual built hook, and the daemon's runtime
dependencies. The harness creates temporary files only below `--work-dir`,
including fresh fixture credentials, and uses no production configuration. It
uses native HTTP on an OS-selected loopback port with file-based Basic
authentication. It keeps Kea's security checks enabled. Unix sockets on this
workstation's `/mnt/c` mount could not bind and its directory permissions failed
Kea's checks, so the lifecycle fixture uses HTTP rather than disabling checks.

## PostgreSQL read integration

See [PostgreSQL setup, command contract and tests](postgresql.md). The opt-in
`postgresql_read` CTest uses an isolated ephemeral cluster, the unchanged 3.2.1
schema and native PostgreSQL hook. Missing dependencies are explicitly skipped.
Transport and lifecycle tests remain independent of PostgreSQL. The hook performs
no database mutations, initializes no backend and accepts no connection parameters.

## Future SQL integration gates

For each candidate Kea release and each SQL engine, provision an isolated test
database and initialize its schema with that exact release's `kea-admin`.
Configure upstream `libdhcp_pgsql.so` or `libdhcp_mysql.so` in Kea and supply
`config-control` normally. Keep real credentials outside tracked files. This
hook does not read credentials or accept database connection parameters.

Future tests must cover selectors/tags, unsupported and ambiguous backends, schema
mismatch, validation failures before writes, transaction rollback, audit entries,
repeated fetches, concurrent writers, disconnects before/after commit, pull failure
after a confirmed commit, effective DHCPv4/v6 configuration, and reload safety.
Test MySQL and MariaDB separately before claiming both are compatible. Backend
read/write integration and runtime activation are separate acceptance gates.

## Initialization verification record

The initial workstation is Windows with Debian WSL available. A native Windows
run of the Python transport tests passed. Initial Debian inspection
found GCC 12.2 but no Kea installation. After manual prerequisite installation,
CMake, Ninja, pkg-config, Boost headers, log4cplus 2.0.8, OpenSSL 3.0.22,
libpq 15.19, and mysqlclient metadata 3.3.20 were available. The user installed
Meson 1.12.1 in the documented repository-local venv. Upstream Kea 3.2.1 then
configured successfully with C++14, OpenSSL, PostgreSQL, and MariaDB client
support. The unmodified upstream DHCPv4 target and its shared dependencies built
successfully; the entire upstream default target and SQL hook modules were not
built. This is not a run of Kea's upstream unit tests.

The diagnostic source compiled against those headers. Its linked shared library
passed the real-daemon lifecycle harness in both threading modes: `-T`, command
registration and execution, rejected arguments, hook removal/re-addition, and
clean shutdown. Normal security checks stayed enabled. The six transport
tests passed on both native Windows and Debian WSL. Dynamic symbol inspection
confirmed `ConfigBackendDHCPv4Mgr::instance()` and the DHCPv4/v6 pool
`createUpdateSubnet` wrappers in the built `libkea-dhcpsrv.so`.

CMake configuration, the manager API compile/link probe, and the module build
passed using Meson's uninstalled pkg-config metadata. CTest then passed both
registered cases (`control_transport` and `hook_lifecycle`) against the
CMake-built library. `nm` confirmed all four hook entry points; `ldd` resolved
the Kea libraries to the matching upstream build tree with no missing libraries.
Native Ruff checks and formatting checks, and the C++ clang-format check, passed.

No Kea installation or system configuration change was performed by the agent.
Installed packaging, SQL connectivity/mutations/activation, DHCPv6, 3.0.4, and the
full upstream test suite remain unverified. A successful pool accessor does not
establish that a database is configured or reachable.

The Linux CI matrix is provided for future execution. Its passing status must be
established by real workflow runs, not inferred from YAML or source review.

## Milestone 2 verification record

Development moved to the Linux filesystem in Debian 12 WSL2. Kea's public
`Kea-3.2.1` source tag was downloaded into ignored `.upstream/` and rebuilt from
scratch with GCC 12.2, C++14, OpenSSL, shared libraries and PostgreSQL enabled;
MySQL, Kerberos and NETCONF were disabled. Meson 1.12.1 was downloaded into
`.upstream/` and run directly with Python, without installing it. No upstream
source changes or system installation were needed. Build-tree `kea.pc` reports
`3.2.1-git`; headers, daemon and PostgreSQL hook all come from this same tag/build.

The hook's CMake compile/link probe, Debug shared-module build and C++14
`-Wall -Wextra -Wpedantic` syntax check passed. All four exported hook entry points
were present and `ldd` resolved every dependency to the matching build or system
libraries. Six Python transport tests passed; changed Python files passed syntax
checks. Ruff and clang-format are unavailable in this WSL environment, so their
checks were not run. The historical formatter results above apply only to the
initial diagnostic milestone.

The user installed PostgreSQL 15.19 and its development/client prerequisites.
An isolated cluster successfully initialized Kea 3.2.1's unchanged PostgreSQL
schema (version 34.0) and loaded the tracked three-subnet fixture. The distribution
cluster and other databases were left untouched.

The final `ctest --test-dir build-native --output-on-failure` run passed **3/3**
cases in 6.72 seconds: `control_transport` (six unit tests, 0.05 seconds),
`hook_lifecycle` (0.30 seconds), and `postgresql_read` (6.37 seconds). No case was
skipped. Both real-daemon harnesses exercised threading disabled and enabled.
The SQL test confirmed native command registration, empty results, subnet 42
(`192.0.2.0/24`, lifetime 600), universal/specific tag filtering, rejected arguments,
generic disconnected-backend errors and clean shutdown. Inserting the fixture
after startup while runtime `subnet4` remained empty demonstrated a fresh SQL
read. Complete data/sequence snapshots were unchanged across reads; Kea connected
as a SELECT-only role with transactions read-only by default. Both private
clusters stopped and all temporary test files were removed. Missing-dependency
execution was also checked separately and returned skip code 77.

This proves the read-only path through our independently compiled hook and Kea's
native PostgreSQL backend. It does not prove large configurations, reconnect
recovery, complex subnet options/pools, multiple backends, installed packaging,
3.0.4 SQL compatibility or the full upstream test suite. No configuration mutation
command, direct SQL in the hook, package installation, persistent service or
system configuration change was introduced.

## Milestone 3 verification record

The existing dirty worktree was inspected and preserved. Against the same
unmodified Kea 3.2.1 source and shared-library build, the command now selects the
sole configured backend's native type, rejects multiple configured databases,
and refuses shared-network subnets whose membership/inherited settings native
flat serialization would omit. Command arguments remain absent or empty only.
The diagnostic contract is unchanged. See [upstream evidence](backend-behavior.md).

The expanded PostgreSQL 15 test uses the unchanged official schema (34.0), a
SELECT-only role with read-only transactions, private clusters and admin-only
fixture writes. Both threading modes pass semantic checks for multiple subnets,
multiple pools, subnet and pool options, timers, classes, user context, server
associations, empty/unmatched results, duplicate-ID schema rejection,
multiple-backend rejection, shared-network rejection, unchanged database dumps,
disconnection and automatic recovery after private database restart. Repeated
outage reads remain errors while native retry callbacks run. Recovery needs no
config reload, custom reconnect code or new hook-owned connection. Processes
shut down cleanly and temporary files are removed.

Available checks passed:

- CMake configure, expanded native API compile/link probe and C++14 module build
  with `-Wall -Wextra -Wpedantic -Werror`.
- CTest: three passing cases (`control_transport`, `hook_lifecycle`,
  `postgresql_read`) and one explicit prerequisite skip (`mysql_read`).
- Direct Python unit discovery: all six tests passed. All test Python modules
  parsed successfully. Git whitespace check passed.

Ruff (binary and Python module) and clang-format are unavailable; their checks
were skipped. No dependencies were installed to obtain them. These results use
Linux and the uninstalled 3.2.1 build, not native Windows, installed packaging,
the complete upstream test suite, production load or Kea 3.0.4.

MySQL/MariaDB runtime execution is blocked: neither server, client nor installer
is available, and the matching Kea build disabled MySQL and lacks its native
hook. The new [opt-in isolated harness](mysql.md) reports skip code 77, never a
runtime pass. Native MySQL prepares mutation statements even for read commands;
restricted SELECT-only startup is a separate compatibility limitation. Functional
tests need privileges to prepare those native statements and use snapshots to
detect changes. Oracle MySQL bootstrap and automatic MySQL recovery remain
unverified. No package installation, persistent service, system database change,
configuration mutation command, direct SQL in the hook, commit or push occurred.

## Milestone 3.5 verification record

Verified 2026-10-15 in Debian 12 WSL2 using the same unmodified Kea 3.2.1
source and shared-library build. MariaDB server/client 10.11.19 and Connector/C
3.3.20 development files were already installed. No packages were installed and
no persistent service, system database or system configuration was changed.

Enabling Meson's `mysql` option and building the native MySQL hook plus required
daemon/PostgreSQL dependencies succeeded. `ldd` resolved all native hook
dependencies, including `libmariadb.so.3`; `nm` confirmed `load`, `unload`,
`version` and `multi_threading_compatible`. The hook framework version remains
30201. CMake's cached pkg-config metadata needed refreshing after enabling
MySQL, so staged hooks could find the new `libkea-mysql` library directory.
See [reproducible build and test commands](mysql.md).

The MariaDB harness now exercises the official schema 35.0 in fresh private
instances with networking disabled. The native Kea connection successfully uses
`host=localhost` and the fixture's `MYSQL_UNIX_PORT`. Both threading modes pass:
registration, empty and known-subnet reads, multiple subnets/pools, subnet and
pool options, timers, class references, additional class evaluation, user context,
universal/specific/missing/unassigned tags, invalid arguments, and ambiguous
backends with empty and overlapping configuration. All table contents remain
unchanged across reads and reloads. Runtime subnet configuration remains empty.

Fresh-account privilege probes establish that SELECT alone fails native statement
preparation, then INSERT, UPDATE and DELETE are successively required. The
four-grant schema-scoped account initializes and performs all functional reads;
adding EXECUTE is unnecessary. No DDL/global grants are used. PostgreSQL continues
to pass with SELECT-only credentials and read-only transactions. This limitation
belongs to native MySQL statement preparation, not a database-specific hook path.

Both fixtures now use `reconnect-wait-time: 1000`: this release's configuration
backend passes that value unchanged to a millisecond timer. The previous value
1 could exhaust retries before database restart; a real MariaDB run exposed
that timing failure with threading enabled. With the corrected one-second
interval, restart before exhaustion restores complex reads without reload.
MariaDB's separate two-try exhaustion test logs `MYSQL_CB_RECONNECT_FAILED4`,
keeps Kea alive under `serve-retry-continue`, and returns controlled errors.
Restart after exhaustion does not restore reads during the two-second observation;
`config-reload` does. No custom reconnect mechanism was added.

Final available checks passed:

- CMake configure/API compile-link probe and hook build with
  `-Wall -Wextra -Wpedantic -Werror`; no project compiler warnings.
- Full CTest: **4 passed, 0 failed, 0 skipped** in 117.14 seconds;
  PostgreSQL 15.83 seconds and MariaDB 100.96 seconds.
- Direct Python unit discovery: **6 passed, 0 failed, 0 skipped**.
  All five Python test modules parse successfully.
- Git whitespace checks. Temporary database processes stopped and fixture data,
  sockets, credentials and logs were removed.

Ruff (binary/module) and clang-format are unavailable; these two tool checks
were skipped. The upstream dependency rebuild emitted a GCC optimization warning
in upstream code; upstream is unmodified and its build succeeded. The full
upstream test suite was not run. Oracle MySQL, Kea 3.0.4, installed packaging,
startup with an unavailable database, alternative failure policies, production
scale and configuration mutations remain outside this evidence. Shared-network
subnets remain rejected; that rejection is runtime-tested by PostgreSQL.

Milestone 3.5 changes only the two integration fixtures and documentation; the
same native C++ hook serves both engines. No hook SQL, configuration mutation
command, upstream source patch, commit or push was introduced. The next milestone
should specify one DHCPv4 mutation's validation, transaction, audit and activation
contract before implementing and testing it against both verified engines.

## Milestone 4 verification record

Verified on 2026-10-15 in Debian 12 WSL2, using the existing unmodified Kea 3.2.1
shared-library build, PostgreSQL 15.19 and MariaDB 10.11.19. No packages were
installed, upstream source changed, persistent services enabled, system databases
accessed, commits created or changes pushed. Existing worktree changes were
preserved. Temporary databases use the official matching schemas.

`src/diagnostic.cc` adds `cb-subnet4-set` through the native Hooks API and reports
mutation support in the diagnostic. It validates one explicit canonical IPv4
prefix, ID, lifetime and server tag; requires one configured SQL backend; checks
ID and prefix through `ANY`; refuses richer objects and association changes;
then calls native `createUpdateSubnet4` exactly once. Existing listing behavior
is retained. No hook SQL, custom transaction, background job or activation is
introduced. See [the exact request/response contract](commands.md) and
[pinned upstream mutation evidence](backend-behavior.md#native-subnet-mutations).

`tests/mutation.py` shares real persistence and activation assertions between the
two existing SQL harnesses. Both threading modes verify:

- Create/update, persisted ID/prefix/lifetime, explicit named and universal tags.
- Invalid types/bounds/prefixes/selectors, unsupported fields, prefix identity
  conflicts, richer-object and retagging rejection, and ambiguous backends.
- Unchanged unrelated subnet rows and associations, including objects hidden
  by the active server tag, and unchanged existing pools/options after writes.
- Native audit entries and changed modification timestamps across seconds.
- Late association INSERT failures on both create and update: every official
  table, including audit, matches its before snapshot after rollback. Sequence
  and auto-increment allocation is not asserted to roll back.
- Controlled disconnected write errors alongside existing native recovery tests.
- New/updated SQL configuration visible through backend reads without changing
  active `config-get`; explicit native pull/reload applies it, and an actual
  Kea process restart loads the persisted subnet.

PostgreSQL's original read phase retains SELECT-only credentials and read-only
transactions. A separate writer role has table DML and sequence privileges for
the mutation phase. MariaDB's original four-grant account performs reads without
EXECUTE; a valid write fails without EXECUTE with unchanged tables, then succeeds
after that grant for native audit procedure invocation. The late-failure test
uses table-level association privilege revocation: schema-level privilege changes
alone did not revoke the existing connection's access during experimentation.
No permissions are weakened in a live system.

Reproduce the configured build/checks after enabling both SQL tests with the
paths in [PostgreSQL](postgresql.md) and [MariaDB](mysql.md):

```sh
PKG_CONFIG_PATH="$PWD/build-kea-3.2.1/meson-uninstalled" \
  cmake -S . -B build-native -U__pkg_config_checked_KEA \
  -DCMAKE_BUILD_TYPE=Debug -DCMAKE_CXX_FLAGS=-Werror
cmake --build build-native --clean-first --parallel 2
ctest --test-dir build-native --output-on-failure
python3 -B -m unittest discover -s tests -p 'test_*.py'
```

The project build uses `-Wall -Wextra -Wpedantic -Werror` and completes without
compiler warnings. Full CTest passes **4 tests, 0 failures, 0 skips**, including
both real SQL engines and lifecycle with threading on/off. Direct Python unit
discovery passes **6 tests, 0 failures, 0 skips**; all six Python modules parse.
Whitespace checks pass. Ruff (binary/module) and clang-format are unavailable;
their checks were not run. The full upstream Kea test suite was not run.
The disposable harnesses stop processes and remove private files on completion.

The demonstrated guarantee is one native write transaction. Upstream offers no
public transaction spanning preflight and mutation: independent external writers
must be coordinated, and cross-process concurrency is unsupported. Connection
loss at commit can leave an uncertain outcome and requires reconciliation rather
than automatic retry. Subnet timestamps have second precision and are not
revision tokens. Failed activation recovery is not tested. No DHCP packet proof
is claimed: minimal created subnets have no pools and tests listen on no DHCP
interface. Oracle MySQL, Kea 3.0.4 SQL writes, installed packaging and production
load remain unverified. A next milestone should add a narrow pool contract and
real DHCP allocation plus activation-failure tests, retaining these integrity
boundaries and an explicit policy for writer coordination.

## Milestone 5 pool and packet verification

The implementation extends `cb-subnet4-set` with basic IPv4 pools. The
[command contract](commands.md) defines omission, replacement and validation;
[pinned upstream evidence and current results](pools.md) distinguish source
review from executed tests. Historical milestone records above remain unchanged.
The final Milestone 5 run passed all six CTest cases with zero failures or skips
in 302.73 seconds. A clean CMake build passed with warnings treated as errors;
direct Python discovery passed six tests, all eight Python modules parsed, and
documentation links and whitespace checks passed. Ruff and clang-format are
unavailable and were not run. The full upstream Kea test suite was not run.
All five fixture work directories were empty after cleanup.

Enable the existing PostgreSQL and/or MySQL integration options and their
matching prerequisite paths, then add:

```sh
PKG_CONFIG_PATH="$PWD/build-kea-3.2.1/meson-uninstalled" \
  cmake -S . -B build-native -DCMAKE_CXX_FLAGS=-Werror \
  -DKEA_DB_COMMANDS_DHCP_TESTS=ON
cmake --build build-native --parallel 2
ctest --test-dir build-native --output-on-failure
python3 -B -m unittest discover -s tests -p 'test_*.py'
```

`postgresql_read` and `mysql_read` include the shared pool mutation suite.
The additional `postgresql_dhcp` and `mysql_dhcp` cases run each backend's
disposable fixture with packet checks, with threading disabled and enabled.
The packet option requires the corresponding SQL option and native backend
prerequisites. It does not enable DHCP on host interfaces.

Packet tests require Linux `unshare`, user/network namespace support and `ip`.
They also require the matching `kea-lfc` executable, selected with
`-DKEA_LFC_EXECUTABLE=/absolute/path/to/kea-lfc`. For an uninstalled upstream
build, build `src/bin/lfc/kea-lfc` and select that executable. The fixture sets
Kea's data directory to its private temporary directory without host installation.
The runner creates a disposable unprivileged user/network namespace and brings
up only its loopback interface. It must fail closed if isolation is missing.
Kea binds loopback UDP on testing ports 1067/1068; a loopback relay sends real
DHCP packets. No physical/shared interface, Docker, persistent host networking,
or production server is used. Where namespace creation requires host privileges,
obtain explicit approval before running; never bypass isolation or run the
fixture against a host interface. An unavailable prerequisite is a skipped
check, not a pass.

The tests inspect native SQL reconstruction, active `config-get`, OFFER/ACK
contents and Kea's persisted memfile lease separately. Empty-pool checks require
no offer. Pool replacement is followed by explicit reload, and actual daemon
restart is tested. An intentionally invalid runtime activation must leave the
SQL write intact. Recovery consists of correcting activation prerequisites and
explicitly activating again; the hook performs no automatic rollback. Temporary
servers, private database clusters, credentials, leases and namespace resources
are removed by the fixture cleanup paths.

## Milestone 7 lifecycle verification

On 2026-10-15, the fresh `build-m7` Release build against unmodified Kea 3.2.1
passed with compiler warnings treated as errors. The complete integration gate
passed **6 tests, 0 failures, 0 skips in 395.32 seconds**, using PostgreSQL 15.19
and MariaDB 10.11.19. Both engines ran get/delete, rollback, audit/timestamp,
association, shared-network rejection and isolated DHCP checks with threading
disabled and enabled. All temporary integration resource directories were empty
after cleanup. See [lifecycle coverage and reproduction](subnet-lifecycle.md).

Direct Python unit discovery passed **6 tests**; all **15** Python modules in
`tests` and `scripts` parsed. Clang-format dry-run, Ruff, changed-file whitespace
and local Markdown link checks passed. The installed Codex `PreToolUse` hook
blocked the combined runner's PATH assignment; automatic approval review then
rejected a wrapper retry. The task-relevant checks were executed separately on
explicit file types and paths. The [approval investigation](quality-approval.md)
records the reproduced environment-level false positive and remaining action.

SQL deletion, native backend absence, unchanged active runtime, explicit
pull/reload removal and absence after daemon restart were distinguished. Real
DORA still succeeded before activation; after activation no new OFFER was
received and existing memfile lease bytes were unchanged. The hook initiates
neither activation nor lease deletion. SQL lease stores, distributed activation,
concurrent independent writers, Oracle MySQL, Kea 3.0.4 runtime compatibility,
production load and the full upstream Kea suite remain unverified. Mutation
preflight requires externally coordinated writers, as documented for set/delete.

## Earlier MariaDB backend build

The following commands used the earlier uninstalled build tree. Current builds
use the installed-prefix procedure in [reproducible builds](reproducible-builds.md).

```sh
python3 .upstream/meson-1.12.1/meson.py configure build-kea-3.2.1 -Dmysql=enabled
ninja -C build-kea-3.2.1 -j 2 \
  src/hooks/dhcp/mysql/libdhcp_mysql.so \
  src/bin/dhcp4/kea-dhcp4 \
  src/hooks/dhcp/pgsql/libdhcp_pgsql.so \
  src/lib/d2srv/libkea-d2srv.so
```

This used Kea's supported Meson option without modifying upstream source or
installing Kea. Enabling MySQL changes generated headers, so Ninja may rebuild
required core dependencies. The daemon, both native hooks and this hook must
share the same source tag, compiler ABI and shared-library build.
