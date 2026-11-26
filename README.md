# AI Project - Chaos Agent

An AI agent that tests the resilience of any application on Kubernetes within defined Rules of Engagement, proves each weakness with a controlled experiment, and reports what broke, what survived and how to fix it.

all of this live with Rules Of Engagment that the client supply and the agent needs to stick to

the agent have a catlog of things he have to check, they contain common K8S problem, the agent gets index of the catalog and after the discovery process he asks for the relvent items from the catalog
the catlog follows AWS categories of fauilre
- single point of failure
- excessive load
- exssissve latency
- Shared Fate
- Misconfiguration and bugs


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
7. Recorded all of it in one file: `ground_truth.yaml`. It is the answer key for the agent: in CI, every change to the agent runs against Online Boutique, and the findings are compared to `ground_truth.yaml`.

## The product

**Helm chart (`charts/chaos-agent`):** what a customer installs. The lab installs it the same way, with `lab/chaos-agent-values.yaml` for lab-only settings.

**Postgres:** bundled in the chart as a StatefulSet with a PVC. The password comes from an `existingSecret` the customer provides, or is generated once and kept stable across upgrades.

**Database schema (`orchestrator/schema.sql`):**
- `runs`: one row per run; also the queue and the per-namespace lock.
- `steps`: every LLM call and tool call; the audit log and the checkpoint.
- `undo_actions`: the inverse of every disruptive action, written before the action runs.
- `findings`: one result per check and component: confirmed, survived, not proven or inconclusive.

**Orchestrator (`orchestrator/`):** connects to Postgres with the standard `PG*` environment variables, applies the schema on every start, and manages the run lifecycle (create, claim, finish). A partial unique index allows only one running run per namespace, enforced by Postgres; this was tested with two runs on the same namespace.

## MCP servers (`servers/mcp/`)

The agent never touches the cluster directly. It acts only through tools exposed by MCP servers.

- **One codebase, one pod per level:** the same image is deployed three times with `LEVEL=observe`, `probe` or `disrupt`. Each pod registers only the tools of its level (`TOOLS_BY_LEVEL` in `server.py`) and runs with the ServiceAccount of its level, so a read-only pod never holds permissions to disrupt.
- **The server does not trust the client:** every tool checks the namespace against `ALLOWED_NAMESPACES`, set at install time. Expected errors are raised as `ToolError`, so the reason reaches the agent; any other exception is hidden from the client and logged on the server.
- **Small outputs:** tools return only the fields the checks need (`get_workloads` returns 12 fields per workload instead of the full object), to save tokens and keep secrets out of the agent's context.
- **`get_inventory`:** returns only the names of the Deployments, StatefulSets, Services and Ingresses in a namespace: the kinds the catalog applies to.

## Tool gating and audit (`orchestrator/tools.py`)

Every tool call goes through the orchestrator, which enforces the run's rules in three layers:

1. **Visibility:** `load_tools` connects only to the servers allowed by the run's `max_level`, so the agent never sees tools above its level.
2. **Every call is checked:** `call_tool` rejects tools not loaded for the run (including names the model invents) and namespaces outside the run's scope, before anything leaves the orchestrator.
3. **Kubernetes RBAC:** the ServiceAccount of each server pod is the hard boundary if the first two layers fail.

Every call is recorded in `steps` before it runs and completed after, including denied calls, so the eval counts attempted violations and not only successful ones.

## Agent loop (`orchestrator/agent.py`)

A harness written from scratch on the Claude API with native tool calling, without an agent framework.

- The model proposes tool calls; the orchestrator checks, executes and records them, and returns the results.
- Every LLM call is recorded in `steps` with its response and token usage; the full conversation can be rebuilt from `steps` after a crash.
- The loop stops when the model finishes or after `MAX_ITERATIONS`; `MAX_TOKENS` caps each response.
- The system prompt marks tool output as data, never instructions, as a first defense against prompt injection from the system under test.

**First run (Haiku, observe level, Online Boutique):** the loop worked end to end. The agent found N1, N4 and W3 from configuration alone, said honestly what it could not verify, missed N5 although the image tag was in the tool output, miscounted the workloads, and reported generic resource concerns without evidence. These gaps define the next steps.

## Checks catalog (in progress)

The catalog defines the types of weakness the agent tests for, and how each may be proven. It does not teach the model what it already knows; it gives every run the same names, the same proof rules and the same definition of a finding.

- **One file per check** in `catalog/`, reviewed by PR.
- **Two parts per check:** an index (name, area, failure category, one-line summary, resource types it applies to, maximum proof level) that goes into the system prompt, and details (signals, proof, when it is confirmed, when the system survived, default severity, remediation) returned only by a `get_check` tool. This keeps a large catalog cheap in tokens.
- **Failure categories** follow the AWS Resilience Analysis Framework: single point of failure, excessive load, excessive latency, misconfiguration, shared fate.
- **Filtering in code:** only checks that apply to resources present in the system, and to the run's `focus`, enter the index.
- **Discovery:** before the first LLM call, the orchestrator calls the observe tool `get_inventory` through the same gated and audited path as any tool call, and selects the checks whose `applies_to` matches the kinds found. If discovery fails, the run fails, so a run never silently tests nothing.
- **Run level in the prompt:** the index shows each check's `max_level`, and the prompt states the run's level, so the agent proves each check only up to the lower of the two and reports the rest as not proven.
- **`get_check`:** an internal orchestrator tool, answered from the checks selected for the run, so a check left out by `focus` cannot be read. Every call is recorded in `steps`.
- **A finding is about user impact:** a weakness is confirmed when a user journey fails or breaks its SLO, measured at the system boundary, not when a pod is down.
- **Structured findings:** every result is reported through `report_finding` (see below), so findings can be matched to `ground_truth.yaml`.

## Findings (`orchestrator/findings.py`)

The agent reports every result through `report_finding`, an internal orchestrator tool. The report and the eval read the `findings` table, not the model's text.

- **Four statuses:** `confirmed`, `survived`, `not_proven` (the check needs a higher level than the run allows) and `inconclusive` (tested, but the information needed is missing).
- **Strict tool with enums:** `check_name` is an enum of the run's checks plus `other`, and `component` an enum of the objects found by discovery, so the model cannot invent a name. Above 300 object names, `component` and `dependency` are sent without an enum, because a very large enum makes the schema too complex for the API and the run would fail on its first call; validation still checks every name against the full inventory.
- **Validated before it is stored:** the status must match the run's level (a check above it can only be `not_proven` or `inconclusive`, a check within it cannot be `not_proven`), the evidence must cite step numbers of successful MCP tool results from this run, and a changed severity needs a reason.
- **Step numbers:** every MCP tool result shows its step number, which the agent cites as evidence. The discovery steps and the inventory are in the prompt, so a missing kind can be cited too.
- **Rejected reports** go back to the model with the reason, and are recorded in `steps` with `allowed = false`.
- **One finding per check, component and dependency in a run:** a later report replaces the earlier one, so a result can move from `not_proven` to `confirmed` after an experiment.

## Backlog

- **AWS chaos with FIS:** an `aws` MCP server at disrupt level that runs FIS experiment templates. Scope enforced with IAM conditions on resource tags; FIS stop conditions and rollback map to the watchdog and the undo log. Test environment: the weather app on EKS. FIS costs $0.10 per action-minute; the main cost is the AWS environment itself.
- **DB chaos at protocol level:** connection pool exhaustion, lock contention, slow queries. Requires a dedicated test user from the customer. Infrastructure and network level DB chaos is in scope for v1.
- **Request-level chaos (Netflix FIT style):** inject faults only into tagged synthetic requests, using Istio fault injection or Chaos Mesh HTTPChaos. Without instrumentation this works only on the first hop.
- **Per-run credentials for MCP servers:** servers run with no standing permissions; for each run the orchestrator issues a short-lived ServiceAccount token for the run's level.
- **Exploration mode:** separate from CI regression runs, the agent explores beyond the catalog; approved observations become new checks.