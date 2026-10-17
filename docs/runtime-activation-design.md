# Persistence-to-activation design

## Supported initial policy

Propose **operator-controlled sequential activation**, with one change window per
configuration database, a canary, and verified activation on every intended Kea
instance. Keep periodic configuration fetching disabled for this workflow using
the supported native Kea configuration. This is an operational policy to qualify,
not a new hook feature or a claim of atomic multi-instance activation.

The hook persists through native configuration-backend APIs and reports
`activation-requested: false`. Existing [packet tests](../tests/dhcp.py) verify
that SQL changes and DHCP behavior differ until pull/reload; existing
[multi-process tests](../tests/concurrency.py) verify per-instance activation.
Do not infer live state from `cb-subnet4-get`, which reads SQL.

## Workflow

| Stage | Required evidence / stop condition |
| --- | --- |
| Establish window | Fence one writer; inventory every consumer, server selector, local overrides, active configuration and relevant leases. Stop if any consumer or other writer is unknown. |
| Validate intent | Apply existing hook input checks and review complete node configuration compatibility: interfaces, subnet relationships, classes/options, pools, active leases and tag visibility. Isolated staging/canary validation is additional evidence, not something current subnet parsing guarantees. |
| Persist once | Submit through the designated writer and retain outcome. On uncertainty use [reconciliation](transaction-recovery-policy.md); do not activate or retry blindly. |
| Verify stored candidate | Read back complete managed subnet/pool state and check ID/prefix and ownership guards. Resolve hidden association ambiguity before proceeding. Request echoes are insufficient. |
| Activate canary | Prefer native `config-backend-pull` when its backend remains configured. Use controlled `config-reload` when rebuilding configuration/backend state is necessary. A restart is a maintenance/recovery action. |
| Verify canary | Inspect `config-get` and compare the expected managed fields in the merged active configuration; verify critical service behavior. A command result 0 alone is insufficient. |
| Activate remaining nodes | Proceed sequentially or in explicitly approved batches, recording each outcome. Require compatible transient mixed configurations or use a maintenance window. |
| Close window | Record persisted state and all node active states, errors and unresolved nodes. Admit the next write only after success or an explicit operator resolution. |

Whole-file equality is usually inappropriate because nodes have local interfaces,
overrides and selectors. Compare normalized managed objects and the settings
necessary for this change, while retaining each node's full protected snapshot
for diagnosis. An external rollout generation may label records but is not a
native database revision or CAS guarantee. Native audit cursors likewise do not
make activation atomic.

## Validation boundaries

Kea configuration checking of local JSON does not by itself prove that a future
SQL fetch will form a valid merged configuration. The existing hook cannot dry-run
a complete multi-node configuration or validate arbitrary richer objects. Qualify
a staging/canary procedure using exact node configuration, Kea build and native
APIs before calling it a production validation gate. Until then use conservative
minimal changes and a maintenance window for lease-sensitive changes.

Tests already demonstrate invalid-interface reload failure, persistence surviving
that failure, corrected reload, explicit pool activation, restart and deletion
with retained leases. They do not establish production fleet rollout or all
class/option/global combinations. Future acceptance should include a deliberately
invalid local configuration, not database interruption.

## Partial failures and restart

Stop subsequent mutations if one consumer fails activation. Keep a per-node
record of old/new/unknown state. Resolve by fixing the node and rolling forward,
or by an explicitly reviewed compensating SQL mutation followed by another
verified rollout. Do not automatically revert SQL: compensation can fail and
affects already updated consumers and leases.

Native pull can return success without applying the desired content when its
backend has been removed. Verify the backend configuration and active objects;
reload may be required to restore backend management. See
[backend recovery observations](backend-behavior.md).

Disabling periodic fetch does not pin a configuration across restarts. A consumer
starting or reloading during a pending change may read current SQL. Serialize
planned restarts with the change window, monitor unplanned restarts, and treat
them as possible activation events. If preservation of an old generation across
restart is required, a qualified snapshot/staging design is additional work;
the current hook offers no revision-pinning mechanism.

No response or orchestration creates atomic activation across processes. Mixed
states may be unsafe for pool reassignment or identity reuse; a healthy canary
does not eliminate that risk. Supervised restart does not guarantee zero DHCP
interruption. This design does not add an HA protocol or lease synchronization.

## Observability and acceptance

Maintain separate records for persisted candidate, node activation attempt and
verified active state. Capture error category and timings without credentials or
full sensitive configurations in shared logs. Use real native reads for SQL health,
`config-get` for active content, and qualified packet probes for service behavior.
Do not use `db-commands-diagnostic` as either a DB or DHCP health assertion.

Future tests should cover PostgreSQL/MariaDB and both packet threading modes with
two consumers: neither changes before activation; canary changes alone; one
activation fails; later correction converges both; restart during a pending
window is detected; deletion keeps leases. No destructive fault injection is
needed to establish these orchestration rules.
