# ADR-0003: The agent must work on any application, on any cluster

**Status:** Accepted, 2026-11-26
**Related:** ADR-0004 (the lab), ADR-0020 (three inputs, three owners), ADR-0026 (measurement settings)

## Context
The lab runs one application, Online Boutique, on one kind cluster. Every shortcut that only works there ("Online Boutique doesn't use CRDs", "the frontend is always on port 80", "the cluster domain is cluster.local") would make the agent a demo for one app. The question: how far do we design beyond the lab?

## Options
1. **Build for the lab, generalize later.** Fastest to a working demo. But shortcuts end up everywhere, and generalizing later means rewriting the parts that matter most (discovery, measurement, permissions).
2. **Design every decision for any application and any cluster, and use the lab only to test.** Slower per decision. But the agent is a product from the start, and the lab is a test case, not the target.

## Decision
Option 2. Concretely:
- **Nothing about Online Boutique is in the code.** What the application is (its entrypoint, journeys, steady state, measurement settings) comes from `target.yaml`; what the agent may do comes from the RoE. The lab has its own copies in `lab/apps/boutique/`.
- **Discovery lists every kind the API server can list,** CRDs included, instead of a fixed list (ADR-0012).
- **The disrupt server may change any kind** except a short denylist (ADR-0016).
- **Measurement needs nothing installed in the customer's cluster** beyond our chart: k6 runs inside the probe pod (ADR-0021).
- **Kubernetes conventions over lab facts:** zones are read from the standard `topology.kubernetes.io/zone` label, Services are addressed as `<service>.<namespace>.svc` so a cluster domain other than `cluster.local` works.
- **"The lab doesn't use it" is never a reason to leave something out.**

## Consequences
- **Gains:** the same chart and code run on kind, EKS or any conformant cluster; a new application needs only its `target.yaml` and an RoE.
- **Trade-offs:** more validation and more general code than the lab needs (for example the merge patch fallback for CRDs, which Online Boutique never exercises). Some features are harder to test in the lab, since it cannot show what it does not contain.
- **Not solved:** cluster-specific failures that the Kubernetes API cannot simulate (a node that dies without warning, a cloud zone outage): they need cloud tools such as AWS FIS, and are in the backlog.

## In the code
- `orchestrator/run_config.py`: `load_target` and `load_roe`, the only way the application and the rules enter a run.
- `servers/mcp/k8s.py`: `namespaced_kinds` and `listable_kinds` (every kind the API server lists).
- `servers/mcp/probe.py`: `service_url` (`.svc` addressing).
- `lab/apps/boutique/target.yaml` and `lab/apps/boutique/roe.yaml`: the lab's inputs, kept outside the code.
