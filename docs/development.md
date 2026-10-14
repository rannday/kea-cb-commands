# Development and verification

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
  -Dmysql=enabled -Dpostgresql=enabled -Dkrb5=disabled -Dnetconf=disabled
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
ninja -C "build-kea-$KEA_VERSION" -j 2 src/bin/dhcp4/kea-dhcp4
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

## SQL integration gates (not implemented yet)

For each candidate Kea release and each SQL engine, provision an isolated test
database and initialize its schema with that exact release's `kea-admin`.
Configure upstream `libdhcp_pgsql.so` or `libdhcp_mysql.so` in Kea and supply
`config-control` normally. Keep real credentials outside tracked files. This
prototype does not read credentials or accept database connection parameters.

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
