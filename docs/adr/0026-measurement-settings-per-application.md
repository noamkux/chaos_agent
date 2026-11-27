# ADR-0026: Measurement settings belong to the application, caps to the cluster

**Status:** Accepted, 2026-11-27
**Related:** ADR-0003 (any application), ADR-0020 (owners), ADR-0021 (k6), ADR-0025 (steady check)

## Context
Every timing and rate of a measurement was a constant in the code: the warm-up, the steady check, the seconds before the action and after the restore, the rate (`runner.py`), and the request timeout and the number of virtual users (`probe.py`). These depend on the application. In the lab, payment recovers 25 s after a restore, so a 30 s recovery window barely fits; an application with a 60 s readiness probe would always look broken. A JVM service may need 30 s to warm up. Customers had no way to change any of them, which breaks ADR-0003.

## Options
1. **Keep the constants and pick conservative values.** Nothing to build. Long windows on every experiment, still wrong for some applications.
2. **Everything in the RoE.** One file to edit. But the RoE says what the agent may do, and is written by security. How long an application takes to recover is not a permission, and security would have to know the application to write it.
3. **Let the model choose them per experiment.** Most flexible. But whoever controls the recovery window controls what the judge sees: the same problem as letting the agent write its own journeys.
4. **Split by owner:** timings and rate in `target.yaml` (the application team), safety caps in the chart values (the cluster admin), and the number of concurrent users computed by the probe server.

## Decision
Option 4.
- **`target.yaml` gets an optional `measurement` section:** `new_users_per_second`, `fail_request_after_s`, `warmup_ignored_s`, `steady_check_s`, `steady_check_attempts`, `wait_between_steady_checks_s`, `measure_before_action_s` and `measure_after_restore_s`. Every setting has the old constant as its default, so a target without the section behaves as before. Unknown settings are rejected (a typo would otherwise be ignored silently), and two have minimums the judge needs: `steady_check_s` at least 5, `measure_before_action_s` at least 3.
- **The chart sets four caps on the probe server,** `mcp.levels.probe.limits`, passed as environment variables: `LONGEST_K6_RUN_S`, `LONGEST_REQUEST_WAIT_S`, `MAX_NEW_USERS_PER_SECOND` and `MAX_CONCURRENT_USERS_PER_JOURNEY`. The server refuses any measurement over them.
- **The number of concurrent users is not a setting:** the probe computes it per journey as `new_users_per_second × fail_request_after_s × steps` (Little's law, the worst case where every step waits until it fails), capped by `MAX_CONCURRENT_USERS_PER_JOURNEY`.
- **Names say what the value does and keep the unit suffix:** `fail_request_after_s`, not `timeout_s`; `measure_after_restore_s`, not `recovery_s`; `LONGEST_K6_RUN_S`, not `MAX_DURATION_S`. In the same change, `hold_s` became `restore_after_s` (and `max_hold_s` became `max_restore_after_s`), and `duration_s` became `measure_for_s`.

## Consequences
- **Gains:** each application is measured on its own terms; the cluster stays protected whatever a target asks for; a customer sets what they understand (rate and timeout), not a k6 internal; the lab target documents every setting.
- **Trade-offs:** more to validate when a target is loaded. The orchestrator does not know the chart's caps, so a target over them fails at the first measurement, not when it is loaded. Past the concurrency cap, users are reported as not sent: what real users would meet, but it makes the cap part of the result.
- **Not solved:** rates below 1 per second (k6 supports them through `timeUnit`, which would change the per-second judging).

## In the code
- `orchestrator/run_config.py`: `MEASUREMENT_DEFAULTS`, `MEASUREMENT_MINIMUMS`, and the `measurement` checks at the end of `load_target`.
- `orchestrator/runner.py`: `run_experiment` (`settings = target["measurement"]`, `measure`) and `wait_for_steady`.
- `servers/mcp/probe.py`: the caps at the top, `concurrent_users`, and the checks in `measure_journeys`.
- `servers/mcp/journeys.js`: `options.scenarios` (`rate`, `duration`, `preAllocatedVUs`, `maxVUs`, `gracefulStop`) and the request `timeout` in `run`.
- `charts/chaos-agent/values.yaml`: `mcp.levels.probe.limits`; `charts/chaos-agent/templates/mcp.yaml`: the `with $config.limits` env block.
- `lab/apps/boutique/target.yaml`: the `measurement` section, every setting with its default.

## Follow-ups
- A `get_limits` observe tool, so a run can reject a target over the caps before it starts.
