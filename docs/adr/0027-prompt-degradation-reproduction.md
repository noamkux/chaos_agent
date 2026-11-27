# ADR-0027: The prompt steers toward degradation, reproduction, and citing steps

**Status:** Accepted, 2026-11-27
**Related:** ADR-0014 (no catalog), ADR-0023 (the judge), ADR-0025 (not_run)

## Context
The first disrupt run (2026-11-26, 13 experiments) showed four problems in how the agent worked:
1. **No variety:** almost only `replicas: 0`, annotations and pod deletions. Scaling a dependency to 0 always breaks its callers, so it teaches little after the first time.
2. **No reproduction:** a surprising result ("email down slows every journey") was reported as a finding after one run.
3. **Citations by experiment number,** not by step, so the summary could not be checked against the audit. The cause was in the code: `run_experiment` never returned its own step.
4. **`not_run` and `inconclusive` were new** and the agent did not know what they mean.

## Options
1. **Restrict the actions** (forbid scaling to 0). Forces variety, but bans a legitimate experiment: a dependency that is down for every caller (after a bad deploy or a failed shared dependency) tests whether the callers have timeouts and fallbacks.
2. **Teach the method in the prompt, and fix the code where the model lacked information.**

## Decision
Option 2.
- **Degradation:** scale a component to 0 at most once, to map which journeys depend on it; then prefer partial changes (fewer replicas, one pod deleted, tighter CPU or memory limits, a slower or stricter readiness probe), because weaknesses users feel are usually in how a system behaves when a dependency is slow or partly down.
- **Rollouts:** a change to a pod template restarts all its pods, and that rollout is part of what is measured.
- **Reproduction:** a result the agent did not expect is not a finding until it is reproduced once; a weakness seen once is reported as unconfirmed, even when it looks like a confirmed one.
- **`not_run` and `inconclusive`** explained, with what each says about recovery.
- **Citations by step,** and `run_experiment` now returns its own `step`.
- **The summary:** confirmed weaknesses (with the steps that showed and reproduced them, which journeys, how they failed, for how long, and the recovery), unconfirmed, what held, and what to test next.

## Consequences
- **Gains:** in the run of 2026-11-27 there were no scale-to-zero experiments, two findings were reproduced (productcatalog, shipping), every experiment was cited by step, and the hidden cart-to-shipping coupling was reported with a clear note that the call path was inferred.
- **Trade-offs:** reproduction costs experiments from the budget. The prompt still cannot make the agent test what it has no tool for (zones, latency): that needs ADR-0030 and Chaos Mesh. A later version should name the real-world event each experiment simulates (a node failing, a zone going down, a bad rollout).

## In the code
- `orchestrator/agent.py`: `SYSTEM_PROMPT`, the Method bullets and the summary structure; `format_profile` (the measurement line, so the model knows a 10 s timeout is ours).
- `orchestrator/runner.py`: `finish` in `run_experiment` returns `{"step": step, ...}`.
