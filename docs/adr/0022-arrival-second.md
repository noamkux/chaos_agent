# ADR-0022: Results are counted by the second a user arrived, not the second they finished

**Status:** Accepted, 2026-11-26
**Related:** ADR-0021 (k6), ADR-0023 (the judge)

## Context
A user who arrives during an outage can wait up to the request timeout (10 s by default) before failing. Every result has two times: when the user arrived and when they finished. The question: which second does a result belong to?

## Options
1. **The second it finished** (k6's own timestamp). Free. But every failure is shifted by up to the timeout: with a change restored after 20 s, users who failed because of the outage would be counted after the restore, and the judge would see a longer outage and a later recovery than really happened.
2. **The second it arrived,** tagged by the journey script when the user starts.

## Decision
Option 2. `run` in `journeys.js` computes the arrival second from `exec.scenario.startTime` and tags every journey metric with it; `summarize` buckets by that tag. A result shows the state of the system at the moment the user met it.

## Consequences
- **Gains:** outages start and end where they really did; recovery is measured from the restore, not from when the last stuck user gave up.
- **Trade-offs:** the last seconds of a measurement fill in late (a user who arrived in the last second is still waiting). A user started just after the end can be tagged with a second past `measure_for_s`; the judge reads only `range(measure_for_s)`, so it is ignored (seen in the run of 2026-11-27).

## In the code
- `servers/mcp/journeys.js`: `run`, the `second` tag.
- `servers/mcp/probe.py`: `summarize`, bucketing by `tags["second"]`.
- `orchestrator/experiment.py`: `statuses_of`, `range(measurement["measure_for_s"])`.
