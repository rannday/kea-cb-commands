# C++ development tools

Run tools inside Debian WSL, with the checkout on its Linux filesystem. Open
this directory in Zed through a WSL remote connection so clangd, headers and
compiler all run in Debian. Opening the directory as a Windows filesystem path
does not supply the Linux Kea build environment.

## Tools

Use the unversioned system executables `/usr/bin/clang`, `/usr/bin/clang++`
and `/usr/bin/clangd`. They currently select **22.1.8** in this checkout's
Debian environment. Other developers should verify their selected versions;
clangd **14.0.6** crashed in the full feature probe described below.

```bash
/usr/bin/clang --version
/usr/bin/clang++ --version
/usr/bin/clangd --version
```

Earlier static-analysis verification used Debian clang-format, clang-tidy and
Clang Static Analyzer **14.0.6**, plus cppcheck **2.10**. Those results describe
the tested versions; rerun the relevant checks after changing tools. This
project does not install packages or change system alternatives. On a
development machine missing the other tools:

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
Headers borrow commands from the matching source file. `.zed/settings.json`
selects `/usr/bin/clangd` inside the Debian remote environment, following the
system's default version. No global Zed settings or system alternatives are
changed by the project. Verify Zed's language-server log shows the intended
version (verified here with 22.1.8) and the expected database. If another build
directory is used,
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

## Project-local clangd MCP for development agents

The installed `isaacphi/mcp-language-server` bridges MCP tools to clangd over
stdio. The [upstream C/C++ setup](https://github.com/isaacphi/mcp-language-server#setup)
uses `--workspace`, `--lsp`, then `--` before clangd arguments. The installed
binary's `--help` confirms those arguments. Developers need:

- `mcp-language-server` on the `PATH` inherited by Codex. The verified Go module
  version is `v0.1.1`; its MCP handshake reports server version `v0.0.2`.
  For a default Go installation, add `$(go env GOPATH)/bin` to your shell's
  `PATH` before starting Codex.
- `/usr/bin/clangd`, following the system default. Debian clangd `22.1.8`
  is the verified version; other versions need the semantic checks below
  before claiming equivalent results.
- Git and a POSIX shell, available in the supported Linux/WSL environment.
- A compilation database configured for their own Kea installation at
  `build/integration/compile_commands.json`.

The launcher derives the workspace with `git rev-parse --show-toplevel`, so it
works from the repository root or a subdirectory, including checkout paths with
spaces. It passes `--background-index` and the absolute integration database
path to clangd. No developer home or checkout path is stored in the config.
Existing compilation databases contain machine-specific paths; another developer
must configure their own build using the build guide. Preserve an already
configured build's selected Kea installation and `.clangd` policy. Do not
substitute `build/compile_commands.json` or regenerate an already correct build
merely to connect an agent.

### Client configuration and registration

[Codex MCP configuration](https://developers.openai.com/codex/mcp/) uses
`.codex/config.toml` for a trusted project. A project-root `.mcp.json` is not
Codex-native configuration; this repository keeps only the Codex configuration.
Do not register another copy globally or launch a second MCP bridge for routine
navigation in the same client.

The project-local Codex configuration is:

```toml
# Project-local clangd MCP; see docs/cpp-tooling.md.
[mcp_servers.clangd]
command = "sh"
args = ["-c", '''
workspace=$(git rev-parse --show-toplevel) || exit
exec mcp-language-server --workspace "$workspace" --lsp /usr/bin/clangd -- \
    --background-index --compile-commands-dir="$workspace/build/integration"
''']
```

MCP, Zed and the clangd probe script all use `/usr/bin/clangd`. Its version
is selected by the developer's system configuration; the project has no
version-specific executable preference or environment override. `clang` is the
compiler, while `clangd` is the language server. Changing system defaults does
not replace the compiler recorded in an existing CMake build. Restart Codex and
Zed's language server after changing the selected language-server executable.

No credentials or global MCP changes are required. Project configuration is
loaded only when Codex trusts this checkout. Start Codex from this repository
in Debian WSL; an existing session may need to be restarted to load new servers.
From the repository root, check parsed configuration without starting another
server:

```bash
codex --version
codex mcp get clangd --json
```

In the interactive Codex session, run `/mcp`. Confirm exactly one enabled,
connected `clangd` entry with the shell launcher above and its tools available.
Check that its tools include `definition`, `references`, `hover` and
`diagnostics`. Then request the semantic checks below through those tools.
A configured entry or successful initialize response alone does not establish
working C++ analysis. If `clangd` is absent, check project trust and restart the
client; do not work around registration by editing global configuration.

### Agent workflow and semantic checks

Use this project's clangd MCP first for C++ definitions, references, hover and
diagnostics. Use file/text tools for ordinary reads and searches. If the MCP
tools are unavailable, report that limitation and use the existing Serena C++
server or bounded source inspection; do not claim those results came from this
MCP server. Rename and edit tools also exist, but require the same task scope
as any other source edit. Do not invoke them during a read-only tooling check.

Tool arguments use absolute `filePath` values; hover `line` and `column` are
**1-based**. Representative calls from the verified source revision:

| Tool | Arguments or target | Expected evidence |
| --- | --- | --- |
| `definition` | `{"symbolName": "parseSubnet4"}` | Definition in `src/arguments.cc`, declared in `src/arguments.h` |
| `references` | `{"symbolName": "parseSubnet4"}` | Call in `src/subnet4.cc` at line 163 |
| `definition` | `{"symbolName": "listSubnets"}` | Definition in `src/subnet4.cc` |
| `references` | `{"symbolName": "listSubnets"}` | Call in `src/commands.cc` at line 75 |
| `hover` | `src/arguments.cc`, line 61, column 23 | `parseSubnet4` returns `isc::dhcp::Subnet4Ptr` |
| `hover` | `src/commands.cc`, line 75, column 37 | `listSubnets` signature and `subnet4.h` documentation |
| `hover` | `src/subnet4.cc`, line 163, column 25 | `parseSubnet4` signature and `arguments.h` documentation |
| `hover` | `src/subnet4.cc`, line 35, column 36 | Native `ConfigBackendPoolDHCPv4::getAllSubnets4` signature, selectors and return type |
| `definition` | `{"symbolName": "getAllSubnets4"}` | Native header under the configured Kea installation |
| `diagnostics` | Each of the four absolute `src/*.cc` paths, one call per file | Published project diagnostics, not just MCP initialization |

Resolve positions again after source changes. Name-based definition results
can include an enclosing namespace's source rather than only the requested
function; inspect the named symbol within that output. References observed here
contain call sites, not a promise to enumerate declarations or every external
Kea implementation. Allow indexing to finish before treating missing results
as evidence. Native header navigation proves installed API visibility, not SQL
connectivity or runtime behavior.

Verification on 2026-10-16 used Codex CLI `0.163.0`. Before adding the TOML file,
`codex mcp get clangd --json` reported no such server; afterward it returned the
enabled stdio registration above. The active agent session did not expose this
server's tools, so interactive Codex tool availability remains to be confirmed
with `/mcp` in a fresh session. A temporary direct MCP stdio client using the
same launch settings successfully called all four read tools: three definitions,
two reference searches, five hovers and diagnostics for all four sources.
The probe stopped its own bridge and clangd processes afterward.

The server's debug log confirmed loading
`build/integration/compile_commands.json` and constructing all four source ASTs
with `/usr/bin/c++`, `-std=c++14`, `-O3`, `-DNDEBUG`, PIC/visibility flags,
`-Wall -Wextra -Wpedantic -Werror`, prefix maps and the configured Kea,
MariaDB and PostgreSQL system include paths. No fallback command was observed.
All four sources published empty diagnostic lists. The retained Kea prefix was
`build-repro-clean/install` (`KEA_VERSION=3.2.1-git`); no reconfiguration was
needed. Empty diagnostics alone would not establish correct database use.

The clangd 22 `ExtractFunction` full-probe limitation in `src/subnet4.cc`
[still applies](#clangd-feature-probes). Normal MCP diagnostics and navigation
passed; extraction/refactoring correctness is not established. Do not suppress
warnings or change production code to make the bridge or full probe pass.
Interactive Zed and Codex UI behavior are separate checks.

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
This is an accepted warning, not a hook defect. The standalone clang-tidy results
above were obtained with version 14; rerun them after changing the selected tool.
The project configuration is unchanged.
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
/usr/bin/clangd --compile-commands-dir=build/integration --check=src/arguments.cc
# Also verify automatic discovery through .clangd:
/usr/bin/clangd --check=src/arguments.cc
```

Debian clangd 14.0.6 reproducibly segfaulted during `--check=src/arguments.cc`
after parsing and indexing, at its per-token feature tests. clangd **22.1.8**
resolves that reproducible crash: the original command completes with zero
errors. However, the full `src/subnet4.cc` probe reports an `ExtractFunction`
feature-test failure: `Cannot extract break/continue without corresponding
loop/switch statement.` This is a language-server refactoring probe failure,
not a compiler diagnostic or crash. The full script keeps returning failure
to expose it; no checks or production flags are removed to hide it.

The script explicitly invokes `/usr/bin/clangd`; it preserves C++14 and the existing
Kea flags. No hook source or production compiler settings changed. These
command-line probes do not verify every interactive completion, hover or
refactoring request inside Zed.
