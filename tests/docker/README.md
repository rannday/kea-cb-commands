# Published release installation test

This Compose harness installs the public **v0.1.0** hook into a clean Ubuntu
24.04 x86_64 container running unmodified ISC Kea 3.2.1. It never builds the
project hook or copies a local hook binary. This is separate from the existing
[source-build CI and acceptance suite](../../docs/reproducible-builds.md).

## Prerequisites and commands

Run from Debian WSL with Docker Desktop's Linux WSL2 engine and Compose v2.
The engine must support Linux amd64 containers. Network access is needed during
the build for Ubuntu packages, pinned Python tools, Kea source and GitHub release
assets. The first Kea build took about 25 minutes with two jobs in the verified
environment; subsequent runs reuse layers.
No host Kea installation, SQL server, Python environment or root access is needed.

From the repository root:

```sh
tests/docker/run.sh start        # Build image; start and wait for both databases
tests/docker/run.sh test         # Also starts dependencies; runs all acceptance checks
tests/docker/run.sh diagnostics  # Container state and recent logs
tests/docker/run.sh stop         # Remove this project's containers and network
tests/docker/run.sh clean        # Also remove this project's disposable volumes
```

`test` returns nonzero on failure and copies logs, command responses, lease files,
dependency/export checks, package versions and release provenance into
`build/docker/results/`. Generated credential files are removed. Logs can include
the public disposable database password; never substitute production credentials.
Containers remain available for diagnosis until `stop` or `clean`. After `clean`,
running `test` initializes fresh databases again. Images and build cache remain;
the script never prunes other Docker resources.

The fixed project name is `kea-cb-release-validation`. Do not run two copies
concurrently. Docker client/buildx state defaults to ignored `build/docker/client/`
so this harness does not change global Docker configuration. An existing
`DOCKER_CONFIG` is respected.

## Files and installation

- `compose.yml`: digest-pinned Ubuntu runtime build, PostgreSQL 15.18 and MariaDB
  10.11.16 services, private internal network and disposable volumes.
- `Dockerfile`: builds only upstream Kea with the existing checksum-pinned
  [Kea 3.2.1 builder](../../scripts/build_kea.py), then installs runtime packages
  and the published hook in a separate stage. Native SQL hooks and schemas come
  from that matching Kea installation. `kea-lfc` is retained because Kea requires
  the lease-file helper even with automatic cleanup disabled.
- `Dockerfile.dockerignore`: allowlist excluding project hook sources, local
  builds, Git state and credentials from the build context.
- `install_release.py`: validates the GitHub release identity and annotated tag's
  commit, downloads the official archive and checksum, verifies both the checksum
  file and the independently pinned hash before extraction, inspects the exact
  archive contents, and installs the library as described in
  [release installation](../../docs/release-install.md).
- `validate.py`: reuses existing HTTP command, lifecycle, DHCP wire and lease
  assertion helpers. `run.sh` provides the workflow above.

The artifact is
`kea-cb-commands-0.1.0-linux-ubuntu-24.04-x86_64-kea-3.2.1.tar.gz`, downloaded
from the [official v0.1.0 release](https://github.com/rannday/kea-cb-commands/releases/tag/v0.1.0).
Its SHA-256 is
`4287269544a64fba46ccff98e794c265a7116a64f0bf64f7a918d828f6428402`.
The tag must resolve to `b5a1b8b10e3c45d050527f2727a5959abf470117`.
Only the archive's `lib/kea/hooks/libdhcp_db_commands.so` is installed, at
`/opt/kea/install/lib/kea/hooks/libdhcp_db_commands.so`.

Image digests, Kea source/hash and Python tool hashes are pinned. Ubuntu security
packages are resolved from the Ubuntu 24.04 repositories at build time; their
installed versions are captured in `runtime-packages.txt`. This is not an
immutable snapshot of the Ubuntu package repositories.

## Coverage and isolation

Before functional tests, the harness checks Ubuntu/architecture, Kea version,
required C exports and `ldd` resolution for the published hook and both native
SQL hooks. Kea's `-T` validates generated configurations and loads the libraries.
The lifecycle helper verifies registration, missing-backend errors, unload,
reload and clean shutdown with packet multithreading off and on.

Each of four PostgreSQL/MariaDB and threading-mode combinations initializes its
own database with the matching `kea-admin`, then checks empty listing, creation,
ID/prefix retrieval, updates, pool preservation/replacement/removal, rejected
arguments and prefix conflicts, recovery after rejection, restart persistence,
deletion and retained leases. The native SQL hook precedes the release hook in
`hooks-libraries`; `config-control` selects one database. MariaDB uses Kea's
`mysql` backend. Test credentials and all databases are disposable.

Actual relayed DHCP DISCOVER/OFFER/REQUEST/ACK packets use only the Kea
container's loopback: server `127.0.0.1:1067`, relay `127.0.0.2:1068`, subnet
`127.0.0.0/24`. Tests verify the pool, ACK identity and an active memfile lease
with the expected hardware address, subnet ID and lifetime. They verify silence
before activation and after pool removal/deletion. Pool replacement is tested
across a real Kea restart. Activation uses explicit native `config-reload`;
commands only persist SQL state. See [command contracts](../../docs/commands.md).

No broadcast across a Docker bridge is assumed. The harness has no published
ports, host networking or privileged containers. Kea drops all Linux
capabilities and uses unprivileged UDP ports. Its only attached bridge network
is internal to this project. Database traffic stays on that network; DHCP stays
on private loopback. No Windows, WSL, external interface or physical LAN receives
DHCP test traffic. This tests relayed DHCP processing, not a physical client,
bridge broadcast forwarding, raw Ethernet, or a production deployment topology.

Results validate this Ubuntu amd64 runtime only. Running Docker from Debian WSL
does **not** establish Debian binary compatibility. Oracle MySQL, other Kea
versions and other architectures remain unverified. Existing exclusive-writer,
minimal-subnet and explicit-activation limitations still apply; see
[operations](../../docs/operations.md).

## Verified execution

On 2026-10-16, Docker Desktop's Linux x86_64 engine 29.8.2 completed two full
runs from Debian WSL, with this project's containers, network and volumes removed
between runs. Ubuntu 24.04 ran the pinned unmodified Kea 3.2.1 source (reporting
`3.2.1-git`) with the public v0.1.0 hook. PostgreSQL 15.18 and MariaDB 10.11.16
passed all four backend/threading combinations per run. Each run completed eight
successful DORA exchanges and lease checks, plus lifecycle, CRUD, restart,
activation and rejection checks. The published checksum, required exports,
shared dependencies and configuration validation passed. No additional Linux
capabilities were needed. Repository quality and shell syntax checks passed.

These are local Docker results, separate from GitHub Actions. They do not
establish Debian binary compatibility or broadcast DHCP behavior.
