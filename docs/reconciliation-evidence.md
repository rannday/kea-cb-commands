# Reconciliation evidence — Milestone 22

**Status: PARTIAL. Production readiness remains NO-GO.** The new diagnostic
workflow retains independently collected state and fails closed. It cannot yet
establish exact full-configuration equivalence or authorize real recovery.
A passing safety test means incomplete evidence blocked writes, not that the
deployment met M22 acceptance. See [operator recovery](operator-recovery.md).

## State model and evidence sources

| State | Definition and source |
| --- | --- |
| Persisted | Configuration committed to the native SQL backend; native read commands plus diagnostic association SQL |
| Intended | Operator-approved configuration for each selector; this fixture verifies its minimal request and retains native readback as its expected subnet |
| Active | Each running consumer's independently queried native `config-get` subnet subtree |
| Writer ownership | Trusted supervisor's complete child inventory, admission, packetless check, process instance and endpoint checks |
| Recovery | Classification of fresh observations plus durable uncertainty/hold state |

Database rows, native serialization and runtime serialization are different
evidence sources. Neither a successful mutation nor a successful pull establishes
active convergence. Fixture intent is not a production intent registry.

Implementation: [canonicalizer and gate](../tests/reconciliation.py),
[real collector](../tests/recovery.py), and
[unit regressions](../tests/test_reconciliation.py). The collector reuses
[M21 roles](../tests/designated_writer.py) and both existing SQL fixtures.
It adds no production command, hook SQL, activation or retry.

The report retains native universal subnet readback, diagnostic SQL subnet IDs,
prefixes, actual association tags (including NULL) and modification timestamps.
Selector-specific native get results are kept separately. Consumer observations
retain logical identity, expected and runtime selector, endpoint, PID/start ticks/
boot ID, admission, subnet configuration, safe backend type/name/host/port,
observation time and available status PID/uptime/reload fields.

Do not persist complete `config-get` replies: `config-control` can expose
credentials. The collector stores an explicit safe subset, never passwords,
authorization or raw database dumps. Subnet option/context data is retained for
comparison; exporting diagnostics from a real deployment needs a separate review
of operator-supplied content. These fixtures use disposable non-secret data.

## Canonicalization and fingerprints

Every received configuration field is retained, including unknown fields.
Dictionary keys are serialized in sorted order. Only subnet, pool, association
and server-tag collections are sorted; duplicates are preserved. Other arrays
retain order because their semantics have not been proved order-independent.
Selectors remain separate report entries; they are never unioned.

IPv4 pool CIDR and range syntax normalize to inclusive address pairs. For example,
`192.0.2.0/25` and `192.0.2.0 - 192.0.2.127` both become
`["192.0.2.0","192.0.2.127"]`. Remaining pool fields remain present.
Omission, `null` and `[]` remain distinct. No default, option, association or
timestamp is dropped to force agreement.

Fingerprints use SHA-256 over UTF-8 JSON with sorted dictionary keys, compact
separators, unescaped Unicode and rejected non-finite numbers. Each fingerprint
is stored alongside its canonical `data`; a hash alone is not evidence.
Unit tests cover equivalent syntax/order, idempotence, changed associations,
omitted/empty/null and order-sensitive unknown arrays.

## Native limitations and exactness

Pinned Kea 3.2.1 source establishes:

- `Subnet4::toElement()` in `src/lib/dhcpsrv/subnet.cc` serializes subnet
  configuration but not actual server tags or modification timestamps.
  PostgreSQL native fetch retains those separately in `pgsql_cb_dhcp4.cc`.
  Pool modification timestamps are not retained in the serialized pool.
- The public get command echoes the requested selector, not the object's actual
  complete association set. Internal ANY is not a public bulk inventory.
- `config-get` in `src/bin/dhcp4/ctrl_dhcp4_srv.cc` reads active CfgMgr state.
  Its content hash is not a SQL revision or activation generation.
  `status-get` does not provide a durable process-instance token.
- Runtime subnet readback includes `reservations: []` in this fixture while
  native backend serialization omits that field. The collector preserves the
  difference. Equivalence of defaults, inherited globals, classes, options and
  local versus SQL configuration is not qualified.

The SQL supplement is intentionally a narrow diagnostic query, not a complete,
transactionally consistent backend snapshot. Globals, shared networks, global/
pool options, audit cursors, pool timestamps and rich inheritance semantics are
not fully inventoried. Native audit time/revision cursors are selector-filtered;
no audit cursor or timestamp is treated as a complete configuration version.

Consequently the real collector always sets `complete: false`. It cannot
resolve unknown commits or release the durable gate. It separately reports the
M21 managed projection (ID, prefix, lifetime and pools), including pending and
partial activation. A projection's CONVERGED result is only evidence for those
fields; it never feeds the admission gate. Synthetic complete observations test
the generic gate's recovery algorithm, not real backend exactness.

## Associations and selectors

Both engines exercise universal association 910; single associations 920/921;
multi-association 922; and unassigned 923. Distinct IDs with overlapping prefixes
are supported. Globally unique IDs and equal-prefix constraints prevent using
tags as independent mutation namespaces.

Native ALL sees 910. ONE(consumer-a) sees 910/920/922 and
ONE(consumer-b-recovered) sees 910/921/922. Unassigned 923 is absent from those
views but remains visible in diagnostic SQL. The association evidence preserves
both tags on 922 and NULL on 923. It does not infer ownership from a get request's
selector. Selector tests are native reads; consumers activate universal fixture
910. Differing selector-specific runtime deployments remain unqualified.

## Validity and staleness

A collection has a random workflow session, increasing serial and wall-clock
observation time. Linux boot ID plus /proc start ticks distinguishes reused PIDs.
These are correlation evidence, not distributed fencing or signed attestations.
Control identity must agree with the supervised instance and its admission.

No API accepts an old evidence file as authority. Recovery and promotion collect
again; even a retained contradictory CONVERGED result cannot authorize either.
A missing required consumer is incomplete. An endpoint exception fails the
operation with the durable hold already saved; it is not a convergence result.
Collections are sequential observations, not an atomic fleet/SQL transaction.
Only a trusted, serialized local supervisor without external writers is in scope.

Reports are generated under `build/integration/reconciliation-results/`.
They preserve evidence after private SQL fixtures and processes are cleaned up.
See the requested local `build/milestone22/checks.md` for executed commands,
matrix, failures/corrections and remaining acceptance gaps.
