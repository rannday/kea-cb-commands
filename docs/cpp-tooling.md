# C++ development tools

Run tools inside Debian WSL, with the checkout on its Linux filesystem. Open
this directory in Zed through a WSL remote connection so clangd, headers and
compiler all run in Debian. Opening the directory as a Windows filesystem path
does not supply the Linux Kea build environment.

## Tools

Use clangd **22.1.8**, verified on Debian 12 WSL. Debian's default `clangd` may
still select **14.0.6**, which crashes in the full feature probe described below.
Check both executable selections:

```bash
command -v clangd
clangd --version
command -v clangd-22
clangd-22 --version
```

The other tools remain Debian clang-format, clang-tidy and Clang Static Analyzer
**14.0.6**, plus cppcheck **2.10**. They do not need an LLVM 22 upgrade. clangd 22
was installed separately before verification; this workflow changes no packages
or system alternatives. On a development machine missing the other tools:

```bash
sudo apt-get update
sudo apt-get install --no-install-recommends clang-format clang-tidy clang-tools cppcheck
```

The existing quality environment pins clang-format **18.1.8**. Keep using that
environment for the canonical formatting/quality gate; the existing
`.clang-format` also passed with Debian clang-format 14. No style changes are
required. These local analysis tools supplement existing CI and SQL/DHCP tests.
They are not runtime dependencies or a replacement for integration tests.

## Compilation database and Zed

First configure the matching Kea installation using the
[build guide](reproducible-builds.md). Reuse an existing configured Release build
without replacing its compiler, Kea prefix or test options:

```bash
cmake -S . -B build/integration -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
cmake --build build/integration --parallel 2
```

For this checkout, the existing cache uses the retained
`build-repro-clean/install` Kea 3.2.1 installation. New environments follow the
build guide and use `build/upstream/install`. Do not relocate either installed
prefix. Verify `KEA_PREFIX`, `KEA_VERSION`, compiler and include paths in the
chosen cache before reusing it. Reconfiguring an uninitialized directory still
requires the build guide's matching pkg-config environment.

CMake writes ignored `build/integration/compile_commands.json`, with all four
project translation units, `-std=c++14`, native Kea include paths, definitions
and actual Release warning flags. Regenerate it after build configuration or
source-list changes. Never commit this generated database or its absolute paths.

The project `.clangd` selects that directory relative to the repository root.
No root symlink, copied include paths or global editor configuration is needed.
Headers borrow commands from the matching source file. Because `/usr/bin/clangd`
still selects version 14 here, `.zed/settings.json` explicitly selects
`/usr/bin/clangd-22` inside the Debian remote environment. No global Zed settings
or system alternatives change. Verify Zed's language-server log shows version
22.1.8 and the expected database. If another build directory is used,
`--build-dir` changes the script's database, while `.clangd` still selects
`build/integration` for the editor.

See the official [Zed C++ settings](https://zed.dev/docs/languages/cpp) and
[clangd configuration](https://clangd.llvm.org/config.html#compilationdatabase).
Local clangd 22 verification covers all four sources and three project headers,
including full per-token feature probes and automatic database discovery.
Normal LSP initialize, open, diagnostics, close and shutdown also passed with
clangd 22: all seven files returned empty diagnostics. Full probes passed for
three sources and all headers; `subnet4.cc` has the limitation described below.
Interactive Zed UI behavior was not tested. After opening the WSL project,
restart its language server and confirm the executable/version and database in
Zed's log, then check diagnostics and navigation in `src/arguments.cc`.

## Repeatable checks

Run from the repository root. Each command fails on a tool error or an enabled
project diagnostic. Tools do not apply fixes or change production compiler
settings. The script checks that the database contains exactly the project
sources before running analysis.

```bash
PATH="$PWD/build/quality/bin:$PATH" python3 -B scripts/analyze.py format
python3 -B scripts/analyze.py tidy
python3 -B scripts/analyze.py analyzer
python3 -B scripts/analyze.py cppcheck
PATH="$PWD/build/quality/bin:$PATH" python3 -B scripts/analyze.py all
```

Use `--build-dir build/another-configured-build` when needed. `all` runs formatting,
clang-tidy, the Clang Static Analyzer and cppcheck serially. It stops at the first
failure. Run the existing quality gate separately:

```bash
PATH="$PWD/build/quality/bin:$PATH" python3 -B scripts/quality.py
git diff --check
```

### clang-tidy

`.clang-tidy` enables `bugprone-*`, `clang-analyzer-*`, `performance-*` and
`portability-*`, with all other groups disabled. The Debian 14 checks completed
under C++14 without exclusions or source changes. Newer tool versions can add
checks; review their diagnostics before changing the policy. All enabled project
warnings fail the command. The header filter covers `src/*.h` and `src/*.cc`;
CMake marks Kea/SQL includes as system headers. Third-party headers are not
edited or included in the diagnostic gate.

Verification produced zero project diagnostics. clang-tidy reported 138615
suppressed non-user warnings across the four translation units; that count is
not a finding against this hook, and those upstream warnings were not reviewed.
clangd 22 adds `bugprone-empty-catch`, which flags the intentional catch around
failure logging in `src/diagnostic.cc`. `.clangd` excludes that check for this
file only: a logging exception must not escape the Kea lifecycle boundary.
This is an accepted warning, not a hook defect. Standalone clang-tidy 14 and its
configuration remain unchanged.
Review future findings individually: distinguish a source defect from an
incorrect compilation command or a documented native API constraint. Do not
apply automated fixes or suppress genuine defects to obtain a passing result.

### Clang Static Analyzer

The script runs Debian `clang++ --analyze` on each translation unit using its
actual compilation command. It retains definitions, include paths, C++14,
Release `NDEBUG` and compiler flags, replacing only compile/output switches.
This avoids another Kea build or a compiler change in the production build.
Analyzer diagnostics fail the command. Reports are written under the selected
build's `analysis/*.plist`; inspect their diagnostics and paths when a run fails.
Verification found zero diagnostics in all four reports.

This uses Clang's default path-sensitive checkers. It analyzes project code in
its Release configuration, without cross-translation-unit analysis or a claim
to prove all native backend behavior. clang-tidy's analyzer checks overlap;
the standalone invocation separately verifies compiler analyzer execution.

### cppcheck

cppcheck imports the same database with `--std=c++14` and enables only warning,
performance and portability checks. It checks all four project sources, with
no style, inconclusive checks or diagnostic suppressions. Verification found
zero diagnostics. CMake's system-header classification is retained; cppcheck is
a supplementary source analysis, not proof that every external API is modeled.

## clangd feature probes

The optional full clangd feature probe is separate from `all`:

```bash
python3 -B scripts/analyze.py clangd
clangd-22 --compile-commands-dir=build/integration --check=src/arguments.cc
# Also verify automatic discovery through .clangd:
clangd-22 --check=src/arguments.cc
```

Debian clangd 14.0.6 reproducibly segfaulted during `--check=src/arguments.cc`
after parsing and indexing, at its per-token feature tests. clangd **22.1.8**
resolves that reproducible crash: the original command completes with zero
errors. However, the full `src/subnet4.cc` probe reports an `ExtractFunction`
feature-test failure: `Cannot extract break/continue without corresponding
loop/switch statement.` This is a language-server refactoring probe failure,
not a compiler diagnostic or crash. The full script keeps returning failure
to expose it; no checks or production flags are removed to hide it.

The script explicitly invokes `clangd-22`; it preserves C++14 and the existing
Kea flags. No hook source or production compiler settings changed. These
command-line probes do not verify every interactive completion, hover or
refactoring request inside Zed.
