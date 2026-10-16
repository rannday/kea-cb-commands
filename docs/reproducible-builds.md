# Reproducible builds and acceptance gates

The supported execution target is **unmodified Kea 3.2.1 on Linux**, with native
PostgreSQL and MariaDB backends. Kea 3.0.4 remains source-assessed only. No binary
compatibility with another Kea version is claimed. Build a separate hook against
the exact installation that will load it.

## Repository audit

| Previous assumption | Acceptance workflow |
| --- | --- |
| Developer-specific Kea source/library/schema paths | One explicit installed prefix supplies headers, libraries, hooks and SQL schemas |
| Previously built upstream artifacts | Fresh source download and empty work directory; no restored build cache |
| Opt-in SQL/packet tests can return skip code 77 | Strict JUnit gate requires exactly six passing tests |
| Build-only/lifecycle CI matrix | Separate quality and full PostgreSQL/MariaDB/packet jobs for 3.2.1 |
| Unpinned formatter and unavailable lint tools | Hash-pinned private Python tool environment |
| CMake development RPATH and source paths | Explicit matching loader environment, mapped source paths and ELF inspection |

Remaining nondeterminism includes runner/package updates, scheduler and database
startup timing, temporary directory names, ephemeral control ports, DHCP
transaction IDs and audit timestamps. Tests compare relevant state and protocol
invariants rather than fixed timestamps or random identifiers. A control-port
probe/bind collision fails the test. Serial execution reduces contention but
does not eliminate host-load sensitivity. Test timeouts remain bounded.

## Source and dependency contract

[`scripts/kea-source.json`](../scripts/kea-source.json) locks the official
`isc-projects/kea` release tag `Kea-3.2.1` to commit
`1737462bc79276e3269304ea8cd3d1c03400e30d` and its HTTPS codeload archive SHA-256:

```text
2aebb52859cc402ae20004f54574714045fc6366825df1b09b7845130f9f798b
```

This is a recorded archive digest, not a claim of publisher-signature verification.
The script downloads anew, checks the digest before extraction, rejects unsafe
archive paths/links, and refuses a nonempty work directory. A changed archive
fails closed. Nothing is vendored or patched. GitHub release source can identify
itself as `3.2.1-git`; the pinned commit is the release commit.

Required build tools: a C++14 compiler, CMake/CTest 3.21+, Ninja, pkg-config, Python
3.10+, Meson, Bison and Flex. Required development libraries: Boost and Boost
System, log4cplus, OpenSSL, libpq and a MySQL-compatible connector (MariaDB here).
The integration gate additionally needs PostgreSQL server/client tools, MariaDB
server/client/bootstrap tools, `ip`, `unshare` and binutils. It runs as a normal
user, because PostgreSQL refuses initialization as root.

On an Ubuntu 24.04 development machine, install these prerequisites deliberately:

```bash
sudo apt-get update
sudo apt-get install --no-install-recommends -y \
  build-essential cmake ninja-build pkg-config python3-venv bison flex \
  ca-certificates libboost-dev libboost-system-dev liblog4cplus-dev \
  libssl-dev libpq-dev libmariadb-dev libmariadb-dev-compat \
  postgresql postgresql-client mariadb-server mariadb-client \
  iproute2 util-linux binutils
```

Debian 12 uses the same package names. Local verification uses Debian 12; CI is
configured for Ubuntu 24.04. No local system packages are installed by the build
scripts. The scripts detect missing dependencies and fail with diagnostics.

For output layout and safe reuse of an existing Kea installation, see
[local development](development.md#generated-output-layout).

## Clean build

Run from the checkout on a Linux filesystem, including Debian WSL2:

```bash
python3 -m venv build/quality
build/quality/bin/pip install --require-hashes --only-binary=:all: \
  -r scripts/requirements-quality.txt
export PATH="$PWD/build/quality/bin:$PATH"
python3 scripts/build_kea.py --work-dir build/upstream --jobs 2 \
  > build/upstream.log 2>&1
```

The pinned wheels target Linux x86-64. Other architectures need separately
reviewed wheel hashes. Meson 1.7.2, clang-format 18.1.8 and Ruff 0.11.13 are
pinned with hashes. No compiler/build cache is used. Choose another fresh work
directory for a second build; failure evidence is retained rather than erased.

Kea is installed privately under `build/upstream/install`, with shared libraries
under `lib`. Both SQL backends and OpenSSL are enabled. Upstream unit tests,
fuzzing, Kerberos and NETCONF are disabled. Kea's build does not provide a simple
DHCPv4-only component selection; the default server/tool targets are built. This
does not add DHCPv6 support to this hook. Source is never modified.

`toolchain.txt`, `config.report` and the Meson log record compiler, linker,
architecture, libc, SQL connector, OpenSSL, Boost and log4cplus versions and
feature choices. Preserve these with test results. This is a repeatable,
verified-source procedure, **not a promise of byte-identical artifacts across
different OS packages or build paths**. Ubuntu runner images and apt packages
receive updates; their resolved versions must be reviewed when diagnosing drift.

## Local quality and full integration

```bash
PATH="$PWD/build/quality/bin:$PATH" python3 -B scripts/quality.py
python3 -B -m unittest discover -s tests -p 'test_*.py' -v
python3 -B -m unittest discover -s scripts -p 'test_*.py' -v
python3 scripts/integration.py --kea-prefix build/upstream/install \
  --build-dir build/integration --jobs 2
```

The strict runner selects only that prefix's Kea metadata and shared libraries,
clears stale Kea CMake discovery, builds Release with `-Wall -Wextra -Wpedantic
-Werror`, and enables all test families. It removes Python optimization from the
test environment so assertions execute. It runs CTest serially to limit database
startup contention and requires exactly six passing tests in the JUnit report.
Missing, failed, duplicate or skipped tests fail the gate. Optional CMake tests
still support skip code 77 for smoke-only development; a green partial CTest run
does not establish full integration success.

The six tests cover transport, real hook lifecycle, PostgreSQL mutations/reads,
PostgreSQL DHCP, MariaDB mutations/reads and MariaDB DHCP. Both threading modes,
pool replacement/omission/removal, rejected-mutation snapshots, late transaction
failures, audit/timestamps, activation failures, reload/restart and twelve real
DORA exchanges are exercised. The two packet tests verify recorded leases.
See [pool evidence](pools.md) and [mutation semantics](commands.md).

Databases are private temporary clusters using Unix sockets with TCP disabled.
Schema initialization uses the installed, unchanged upstream SQL files. The
packet harness enters private user/network namespaces, enables namespace
loopback, and exchanges real relayed DHCP UDP packets there. It does not bind a
physical or shared interface. Normal success and Python exceptions stop children
and remove temporary resources. The strict runner checks all five resource
directories are empty. Forced process termination, machine loss or CTest timeout
can interrupt `finally` cleanup; inspect failed-run process/log evidence before
removing leftovers. Do not reuse production database credentials or directories.

Namespace support is required, not silently skipped. If local policy denies
unprivileged namespaces, obtain approval before any privileged networking or
host-policy change. No local privilege bypass is automated.

## CI architecture and privilege boundary

[`ci.yml`](../.github/workflows/ci.yml) defines three Ubuntu 24.04 jobs:

1. Fast formatting, Ruff, JSON/relative documentation links/whitespace checks and
   Python unit tests.
2. A fresh verified Kea build, hook build, strict six-test gate, versioned archive,
   checksum verification, extracted install and artifact/lifecycle inspection.
   No upstream build cache is restored.
3. Publication of the verified archive/checksum after both jobs succeed, only
   for an explicit matching version-tag push. Branches, PRs and manual dispatch
   do not publish. See the [release procedure](releases.md).

Actions are pinned to commit SHAs, checkout credentials are not persisted, and
workflow permissions default to read-only. Only the tag publication job has
`contents: write` and `actions: read`. Diagnostic reports and separately uploaded
verified archives are retained for seven days. Database directories and generated
credential files are excluded from upload paths. Test credentials are disposable;
never supply production credentials to these jobs. CI never deploys to a server.

Ubuntu 24.04 restricts unprivileged user namespaces through AppArmor. On the
ephemeral CI VM only, a copied `unshare` executable receives an executable-specific
AppArmor profile allowing user namespaces. Profile loading/removal uses runner
sudo; the tests themselves run as the normal runner user inside namespaces.
This avoids globally disabling the restriction. The profile is removed by an
`always()` step; VM destruction is the final cleanup boundary if the job is
cancelled abruptly. The copied executable can create user namespaces for that
runner account, so this exception belongs only on an isolated disposable runner.
See Ubuntu's [namespace restriction documentation](https://documentation.ubuntu.com/security/security-features/privilege-restriction/apparmor/).

The workflow is configured; **a successful GitHub Actions execution has not been
observed in this milestone**. In particular, the Ubuntu-specific AppArmor step
has not been exercised by the local Debian run.

## Shared-library verification and compatibility

```bash
cmake --install build/integration --prefix "$PWD/build/stage"
python3 scripts/verify_artifact.py \
  --library build/stage/lib/kea/hooks/libdhcp_db_commands.so \
  --kea-prefix build/upstream/install --forbid-path "$PWD"
LD_LIBRARY_PATH="$PWD/build/upstream/install/lib" python3 -B tests/smoke.py \
  --server "$PWD/build/upstream/install/sbin/kea-dhcp4" \
  --hook "$PWD/build/stage/lib/kea/hooks/libdhcp_db_commands.so" \
  --work-dir "$PWD/build/staged-lifecycle"
```

The verifier checks the filename, `load`, `unload`, `version` and
`multi_threading_compatible` exports, dependency resolution to the selected Kea
prefix, missing libraries, absence of RPATH/RUNPATH, and specified development
path/private-key markers. The hook has no proprietary dependency. Its native
backend hooks are supplied by upstream Kea. Source paths are mapped to relative
paths during compilation; no development RPATH is installed. Runtime loading
still requires the matching Kea library search path. A source/dependency audit
complements marker checks; arbitrary credential absence cannot be established
by searching a few strings alone.

Kea and this hook must agree on the C++ ABI, including the standard library and
libstdc++ dual-ABI setting, compiler ABI flags and compatible Boost/runtime
dependencies. Build both with a compatible toolchain; do not mix static Kea
copies or Windows/MSYS2 libraries into a Linux server. The artifact is not a
portable binary distribution across arbitrary runtimes. SQL connector, OpenSSL,
libc and libstdc++ symbol
requirements come from the actual build environment. The verifier prints symbol
version requirements for inspection. Only unmodified Kea 3.2.1 is runtime-tested.
The staged-artifact smoke test also verifies load, reload, unload and shutdown in
both threading modes; CI runs it after artifact inspection.

## Milestone 6 local execution record

Local verification on Debian 12 x86-64 used GCC 12.2.0, CMake 3.25.1,
Python 3.11.2, Meson 1.7.2, Ninja, binutils 2.40, glibc 2.36, Boost 1.74,
log4cplus 2.0.8, OpenSSL 3.0.22, PostgreSQL 15.19 and MariaDB 10.11.19
with Connector/C 3.3.20. Exact compiler/package details are retained in
`build-repro-clean/toolchain.txt` and `config.report`.

The locked archive passed SHA-256 verification and unmodified Kea built and
installed under a fresh private prefix. A terminal interruption required resuming
that same fresh upstream build; no earlier Kea installation or compiler cache
supplied artifacts. A later interruption stopped the first SQL test run. Its
stopped fixture resources were removed after checking recorded process IDs;
the final acceptance run uses a separate build directory.

The hook compiled in Release mode with warnings as errors against the new prefix.
All 23 Python unit tests and formatting, Ruff, JSON, documentation-link and
whitespace checks passed. Workflow YAML parsed and all nine shell steps passed
`bash -n`; these checks do not execute GitHub Actions.

The installed `lib/kea/hooks/libdhcp_db_commands.so` passed export/dependency
inspection, resolved all Kea shared libraries to the new prefix, contained no
RPATH/RUNPATH or `/home/rann` marker, and passed the staged lifecycle test in
both threading modes. The build and dependency audit found no proprietary ISC
component. These checks do not establish compatibility with another Kea release.

The final strict acceptance run passed all six CTest tests with no skips in
305.96 seconds:

| Test | Result | Seconds |
| --- | --- | ---: |
| `control_transport` | Passed | 0.06 |
| `hook_lifecycle` | Passed | 0.34 |
| `postgresql_read` | Passed | 44.54 |
| `postgresql_dhcp` | Passed | 55.19 |
| `mysql_read` | Passed | 100.29 |
| `mysql_dhcp` | Passed | 105.54 |

Both SQL engines exercised pools, replacement/omission/empty-list semantics,
validation and transaction failures, audit state, activation failures and
reload/restart behavior with multithreading enabled and disabled. The packet
tests completed twelve real DORA exchanges across both engines and verified
recorded leases. The strict runner confirmed all five temporary resource
directories were empty; a surrounding process check found no additional Kea,
database or namespace processes after completion. The staged lifecycle directory
was also empty. Interrupted-run database resources were cleaned separately.
The JUnit evidence is `build-m6-final/ctest-results.xml`.

CI remains configured and unexecuted; these are local Milestone 6 results,
not historical Milestone 5 results or a GitHub Actions success claim.

The current [Milestone 9 readiness record](release-readiness.md) adds focused
concurrent-request coverage and installation/operations guidance. Performance
and scale certification and binary portability across runtimes remain unverified;
the existing exclusive-writer policy still applies. Versioned packaging and its
local verification are described in the [release procedure](releases.md).
