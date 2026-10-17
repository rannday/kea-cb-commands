# C++ standard feasibility — Milestone 17

Assessment date: 2026-10-16. **Recommendation: retain C++14.** C++17 is a viable
local modernization candidate, but no current feature requires migration.
C++20 also builds and loads locally, with a higher observed libstdc++ symbol
requirement and no demonstrated benefit for this hook. Production sources,
default CMake standard, pinned Kea and release packaging were not changed.

Changing the hook's language standard does **not** repair Kea's native SQL
transaction exception-safety defect; see the
[ISC issue draft](isc-sql-transaction-issue.md).

## Kea requirements and project boundary

Kea 3.2.1 does not universally require C++14 or the same language standard as
every hook. Its actual
[Meson compiler checks](https://github.com/isc-projects/kea/blob/Kea-3.2.1/meson.build#L389-L447)
require at least C++11, recommend C++14, probe whether Boost Math requires
C++14, and require C++20 for the selected NETCONF/Botan dependency paths.
These are conditional build requirements, not an ABI compatibility guarantee.
The reused installation's `meson-info/intro-buildoptions.json` records
`cpp_std: c++14`, `buildtype: release` and no extra C++ arguments. Kea was not
rebuilt or modified for these experiments.

The [hook CMake configuration](../CMakeLists.txt) defaults to C++14 only if the
caller has not supplied `CMAKE_CXX_STANDARD`. It requires the selected standard,
disables compiler extensions, builds one shared module and links to the
selected Kea installation through pkg-config. Its API/link probe checks native
backend pool APIs and the assessed Kea hook API versions. Static Kea libraries
are rejected to avoid duplicate core/singleton state. C++17/20 can therefore be
tested with an ordinary cache override without changing production files.

The supported runtime remains Linux DHCPv4 with unmodified Kea 3.2.1;
Kea 3.0.4 is only source-assessed. PostgreSQL 15 and MariaDB 10.11 are the
existing SQL targets. This milestone establishes no new operating-system,
database, compiler or Kea support commitment.

## Compatibility experiments

All builds used unchanged source, the same pinned installation at
`build-repro-clean/install`, Release, no GNU language extensions,
`-Wall -Wextra -Wpedantic -Werror`, hidden visibility and `-Wl,-z,defs`.
The installation was not relocated. All outputs are ignored under
`build/milestone17/`; no published v0.1.0 artifact was replaced.

Environment: Debian 12 WSL, x86-64; GCC 12.2.0
(`12.2.0-14+deb12u1`), Clang 22.1.8 (`1~deb12u1`), installed libstdc++,
and Kea 3.2.1. Clang used libstdc++, not libc++.

| Compiler | Standard | Configure/API-link probe | Release build | Warnings/errors | CTest |
| --- | --- | --- | --- | --- | --- |
| GCC 12.2 | C++14 baseline | Pass | Pass | None | 2/2 pass, zero skips |
| GCC 12.2 | C++17 | Pass | Pass | None | 2/2 pass, zero skips |
| GCC 12.2 | C++20 | Pass | Pass | None | 2/2 pass, zero skips |
| Clang 22.1.8 | C++17 | Pass | Pass | None | 2/2 pass, zero skips |
| Clang 22.1.8 | C++20 | Pass | Pass | None | 2/2 pass, zero skips |

Each CTest run consists of `control_transport` and `hook_lifecycle`.
[The lifecycle test](../tests/smoke.py) runs the actual pinned `kea-dhcp4`
with packet multithreading disabled and enabled. It validates configuration,
loads the module, registers all five commands, executes the diagnostic
successfully, checks CRUD validation/missing-backend error responses, unloads
and reloads the module, verifies deregistration/reregistration, and shuts down
cleanly. These are real command executions; no successful SQL mutation is
implied. The diagnostic explicitly does not test database connectivity.

### Reproducible commands and records

From the repository root, repeat for `standard=14`, `17`, `20` with GCC;
for Clang use `compiler=clang`, `/usr/bin/clang++` and standards 17/20:

```bash
prefix="$PWD/build-repro-clean/install"
standard=17
compiler=gcc
build_dir="$PWD/build/milestone17/$compiler-cpp$standard"
export PKG_CONFIG_PATH="$prefix/lib/pkgconfig"
export LD_LIBRARY_PATH="$prefix/lib"
cmake -S . -B "$build_dir" \
  -DCMAKE_CXX_COMPILER=/usr/bin/g++ \
  -DCMAKE_CXX_STANDARD="$standard" \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_EXPORT_COMPILE_COMMANDS=ON \
  -DKEA_DB_COMMANDS_WARNINGS_AS_ERRORS=ON \
  -DBUILD_TESTING=ON -DKEA_DB_COMMANDS_RUNTIME_TESTS=ON \
  -DKEA_DHCP4_EXECUTABLE="$prefix/sbin/kea-dhcp4"
cmake --build "$build_dir" --parallel 2
ctest --test-dir "$build_dir" --output-on-failure \
  --output-junit "$build_dir/results.xml"
python3 -B scripts/verify_artifact.py \
  --library "$build_dir/libdhcp_db_commands.so" \
  --kea-prefix "$prefix" --forbid-path "$PWD"
```

Each build directory retains `configure.log`, `build.log`, `ctest.log`,
`results.xml`, `compile_commands.json`, `release-build.json`, `artifact.log`
and `exports.txt`. `build/milestone17/artifact-summary.json` records direct
dependencies, symbol versions, sizes and actual compile flags. Test fixture
credentials/configurations were temporary and removed by the lifecycle test;
these should not be included as issue attachments.

### Deliberately unrun coverage

Candidate-standard PostgreSQL/MariaDB command integration is **unverified**.
The existing SQL harnesses include intentional database shutdown/recovery
tests even without multiprocess mode. Running them would perform a connection
interruption prohibited in this milestone; neither harness was executed or
reported as passing. Historical C++14 SQL acceptance does not validate the
candidate-standard artifacts. No new test mode or fixture was introduced.

No Docker, deliberate crash/concurrency, DHCP packet, sanitizer or cross-distro
suite was run. There were no production edits requiring those broader gates.
Before migration, use an approved non-interrupting SQL test path or separately
authorize the appropriate full acceptance run. Commands remain on the main
thread when packet multithreading is enabled; the lifecycle checks cover
both modes but not SQL concurrency or packet service.

## ABI, linking and deployment

Language dialect and binary ABI are different constraints. Building a C++17
or C++20 module against C++14-built Kea can work, as demonstrated locally.
That does not make arbitrary compiler, library or distribution combinations
compatible. Public Kea headers expose C++ classes, templates, exceptions,
standard-library strings/containers and Boost smart pointers across the
module boundary; the four C lifecycle exports do not make it a C-only ABI.
Header layouts, inline/template definitions, compiler ABI, exception runtime,
Boost configuration and library versions must remain compatible with the
loading Kea build. Mixed-dialect inline definitions can also raise ODR risks
not exhaustively proved away by a smoke test.

GCC's [libstdc++ dual ABI documentation](https://gcc.gnu.org/onlinedocs/libstdc++/manual/using_dual_abi.html)
states that `_GLIBCXX_USE_CXX11_ABI` selection is independent of `-std`.
Changing the dialect does not by itself switch the string/list ABI. These
builds use the installed default ABI and expose `std::__cxx11` references;
no alternate ABI macro or libc++ combination was tested. Some layout
incompatibilities do not produce distinct linker names, so linking alone is
insufficient proof.

All five artifact verifier runs passed: required lifecycle exports present,
shared Kea dependencies resolved inside the selected prefix, no missing
libraries, no RPATH/RUNPATH, and no embedded checkout path. ELF inspection
found these differences:

| Build | Bytes | Defined dynamic symbols | Highest required GLIBCXX version |
| --- | --- | --- | --- |
| GCC C++14 | 168264 | 77 | 3.4.21 |
| GCC C++17 | 168272 | 77 | 3.4.21 |
| GCC C++20 | 167864 | 78 | 3.4.29 |
| Clang C++17 | 123112 | 43 | 3.4.26 |
| Clang C++20 | 122800 | 44 | 3.4.29 |

GCC C++14 and C++17 have equal defined dynamic symbol-name sets and equal
direct `DT_NEEDED` lists. GCC C++20 retains those names and adds a Boost
`system::detail::to_std_category` symbol; its direct dependency list is equal.
Clang retains more direct dependencies from the pkg-config link list than
GCC, including SQL client and additional Kea libraries; all resolved locally.
Symbol counts include emitted C++/Boost symbols, not just the four required
C entry points, and are not a stable export contract.

C++20 introduces a `GLIBCXX_3.4.29` string-stream reference in both compilers
(`basic_stringbuf::str() const &` for GCC,
`basic_ostringstream::str() const &` for Clang). All five modules also require
`CXXABI_1.3.9` and `GLIBC_2.32`. These are **module** requirements; the complete
dependency graph can demand more. Matching SONAMEs alone do not establish
symbol-version availability on another host. Smaller size is not evidence
of faster execution or greater safety. No performance study was performed.

No cross-distribution binary compatibility is claimed. A migration must check
the oldest supported compiler/libstdc++/glibc combination, exact target Kea
headers/libraries, and real target loading/SQL operation. Debian 12's two
installed compilers support both dialects in this experiment; other compiler
versions and Ubuntu/container targets remain unverified. Build against the
exact Kea installation that will load the module.

The [reproducible release process](reproducible-builds.md) currently records
the compiler and dialect in `release-build.json` and pins upstream source.
A future migration requires an intentional baseline/CI/container/package
matrix decision, updated metadata expectations and release-artifact validation.
These local experiments do not establish reproducibility across toolchains
or authorize replacing published artifacts.

## Benefits and recommendation

| Standard | Potential value | Evidence and cost | Decision |
| --- | --- | --- | --- |
| C++14 | Meets current native-API implementation needs | Existing baseline; fresh Release/lifecycle checks pass | Retain |
| C++17 | `optional`, `string_view`, structured bindings and filesystem utilities where justified | Both compilers pass local build/load; GCC symbol floor unchanged here; SQL/release matrix unverified | Viable follow-up candidate |
| C++20 | Concepts, ranges, span and other tools for larger future changes | Both compilers pass local build/load; higher observed runtime symbol floor; no present need | Defer |

The hook is small and delegates database work to native Kea. No concrete
correctness or maintainability problem currently requires a newer language
feature. Introducing views would also require careful lifetime handling at
Kea API boundaries. A dialect change alone provides none of the hypothetical
benefits until source changes use it, and cannot change destructors already
compiled into Kea's shared libraries.

Retain C++14 now. Consider C++17 when a specific feature has a measurable
maintenance benefit, after successful PostgreSQL/MariaDB native operations,
both threading modes, full release/acceptance validation on supported target
images, artifact comparison and any appropriate sanitizer coverage. C++20
needs an additional justified feature and deployment-floor decision.

The existing quality gate passed formatting, Python lint, whitespace and local
document-link checks across 66 files (`build/milestone17/quality.log`).
`git diff --check` passed; the two new untracked documents were also checked
explicitly for trailing whitespace. These checks do not validate remote links
or replace the runtime coverage described above.

Assessment: **GO for the local feasibility result; PARTIAL compatibility
evidence for migration.** Production-standard migration is not approved or
performed. SQL transaction availability remains a separate unresolved risk.
