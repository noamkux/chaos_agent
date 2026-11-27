# ADR-0025: A steady check before every experiment; an experiment that never gets steady is not run and not counted

**Status:** Accepted, 2026-11-27
**Related:** ADR-0023 (the judge), ADR-0024 (warm-up), ADR-0027 (prompt)

## Context
An experiment run on a system that is already broken proves nothing: the result cannot be told apart from what was already there. In the first disrupt run (2026-11-26), 3 of 13 experiments were inconclusive because the system had not recovered from the one before (payment takes 25 s after a restore), and each of them used up one experiment of the budget while nothing had been learned.

The question: what happens when the system is not steady before an experiment?

## Options
1. **Run anyway, and let the judge say inconclusive.** Simple, but wastes budget, and makes a change on a system that is already disturbed.
2. **Make the recovery window longer for every experiment.** Fixes the slow recoveries, but every experiment pays for it, including those that recover in 2 s.
3. **Check before every experiment, and wait and retry when the check fails;** touch nothing and count nothing until the system is steady.

## Decision
Option 3. `wait_for_steady` measures `warmup_ignored_s + steady_check_s`, and accepts the system only if every second of every chosen journey is `ok`. If not, it waits `wait_between_steady_checks_s` and tries again, up to `steady_check_attempts` times.
- **Steady:** the experiment is counted, and the steady check becomes its baseline.
- **Never steady:** the result is `not_run` with `counted: false`, the reason and the timelines of the last try. Nothing is changed.
- The tool description and the prompt explain the difference: `not_run` means nothing was changed and nothing counted; `inconclusive` means the change was made and counted, but the seconds just before it were not steady. A `not_run` right after the agent's own experiment is itself a finding about recovery.

## Consequences
- **Gains:** the budget is spent only on experiments that can be judged; a slow recovery shows up as a finding instead of a wasted experiment.
- **Trade-offs:** an unsteady system can cost up to `steady_check_attempts × (warm-up + steady check) + (attempts - 1) × wait` before giving up (about two minutes with the defaults). A `not_run` does not count, so a system that is never steady could let the model call `run_experiment` until `MAX_ITERATIONS`: accepted, since that limit stops it.
- **Not solved:** the check compares to the steady state's thresholds, not to the system's own normal, so a degraded system under the threshold passes (ADR-0023).

## In the code
- `orchestrator/runner.py`: `wait_for_steady`; step 1 of `run_experiment` (`state["experiments"] += 1` only after a steady check); the `not_run` and `inconclusive` sentences in `run_experiment_tool`.
- `orchestrator/run_config.py`: `steady_check_s`, `steady_check_attempts`, `wait_between_steady_checks_s` in `MEASUREMENT_DEFAULTS`, and the minimum for `steady_check_s`.
- `orchestrator/agent.py`: the `not_run` and `inconclusive` bullets in `SYSTEM_PROMPT`.
- `orchestrator/tests/try_experiment.py`: one fixed experiment through the runner, without the model.
