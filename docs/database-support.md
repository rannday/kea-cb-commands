# Database support and acceptance targets

Development targets the latest stable PostgreSQL major and the latest stable
MariaDB long-term support (LTS) series. As of 2026-10-17:

| Database | Target series | Current stable patch |
| --- | --- | --- |
| PostgreSQL | 18 | 18.6 |
| MariaDB | 12.3 LTS | 12.3.3 |

PostgreSQL has no separate LTS release label: each major receives five years of
support. See its [version policy](https://www.postgresql.org/support/versioning/).
MariaDB 12.3 is the [current LTS](https://mariadb.org/mariadb-server-12-3-lts-released/);
13.0 is a rolling release and is outside this target. Check the official
[MariaDB releases](https://mariadb.org/mariadb/all-releases/) when updating pins.

Older series and Oracle MySQL are outside the current acceptance target.
Historical verification records retain the versions actually tested. A database
target change does not change Kea's version, native schema or command contracts.
Build this hook against the exact unmodified Kea 3.2.1 installation that loads it.

## Version selection and evidence

The strict [integration runner](../scripts/integration.py) discovers PostgreSQL
through `pg_config --bindir` and MariaDB through `mariadbd` (or its `mysqld`
alias). It rejects servers outside PostgreSQL 18 and MariaDB 12.3 before creating
private databases. It prints the exact server versions and records executable
paths and version output in `build/integration/database-versions.json`. Each
private fixture starts those selected binaries; no host cluster is used.

Install current maintenance patches within those series. The runner validates
the release series without network access; it does not determine whether a
newer patch has been published. Review and update this policy, version checks,
unit tests and Docker pins when the latest stable PostgreSQL major or MariaDB
LTS changes. Do not automatically select rolling releases or prereleases.

[CI](../.github/workflows/ci.yml) selects the official PostgreSQL and MariaDB
repositories for Ubuntu 24.04, installs PostgreSQL 18 and MariaDB 12.3, and
uploads version evidence with the six-test report. Distribution-default
`postgresql` and `mariadb-server` packages alone can select older series.
For local prerequisite installation, configure the official repositories for your
distribution first:
[PostgreSQL Ubuntu](https://www.postgresql.org/download/linux/ubuntu/),
[PostgreSQL Debian](https://www.postgresql.org/download/linux/debian/), and
[MariaDB repository setup](https://mariadb.com/docs/server/server-management/install-and-upgrade-mariadb/mariadb-package-repository-setup-and-usage).
Build/test scripts never install packages or upgrade persistent databases.

The separate [published-release Docker test](../tests/docker/README.md) pins
PostgreSQL 18.6 and MariaDB 12.3.3 images by digest and verifies actual SQL server
versions. It uses new series-specific disposable volumes. PostgreSQL 18's image
mount is `/var/lib/postgresql`; older PostgreSQL data directories must not be
reused. Existing older-series volumes are left alone.

## Current verification

On 2026-10-17, the strict current-source gate passed all six tests with zero
skips on Debian 12 WSL2 x86_64, using PostgreSQL 18.6, MariaDB 12.3.3 and the
existing unmodified Kea 3.2.1 installation. The run took 555.41 seconds and kept
outage/recovery checks enabled. SQL and DHCP suites covered both packet
threading modes; the runner confirmed disposable fixture cleanup. Evidence is
`build/integration/database-versions.json` and
`build/integration/ctest-results.xml`.

The separate Ubuntu 24.04 amd64 published-release Docker harness passed all
four database/threading combinations and eight DORA exchanges with lease
checks on the same database patches. Its evidence is
`build/docker/results/database-versions.jsonl`; see the
[execution record](../tests/docker/README.md#verified-execution). The pinned
v0.1.0 binary predates mutation admission; that newer contract remains covered
by the current-source gate.

All 34 Python unit tests, repository formatting/lint/whitespace/link checks,
workflow YAML and shell syntax checks, and staged hook export/dependency checks
passed. GitHub Actions itself remains unexecuted; these are local results.
Existing exclusive-writer and explicit-activation requirements remain in force.
This is compatibility testing, not an in-place database upgrade or production
qualification.
