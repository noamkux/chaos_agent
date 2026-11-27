# ADR-0021: Steady state is measured from user journeys, by k6 running inside the probe pod at a constant arrival rate

**Status:** Accepted, 2026-11-26
**Related:** ADR-0022 (arrival second), ADR-0023 (the judge), ADR-0026 (measurement settings)

## Context
Every experiment needs a measurement of what users see before, during and after the change. Three questions:
1. What is measured: pod status, metrics, or user requests?
2. With what tool, and where does it run?
3. How do we avoid the measurement slowing down with the system it measures?

## Options
**What is measured:**
1. **Pod and Deployment status.** Says the pods are Running, not that users are served.
2. **The customer's metrics (Prometheus, Datadog).** Real traffic, but depends on what each customer has and how it is labeled.
3. **Synthetic user journeys at the entrypoint**, defined in `target.yaml`: works on every cluster.

**The first attempt, a request loop in the orchestrator** (one MCP call per request) had two problems: resolution (an experiment of 60 s at 2 per second is 120 steps), and, more important, **coordinated omission**: a loop that waits for each answer sends one request in 20 s when the system is stuck, and measures "failed once" instead of "every user stuck for 20 s".

**The tool and where it runs:**
1. **k6 as a binary inside the probe server's pod, run as a subprocess.** Nothing to install in the customer's cluster; starts in under a second, so the timing against the action is accurate; one image to copy into an air-gapped registry.
2. **A k6 Job per measurement** (like Litmus's helper pod). Better isolation, but needs permission to create Jobs and takes seconds to start.
3. **k6-operator.** Installs a CRD and needs admin to install; built for heavy distributed load, not for measurement.
4. **A Python load library (Locust).** Closed model by default, so the same coordinated omission problem.

This matches how chaos tools measure steady state: Litmus's continuous httpProbe, Chaos Mesh's StatusCheck, Gremlin's status checks, and Steadybit and Litmus running k6 in the cluster during faults.

## Decision
- **Synthetic journeys at the entrypoint,** from `target.yaml`, measured continuously through the whole experiment in one call (`measure_journeys`), in the background while the runner makes the change.
- **k6 inside the probe pod** (option 1), copied from its official image pinned by digest.
- **The open model:** k6's `constant-arrival-rate` executor, one scenario per journey, so a stuck journey cannot slow the measurement, and one journey's stuck users cannot take another journey's virtual users. Users k6 could not start are reported as `not_sent`.
- **A new cookie jar per user,** so every iteration is a new session.
- **Success by status code,** after following redirects; a step that fails ends the journey.
- **The probe server only counts; it never judges.** Judging stays in the orchestrator (ADR-0023).

## Consequences
- **Gains:** works on any cluster with nothing installed; measures what users feel; a stuck system looks stuck.
- **Trade-offs:** synthetic traffic, not real users. Success by status code only: a `200` page that says "something went wrong" counts as success (follow-up: an expected text per step, checked only for those requests). Response bodies are discarded to save memory, which is also why. One pod cannot generate heavy load: load experiments may need a Job or the operator later.

## In the code
- `servers/mcp/probe.py`: `measure_journeys`, `run_k6`, `summarize`.
- `servers/mcp/journeys.js`: `options.scenarios` (`constant-arrival-rate`, one per journey), `run`.
- `servers/mcp/Dockerfile`: `COPY --from=k6`.
- `orchestrator/runner.py`: the background `measuring` task in `run_experiment`.
