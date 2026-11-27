# Architecture Decision Records

Every architectural decision of the Chaos Agent, with the question it answered, the options that were considered, what was chosen, what it costs, and where it lives in the code. Format and rules: [ADR-0001](0001-record-architecture-decisions.md).

A record is never deleted. When a decision changes, a new record supersedes it, and the old one stays as history.

**Status:** Accepted (in the code), Proposed (decided, not built yet), Superseded (replaced by a later record).

## Goal and scope

| # | Decision | Status |
|---|---|---|
| [0001](0001-record-architecture-decisions.md) | Record architecture decisions | Accepted |
| [0002](0002-chaos-not-sre.md) | The goal is chaos engineering, not SRE reporting | Accepted |
| [0003](0003-any-application-any-cluster.md) | The agent must work on any application, on any cluster | Accepted |
| [0004](0004-lab-online-boutique.md) | The lab: Online Boutique on kind, with planted weaknesses and a ground truth | Accepted |
| [0005](0005-helm-chart-product.md) | The product is a Helm chart, and the lab installs it like a customer | Accepted |
| [0006](0006-postgres-run-store.md) | Postgres holds runs, every step, and the undo log | Accepted |

## The agent and its tools

| # | Decision | Status |
|---|---|---|
| [0007](0007-agent-loop-from-scratch.md) | The agent loop is written on the Claude API, without an agent framework | Accepted |
| [0008](0008-mcp-server-per-level.md) | One MCP server codebase, deployed once per level, each with its own ServiceAccount | Accepted |
| [0009](0009-levels-are-permission-boundaries.md) | observe, probe and disrupt are permission boundaries, not "AI or not" | Accepted |
| [0010](0010-orchestrator-calls-every-tool.md) | The orchestrator calls every MCP tool; the model's only tool is run_experiment | Accepted |
| [0011](0011-deterministic-or-agent.md) | Collection, tools, safety and judging are deterministic; the agent plans and interprets | Accepted |
| [0012](0012-discovery-by-the-orchestrator.md) | Discovery is done by the orchestrator, returns raw facts, and names kinds as group/Kind | Accepted |
| [0013](0013-checks-catalog.md) | A checks catalog the agent works through | Superseded by 0014 |
| [0014](0014-no-catalog.md) | No catalog: the agent invents its own experiments | Accepted |
| [0027](0027-prompt-degradation-reproduction.md) | The prompt steers toward degradation, reproduction, and citing steps | Accepted |

## Safety

| # | Decision | Status |
|---|---|---|
| [0015](0015-generic-disrupt-tools.md) | A few generic disrupt tools instead of a tool per fault | Accepted |
| [0016](0016-denylist-enforced-twice.md) | A denylist, not an allowlist, enforced in the server and in the API server | Accepted |
| [0017](0017-snapshots-and-write-ahead-undo.md) | Snapshots are Secrets in chaos-system, restored by replace, with a write-ahead undo log | Accepted |
| [0018](0018-deny-groups.md) | API groups whose controllers act outside the namespace are denied by default | Accepted |
| [0019](0019-protected-workloads.md) | Data stores are protected only through protected_workloads in the RoE | Accepted |
| [0020](0020-three-inputs-three-owners.md) | Three inputs with three owners: target.yaml, the RoE, and the chart values | Accepted |
| [0028](0028-image-and-pod-hardening.md) | The MCP image and pods are locked down: pinned digests, hashed dependencies, non-root, read-only | Accepted |
| [0029](0029-env-values-never-leave.md) | Env values and Secrets never leave the MCP servers | Accepted |

## Measuring and judging

| # | Decision | Status |
|---|---|---|
| [0021](0021-k6-in-the-probe-pod.md) | Steady state is measured from user journeys, by k6 inside the probe pod at a constant arrival rate | Accepted |
| [0022](0022-arrival-second.md) | Results are counted by the second a user arrived, not the second they finished | Accepted |
| [0023](0023-deterministic-judge.md) | A deterministic judge decides broke, withstood or inconclusive, second by second | Accepted |
| [0024](0024-warm-up-thrown-away.md) | The warm-up of every measurement is thrown away before judging | Accepted |
| [0025](0025-steady-check-not-run.md) | A steady check before every experiment; an experiment that never gets steady is not run and not counted | Accepted |
| [0026](0026-measurement-settings-per-application.md) | Measurement settings belong to the application, caps to the cluster | Accepted |

## Next

| # | Decision | Status |
|---|---|---|
| [0030](0030-node-and-zone-failure.md) | Node and zone failures: a drain mode and a lost mode, set by node_actions in the RoE | Proposed |
| [0031](0031-restore-pending-undos-on-startup.md) | Pending undos are restored when the orchestrator starts | Proposed |
| [0032](0032-eval-against-a-deterministic-baseline.md) | The eval compares the agent with a deterministic baseline, on a weak and a hardened application | Proposed |
| [0033](0033-rag-memory-of-past-runs.md) | Retrieval over past experiments, so a run builds on the ones before it | Proposed |
| [0034](0034-ci-github-actions.md) | GitHub Actions runs the cheap checks on every change | Proposed |

## Template

```markdown
# ADR-NNNN: <the decision, as a sentence>

**Status:** Accepted | Proposed | Superseded by ADR-XXXX, <date>
**Related:** ADR-XXXX (<why>)

## Context
<the question, and why it came up>

## Options
1. **<option>.** <pros, cons>

## Decision
<what was chosen, and the details that matter>

## Consequences
- **Gains:**
- **Trade-offs:**
- **Not solved:**

## In the code
- `<file>`: `<function or constant>`
```
