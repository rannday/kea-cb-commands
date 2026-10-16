# Install a release archive

Obtain the archive and its matching `.tar.gz.sha256` file from the project's
[GitHub Releases](https://github.com/rannday/kea-cb-commands/releases).
The initial version is **v0.1.0**; publication requires explicit maintainer
approval. Choose the archive for your distribution, version and architecture.
For example, a Debian 12 x86_64 build is named:

```text
kea-cb-commands-0.1.0-linux-debian-12-x86_64-kea-3.2.1.tar.gz
```

Local verification covers Debian 12 WSL2 x86_64 only. Ubuntu 24.04 is a CI
target, pending a successful remote run. An Ubuntu-built archive is not a
verified Debian binary. Other operating systems and architectures are unverified.
When the runtime differs, build the hook against the installation that will
load it using the
[source build guide](https://github.com/rannday/kea-cb-commands/blob/v0.1.0/docs/reproducible-builds.md).
Version-pinned source links become available when the approved tag is created.

## Runtime requirements

- Unmodified ISC Kea **3.2.1**, dynamically linked, with a compatible C++ ABI
  and matching native Kea shared libraries. The required hook ABI is 30201.
- Linux x86_64, glibc, libstdc++ and libgcc runtimes satisfying **all** symbol
  versions in `manifest.json`. The local build uses GCC 12.2 and glibc 2.36.
  Match Kea's compiler ABI flags, libstdc++ dual ABI and Boost ABI as well;
  the Kea version number alone does not establish binary compatibility.
- Kea's transitive dependencies, including its SQL connector and logging,
  crypto and Boost libraries. `manifest.json` lists the hook's direct NEEDED
  libraries; the target loader must also resolve their dependencies.
- Kea's matching upstream `libdhcp_pgsql.so` or `libdhcp_mysql.so`, initialized
  native configuration-backend schema, and a reachable SQL server.
  PostgreSQL 15 and MariaDB 10.11 are tested. MariaDB uses backend type `mysql`;
  Oracle MySQL is unverified. SQL servers may run separately from Kea.

The archive contains only the hook, MPL-2.0 license, this guide, release notes
and a build/dependency manifest. It supplies no Kea, SQL servers or system
libraries. A compiler, CMake, pkg-config, development headers and Python are
build/verification dependencies; they are not needed to load an installed hook.

## Verify, inspect and stage

Download both files through a trusted channel. A checksum detects corruption;
it does not authenticate the publisher independently of that channel.
In the download directory, substitute the chosen archive name below:

```bash
sha256sum --check kea-cb-commands-0.1.0-linux-debian-12-x86_64-kea-3.2.1.tar.gz.sha256
tar -tzf kea-cb-commands-0.1.0-linux-debian-12-x86_64-kea-3.2.1.tar.gz
mkdir -p stage
tar -xzf kea-cb-commands-0.1.0-linux-debian-12-x86_64-kea-3.2.1.tar.gz \
  -C stage --strip-components=1
cat stage/manifest.json
```

Inspect dependencies only for a trusted artifact. With the matching Kea prefix:

```bash
export KEA_PREFIX=/absolute/kea
export LD_LIBRARY_PATH="$KEA_PREFIX/lib"
ldd stage/lib/kea/hooks/libdhcp_db_commands.so
readelf --dyn-syms --wide stage/lib/kea/hooks/libdhcp_db_commands.so
readelf --version-info stage/lib/kea/hooks/libdhcp_db_commands.so
install -m 755 stage/lib/kea/hooks/libdhcp_db_commands.so \
  "$KEA_PREFIX/lib/kea/hooks/libdhcp_db_commands.so"
```

Every dependency must resolve to the intended installation. Required C exports
are `version`, `load`, `unload` and `multi_threading_compatible`. Installation
requires write access to the selected directory. Keep the previous binary and
configuration for rollback; replace a loaded library only during a planned
daemon stop/restart. Configure the service's loader environment or administrator
managed loader paths; an interactive shell export does not configure a service.

## Configure and confirm loading

Initialize the native schema with the matching Kea tools. Follow the detailed
[PostgreSQL setup](https://github.com/rannday/kea-cb-commands/blob/v0.1.0/docs/postgresql.md)
or [MariaDB setup](https://github.com/rannday/kea-cb-commands/blob/v0.1.0/docs/mysql.md)
for grants, `config-control`, server tags and control-channel settings.
MariaDB needs native statement preparation/write grants even for list; tested
PostgreSQL reads can use a SELECT-only account. Do not copy test credentials.

Add the upstream SQL hook first, then this hook, inside the existing `Dhcp4`
object, using absolute paths within Kea's permitted hook directory:

```json
"hooks-libraries": [
  { "library": "/absolute/kea/lib/kea/hooks/libdhcp_pgsql.so" },
  { "library": "/absolute/kea/lib/kea/hooks/libdhcp_db_commands.so" }
]
```

Use `libdhcp_mysql.so` for MariaDB. Configure exactly one native backend in
`config-control`; this hook does not establish connections or read credentials.
Validate the full Kea configuration and load it in an isolated instance before
deployment. Check daemon logs for successful loading and registration. Send
these requests through the configured native control channel:

```json
{"command":"list-commands"}
{"command":"db-commands-diagnostic"}
{"command":"cb-subnet4-list"}
```

The diagnostic should return `result: 0`, `kea-hooks-version: 30201`,
`configuration-backend-pool-accessible: true` and
`database-connectivity-tested: false` inside `arguments`. It proves API access;
the list request additionally exercises the configured SQL backend. A failed
SQL request must not be treated as successful loading/connectivity validation.

## Operation and troubleshooting

The supported interfaces are `cb-subnet4-list`, `cb-subnet4-get`,
`cb-subnet4-set`, `cb-subnet4-del` and `db-commands-diagnostic`. Consult the
[exact contracts](https://github.com/rannday/kea-cb-commands/blob/v0.1.0/docs/commands.md)
before writing. The hook never requests activation; use explicit native
`config-backend-pull`, reload or restart. Keep `config-fetch-wait-time: 0` when
manual activation is required: independently enabled periodic fetching can
activate persisted changes. Delete retains leases.
Follow the exclusive-writer and uncertain-write reconciliation rules in
`RELEASE-NOTES.md`. No automatic activation is performed.

For missing symbols/libraries or ABI rejection, verify the exact Kea installation,
loader paths and manifest requirements, then rebuild against the target if they
differ. For backend failures check the upstream SQL hook, schema, grants,
connection configuration and server reachability. Once native reconnect attempts
are exhausted, a reload/restart may be required; reconcile uncertain writes
before retrying. Rich objects, shared-network subnets and unsafe server-tag
associations are intentionally rejected. See
[operations and security](https://github.com/rannday/kea-cb-commands/blob/v0.1.0/docs/operations.md)
and [backend recovery](https://github.com/rannday/kea-cb-commands/blob/v0.1.0/docs/backend-behavior.md).

Protect control-channel access and SQL credentials with restrictive permissions
and the transport's authentication controls. Commands execute synchronously and
can delay other commands during SQL latency. Do not expose control access to
untrusted users. Logs and native errors may require restricted access even
though command responses suppress native exception details.

Source and license: [v0.1.0 source](https://github.com/rannday/kea-cb-commands/tree/v0.1.0),
with MPL-2.0 terms included in `LICENSE`.
