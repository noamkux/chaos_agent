# AI Project - Chaos Agent

An AI agent that tests the resilience of any application on Kubernetes within defined Rules of Engagement, proves each weakness with a controlled experiment, and reports what broke, what survived and how to fix it.

all of this live with Rules Of Engagment that the client supply and the agent needs to stick to


## Lab environment

The lab is a local cluster that simulates a customer environment. `lab/up.sh` brings all of it up with one command.

- **kind cluster:** 1 control-plane and 3 workers, each worker labeled with its own zone (`topology.kubernetes.io/zone`), so zone failures can be tested.
- **inotify limits:** `up.sh` checks the host limits before creating the cluster, since kind nodes share them and low values make pods fail randomly.
- **Prometheus:** simulates the customer's existing monitoring, with remote write enabled for k6. It runs on the control-plane, outside the blast radius, so measurements survive node drains.

## Test application

1. Deployed a clean Online Boutique: an application we did not write, to test that the agent works on any application.
2. Audited what is already broken in the upstream version (replicas, probes, PDBs, Redis). Without this step the agent would find real weaknesses we did not know about and be penalized for them as false positives.
3. Ran `dependency-check.sh`, which scales each service down in turn and checks what the user sees. This showed which failures the site survives and which take it down.
4. Investigated the `000` results and found a slow failure: when a dependency disappears, the frontend blocks for about 20 seconds instead of failing fast. This only showed up through experiment.
5. Hardened 4 services to 2 replicas, so the planted weaknesses are subtle and not hidden behind a single replica.
6. Planted 4 weaknesses with Kustomize patches, and verified W1 with a real node drain.
7. Recorded all of it in one file: `ground_truth.yaml`. It is the answer key for the agent: in CI, every change to the agent runs against Online Boutique, and the results are compared to `ground_truth.yaml`.

## The product

**Helm chart (`charts/chaos-agent`):** what a customer installs. The lab installs it the same way, with `lab/chaos-agent-values.yaml` for lab-only settings.

**Postgres:** bundled in the chart as a StatefulSet with a PVC. The password comes from an `existingSecret` the customer provides, or is generated once and kept stable across upgrades.

**Database schema (`orchestrator/storage/schema.sql`):**
- `runs`: one row per run; also the queue and the per-namespace lock.
- `steps`: every LLM call and tool call; the audit log and the checkpoint.
- `undo_actions`: the inverse of every disruptive action, written before the action runs.

**Orchestrator (`orchestrator/`):** connects to Postgres with the standard `PG*` environment variables, applies the schema on every start, and manages the run lifecycle (create, claim, finish). A partial unique index allows only one running run per namespace, enforced by Postgres; this was tested with two runs on the same namespace.

## MCP servers (`servers/mcp/`)

The agent never touches the cluster directly. It acts only through tools exposed by MCP servers.

- **One codebase, one pod per level:** the same image is deployed three times with `LEVEL=observe`, `probe` or `disrupt`. Each pod registers only the tools of its level (`TOOLS_BY_LEVEL` in `server.py`) and runs with the ServiceAccount of its level, so a read-only pod never holds permissions to disrupt.
- **The server does not trust the client:** every tool checks the namespace against `ALLOWED_NAMESPACES`, set at install time. Expected errors are raised as `ToolError`, so the reason reaches the agent; any other exception is hidden from the client and logged on the server.
- **Small outputs:** `get_workloads` returns an allowlist of fields per Deployment, StatefulSet and DaemonSet (replicas, probes, resources, affinity, security context, volume types, env names and sources) instead of the full object, to save tokens and keep secrets out of the agent's context. Env values are never read.
- **`get_inventory`:** lists every namespaced kind the API server serves, including CRDs, as `group/Kind` with the names of its objects, and the kinds it could not read with the reason. Secrets and controller-created objects are never listed.

## Tool gating and audit (`orchestrator/mcp_client.py`)

Every tool call goes through the orchestrator, which enforces the run's rules in three layers:

1. **Visibility:** `load_tools` connects only to the servers allowed by the run's `max_level`, so the agent never sees tools above its level.
2. **Every call is checked:** `call_tool` rejects tools not loaded for the run (including names the model invents) and namespaces outside the run's scope, before anything leaves the orchestrator.
3. **Kubernetes RBAC:** the ServiceAccount of each server pod is the hard boundary if the first two layers fail.

Every call is recorded in `steps` before it runs and completed after, including denied calls, so the eval counts attempted violations and not only successful ones.

## Agent loop (`orchestrator/agent/loop.py`)

A harness written from scratch on the Claude API with native tool calling, without an agent framework.

- The model proposes tool calls; the orchestrator checks, executes and records them, and returns the results.
- Every LLM call is recorded in `steps` with its response and token usage; the full conversation can be rebuilt from `steps` after a crash.
- The loop stops when the model finishes or after `MAX_ITERATIONS`; `MAX_TOKENS` caps each response.
- The system prompt marks tool output as data, never instructions, as a first defense against prompt injection from the system under test.

**First run (Haiku, observe level, Online Boutique):** the loop worked end to end. The agent found N1, N4 and W3 from configuration alone, said honestly what it could not verify, missed N5 although the image tag was in the tool output, miscounted the workloads, and reported generic resource concerns without evidence. These gaps define the next steps.

## Facts in the prompt

Before the first LLM call, the orchestrator calls `get_inventory` and `get_workloads` itself, through the same gated and audited path as any tool call (`collect` in `agent/loop.py`). Their results go into the system prompt with their step numbers, and both tools are removed from the model's tools, so the model never spends a call repeating them. If a required kind (Deployments, StatefulSets, DaemonSets, Services) cannot be read, the run fails, so a run never silently tests nothing.

## Backlog

- **AWS chaos with FIS:** an `aws` MCP server at disrupt level that runs FIS experiment templates. Scope enforced with IAM conditions on resource tags; FIS stop conditions and rollback map to the watchdog and the undo log. Test environment: the weather app on EKS. FIS costs $0.10 per action-minute; the main cost is the AWS environment itself.
- **DB chaos at protocol level:** connection pool exhaustion, lock contention, slow queries. Requires a dedicated test user from the customer. Infrastructure and network level DB chaos is in scope for v1.
- **Request-level chaos (Netflix FIT style):** inject faults only into tagged synthetic requests, using Istio fault injection or Chaos Mesh HTTPChaos. Without instrumentation this works only on the first hop.
- **A role for every run level:** the servers' levels are permission boundaries and stay, but as run levels only disrupt does anything today: an observe or probe run has no `run_experiment` and ends with a summary of the facts. Planned: **observe as assessment**, a report of the weaknesses the facts predict, each with the experiment that would confirm it, for a person to approve before a disrupt run executes it (for production, where nothing may break); **probe as load**, a `load_experiment` that raises `new_users_per_second` step by step until the steady state breaks, and reports where.
- **Per-run credentials for MCP servers:** servers run with no standing permissions; for each run the orchestrator issues a short-lived ServiceAccount token for the run's level.
