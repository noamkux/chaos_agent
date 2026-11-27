# ADR-0032: The eval compares the agent with a deterministic baseline, on a weak and a hardened application

**Status:** Proposed, 2026-11-26
**Related:** ADR-0004 (lab and ground truth), ADR-0011 (deterministic or agent), ADR-0014 (no catalog)

## Context
Without the catalog there is no checklist to score coverage against. And the honest question about this project is whether the agent finds more than a script would (ADR-0011). The eval must answer it with numbers.

## Options
1. **Score findings against the ground truth only.** Says what the agent found, not whether an agent was needed.
2. **Compare the agent with a deterministic baseline:** a matrix that runs every action on every component, scored on the same measures.
3. **An LLM judge of the summaries.** Useful for wording, but an LLM grading an LLM is the weakest kind of evidence; it is not the main measure.

## Decision
Option 2, with:
- **A ground truth rewritten by action and impact** ("deleting a pod of checkoutservice breaks checkout for about 22 s"), not by check and component. W3 at 200m; the stall after idle stays out on purpose.
- **Measures:** findings (confirmed against the ground truth, and unknown ones), number of experiments, total disruption time, and RoE violations (must be zero).
- **A control group, `boutique-hardened`:** a Kustomize overlay with 3 replicas, PDBs, topology spread, preStop hooks and tuned probes. Expected: mostly withstood. Every `broke` there is an unknown weakness, or a false positive to investigate.
- **podinfo** as a second, simple target. The OpenTelemetry demo with flagd only as a stretch (heavy for the lab's disk).

## Consequences
- **Gains:** a direct answer to "does the agent justify itself"; regressions in the prompt or the judge show up as numbers.
- **Trade-offs:** a full eval is several runs of 20 minutes each on a laptop, and costs tokens; it cannot run on every commit (CI runs the cheap parts, ADR-0034). Runs vary, so one run per configuration is weak evidence.

## In the code
- Not built yet. Today: `lab/apps/boutique/ground_truth.yaml` (catalog-era format), `orchestrator/tests/try_agent.py` (one run with its tables).
