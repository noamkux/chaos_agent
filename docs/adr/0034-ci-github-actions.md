# ADR-0034: GitHub Actions runs the cheap checks on every change

**Status:** Proposed, 2026-11-26
**Related:** ADR-0028 (image hardening), ADR-0032 (eval)

## Context
Every change to the agent can break it in ways that only show up in a 20-minute run against the lab. CI is a course requirement. The question: what runs on every change, and what does not?

## Options
1. **The full eval on every pull request** (kind on the runner, a run with the model). The strongest signal; slow, flaky on shared runners, and it costs tokens on every push.
2. **The cheap, deterministic checks on every change; the eval on demand.**

## Decision
Option 2. On every push and pull request:
- **Lint:** pyflakes on `orchestrator/` and `servers/mcp/`.
- **Unit tests** for the deterministic parts: `run_config` (loading and validation), `experiment` (statuses, timeline, verdicts), `runner.check`, `probe.summarize` and `concurrent_users`, `disrupt.forbidden_fields` and `clean`.
- **The chart:** `helm lint` and `helm template` with the lab values.
- **The image:** build, push by digest, and a Trivy scan that fails on high or critical vulnerabilities.

## Consequences
- **Gains:** most regressions (a broken validation, a template that does not render, a vulnerable dependency) are caught in minutes, for free.
- **Trade-offs:** CI does not prove that the agent still finds things; that stays a manual eval run until it can run on a schedule.

## In the code
- Not built yet. Planned: `.github/workflows/`. Today the manual checks live in `orchestrator/tests/` and `servers/mcp/tests/`.
