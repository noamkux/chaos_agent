# ADR-0014: No catalog: the agent invents its own experiments

**Status:** Accepted, 2026-11-26
**Supersedes:** ADR-0013
**Related:** ADR-0002 (chaos), ADR-0015 (generic disrupt tools), ADR-0027 (prompt)

## Context
With the catalog removed (ADR-0013), the agent needs another way to decide what to test. The question: how much structure do we give it?

## Options
1. **A catalog of experiments** (instead of checks): "kill one pod of every Deployment", "scale every dependency to 0". Predictable, but the same menu problem.
2. **A method, not a list:** the agent gets the facts and a chaos engineering method (hypothesis, one change, read the timeline, follow up), and designs every experiment itself, limited only by the Rules of Engagement.

## Decision
Option 2. The prompt teaches the method; the facts come from discovery; the experiments are the agent's. What it may do is limited by damage limits (scope, denylist, protected workloads, caps, the restore), not by a list of allowed actions.

## Consequences
- **Gains:** the agent can find weaknesses that were never written down. In the run of 2026-11-26 it found a hidden coupling (cart depends on shipping) that was in no manifest and no ground truth.
- **Trade-offs:** less predictable runs; quality depends on the prompt and the model. In the first run the agent mostly scaled things to 0, which always breaks and teaches little; the prompt had to steer it toward partial changes (ADR-0027). Measuring "coverage" is harder without a list: the eval compares outcomes, not checklists (ADR-0032).

## In the code
- `orchestrator/agent.py`: `SYSTEM_PROMPT`, the Method section.
- `orchestrator/runner.py`: `run_experiment_tool`, the generic action schema.
