# ADR-0030: Node and zone failures: a drain mode and a lost mode, set by node_actions in the RoE

**Status:** Proposed, 2026-11-27
**Related:** ADR-0012 (discovery), ADR-0015 (generic tools), ADR-0016 (denylist), ADR-0017 (undo), ADR-0031 (restore on startup)

## Context
Every action so far works on objects in the tested namespaces. None of them tests what topology spread, anti-affinity and PDBs are for: surviving the loss of part of the infrastructure. W1 (frontend pinned to one zone) can only be found by losing that zone; scaling to 0 never shows it. The questions:
1. Which node failure do we simulate, and how, through the Kubernetes API?
2. A node is cluster-scoped: whose pods are moved?
3. How is it restored?
4. What must the agent see to plan it?
5. What permissions does it need, and how are they fenced?

## Options

**1. Which failure:**
- **Marking the node NotReady.** Not possible: Ready is a status condition owned by the kubelet, which rewrites it every few seconds; the node controller also removes the `node.kubernetes.io/unreachable` taint from a node whose kubelet is alive.
- **Drain through the Eviction API** (cordon, then evict each pod). Simulates planned events (node upgrades, autoscaler scale-down, spot replacement), the most common node events in production. Respects PDBs, so it also tests them.
- **A `NoExecute` taint of our own** (`chaos-agent.io/node-lost`). Every pod without a matching toleration is removed at once, PDBs are not consulted, and the pods are recreated elsewhere. Simulates a sudden loss.
- **Stopping the node** (`docker stop` on kind, AWS FIS in the cloud). The real thing, including the 40 s until NotReady and the 300 s `tolerationSeconds` before eviction. Not available through the Kubernetes API, so not on every cluster.

**2. Whose pods:**
- **Only pods in scope** (cordon, evict only in the RoE's namespaces). Keeps "the agent touches only its scope"; but the application gets the remaining nodes to itself, which is optimistic.
- **Every pod on the node.** Realistic, but touches every namespace on it.

**3. Node or zone:** a zone is every node with the same `topology.kubernetes.io/zone` value, the standard label every cloud sets.

## Decision
- **One action, `node_failure`,** with a `node` or a `zone` target and a `mode`:
  - `drain`: cordon, then evict through the Eviction API; a pod blocked by a PDB (429) is reported as `blocked_by_pdb`, not retried.
  - `lost`: cordon, then the `NoExecute` taint.
- **`node_actions` in the RoE replaces `allow_node_actions`:** `off` (default), `scope_only` (drain only, evicting only pods in scope), `whole_node` (drain of every pod, and `lost`, which cannot be scoped).
- **Restore:** remove the taint and uncordon. The undo is written before the cordon. Pods do not move back on their own (only a descheduler does that), so the result includes the placement after the experiment, and the prompt says that later experiments run on that placement.
- **Guards in the orchestrator:** never a control-plane node; never every schedulable node; a zone failure only when at least two zones exist; `node_actions` in the RoE and `allowNodeActions` in the chart values (two layers).
- **The agent sees placement:** a new observe tool returns nodes with their zone and, per node, the workloads in scope that have pods there. Needs `get` and `list` on nodes (a ClusterRole, read-only).
- **Permissions:** `patch` on nodes (cordon and taint), and `create` on `pods/eviction` in scope. The admission policy allows the disrupt ServiceAccount to change only `spec.unschedulable` and taints whose key starts with `chaos-agent.io/`; labels, annotations, other taints and the rest of the spec are denied by the API server.

## Consequences
- **Gains:** topology spread, anti-affinity and PDBs are tested by the events they exist for; W1 becomes findable. Pods left Pending because a `DoNotSchedule` spread cannot be satisfied in the remaining zones are a real finding.
- **Trade-offs:** the widest blast radius of any action, which is why it is off by default and fenced twice. `lost` starts evicting at once, so it is an optimistic version of a real node loss. In the lab one node is one zone, so node and zone failures cannot be told apart.
- **Not solved:** an ungraceful node death with the real detection delay (backlog, with AWS FIS). A watchdog that uncordons if the orchestrator dies and never comes back (backlog; ADR-0031 covers a restart).

## In the code
- Not built yet. Planned: an observe placement tool in `servers/mcp/k8s.py`; node tools in `servers/mcp/disrupt.py`; the `node_failure` action in `orchestrator/runner.py`; `node_actions` in `orchestrator/run_config.py`; RBAC and the policy in `charts/chaos-agent/templates/`.
