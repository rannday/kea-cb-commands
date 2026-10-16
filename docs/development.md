# Development and verification

Use [reproducible builds](reproducible-builds.md) for prerequisites, the pinned
Kea source/tool environment, full acceptance commands, CI and artifact checks.
Use [C++ tooling](cpp-tooling.md) for Zed/clangd and local static analysis.
The [architecture](architecture.md#implementation-layout) describes module
ownership; [command contracts](commands.md) define behavior before implementation.
Earlier setup instructions and execution records are preserved in
[development history](development-history.md), including the
[quality approval investigation](quality-approval.md).

## Local environment

Use native Linux or Debian WSL2. Keep large builds on the Linux filesystem;
`/mnt/c` can be slower and has longer paths. In VS Code, open the checkout through
the WSL extension so the terminal, compiler and language server run in Debian.
Windows/MSYS2 libraries cannot produce a Linux Kea-compatible hook.

Use the target Kea installation's compiler ABI, standard library, Boost and build
flags. Recreate virtual environments and CMake/Meson trees after relocating a
checkout: caches, scripts and installed pkg-config metadata embed absolute paths.
No Docker setup is required or supplied.

## Generated output layout

All new repository-local generated output belongs under ignored `build/`:

| Path | Purpose |
| --- | --- |
| `build/quality/` | Hash-pinned Meson, clang-format and Ruff virtual environment |
| `build/upstream/` | Verified Kea archive, source, Meson build and installed prefix |
| `build/upstream.log` | Upstream build transcript |
| `build/hook/` | Normal hook CMake build |
| `build/integration/` | Full CMake/CTest build, fixture work directories and JUnit report |
| `build/stage/` | Staged hook installation |
| `build/staged-lifecycle/` | Staged-artifact lifecycle fixture |
| `build/release/` | Versioned release archives and SHA-256 checksums |
| `build/package-stage/` | Extracted release installation |
| `build/packaged-lifecycle/` | Packaged-artifact lifecycle fixture |
| `build/cache/ruff/` | Ruff cache |
| `build/legacy/` | Archived root build trees, virtual environment, wheels and logs |

Use a fresh subdirectory under `build/` for another variant. The upstream builder
requires an empty work directory. Temporary database sockets and private packet
namespaces retain their harness-managed locations; they are not reusable builds.

Old root build trees and logs are archived under `build/legacy/`. Treat those
cached builds and the old virtual environment as historical artifacts: embedded
absolute paths make them unsuitable for reuse after relocation. The verified
replacement builds and quality environment are outside `legacy/`.
`.upstream/` downloads and `.local/` assets remain ignored. `.serena/` is
persistent project metadata, not a disposable build directory. Source
directories, scripts and SQL fixtures stay in place.

Do not move old CMake caches or an installed Kea prefix. For this checkout's
existing installation, reuse the explicit prefix while generating a fresh hook
build in the new layout:

```bash
python3 -B scripts/integration.py --kea-prefix build-repro-clean/install \
  --build-dir build/integration --jobs 2
```

This avoids rebuilding the full Kea toolchain. New clean environments use
`build/upstream/install` as shown in the build guide. Legacy artifacts can be
removed separately after their replacements pass, provided no active cache,
installed metadata or developer tool still references them. The reused
`build-repro-clean/` is the sole remaining root build directory. Its installation
has absolute ELF runtime search paths and pkg-config metadata referring to the
current location. Keep it until a new upstream build is verified; archiving it
would break the active environment. Historical paths in the development history
refer to their original locations, before archival.

## Select validation

Run the combined source/documentation gate from the repository root:

```bash
PATH="$PWD/build/quality/bin:$PATH" python3 -B scripts/quality.py
python3 -B -m unittest discover -s tests -p 'test_*.py' -v
python3 -B -m unittest discover -s scripts -p 'test_*.py' -v
```

The quality runner includes repository guidance, skill Markdown and Serena YAML.
Its link checks verify local targets, not remote URLs or Markdown anchors.
Python unit suites validate transport and build-runner logic without databases.

For a configured build, use `cmake --build build/integration --parallel 2` and
`ctest --test-dir build/integration --parallel 1 --output-on-failure`. For a fresh
full build and real SQL/DHCP coverage, use the strict integration runner in the
build guide; it enables every test family and rejects skips. Optional CTest
families are controlled by `KEA_DB_COMMANDS_RUNTIME_TESTS`,
`KEA_DB_COMMANDS_POSTGRESQL_TESTS`, `KEA_DB_COMMANDS_MYSQL_TESTS` and
`KEA_DB_COMMANDS_DHCP_TESTS`.

`tests/smoke.py` exercises actual Kea loading without a database.
`tests/postgresql.py` and `tests/mysql.py` start private SQL servers and share
assertions from `tests/mutation.py` and `tests/lifecycle.py`. `tests/dhcp.py` and
`tests/packet_namespace.py` add real DORA packets and lease checks. SQL and packet
coverage must pass with threading disabled and enabled. See
[PostgreSQL](postgresql.md), [MariaDB](mysql.md) and [pools](pools.md) for details.

The installed-artifact export, dependency and staged loading commands are in the
[build guide](reproducible-builds.md#shared-library-verification-and-compatibility).
Source checks, lifecycle loading, SQL integration and packet integration provide
different evidence; a partial CTest pass does not establish the full gate.
See the [release procedure](releases.md) for packaging and verifying a candidate.
