# ADR-0024: The warm-up of every measurement is thrown away before judging

**Status:** Accepted, 2026-11-26 (extended to the experiment measurement 2026-11-27)
**Related:** ADR-0023 (the judge), ADR-0025 (steady check), ADR-0026 (measurement settings)

## Context
Two things make the first seconds of a measurement slow for reasons that have nothing to do with the experiment:
- **The application after idle:** in Online Boutique the first request after a quiet period can wait about 10 s.
- **A new run of k6 starts cold:** new TCP connections, virtual users just allocated. In the run of 2026-11-27, steps 65 and 70 had a second 0 at 595 to 945 ms and 10 to 20 ms right after.

At first only the steady check threw its warm-up away. The experiment measurement did not, so a cold second 0 was judged as "not steady before the action", and three of fifteen experiments were wasted as inconclusive while the pod had already been deleted.

## Options
1. **Discard nothing.** Every first second risks a false inconclusive.
2. **Warm the connections in k6's `setup()`.** `setup` runs once per run of k6, but connections belong to each virtual user, so the users still start cold.
3. **Measure `warmup_ignored_s` extra seconds at the start of every measurement, and drop them before judging,** in the steady check and in the experiment measurement alike.

## Decision
Option 3. Every measurement starts `warmup_ignored_s` seconds earlier; the runner waits for them before the action; `without_warmup` removes them, renumbers the seconds from 0, and moves `started_at` by the same amount, so `second_of` still marks the action in the right second.

## Consequences
- **Gains:** a cold start is never judged; inconclusive means the system was really not steady.
- **Trade-offs:** each experiment is `warmup_ignored_s` seconds longer (5 by default), and the warm-up of the experiment measurement adds to the time a change is measured before it is made, not to the disruption.

## In the code
- `orchestrator/runner.py`: `without_warmup`, `wait_for_steady`, and the `warmup` lines in step 2 and step 4 of `run_experiment`.
- `orchestrator/run_config.py`: `warmup_ignored_s` in `MEASUREMENT_DEFAULTS`.
