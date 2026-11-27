# ADR-0009: observe, probe and disrupt are permission boundaries, not "AI or not"

**Status:** Accepted, 2026-11-26
**Related:** ADR-0008 (a server per level), ADR-0011 (deterministic or agent)

## Context
When deterministic work moved from the model to the orchestrator (ADR-0011), it was tempting to read the levels as "observe and probe are deterministic, disrupt is the AI". That would mix two separate questions: what a run may do to the cluster, and who decides what to do.

## Options
1. **Levels describe who acts:** observe and probe are scripts, disrupt is the agent.
2. **Levels describe what a run is allowed to do to the cluster,** whoever decides: observe reads, probe also sends traffic to the application, disrupt also changes things. Each level includes the ones below it.

## Decision
Option 2. A level is set in the RoE (`max_level`) by whoever owns the cluster, and it limits three things at once:
- which servers the orchestrator connects to and loads tools from (`ALLOWED_LEVELS`);
- which ServiceAccount, and so which RBAC, the tool runs with (ADR-0008);
- whether the model gets `run_experiment` at all (only when every experiment tool is loaded).

The model can work at every level: at observe it reasons over the facts; at disrupt it plans experiments.

## Consequences
- **Gains:** a cluster owner can allow measurement without allowing change, and the boundary is enforced by Kubernetes, not by a prompt.
- **Trade-offs:** a run at observe level has little for the model to do since the catalog was removed (ADR-0014); in practice runs are at disrupt.

## In the code
- `orchestrator/tools.py`: `ALLOWED_LEVELS`, `load_tools`.
- `orchestrator/run_config.py`: `LEVELS` and the `max_level` check in `load_roe`.
- `orchestrator/agent.py`: `can_experiment = runner.EXPERIMENT_TOOLS <= server_tools` in `run_agent`.
