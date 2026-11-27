# ADR-0020: Three inputs with three owners: target.yaml, the RoE, and the chart values

**Status:** Accepted, 2026-11-26 (measurement and caps added 2026-11-27)
**Related:** ADR-0005 (chart), ADR-0018 (deny groups), ADR-0019 (protected workloads), ADR-0026 (measurement settings)

## Context
A run needs to know what the application is, what normal looks like for it, what the agent may do, and what the cluster can tolerate. The mentor asked that the agent start from a document describing the application's expectations. The question: one configuration file, or several, and who writes each?

## Options
1. **One file with everything.** One place to look. But the people who know each part are different: the application team knows the journeys, security decides what may be broken, the cluster admin decides what the cluster can take. One file means one owner deciding for all three, or three owners editing the same file.
2. **One file per owner,** each validated on its own, with safe defaults for everything optional.

## Decision
Option 2.
- **`target.yaml`, the application team:** the entrypoint Service and port, the user journeys (steps, and whether they write data), the steady state (success rate and p95), and how to measure the application (ADR-0026). The agent reads it.
- **The RoE, security or operations:** scope (namespaces), the highest level, whether write journeys and node actions are allowed, protected workloads, denied API groups, how many experiments and how long a change may stay. Every optional setting defaults to the safe value: an RoE that says nothing allows nothing extra.
- **The chart values, the cluster admin:** which namespaces the servers may touch at all, which levels are deployed, and the probe's caps.

Each is checked before a run starts; a malformed file stops the run with a message that names the file and the setting.

## Consequences
- **Gains:** each owner edits only what they know; a security review reads the RoE alone; the same target works under different RoEs (a lab RoE and a production RoE).
- **Trade-offs:** three files to keep consistent: a target can ask for a rate the chart caps lower, or an RoE can allow a hold longer than the probe's longest run; today that is found only at the first measurement (follow-up: a `get_limits` observe tool).

## In the code
- `orchestrator/run_config.py`: `load_target`, `load_roe`, `ROE_DEFAULTS`, `MEASUREMENT_DEFAULTS`.
- `lab/apps/boutique/target.yaml`, `lab/apps/boutique/roe.yaml`: the lab's two files, with comments for every setting.
- `charts/chaos-agent/values.yaml`: `mcp.allowedNamespaces`, `mcp.levels`, `mcp.levels.probe.limits`.
