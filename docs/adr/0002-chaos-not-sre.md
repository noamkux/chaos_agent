# ADR-0002: The goal is chaos engineering, not SRE reporting

**Status:** Accepted, 2026-11-26
**Related:** ADR-0011 (deterministic or agent), ADR-0013 (the checks catalog, superseded), ADR-0014 (no catalog)

## Context
The first version of the agent read the cluster's configuration and reported findings such as "this Deployment has no PodDisruptionBudget" or "this Secret is in an env variable". It worked, but the mentor pointed out that the project was drifting into SRE: a report of configuration gaps that a static checker (kube-score, Polaris, Kubescape) already produces, with an LLM in the middle. A script could do it; the AI added little.

The question: what is the agent for?

## Options
1. **Configuration review (SRE report).** Read the manifests and list what is missing. Cheap, safe, and fast. But it only finds what someone thought to check, and it does not prove that a gap matters to users: a missing PDB is a problem only if a drain actually hurts.
2. **Chaos engineering.** The agent gets the cluster's components and, by its own judgment, breaks, changes and takes things down within the Rules of Engagement, then measures whether the system withstands it. Slower and riskier, but every finding is proven by an experiment, and it can find weaknesses nobody wrote a check for.
3. **Both, equally.** Keeps everything already built. But splits the time between two products, three days before the deadline, and leaves the agent's core value unclear.

## Decision
Option 2. The core loop is: hypothesis, one change, measure what users see, judge, follow up. Observation is an input to that loop (the agent needs to know what exists), not a product of its own. There are no reports of the form "has a PDB or not".

## Consequences
- **Gains:** a clear answer to "why an agent": choosing which experiment to run next, from the results of the last one, is judgment a script does not have. Every finding comes with evidence (the steps of the experiment that proved it).
- **Trade-offs:** the work already done on static checks (the catalog, report_finding, the findings table, the first eval) was removed. Every run now changes the system under test, which needs a safety model (ADR-0015 to ADR-0019) that a read-only report never needed.
- **Not solved:** whether the agent actually finds more than a deterministic sweep of the same actions. That is what the eval must show (ADR-0032).

## In the code
- `orchestrator/agent.py`: `SYSTEM_PROMPT` (the chaos engineering method) and `run_agent`.
- `orchestrator/runner.py`: `run_experiment`, the only tool the model has.
- Commit `393037e`: the removal of the catalog and of report_finding.
