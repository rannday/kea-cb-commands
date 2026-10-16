# Producing a release

The initial project version is **0.1.0**, declared in CMake; the corresponding
release tag is **v0.1.0**. This does not change Kea's `version()` ABI export.
Read [release notes](release-notes.md), [installation](release-install.md) and
the [verified-source build guide](reproducible-builds.md) first.

## Local candidate

Use the existing pinned quality environment and a matching verified Kea 3.2.1
installation. Reuse this checkout's `build-repro-clean/install` without moving
it; a new environment builds `build/upstream/install` using the pinned source
guide. Set `KEA_PREFIX` to the applicable absolute prefix.

```bash
export KEA_PREFIX="$PWD/build/upstream/install"
PATH="$PWD/build/quality/bin:$PATH" python3 -B scripts/quality.py
python3 -B -m unittest discover -s tests -p 'test_*.py' -v
python3 -B -m unittest discover -s scripts -p 'test_*.py' -v
python3 -B scripts/integration.py --kea-prefix "$KEA_PREFIX" \
  --build-dir build/integration --jobs 2
python3 -B scripts/package_release.py --kea-prefix "$KEA_PREFIX" \
  --build-dir build/integration --output-dir build/release --tag v0.1.0
```

The strict gate configures Release C++14 with warnings as errors, runs all six
CTest tests with zero skips, and checks cleanup. It covers PostgreSQL/MariaDB,
both packet threading modes, real DHCP DORA and lease behavior. Packaging
requires those results to postdate the library, installs through CMake into a
temporary staging directory, and verifies exports and matching dependencies.
It refuses a mismatched tag, unsupported Kea version, non-Release/non-C++14
build or nonnative Linux x86_64 target.

The output is named
`kea-cb-commands-0.1.0-linux-<distribution>-<version>-x86_64-kea-3.2.1.tar.gz`
with an adjacent `.tar.gz.sha256`. A single versioned root directory contains
exactly:

```text
lib/kea/hooks/libdhcp_db_commands.so
LICENSE
INSTALL.md
RELEASE-NOTES.md
manifest.json
```

The manifest records project/Kea versions, pinned Kea source, compiler, platform,
libc, direct NEEDED libraries, required GLIBC/GLIBCXX/CXXABI symbol versions,
source tag URL and library SHA-256. No dependencies, credentials, databases,
virtual environments or other development output are bundled. Runtime and
build dependencies are distinguished in the installation guide.

Archive ordering, ownership, modes, tar timestamps and gzip metadata are fixed.
Identical library bytes and metadata on the same packaging runtime produce
identical archives. This does not promise byte-identical compiler outputs across
different toolchains, OS packages or zlib versions. Source/dependency pins and
the recorded environment bound the reproducibility claim.

Inspect and install the packaged artifact into an isolated staging directory:

```bash
cd build/release
sha256sum --check *.sha256
tar -tzf *.tar.gz
cd ../..
mkdir -p build/package-stage
tar -xzf build/release/*.tar.gz -C build/package-stage --strip-components=1
python3 -B scripts/verify_artifact.py \
  --library build/package-stage/lib/kea/hooks/libdhcp_db_commands.so \
  --kea-prefix "$KEA_PREFIX" --forbid-path "$PWD"
LD_LIBRARY_PATH="$KEA_PREFIX/lib" python3 -B tests/smoke.py \
  --server "$KEA_PREFIX/sbin/kea-dhcp4" \
  --hook "$PWD/build/package-stage/lib/kea/hooks/libdhcp_db_commands.so" \
  --work-dir "$PWD/build/packaged-lifecycle"
git diff --check
```

Use a directory containing only the chosen candidate when expanding wildcards.
The packaged lifecycle test loads, reloads, unloads and shuts down Kea in both
threading modes. Do not substitute this smoke test for the SQL/packet gate.
Local archive inspection and smoke tests require no production deployment.

## CI and publication gates

The existing [CI workflow](../.github/workflows/ci.yml) runs quality/unit checks,
then builds the checksum-pinned unmodified Kea source and runs full acceptance
on Ubuntu 24.04 x86_64. It packages the hook, verifies the checksum, inspects the
archive and tests the extracted library before uploading `versioned-release`.
Diagnostic logs/reports are uploaded even on failure, with a seven-day retention;
fixture directories and credentials are excluded. Package uploads require all
preceding checks to succeed. No upstream build cache is used.

Ordinary branch pushes, pull requests and manual dispatch run verification only.
Only a **push of an explicitly created `v*` tag**, matching CMake's version,
can enter the release job after both required jobs succeed. Workflow permissions
default to `contents: read`; only that job receives `contents: write` and
`actions: read`. It downloads the verified artifact from the same run, verifies
its checksum again, and uses the GitHub CLI to attach the archive and checksum
with the checked-out release notes. No publishing service is involved.
See GitHub's [workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)
and [release CLI](https://cli.github.com/manual/gh_release_create).

Before approving publication, review the exact commit, version, notes, license,
platform dependency manifest and all test results. Commit/push changes and
observe a successful branch CI run first. After separate explicit authorization,
create and push the matching release tag; that push authorizes publication by
the workflow. Do not push a release tag merely to test CI. No release is made
from an untagged commit or a manual dispatch, even if it selects a tag.
An existing release makes creation fail; inspect it rather than retagging or
silently replacing public assets.

Remote CI, the Ubuntu AppArmor namespace step, token permissions, GitHub artifact
transfer and publication remain unverified until exercised remotely. Local
verification does not establish their success. Ubuntu-built artifacts must pass
their own gates; the locally tested Debian archive does not prove compatibility
with Ubuntu or another runtime.

## Milestone 10 local verification

Verified on Debian 12 WSL2 x86_64 using GCC 12.2.0 and glibc 2.36. The existing
verified, unmodified Kea 3.2.1 installation at `build-repro-clean/install` was
reused; Kea was not rebuilt. A fresh `build/m10-integration` configured and built
the hook in Release C++14 with `-Wall -Wextra -Wpedantic -Werror`.

All six CTest tests passed with zero skips in 383.01 seconds: transport,
lifecycle, PostgreSQL reads/mutations and DHCP, MariaDB reads/mutations and DHCP.
SQL and packet tests covered both threading modes, DORA and lease checks.
The strict runner confirmed temporary resource cleanup. All 25 Python unit tests
passed, including two new packaging tests for deterministic archive contents and
compatibility/tag rejection. The combined quality runner passed formatting,
Ruff, whitespace, JSON and local documentation links.

Produced `build/release/kea-cb-commands-0.1.0-linux-debian-12-x86_64-kea-3.2.1.tar.gz`
and its `.sha256` file. Archive SHA-256:

```text
a35061a346dc019745aa688a991b0baff11893c5abe151012949ff0bb67753e5
```

Two packaging runs into separate output directories produced identical bytes.
Inspection confirmed exactly the five regular files listed above, fixed metadata,
the original license and a matching manifest library hash. Checksum verification,
staged extraction, required exports, matching native dependencies and absence of
RPATH/RUNPATH/development paths passed. The extracted library passed real Kea
validation, commands, reload, unload and shutdown in both threading modes; its
fixture directory was empty afterward. A mismatched `v0.2.0` tag was rejected.

Workflow YAML parsing, job dependencies, tag-only publication conditions, scoped
permissions, action SHA pins and all 11 shell scripts (`bash -n`) passed local
inspection. `actionlint`, `zizmor` and the GitHub CLI were unavailable locally;
no full Actions expression validation or remote execution is claimed.
`git diff --check` passed. Remote CI, Ubuntu runtime compatibility and release
publication remain pending. No commit, push, tag or remote workflow was performed.
