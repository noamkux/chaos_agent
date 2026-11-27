# ADR-0011: Collection, tools, safety and judging are deterministic; the agent plans and interprets

**Status:** Accepted, 2026-11-26
**Related:** ADR-0002 (chaos), ADR-0010 (orchestrator calls every tool), ADR-0023 (the judge), ADR-0032 (eval)

## Context
After the first runs, the agent felt too deterministic: it read configurations and listed gaps, which a script could do. The opposite risk is just as real: an LLM that decides whether the system broke can decide it broke because it expected it to. The question: which parts of a run should be the model's, and which code?

## Options
1. **The model does everything:** collects facts, runs tools, judges results, writes the report. Simple to build, hard to trust, and the most expensive in tokens.
2. **Deterministic where an answer can be computed, the model where judgment is needed.**
3. **No model at all:** a deterministic sweep of every action on every component. Reproducible and cheap per decision, but it only runs what was enumerated, and it does not adapt to what it finds.

## Decision
Option 2.
- **Deterministic:** collecting facts (inventory, workload facts), running tools, every safety rule (RoE, scope, denylist, protected workloads, caps), the order of an experiment, measuring, and judging (broke, withstood, inconclusive).
- **The agent:** choosing what to break and how, forming the hypothesis, reading the timeline and the errors, following up on surprises, deciding when a finding is reproduced, and writing the summary.

Option 3 is not rejected: it is the eval's baseline (ADR-0032). If the agent does not beat a deterministic sweep on findings per experiment, that is a valid result.

## Consequences
- **Gains:** the verdict cannot be argued by the model; facts in the prompt are complete and citable; the model's tokens go to the part only it can do.
- **Trade-offs:** the model can only act through what the orchestrator implements; a capability the agent "would" use must be built first.
- **Not solved:** whether disrupt justifies an LLM is an empirical question, answered by the eval, not by this record.

## In the code
- `orchestrator/agent.py`: `discover_inventory`, `collect_workloads` (deterministic collection), `SYSTEM_PROMPT` (what the agent does).
- `orchestrator/runner.py`: `check` and `run_experiment` (deterministic execution).
- `orchestrator/experiment.py`: `judge` (deterministic verdict).
