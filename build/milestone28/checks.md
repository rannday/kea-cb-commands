# Milestone 28 verification

**Status: PARTIAL.** Bounded rich subnet/pool functionality is implemented;
important native attributes, scoped-option preservation through accepted writes,
and member-subnet updates remain unavailable. Production readiness remains NO-GO.
Final SQL/DHCP acceptance passed all six tests with zero skips; temporary
resource cleanup was verified by the strict runner.
Date: 2026-10-18.

## Baseline and implementation

Initial worktree was clean on main/origin/main at
`7be242b9dff97c21d6a377172ac897c2e3bb5681` (M27).
Pinned public ISC Kea 3.2.1 source commit:
`1737462bc79276e3269304ea8cd3d1c03400e30d`.
Source: build-repro-clean/source. Install: build-repro-clean/install.
Release GNU C++ 12.2.0, Linux x86_64 Debian WSL2, C++14, extensions disabled,
-Wall -Wextra -Wpedantic -Werror. PostgreSQL 18.6; MariaDB 12.3.3 LTS (mysql).
Current metadata: build/integration/database-versions.json and release-build.json.

No command registrations or response envelopes changed. Twenty-five project
commands remain registered, including the five original commands. No remote-*
aliases, production SQL, automatic retries or automatic activation were added.

Native calls remain Subnet4::create, Pool4::create, Subnet4::addPool, typed native
attribute setters, fresh native getSubnet4 conflict reads and createUpdateSubnet4.
Existing ALL/ONE visibility, ANY conflicts, one-backend restrictions, named-server
validation and exact single association checks remain. Admission stays explicit
at the existing mutating callout boundary. Native drivers own transaction/audit.

## Capability inventory and mutation semantics

See docs/subnet4-capabilities.md for the native object / SQL binding / native
readback / safe write / runtime observation / commercial scope inventory.
Pinned driver review establishes whole-object replacement: pools, subnet options
and associations are removed/recreated on update. There is no public atomic
expected-revision guard. Timestamps/audit observations are not compare-and-swap;
exclusive designated ownership remains mandatory.

New accepted subnet fields:
- renew-timer and rebind-timer: integer 0..2147483647, nonzero values below valid
  lifetime, and nonzero T1 <= T2.
- next-server: IPv4 address; server-hostname and boot-file-name: strings without
  NUL, at most 63 and 127 bytes respectively.
- client-classes and evaluate-additional-classes: distinct nonempty strings in
  lists; no NUL. Their native order/representation is retained.

Pools accept either start/end addresses or canonical IPv4 CIDR in pool, plus
those two class lists. Native construction validates IPv4, ordering, containment,
overlap and duplicates. Zero endpoints cannot round-trip through pinned SQL
readers and remain rejected. Pool ordering and stable SQL row identity are not
promised.

Existing updates reconstruct only supported native fields, compare the complete
native serialization, merge explicitly supplied typed fields and revalidate.
This is not a generic JSON merge or proof of complete SQL observability.
Omitted optional fields/pools preserve supported stored values. Null is invalid.
Empty strings/lists clear supported boot/class fields; zero clears timers and
0.0.0.0 clears next-server. A supplied pool list replaces it, including [], only
under preservation preconditions. Existing pool class restrictions refuse every
supplied pool list. Options, context, unsupported attributes, membership and
ambiguous associations refuse the entire write, even with omitted pools.
Required ID/prefix/lifetime semantics remain unchanged. Prefix changes must
contain preserved pools. Physical pool IDs/timestamps can change on accepted
native replacement; audit history is retained and new audit rows are expected.

Min/max lifetimes, relay, interface, 4o6, reservations policies, DDNS/cache/TEE,
allocator and other SQL-backed native attributes are not accepted. Shared-network
membership mutation and subnet/pool option writes remain deferred. These are
functional limits, not equivalent implementations of commercial full replacement.

## Commands executed

```sh
cmake --build build/integration --parallel 2
python3 -B -m unittest discover -s tests -p 'test_*.py' -v
python3 -B -m unittest discover -s scripts -p 'test_*.py' -v
python3 -B scripts/integration.py --kea-prefix build-repro-clean/install --build-dir build/integration --jobs 2 --skip-outages
cmake --build build/milestone24/boundary --target callout_boundary --parallel 2
ctest --test-dir build/milestone24/boundary -R '^callout_boundary$' --output-on-failure
PATH="$PWD/build/quality/bin:$PATH" python3 -B scripts/quality.py
python3 -B scripts/analyze.py analyzer
python3 -B scripts/analyze.py cppcheck
python3 -B scripts/analyze.py tidy
python3 -B scripts/verify_artifact.py --library build/integration/libdhcp_db_commands.so --kea-prefix build-repro-clean/install --forbid-path build-repro-clean/source
ctest --test-dir build/integration -N
git diff --check
```

Integration attempts write bounded local logs under /tmp; raw logs are not
published because fixture transport can contain temporary authentication data.
Current final attempt: /tmp/kea-m28-integration-complete.log. Earlier failed
attempts are /tmp/kea-m28-integration-verified.log and
/tmp/kea-m28-integration-final.log. CTest results are under
build/integration/ctest-results.xml and Testing/Temporary/LastTest.log.
No deliberate connection interruption: --skip-outages is explicit. Existing
controlled disposable privilege-failure tests remain in the fixture. No
production network DHCP, historical crash reproduction or destructive fault
injection was run.

## Completed quality checks

Strict Release C++14/Werror build: PASS. Tests unit discovery: 11 PASS.
Scripts/tooling unit discovery: 28 PASS. Actual callout-boundary CTest: 1/1 PASS,
zero skips, 0.01 s. Lifecycle in final runner: PASS, 0.73 s.
Clang analyzer: PASS, seven translation units. cppcheck: PASS, seven translation
units. clang-tidy: UNAVAILABLE, executable missing (exit 1); no installation.
clangd diagnostics for changed C++ implementation: no diagnostics.
Formatting/lint/whitespace/local document links: PASS, 99 checked files.
Artifact exports/shared dependencies/runtime paths: PASS.
git diff --check: PASS. Strict runner process/resource cleanup: PASS.

## Final integration matrix

| Backend | MT off | MT on |
| --- | --- | --- |
| PostgreSQL 18.6 | Read/mutation and packets PASS | Read/mutation and packets PASS |
| MariaDB 12.3.3 LTS | Read/mutation and packets PASS | Read/mutation and packets PASS |

Preceding runner: control_transport 0.05 s, hook_lifecycle 0.75 s,
postgresql_read 137.19 s, mysql_read 259.50 s and mysql_dhcp 277.22 s PASS;
postgresql_dhcp failed before the pool-capacity correction. Total 753.30 s,
5/6 PASS. Each SQL/packet case exercises both MT modes.
Final strict run exited 0: control_transport 0.04 s; hook_lifecycle 0.73 s;
postgresql_read 157.08 s; postgresql_dhcp 152.75 s; mysql_read 333.78 s;
mysql_dhcp 321.13 s. Total 965.51 s. All six required tests ran, zero skips,
zero failures. The runner reported temporary resources removed after its
cleanup verification. CTest ran serially; compilation used two jobs.

New SQL cases exercise rich round-trip, omission preservation, explicit clearing,
CIDR/class pools, invalid fields/types/bounds, class-pool replacement refusal,
unsupported minimum lifetime, existing pool options/context, memberships and
multiple associations. Accepted writes compare unrelated SQL configuration;
refused writes compare full table/audit snapshots. Existing subnet-option,
server/global/definition/option/shared-network and admission cases remain.
Native restart persistence is covered in existing mutation/packet fixtures.

New packet cases inspect persisted versus active configuration separately,
explicitly reload, verify actual OFFER/ACK pool allocation, lifetime, T1/T2 and
boot file, and demonstrate subnet class restriction and clearing. Next-server
and server hostname are independently inspected through config-get, not claimed
as packet-field assertions. Existing router/DNS/custom options, global < network
< subnet < pool inheritance, boot file, DORA and leases remain in the same suite.
This is bounded exercised-field evidence, not exact M22 runtime convergence.

## Failures and corrections

An earlier runner exposed legacy validation-message drift and absent native boot
string length validation. Restored the original missing-field error text and
added explicit 63/127-byte bounds before native writes.
A subsequent full attempt failed all four SQL cases because the new diagnostic
pool-option fixture omitted the final schema's NOT NULL client_classes column
(PostgreSQL SQLSTATE 23502; MariaDB 1364). Added explicit client_classes='[]';
these failures are not PASS evidence. A later strict attempt passed PostgreSQL
read/mutation and the new rich packet
cases, then exposed a fixture interaction in the existing M25 boot regression:
explicit empty subnet boot fields masked the subsequently configured global
boot file. The M28 packet cleanup now restores SQL NULL inheritance through
diagnostic fixture SQL and reloads explicitly after verifying the hook's
explicit-empty behavior. MariaDB then reached the existing shared-network
packet regression and exhausted the eleven-address pool: M28 had added two
fresh leases to a previously exactly-sized fixture. Reusing the initial client
then exposed Kea's remaining-lifetime offer behavior and failed the exact
lifetime assertion. The disposable original pool is now .10-.29 (twenty
addresses), with all range assertions updated consistently. Every exchange
again uses a fresh client and retains exact OFFER/ACK and recorded-lease
lifetime assertions. No leases are deleted or validation relaxed.
The preceding strict attempt passed both SQL read/mutation cases but failed both
packet cases; it is not final acceptance evidence. The intermediate run then
passed MariaDB packets but failed PostgreSQL before the capacity correction.
The final /tmp/kea-m28-integration-complete.log run includes all corrections
and passes all six tests.
No connection fault injection or automatic uncertain-write retry was used.
MariaDB signed timer columns motivated INT32_MAX validation.
Native serialization may omit empty class lists; test comparisons explicitly
treat omission as the native empty-list representation, without discarding
nonempty values.

## Files changed

README.md; docs/architecture.md; docs/command-architecture.md; docs/commands.md;
docs/commercial-parity-gap-analysis.md; docs/compatibility-matrix.md;
docs/dependency-safety-backlog.md; docs/development-roadmap.md; docs/pools.md;
docs/subnet4-capabilities.md (new); src/arguments.cc; src/arguments.h;
src/subnet4.cc; tests/mutation.py; tests/dhcp.py; this requested ignored evidence
file build/milestone28/checks.md (new).

## Remaining limitations and M29

Functional commercial analogues remain 3 implemented / 18 partial / 53 missing
out of 74 (DHCPv4 3/18/15; DHCPv6 0/0/38). Exact interface compatibility remains
0 implemented / 0 partial / 74 missing. The broader bounded subnet path does
not complete commercial full replacement or introduce a new operation.

Dependency/association completeness, scoped-option preservation, safe membership,
concurrent conditional mutation, remote/distributed fencing, upstream transaction
cleanup and exact M22 recovery/convergence remain production blockers.
M22 durable holds and fresh reconciliation requirements are unchanged, not
newly requalified. M29 should establish scope-specific native option identity,
association and dependency evidence, implement only safe scoped-option paths,
and qualify SQL/audit refusals plus actual router/DNS/domain/custom payloads.
Do not begin M29 before review. No commits, pushes, tags or releases performed.
