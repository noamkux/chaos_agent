# ADR-0015: A few generic disrupt tools instead of a tool per fault

**Status:** Accepted, 2026-11-26
**Related:** ADR-0014 (no catalog), ADR-0016 (denylist), ADR-0017 (snapshots), ADR-0030 (node failure)

## Context
The agent must be able to "go wild" within the rules. The question: what do the disrupt tools look like?

## Options
1. **A tool per fault:** `kill_pod`, `scale_to_zero`, `add_cpu_limit`, `break_readiness_probe`... Each is easy to reason about and to restore. But together they are a fixed menu, and every new idea needs a new tool.
2. **A few generic tools bounded by damage limits:**
   - `patch_resource`: a patch on any object in scope, always after a snapshot that can restore it;
   - `delete_pod`: one running pod of a workload, replaced by its controller;
   - later, agent-written Chaos Mesh faults (latency, partition, stress) and node actions.

## Decision
Option 2. With `patch_resource` the agent can change replicas, resources, probes, env, selectors, ports, HPAs, NetworkPolicies, or any field of a custom resource, and the runner restores it from the snapshot. What it may not do is set by the denylist (ADR-0016), not by the tool.

Details that make the generic tools safe:
- **Strategic merge patch**, so lists such as `containers` and `env` merge by name. Custom resources do not support it (the API returns 415), so the server falls back to a JSON merge patch, which replaces lists whole.
- **`resourceVersion` as a precondition** in every patch: if the object changed since its snapshot, the API returns 409 and nothing is written, so the snapshot always describes the state just before our change.
- **In metadata, only labels and annotations** may change: renaming an object is not chaos.
- **`delete_pod` by workload, not by pod name:** the model does not see pods; the server picks the first running pod of the workload's selector by name, so the same request hits the same pod and an experiment can be repeated.

## Consequences
- **Gains:** the agent's ideas are not limited by our tool list; one restore mechanism covers every patch.
- **Trade-offs:** a generic patch is harder to reason about than a named fault, so its safety rests on the denylist and the admission policy. A change to a pod template restarts every pod of the workload, so the rollout is part of every such experiment (stated in the prompt, ADR-0027). `delete_pod` finds pods only through `matchLabels`.

## In the code
- `servers/mcp/disrupt.py`: `patch_resource` (415 fallback, `resourceVersion` precondition, metadata rule), `delete_pod`.
- `orchestrator/runner.py`: `ACTIONS`, `check`, and the `patch` and `delete_pod` branches of `run_experiment`.
