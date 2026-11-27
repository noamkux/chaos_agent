# ADR-0012: Discovery is done by the orchestrator, returns raw facts, and names kinds as group/Kind

**Status:** Accepted, 2026-11-26
**Related:** ADR-0003 (any cluster), ADR-0010 (orchestrator calls every tool), ADR-0029 (env values never leave)

## Context
The agent needs to know what exists in the namespaces it tests and how each workload is configured. Three questions came up:
1. Who calls the discovery tools: the model, or the orchestrator?
2. What do the tools return: conclusions (`has_pdb: false`) or facts?
3. How are kinds named, so the inventory, the RoE and the disrupt tools agree?

And one more: should the orchestrator read the cluster directly, without an MCP server?

## Options
**Who calls:**
1. **The model**, when it wants. It may skip discovery, or read part of it, and then reason about things it never looked at.
2. **The orchestrator**, once per namespace, before the first LLM call, with the results and their step numbers in the prompt.

**Direct access:** giving the orchestrator its own Kubernetes credentials would be simpler, but every cluster access today goes through an MCP server with its own ServiceAccount; a second path would bypass that model.

**What is returned:**
1. **Booleans** (`has_readiness_probe`, `single_replica`). Small, but each is a check we wrote, and the agent sees only what we thought to check.
2. **Raw facts with Kubernetes field names**: every container's resources and probes, affinity, topology spread, env variable names and where each value comes from (never the value).

**Kind names:**
1. `apiVersion/kind` (`apps/v1/Deployment`): versions change between clusters.
2. `group/Kind` without version (`apps/Deployment`, `core/Service`).

## Decision
- **The orchestrator calls `observe__get_inventory` and `observe__get_workloads`** before the first LLM call, through `call_tool`, so they are recorded as steps. The model cites those steps as evidence of what exists.
- **The inventory lists every kind the API server can list,** CRDs included, except kinds that controllers create and that change all the time (Pods, ReplicaSets, Endpoints, Events, Leases) and Secrets. Kinds it could not read are reported as unreadable; a run fails if a required kind (Deployment, StatefulSet, DaemonSet, Service) is unreadable.
- **Workloads are returned as facts,** with the rules for reading them in the prompt ("a field that is left out is not set").
- **Kinds are always `group/Kind`,** in the inventory, the RoE and the disrupt tools.
- No direct cluster access from the orchestrator; no kube-score or similar.

## Consequences
- **Gains:** discovery is complete and identical in every run; the agent sees configuration it can reason about freely; names match across every component.
- **Trade-offs:** the prompt grows with the size of the namespace (a large application means a long inventory; no summarization yet). Facts are more tokens than booleans. Pod placement (which node, which zone) is not included yet, which is why the agent cannot find W1 (ADR-0030 adds it).

## In the code
- `servers/mcp/k8s.py`: `SKIPPED_KINDS`, `namespaced_kinds`, `listable_kinds`, `get_inventory`, `get_workloads`, `CONTAINER_FIELDS`, `POD_FIELDS`, `env_facts`.
- `orchestrator/agent.py`: `collect`, `discover_inventory`, `REQUIRED_KINDS`, `collect_workloads`, and the field rules in `RUN_SECTION`.
