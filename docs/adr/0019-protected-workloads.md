# ADR-0019: Data stores are protected only through protected_workloads in the RoE

**Status:** Accepted, 2026-11-26
**Related:** ADR-0016 (denylist), ADR-0020 (owners)

## Context
Some workloads must not be restarted: in the lab, `redis-cart` keeps every cart on an emptyDir, so one restart deletes all of them. The question: how does the agent know what it may not touch?

## Options
1. **A blanket rule in the prompt:** "never restart a database". Easy. But a database that survives a restart is exactly a resilience test worth running, even in production, and "database" is a guess the model makes from names.
2. **Detect state automatically** (StatefulSets, PVCs, emptyDir volumes) and refuse. Automatic, but wrong both ways: a StatefulSet with replication should be tested; a Deployment with an emptyDir cache may be fine to restart.
3. **A list in the RoE, written by whoever owns the cluster:** `protected_workloads`. The agent may measure them, never change them.

## Decision
Option 3. Empty by default, since only the cluster owner knows what is unsafe. The runner refuses any experiment whose target is in the list, and the prompt shows the list, so the model does not spend experiments on it. No blanket rule about data stores in the prompt.

## Consequences
- **Gains:** a database restart stays a legitimate experiment wherever the owner allows it; the rule is explicit and auditable.
- **Trade-offs:** an owner who forgets to list a fragile store leaves it open. Protection is by name, so it covers direct actions on the workload, not indirect effects (deleting a pod of a service that writes to it).

## In the code
- `orchestrator/run_config.py`: `protected_workloads` in `ROE_DEFAULTS` and its check in `load_roe`.
- `orchestrator/runner.py`: `check` (`action["name"] in roe["protected_workloads"]`).
- `orchestrator/agent.py`: `format_rules`.
- `lab/apps/boutique/roe.yaml`: `protected_workloads: [redis-cart]`, with the reason.
