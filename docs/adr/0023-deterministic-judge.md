# ADR-0023: A deterministic judge decides broke, withstood or inconclusive, second by second

**Status:** Accepted, 2026-11-26 (before_action added 2026-11-27)
**Related:** ADR-0011 (deterministic or agent), ADR-0021 (k6), ADR-0024 (warm-up), ADR-0025 (steady check)

## Context
After an experiment we have, for every journey and every second, how many users succeeded and failed and how slow they were. Someone must decide whether the system broke. Two questions: who decides, and how is the result shown to the model?

## Options
**Who decides:**
1. **The model**, reading the numbers. Flexible, but it can decide the system broke because it expected it to; verdicts would differ between runs of the same data.
2. **Code, against the steady state in `target.yaml`.** Reproducible, and the model cannot argue with it.

**How the result is shown:**
1. **The raw per-second results.** Hundreds of lines of JSON per experiment, in every following prompt.
2. **A timeline of one character per second,** plus totals before and after the change. A minute of seconds fits in one short line, for a few dozen tokens.

## Decision
Code decides, in `experiment.py`:
- **Every second of every journey gets a status:** `fail` if the success rate is below `steady_state.success_rate`, `slow` if everything succeeded but p95 is above `steady_state.p95_ms`, `no_data` if nobody arrived, otherwise `ok`. Success comes first: a second with failures is `fail` whatever its p95.
- **inconclusive** if any second before the action, in the steady check or in the measurement, was not `ok`: the result cannot be told apart from what was already there. It shows the timelines of both, `baseline` and `before_action`, so the model can see why.
- **broke** if, after the action, at least `MIN_BROKEN_S` (2) seconds were not `ok`, or any user could not be sent, or the journey had not recovered by the end of the measurement.
- **withstood** otherwise.
- **Recovery** is the first second from which every second to the end is `ok`, counted from the restore for a patch and from the action for a deleted pod.

**`MIN_BROKEN_S = 2`:** a single bad second can be noise (a garbage collection pause, one slow request); two or more is a finding.

**The timeline:** `.` ok, `s` slow, `x` failed, `_` no data, and `|` before the second of the action and of the restore, for example `.....|xxxxxxxxxxxx|ss....`.

The model gets the verdict, the timeline, the totals before and after (success, worst p95, errors by type), the broken seconds, users not sent, and the recovery time. It adds the interpretation: why it broke, and what to test next.

## Consequences
- **Gains:** the same data always gives the same verdict; the eval can compare runs; the model's context stays small.
- **Trade-offs:** the verdict is only as good as the steady state in `target.yaml`. A threshold that is loose for the system's normal (500 ms against a normal 10 to 20 ms) lets a degraded system pass as steady: in the run of 2026-11-27, step 49 started on a system at 270 ms and was inconclusive (follow-up: a steady check that also compares to the system's own normal). `MIN_BROKEN_S` is a fixed constant, not per application.

## In the code
- `orchestrator/experiment.py`: `TIMELINE_CHARS`, `MIN_BROKEN_S`, `status_of`, `statuses_of`, `timeline`, `phase`, `recovered_at`, `judge`.
- `orchestrator/runner.py`: `second_of` (which second of the measurement the action fell in) and the call to `experiment.judge` in `run_experiment`.
