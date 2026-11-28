# Architecture decisions

Every architectural decision of the Chaos Agent, with the question it answered, the options that were considered, what was chosen, what it costs, and where it lives in the code. Format and rules: [ADR-0001](#adr-0001).

A record is never deleted. When a decision changes, a new record supersedes it, and the old one stays as history. Records are numbered in the order the decisions were made; the index below groups them by topic.

**Status:** Accepted (in the code), Proposed (decided, not built yet), Superseded (replaced by a later record).

## Index

### Goal and scope

| # | Decision | Status |
|---|---|---|
| [0001](#adr-0001) | Record architecture decisions | Accepted |
| [0002](#adr-0002) | The goal is chaos engineering, not SRE reporting | Accepted |
| [0003](#adr-0003) | The agent must work on any application, on any cluster | Accepted |
| [0004](#adr-0004) | The lab: Online Boutique on kind, with planted weaknesses and a ground truth | Accepted |
| [0005](#adr-0005) | The product is a Helm chart, and the lab installs it like a customer | Accepted |
| [0006](#adr-0006) | Postgres holds runs, every step, and the undo log | Accepted |

### The agent and its tools

| # | Decision | Status |
|---|---|---|
| [0007](#adr-0007) | The agent loop is written on the Claude API, without an agent framework | Accepted |
| [0008](#adr-0008) | One MCP server codebase, deployed once per level, each with its own ServiceAccount | Accepted |
| [0009](#adr-0009) | observe, probe and disrupt are permission boundaries, not "AI or not" | Accepted |
| [0010](#adr-0010) | The orchestrator calls every MCP tool; the model's only tool is run_experiment | Accepted |
| [0011](#adr-0011) | Collection, tools, safety and judging are deterministic; the agent plans and interprets | Accepted |
| [0012](#adr-0012) | Discovery is done by the orchestrator, returns raw facts, and names kinds as group/Kind | Accepted |
| [0013](#adr-0013) | A checks catalog the agent works through | Superseded by 0014 |
| [0014](#adr-0014) | No catalog: the agent invents its own experiments | Accepted |
| [0027](#adr-0027) | The prompt steers toward degradation, reproduction, and citing steps | Accepted |

### Safety

| # | Decision | Status |
|---|---|---|
| [0015](#adr-0015) | A few generic disrupt tools instead of a tool per fault | Accepted |
| [0016](#adr-0016) | A denylist, not an allowlist, enforced in the server and in the API server | Accepted |
| [0017](#adr-0017) | Snapshots are Secrets in chaos-system, restored by replace, with a write-ahead undo log | Accepted |
| [0018](#adr-0018) | API groups whose controllers act outside the namespace are denied by default | Superseded by 0035 |
| [0035](#adr-0035) | What the agent may not change is set only by the RoE, by API group or by group/Kind | Accepted |
| [0019](#adr-0019) | Data stores are protected only through protected_workloads in the RoE | Accepted |
| [0020](#adr-0020) | Three inputs with three owners: target.yaml, the RoE, and the chart values | Accepted |
| [0028](#adr-0028) | The MCP image and pods are locked down: pinned digests, hashed dependencies, non-root, read-only | Superseded by 0037 |
| [0037](#adr-0037) | The MCP image runs on Chainguard Python with no shell and no pip, scanned, and signed with provenance and an SBOM | Accepted |
| [0029](#adr-0029) | Env values and Secrets never leave the MCP servers | Accepted |

### Measuring and judging

| # | Decision | Status |
|---|---|---|
| [0021](#adr-0021) | Steady state is measured from user journeys, by k6 inside the probe pod at a constant arrival rate | Accepted |
| [0022](#adr-0022) | Results are counted by the second a user arrived, not the second they finished | Accepted |
| [0023](#adr-0023) | A deterministic judge decides broke, withstood or inconclusive, second by second | Accepted |
| [0024](#adr-0024) | The warm-up of every measurement is thrown away before judging | Accepted |
| [0025](#adr-0025) | A steady check before every experiment; an experiment that never gets steady is not run and not counted | Accepted |
| [0026](#adr-0026) | Measurement settings belong to the application, caps to the cluster | Accepted |
| [0036](#adr-0036) | One bad second before the action is noise, as it is after it | Accepted |

### Next

| # | Decision | Status |
|---|---|---|
| [0030](#adr-0030) | Node and zone failures: a drain mode and a lost mode, set by node_actions in the RoE | Accepted |
| [0031](#adr-0031) | Pending undos are restored when the orchestrator starts | Accepted |
| [0032](#adr-0032) | The eval compares the agent with a deterministic baseline, on a weak and a hardened application | Proposed |
| [0033](#adr-0033) | Retrieval over past experiments, so a run builds on the ones before it: hybrid search in pgvector, as a tool of the model | Accepted |
| [0034](#adr-0034) | GitHub Actions runs the cheap checks on every change: lint, unit tests, the chart on kind, and the image | Accepted |
| [0038](#adr-0038) | The model reads what Kubernetes did through inspect_workload, a read-only observe tool passed through as it is, with event messages redacted | Accepted |
| [0039](#adr-0039) | The orchestrator ships in the chart as a CronJob of runs, with no Kubernetes access, its inputs from a ConfigMap and its API key from the customer's Secret | Accepted |


---

<a id="adr-0001"></a>

## ADR-0001: Record architecture decisions

**Status:** Accepted, 2026-11-27

### Context
The project changed direction several times in a few days: a checks catalog was built and removed, the agent's tools moved to the orchestrator, the permissions model went from an allowlist to a denylist. The reasons lived in chat conversations and in commit messages. Without them, a reviewer (or the next version of us) sees the code but not why it is shaped that way, and is likely to reopen questions that were already settled.

### Options
1. **Keep the reasons in commit messages.** Already done, and tied to the exact change. But a decision often spans many commits, and commit messages do not show the options that were rejected.
2. **One design document, updated in place.** Easy to read top to bottom. But updating in place erases the history: once the catalog section is gone, so is the reason it was removed.
3. **Architecture Decision Records** (Michael Nygard's format, 2011, here in the MADR style): one short record per decision, never deleted; a changed decision gets a new record, and the old one is marked superseded.

### Decision
Option 3, kept in one file (this one) with an index, rather than one file per record. Every record has the same sections:
- **Status:** Accepted, Proposed (decided but not built yet), or Superseded by another record.
- **Context:** the question we faced and why it came up.
- **Options:** what was considered, with its pros and cons.
- **Decision:** what was chosen.
- **Consequences:** what it gives us, its trade-offs, and what it does not solve.
- **In the code:** the files and functions where the decision lives.
- **Related:** other records.

Records are numbered in the order the decisions were made, not by topic; the index at the top groups them by topic.

### Consequences
- **Gains:** the reasons and the rejected options stay next to the code, and are reviewed with it.
- **Trade-offs:** one file means a change to one record shows as a diff in a large file; at this size, one place to read and search is worth it. Records must be written when the decision is made, or they drift into being written from memory. A record points at code that keeps changing, so its "In the code" section must be updated when the code moves.

### In the code
- `docs/architecture-decisions.md`: this file.


---

<a id="adr-0002"></a>

## ADR-0002: The goal is chaos engineering, not SRE reporting

**Status:** Accepted, 2026-11-26
**Related:** ADR-0011 (deterministic or agent), ADR-0013 (the checks catalog, superseded), ADR-0014 (no catalog)

### Context
The first version of the agent read the cluster's configuration and reported findings such as "this Deployment has no PodDisruptionBudget" or "this Secret is in an env variable". It worked, but the mentor pointed out that the project was drifting into SRE: a report of configuration gaps that a static checker (kube-score, Polaris, Kubescape) already produces, with an LLM in the middle. A script could do it; the AI added little.

The question: what is the agent for?

### Options
1. **Configuration review (SRE report).** Read the manifests and list what is missing. Cheap, safe, and fast. But it only finds what someone thought to check, and it does not prove that a gap matters to users: a missing PDB is a problem only if a drain actually hurts.
2. **Chaos engineering.** The agent gets the cluster's components and, by its own judgment, breaks, changes and takes things down within the Rules of Engagement, then measures whether the system withstands it. Slower and riskier, but every finding is proven by an experiment, and it can find weaknesses nobody wrote a check for.
3. **Both, equally.** Keeps everything already built. But splits the time between two products, three days before the deadline, and leaves the agent's core value unclear.

### Decision
Option 2. The core loop is: hypothesis, one change, measure what users see, judge, follow up. Observation is an input to that loop (the agent needs to know what exists), not a product of its own. There are no reports of the form "has a PDB or not".

### Consequences
- **Gains:** a clear answer to "why an agent": choosing which experiment to run next, from the results of the last one, is judgment a script does not have. Every finding comes with evidence (the steps of the experiment that proved it).
- **Trade-offs:** the work already done on static checks (the catalog, report_finding, the findings table, the first eval) was removed. Every run now changes the system under test, which needs a safety model (ADR-0015 to ADR-0019) that a read-only report never needed.
- **Not solved:** whether the agent actually finds more than a deterministic sweep of the same actions. That is what the eval must show (ADR-0032).

### In the code
- `orchestrator/agent/loop.py`: `SYSTEM_PROMPT` (the chaos engineering method) and `run_agent`.
- `orchestrator/experiments/runner.py`: `run_experiment`, the only tool the model has.
- Commit `393037e`: the removal of the catalog and of report_finding.


---

<a id="adr-0003"></a>

## ADR-0003: The agent must work on any application, on any cluster

**Status:** Accepted, 2026-11-26
**Related:** ADR-0004 (the lab), ADR-0020 (three inputs, three owners), ADR-0026 (measurement settings)

### Context
The lab runs one application, Online Boutique, on one kind cluster. Every shortcut that only works there ("Online Boutique doesn't use CRDs", "the frontend is always on port 80", "the cluster domain is cluster.local") would make the agent a demo for one app. The question: how far do we design beyond the lab?

### Options
1. **Build for the lab, generalize later.** Fastest to a working demo. But shortcuts end up everywhere, and generalizing later means rewriting the parts that matter most (discovery, measurement, permissions).
2. **Design every decision for any application and any cluster, and use the lab only to test.** Slower per decision. But the agent is a product from the start, and the lab is a test case, not the target.

### Decision
Option 2. Concretely:
- **Nothing about Online Boutique is in the code.** What the application is (its entrypoint, journeys, steady state, measurement settings) comes from `target.yaml`; what the agent may do comes from the RoE. The lab has its own copies in `lab/apps/boutique/`.
- **Discovery lists every kind the API server can list,** CRDs included, instead of a fixed list (ADR-0012).
- **The disrupt server may change any kind** except a short denylist (ADR-0016).
- **Measurement needs nothing installed in the customer's cluster** beyond our chart: k6 runs inside the probe pod (ADR-0021).
- **Kubernetes conventions over lab facts:** zones are read from the standard `topology.kubernetes.io/zone` label, Services are addressed as `<service>.<namespace>.svc` so a cluster domain other than `cluster.local` works.
- **"The lab doesn't use it" is never a reason to leave something out.**

### Consequences
- **Gains:** the same chart and code run on kind, EKS or any conformant cluster; a new application needs only its `target.yaml` and an RoE.
- **Trade-offs:** more validation and more general code than the lab needs (for example the merge patch fallback for CRDs, which Online Boutique never exercises). Some features are harder to test in the lab, since it cannot show what it does not contain.
- **Not solved:** cluster-specific failures that the Kubernetes API cannot simulate (a node that dies without warning, a cloud zone outage): they need cloud tools such as AWS FIS, and are in the backlog.

### In the code
- `orchestrator/config.py`: `load_target` and `load_roe`, the only way the application and the rules enter a run.
- `servers/mcp/k8s.py`: `namespaced_kinds` and `listable_kinds` (every kind the API server lists).
- `servers/mcp/probe.py`: `service_url` (`.svc` addressing).
- `lab/apps/boutique/target.yaml` and `lab/apps/boutique/roe.yaml`: the lab's inputs, kept outside the code.


---

<a id="adr-0004"></a>

## ADR-0004: The lab: Online Boutique on kind, with planted weaknesses and a ground truth

**Status:** Accepted, 2026-11-24 (ground truth rewritten 2026-11-28, ADR-0032)
**Related:** ADR-0003 (any application), ADR-0032 (eval)

### Context
To develop and evaluate the agent we need a cluster and an application where we know the answers: which failures the system survives and which it does not. The question has three parts: which application, how to plant weaknesses in it, and how to record the answers.

### Options

**The application:**
1. **Our own weather app.** We know it well. But we wrote it, so the agent would be tested on an application shaped by our own assumptions; and it is small.
2. **Bookinfo (Istio's sample).** Small and well known. But it is built around a service mesh, and has few services.
3. **Online Boutique (Google's microservices-demo).** 11 services in several languages, gRPC between them, a Redis, a real user flow (browse, cart, checkout). We did not write it.
4. **podinfo.** A single service: good as a second, simple target, not as the main one.

**Planting weaknesses:**
1. **Edit the upstream manifests.** Simple, but then nobody can tell which weaknesses are upstream and which are ours, and upgrading upstream becomes a merge.
2. **Vendor upstream unchanged, and plant every change as a Kustomize patch.** Every planted weakness is one file, with its reason.

**The cluster:**
- kind with one control-plane and three workers, each labeled with its own zone, so node and zone failures can be tested on a laptop.

### Decision
- **Online Boutique** as the main lab application (Bookinfo dropped first; podinfo stays as a second, simple target).
- **Upstream vendored unchanged** under `lab/apps/boutique/upstream`, every change as a patch in `lab/apps/boutique/patches/`:
  - W1: frontend pinned to a single zone.
  - W2: an aggressive liveness probe on currencyservice.
  - W3: a CPU limit on productcatalogservice (calibrated to 200m, so the lab is steady at low load).
  - W4: a Secret value in checkoutservice's env, with a canary value (ADR-0029).
  - Four services hardened to 2 replicas, so the planted weaknesses are not hidden behind single replicas.
- **Natural weaknesses audited first** (single replicas, no PDBs, Redis on an emptyDir), so the agent is not penalized for real weaknesses we did not plant.
- **One answer key, `ground_truth.yaml`,** which the agent never sees.
- **The kind cluster** with zones, Prometheus as the customer's existing monitoring, all brought up by `lab/up.sh`.

### Consequences
- **Gains:** a realistic application we did not write; every planted weakness is reviewable on its own; the answer key makes runs comparable.
- **Trade-offs:** Online Boutique is heavy for a laptop with limited disk. One node per zone means a node failure and a zone failure cannot be told apart in the lab. Some behaviors (such as a ~10 s stall on the first request after idle) are real but unplanned; the stall was left out of the ground truth on purpose, as an "unknown weakness" the agent might find.
- **Not solved:** W2 and W3 show only under load, which no action can raise yet, and W4 is a configuration weakness: their patches stay in the lab, but they are not in the answer key (ADR-0032).

### In the code
- `lab/up.sh`, `lab/kind-config.yaml`: the cluster with zone labels.
- `lab/apps/boutique/kustomization.yaml`: upstream, the patches and the replica counts.
- `lab/apps/boutique/patches/`: one file per planted weakness.
- `lab/apps/boutique/ground_truth.yaml`: the answer key.
- `lab/dependency-check.sh`, `lab/health-check.sh`: the manual checks used to verify the ground truth and the lab before a run.


---

<a id="adr-0005"></a>

## ADR-0005: The product is a Helm chart, and the lab installs it like a customer

**Status:** Accepted, 2026-11-24
**Related:** ADR-0006 (Postgres), ADR-0008 (MCP servers per level), ADR-0020 (owners)

### Context
Everything the agent needs in a cluster (the MCP servers, their permissions, the database, the admission policy) has to be installed somewhere. The question: how does it get into a customer's cluster, and how does the lab get it?

### Options
1. **Plain manifests (`kubectl apply -f`).** No tooling. But every customer edits YAML by hand for namespaces, images and levels, and upgrades are manual.
2. **An operator with its own CRDs.** The most "Kubernetes-native". But it is far more code, needs cluster-admin to install the CRDs, and is out of reach in the time available.
3. **A Helm chart.** The common way to ship a product to Kubernetes: values for what differs per customer, `helm upgrade` for upgrades, templates for repeated objects (one Deployment per level).

### Decision
Option 3. `charts/chaos-agent` holds everything in `chaos-system`. The lab installs it with `helm upgrade --install` and only its own values file, `lab/chaos-agent-values.yaml`, exactly as a customer would.

What differs per customer is in the values: the namespaces the servers may touch (`mcp.allowedNamespaces`, required), which levels are deployed (`mcp.levels.*.enabled`), the probe's caps (`mcp.levels.probe.limits`), images, resources and placement. The chart refuses to render without `mcp.allowedNamespaces` or an image tag.

### Consequences
- **Gains:** one artifact to install; the lab tests the real install path, so a broken template shows up in the lab first; `helm lint` and `helm template` can run in CI.
- **Trade-offs:** the logic in templates (one Role per level per namespace, the CEL in the admission policy) is harder to read and test than code. The orchestrator still runs on the laptop, not from the chart, until it becomes a Job (backlog).

### In the code
- `charts/chaos-agent/values.yaml`: every setting a customer can change.
- `charts/chaos-agent/templates/mcp.yaml`: the `fail` and `required` checks at the top.
- `lab/up.sh`: step 5, the chart installed with `lab/chaos-agent-values.yaml`.


---

<a id="adr-0006"></a>

## ADR-0006: Postgres holds runs, every step, and the undo log

**Status:** Accepted, 2026-11-24
**Related:** ADR-0017 (write-ahead undo), ADR-0031 (restore on startup)

### Context
A run makes dozens of LLM calls and tool calls, some of which change the cluster. We need to know afterwards exactly what happened (audit), to be able to continue or clean up after a crash (checkpoint and undo), to prevent two runs from breaking the same namespace at once, and to feed the eval. The question: where is that state kept?

### Options
1. **Log files.** Simple. But not queryable, and nothing enforces "one run per namespace".
2. **SQLite on the orchestrator's disk.** No server. But the orchestrator will run as a Job in the cluster, whose disk does not survive it.
3. **Postgres, bundled in the chart.** A real database with constraints and JSON columns, that survives the orchestrator.

### Decision
Option 3. A StatefulSet with a PVC in the chart, its password from an `existingSecret` or generated once and kept across upgrades. Three tables:
- **`runs`:** one row per run, with its RoE and target profile; also the queue and the lock.
- **`steps`:** every LLM call and every tool call, numbered within the run, with input, output, whether it was allowed, and token counts. A call is recorded before it runs and completed after, so a crash leaves a step with input and no output. Denied calls are recorded too.
- **`undo_actions`:** what must be restored, written before the change it undoes (ADR-0017).

**One running run per namespace** is a partial unique index (`one_running_run_per_namespace`), enforced by Postgres, not by code.

### Consequences
- **Gains:** a complete, queryable audit; step numbers the model and the summary can cite as evidence; a lock that holds even with two orchestrators; the undo log survives a crash.
- **Trade-offs:** one more stateful component to run and back up. The schema is applied on every start with `CREATE ... IF NOT EXISTS`, which adds but never changes or removes: the lab database still has the old `findings` table. There are no migrations yet.
- **Not solved:** cost tracking (`spent_usd`, `budget_usd`) exists in the schema but is not enforced yet (backlog).

### In the code
- `orchestrator/storage/schema.sql`: the three tables and the partial unique index.
- `orchestrator/storage/db.py`: `create_run`, `claim_run` (catches the unique violation), `start_step`, `finish_step`, `record_llm_step`, `add_undo`, `finish_undo`.
- `charts/chaos-agent/templates/postgresql-*.yaml`: the StatefulSet, Service and Secret.
- `lab/watch-run.sh`: follows a run live from the database.


---

<a id="adr-0007"></a>

## ADR-0007: The agent loop is written on the Claude API, without an agent framework

**Status:** Accepted, 2026-11-25
**Related:** ADR-0010 (orchestrator calls every tool), ADR-0006 (steps)

### Context
The agent needs a loop: send the conversation to the model, run the tool calls it asks for, send the results back, until it stops. The question: write the loop, or use a framework?

### Options
1. **An agent framework** (LangChain, LangGraph, CrewAI and the like). Ready-made loops, memory and tool wiring. But the parts that matter most here (checking every call against the Rules of Engagement, recording every step before it runs, refusing tools the model invents) would be hooks inside someone else's loop, and the framework's abstractions change often.
2. **The Claude API's native tool calling, with our own loop.** About 50 lines. Every decision in the loop is ours and visible.

### Decision
Option 2. `run_agent` calls `messages.create`, records the response and its token usage as a step, runs each `tool_use` block, and returns the results, until the model stops calling tools or `MAX_ITERATIONS` (20) is reached.
- **`MAX_TOKENS` (16384) cut-off fails the run:** a truncated response may hold a truncated tool call, which cannot be run safely.
- **Automatic prompt caching:** the breakpoint moves to the last block as the conversation grows, so each call pays full price only for what is new. In the run of 2026-11-27, 245K of 270K input tokens came from the cache.
- **Tool output is data, never instructions:** stated in the system prompt, as a first defense against prompt injection from the system under test.

### Consequences
- **Gains:** full control over safety and audit; nothing between the loop and the API to debug; small enough to read in one sitting.
- **Trade-offs:** features a framework gives for free (retries, streaming, conversation summarization when the context grows) must be written by us when needed. A long run grows the context with every experiment result; there is no summarization yet.

### In the code
- `orchestrator/agent/loop.py`: `run_agent`, `MAX_ITERATIONS`, `MAX_TOKENS`, the `cache_control` argument, the `stop_reason` checks.
- `orchestrator/storage/db.py`: `record_llm_step`.


---

<a id="adr-0008"></a>

## ADR-0008: One MCP server codebase, deployed once per level, each with its own ServiceAccount

**Status:** Accepted, 2026-11-25 (what the servers give, now that the model calls none of them, added 2026-11-28)
**Related:** ADR-0009 (levels are permission boundaries), ADR-0010 (orchestrator calls every tool), ADR-0016 (admission policy), ADR-0029 (env values), ADR-0033 (search_knowledge)

### Context
Everything that touches the cluster goes through MCP servers: reading objects, sending traffic, changing things. Their permissions differ wildly: reading is harmless, changing is not. The question: how are the tools grouped into servers, and how does each get its permissions?

### Options
1. **One server with every tool.** One Deployment. But its ServiceAccount must hold the union of all permissions, so a bug in a read-only tool runs with write access.
2. **A server per function** (cluster, metrics, load, chaos, exposure...). Six Deployments, six Dockerfiles, six templates. And some functions belong to two levels: k6 at a low rate is a measurement, at a high rate it is a load experiment.
3. **A server per level** (observe, probe, disrupt), from one codebase and one image. Each Deployment gets `LEVEL` and its own ServiceAccount, and registers only its level's tools at startup.

Least privilege for MCP servers is a published recommendation (OWASP's MCP security cheat sheet, and vendor guides that separate read and write tools). MongoDB's MCP server does the same thing with one codebase and a `--readOnly` mode.

### Decision
Option 3.
- `server.py` reads `LEVEL` (no default: a server that does not know its level does not start) and registers the functions listed under it in `TOOLS_BY_LEVEL`, the only place that decides which tool belongs to which level.
- Each level gets a Deployment, a Service and a ServiceAccount from the same template, and a Role per allowed namespace with only its level's rules.
- Tool names carry the level (`observe__get_workloads`, `disrupt__patch_resource`), so the audit shows what was dangerous at a glance.
- A level holds only its own tools: a probe run connects to both the observe and the probe servers.

### Consequences
- **Gains:** a read-only pod never holds write permissions; one image to build and scan; adding a tool is one line in `TOOLS_BY_LEVEL`.
- **Trade-offs:** three pods instead of one, and the orchestrator talks to several servers in one run. A tool that needs two levels' permissions must be split.

### What the servers give, when the model calls none of them (2026-11-28)
Since ADR-0010 the model's tools (`run_experiment`, and `search_knowledge` from ADR-0033) are the orchestrator's own, and only the orchestrator calls the MCP servers. MCP was built for models to call tools directly, so the question came up: what do the servers still give? Four things, none of them about the model:
- **The permission boundary.** Each level runs in its own pod with its own ServiceAccount and RBAC, and the orchestrator holds no credentials for the cluster at all: it can only call the tools the servers expose, and each server is bounded by its own Role. A compromised orchestrator, or a model that tries something unexpected, has no `kubectl`.
- **An identity for the admission policy.** The ValidatingAdmissionPolicy (ADR-0016) enforces the never-change list against the disrupt server's ServiceAccount. Without a separate pod with its own identity, the API server could not tell the agent's changes from a person's or a controller's.
- **Sensitive values stay in the cluster.** Env values and Secrets are dropped inside the server, before anything is returned (ADR-0029); the orchestrator, Postgres and the model never see them.
- **Running inside the cluster.** k6 sends traffic from the probe pod, on the cluster's network, to `frontend:80`, with no port-forward or Ingress; the orchestrator can run anywhere that reaches the servers (a laptop today, a Job or a hosted service later).

The protocol itself adds a standard interface on top: a schema and a description per tool, tool discovery (`list_tools`), client libraries, servers that can be tested alone (`servers/mcp/tests/try_client.py`), and other clients (Claude Desktop, another agent) that can connect without our orchestrator.

**What is not used today:** a model calling MCP tools directly, the reason most projects choose MCP. The first three points above would hold with plain REST or gRPC as well; today MCP works as our RPC.

**Where it pays off next:** read-only tools. A read tool changes nothing, so it can be offered to the model as it is, with the schema the server defines, through an allowlist of observe tools in the orchestrator, with no wrapper per tool; `inspect_workload` (events, pod status, rollout strategy and probes) is the first. Tools that change something stay behind `run_experiment`, where the orchestrator enforces the RoE. This follows the usual rule for agents: read tools freely, enforcement on what changes. To be recorded in ADR-0010 when it is built.

### In the code
- `servers/mcp/server.py`: `LEVEL`, `TOOLS_BY_LEVEL`, the registration loop.
- `charts/chaos-agent/templates/mcp.yaml`: one ServiceAccount, Deployment and Service per enabled level.
- `charts/chaos-agent/templates/mcp-rbac.yaml` and `_helpers.tpl` (`chaos-agent.mcp.rules`): the Role per level per namespace.
- `orchestrator/mcp_client.py`: `SERVERS`, one address per level.


---

<a id="adr-0009"></a>

## ADR-0009: observe, probe and disrupt are permission boundaries, not "AI or not"

**Status:** Accepted, 2026-11-26
**Related:** ADR-0008 (a server per level), ADR-0011 (deterministic or agent)

### Context
When deterministic work moved from the model to the orchestrator (ADR-0011), it was tempting to read the levels as "observe and probe are deterministic, disrupt is the AI". That would mix two separate questions: what a run may do to the cluster, and who decides what to do.

### Options
1. **Levels describe who acts:** observe and probe are scripts, disrupt is the agent.
2. **Levels describe what a run is allowed to do to the cluster,** whoever decides: observe reads, probe also sends traffic to the application, disrupt also changes things. Each level includes the ones below it.

### Decision
Option 2. A level is set in the RoE (`max_level`) by whoever owns the cluster, and it limits three things at once:
- which servers the orchestrator connects to and loads tools from (`ALLOWED_LEVELS`);
- which ServiceAccount, and so which RBAC, the tool runs with (ADR-0008);
- whether the model gets `run_experiment` at all (only when every experiment tool is loaded).

The model can work at every level: at observe it reasons over the facts; at disrupt it plans experiments.

### Consequences
- **Gains:** a cluster owner can allow measurement without allowing change, and the boundary is enforced by Kubernetes, not by a prompt.
- **Trade-offs:** a run at observe level has little for the model to do since the catalog was removed (ADR-0014); in practice runs are at disrupt.

### In the code
- `orchestrator/mcp_client.py`: `ALLOWED_LEVELS`, `load_tools`.
- `orchestrator/config.py`: `LEVELS` and the `max_level` check in `load_roe`.
- `orchestrator/agent/loop.py`: `can_experiment = runner.EXPERIMENT_TOOLS <= server_tools` in `run_agent`.


---

<a id="adr-0010"></a>

## ADR-0010: The orchestrator calls every MCP tool; the model's only tool is run_experiment

**Status:** Accepted, 2026-11-26 (to be changed by ADR-0038: read-only observe tools passed through to the model)
**Related:** ADR-0011 (deterministic or agent), ADR-0015 (generic disrupt tools), ADR-0007 (the loop), ADR-0038 (inspect_workload)

### Context
At first the model called MCP tools directly: `get_workloads`, then `snapshot_resource`, `patch_resource`, `restore_snapshot`. That leaves the order of a safe experiment to the model: it could patch without a snapshot, forget to restore, or measure after the change instead of before. The question: who calls the tools?

### Options
1. **The model calls every tool, the orchestrator checks each call.** Most freedom for the model. But a check per call cannot enforce a sequence (snapshot, then patch, then restore), and every safety rule is one more instruction the model may not follow.
2. **The model calls some tools (observation), the orchestrator wraps the dangerous ones.** A middle ground, but two paths to the same servers, and observation results the model asked for are not citable as one consistent inventory.
3. **The orchestrator calls every MCP tool. The model gets one internal tool, `run_experiment`, which takes a plan** (hypothesis, action, journeys, how long the change stays) **and returns a measured, judged result.**

### Decision
Option 3.
- The model's tools are only what `run_agent` builds in `available`: `run_experiment`, when every experiment tool is loaded.
- Any other tool name the model sends goes to `call_tool` with an empty allowed set, so it is denied and recorded with `allowed = false`.
- The runner runs every experiment in a fixed order nobody can skip: check, steady check, background measurement, snapshot, write-ahead undo, change, wait, restore, judge.
- Observation (inventory, workload facts) is collected by the orchestrator before the first LLM call and put in the prompt with its step numbers (ADR-0012).

### Consequences
- **Gains:** the order of a safe experiment is code, not a prompt; every server call is made by code we wrote and recorded under the experiment's step; the model's tool schema is small, so its prompt is cheaper.
- **Trade-offs:** the model cannot ask for a fact that discovery did not collect, or run an action the runner does not know. Every new kind of action (a node failure, a Chaos Mesh fault) needs runner code, not only a new server tool.

### In the code
- `orchestrator/agent/loop.py`: `run_agent`, `internal`, `available`, and the `mcp_client.call_tool(conn, run_id, set(), ...)` branch for any other name.
- `orchestrator/experiments/runner.py`: `run_experiment_tool` (the schema the model sees), `run_experiment`, `EXPERIMENT_TOOLS`.
- `orchestrator/mcp_client.py`: `call_tool`, the allowed-set check.


---

<a id="adr-0011"></a>

## ADR-0011: Collection, tools, safety and judging are deterministic; the agent plans and interprets

**Status:** Accepted, 2026-11-26
**Related:** ADR-0002 (chaos), ADR-0010 (orchestrator calls every tool), ADR-0023 (the judge), ADR-0032 (eval)

### Context
After the first runs, the agent felt too deterministic: it read configurations and listed gaps, which a script could do. The opposite risk is just as real: an LLM that decides whether the system broke can decide it broke because it expected it to. The question: which parts of a run should be the model's, and which code?

### Options
1. **The model does everything:** collects facts, runs tools, judges results, writes the report. Simple to build, hard to trust, and the most expensive in tokens.
2. **Deterministic where an answer can be computed, the model where judgment is needed.**
3. **No model at all:** a deterministic sweep of every action on every component. Reproducible and cheap per decision, but it only runs what was enumerated, and it does not adapt to what it finds.

### Decision
Option 2.
- **Deterministic:** collecting facts (inventory, workload facts), running tools, every safety rule (RoE, scope, denylist, protected workloads, caps), the order of an experiment, measuring, and judging (broke, withstood, inconclusive).
- **The agent:** choosing what to break and how, forming the hypothesis, reading the timeline and the errors, following up on surprises, deciding when a finding is reproduced, and writing the summary.

Option 3 is not rejected: it is the eval's baseline (ADR-0032). If the agent does not beat a deterministic sweep on findings per experiment, that is a valid result.

### Consequences
- **Gains:** the verdict cannot be argued by the model; facts in the prompt are complete and citable; the model's tokens go to the part only it can do.
- **Trade-offs:** the model can only act through what the orchestrator implements; a capability the agent "would" use must be built first.
- **Not solved:** whether disrupt justifies an LLM is an empirical question, answered by the eval, not by this record.

### In the code
- `orchestrator/agent/loop.py`: `discover_inventory`, `collect_workloads` (deterministic collection), `SYSTEM_PROMPT` (what the agent does).
- `orchestrator/experiments/runner.py`: `check` and `run_experiment` (deterministic execution).
- `orchestrator/experiments/judge.py`: `judge` (deterministic verdict).


---

<a id="adr-0012"></a>

## ADR-0012: Discovery is done by the orchestrator, returns raw facts, and names kinds as group/Kind

**Status:** Accepted, 2026-11-26
**Related:** ADR-0003 (any cluster), ADR-0010 (orchestrator calls every tool), ADR-0029 (env values never leave)

### Context
The agent needs to know what exists in the namespaces it tests and how each workload is configured. Three questions came up:
1. Who calls the discovery tools: the model, or the orchestrator?
2. What do the tools return: conclusions (`has_pdb: false`) or facts?
3. How are kinds named, so the inventory, the RoE and the disrupt tools agree?

And one more: should the orchestrator read the cluster directly, without an MCP server?

### Options
**Who calls:**
1. **The model**, when it wants. It may skip discovery, or read part of it, and then reason about things it never looked at.
2. **The orchestrator**, once per namespace, before the first LLM call, with the results and their step numbers in the prompt.

**Direct access:** giving the orchestrator its own Kubernetes credentials would be simpler, but every cluster access today goes through an MCP server with its own ServiceAccount; a second path would bypass that model.

**What is returned:**
1. **Booleans** (`has_readiness_probe`, `single_replica`). Small, but each is a check we wrote, and the agent sees only what we thought to check.
2. **Raw facts with Kubernetes field names**: every container's resources and probes, affinity, topology spread, env variable names and where each value comes from (never the value).

**Kind names:**
1. `apiVersion/kind` (`apps/v1/Deployment`): versions change between clusters.
2. `group/Kind` without version (`apps/Deployment`, `core/Service`).

### Decision
- **The orchestrator calls `observe__get_inventory` and `observe__get_workloads`** before the first LLM call, through `call_tool`, so they are recorded as steps. The model cites those steps as evidence of what exists.
- **The inventory lists every kind the API server can list,** CRDs included, except kinds that controllers create and that change all the time (Pods, ReplicaSets, Endpoints, Events, Leases) and Secrets. Kinds it could not read are reported as unreadable; a run fails if a required kind (Deployment, StatefulSet, DaemonSet, Service) is unreadable.
- **Workloads are returned as facts,** with the rules for reading them in the prompt ("a field that is left out is not set"). Since 2026-11-27, a workload is any object with a pod template (`spec.template`, or `spec.jobTemplate.spec.template` for a CronJob), of any kind, custom resources included, so an Argo Rollout or an operator's workload is seen like a Deployment; objects another workload controls are left out. Placement follows each pod's ownerReferences to the top for the same reason.
- **Kinds are always `group/Kind`,** in the inventory, the RoE and the disrupt tools.
- No direct cluster access from the orchestrator; no kube-score or similar.

### Consequences
- **Gains:** discovery is complete and identical in every run; the agent sees configuration it can reason about freely; names match across every component.
- **Trade-offs:** the prompt grows with the size of the namespace (a large application means a long inventory; no summarization yet). Facts are more tokens than booleans. Pod placement (which node and zone every pod runs on) was added on 2026-11-27 for node and zone failures (ADR-0030): `get_placement`, which needs a read-only ClusterRole on nodes, the only cluster-scoped read.

### In the code
- `servers/mcp/k8s.py`: `SKIPPED_KINDS`, `namespaced_kinds`, `listable_kinds`, `get_inventory`, `get_workloads`, `CONTAINER_FIELDS`, `POD_FIELDS`, `env_facts`.
- `servers/mcp/k8s.py`: `get_placement`, `node_facts`, `workload_of`, `ZONE_LABEL`.
- `orchestrator/agent/loop.py`: `collect`, `discover_inventory`, `REQUIRED_KINDS`, `collect_workloads`, `collect_placement`, `format_placement`, and the field rules in `RUN_SECTION`.
- `charts/chaos-agent/templates/mcp-rbac.yaml`: the observe `view` RoleBinding and the `-nodes` ClusterRole.


---

<a id="adr-0013"></a>

## ADR-0013: A checks catalog the agent works through

**Status:** Superseded by ADR-0014, 2026-11-26 (accepted 2026-11-25)
**Related:** ADR-0002 (chaos), ADR-0014 (no catalog)

### Context
To make the agent's work broad and repeatable, we needed a list of what to look for. The question: where does that list live?

### Options
1. **In the prompt.** Simple, but grows without structure, and cannot be validated.
2. **A catalog of checks as files,** each with what it applies to (`applies_to` in `group/Kind`), how to prove it and at which level, loaded by the orchestrator and shown to the model as an index. Findings reported through a strict `report_finding` tool, validated against the catalog, the inventory and the run level, and stored in a `findings` table. Scored by `evaluate.py` against `ground_truth.yaml`.

### Decision (at the time)
Option 2: `catalog/`, a loader, `get_check`, `report_finding` and the `findings` table.

### Why it was superseded
A catalog is a menu. The agent ran checks we wrote, so it could only find weaknesses we already knew about, and the project read as an SRE report generator (ADR-0002). The point of chaos engineering is discovering weaknesses nobody knew about. The catalog, `report_finding`, the findings table and `evaluate.py` were removed in commit `393037e`.

### What stayed
- `group/Kind` naming and dynamic discovery (ADR-0012), first built for `applies_to`.
- Evidence by step number, first required by `report_finding`.

### In the code
- Removed. History: commits `cbefb46`, `8e16b5e`, `282220b`, `f41f4f3` (added) and `393037e` (removed).


---

<a id="adr-0014"></a>

## ADR-0014: No catalog: the agent invents its own experiments

**Status:** Accepted, 2026-11-26
**Supersedes:** ADR-0013
**Related:** ADR-0002 (chaos), ADR-0015 (generic disrupt tools), ADR-0027 (prompt)

### Context
With the catalog removed (ADR-0013), the agent needs another way to decide what to test. The question: how much structure do we give it?

### Options
1. **A catalog of experiments** (instead of checks): "kill one pod of every Deployment", "scale every dependency to 0". Predictable, but the same menu problem.
2. **A method, not a list:** the agent gets the facts and a chaos engineering method (hypothesis, one change, read the timeline, follow up), and designs every experiment itself, limited only by the Rules of Engagement.

### Decision
Option 2. The prompt teaches the method; the facts come from discovery; the experiments are the agent's. What it may do is limited by damage limits (scope, denylist, protected workloads, caps, the restore), not by a list of allowed actions.

### Consequences
- **Gains:** the agent can find weaknesses that were never written down. In the run of 2026-11-26 it found a hidden coupling (cart depends on shipping) that was in no manifest and no ground truth.
- **Trade-offs:** less predictable runs; quality depends on the prompt and the model. In the first run the agent mostly scaled things to 0, which always breaks and teaches little; the prompt had to steer it toward partial changes (ADR-0027). Measuring "coverage" is harder without a list: the eval compares outcomes, not checklists (ADR-0032).

### In the code
- `orchestrator/agent/loop.py`: `SYSTEM_PROMPT`, the Method section.
- `orchestrator/experiments/runner.py`: `run_experiment_tool`, the generic action schema.


---

<a id="adr-0015"></a>

## ADR-0015: A few generic disrupt tools instead of a tool per fault

**Status:** Accepted, 2026-11-26
**Related:** ADR-0014 (no catalog), ADR-0016 (denylist), ADR-0017 (snapshots), ADR-0030 (node failure)

### Context
The agent must be able to "go wild" within the rules. The question: what do the disrupt tools look like?

### Options
1. **A tool per fault:** `kill_pod`, `scale_to_zero`, `add_cpu_limit`, `break_readiness_probe`... Each is easy to reason about and to restore. But together they are a fixed menu, and every new idea needs a new tool.
2. **A few generic tools bounded by damage limits:**
   - `patch_resource`: a patch on any object in scope, always after a snapshot that can restore it;
   - `delete_pod`: one running pod of a workload, replaced by its controller;
   - later, agent-written Chaos Mesh faults (latency, partition, stress) and node actions.

### Decision
Option 2. With `patch_resource` the agent can change replicas, resources, probes, env, selectors, ports, HPAs, NetworkPolicies, or any field of a custom resource, and the runner restores it from the snapshot. What it may not do is set by the denylist (ADR-0016), not by the tool.

Details that make the generic tools safe:
- **Strategic merge patch**, so lists such as `containers` and `env` merge by name. Custom resources do not support it (the API returns 415), so the server falls back to a JSON merge patch, which replaces lists whole.
- **`resourceVersion` as a precondition** in every patch: if the object changed since its snapshot, the API returns 409 and nothing is written, so the snapshot always describes the state just before our change.
- **In metadata, only labels and annotations** may change: renaming an object is not chaos.
- **`delete_pod` by workload, not by pod name:** the model does not see pods; the server picks the first running pod of the workload's selector by name, so the same request hits the same pod and an experiment can be repeated.

### Consequences
- **Gains:** the agent's ideas are not limited by our tool list; one restore mechanism covers every patch.
- **Trade-offs:** a generic patch is harder to reason about than a named fault, so its safety rests on the denylist and the admission policy. A change to a pod template restarts every pod of the workload, so the rollout is part of every such experiment (stated in the prompt, ADR-0027). `delete_pod` finds pods only through `matchLabels`.

### In the code
- `servers/mcp/disrupt.py`: `patch_resource` (415 fallback, `resourceVersion` precondition, metadata rule), `delete_pod`.
- `orchestrator/experiments/runner.py`: `ACTIONS`, `check`, and the `patch` and `delete_pod` branches of `run_experiment`.


---

<a id="adr-0016"></a>

## ADR-0016: A denylist, not an allowlist, enforced in the server and in the API server

**Status:** Accepted, 2026-11-26
**Related:** ADR-0015 (generic tools), ADR-0018 (deny groups), ADR-0030 (node failure)

### Context
The first version of `disrupt.py` had an allowlist of eight patchable kinds (Deployments, Services, ConfigMaps, HPAs, PDBs, NetworkPolicies...). That is a menu again, one level down: applications with CRDs (Argo Rollouts, Istio VirtualServices, KEDA ScaledObjects) hide their most interesting weaknesses exactly there. Two questions:
1. Allowlist or denylist?
2. Kubernetes RBAC has no exclusions ("everything except Secrets" cannot be written as a Role). How do we grant "almost everything" without trusting only our own code?

### Options
**What may be changed:**
1. **An allowlist of kinds.** Tight, but a menu.
2. **A denylist of kinds and of fields.** Deny only what cannot be restored or is about permissions; everything else, custom resources included, is open.

**How it is enforced:**
1. **RBAC with an explicit list of kinds.** Tight RBAC, but it is the allowlist again, and a new CRD is out of reach.
2. **RBAC `*` in the tested namespaces, with the denylist only in code.** Matches the denylist, but then Secrets are writable at the RBAC level, and our code is the only guard.
3. **RBAC `*` in the tested namespaces, plus a ValidatingAdmissionPolicy (GA since Kubernetes 1.30) that denies the denylist for the disrupt ServiceAccount in the API server itself.**

How other tools handle it: Litmus gives each experiment its own minimal ServiceAccount (an allowlist that works because its experiments are known in advance); Harness binds one Role per application namespace instead of a ClusterRole; Chaos Mesh adds a second fence with `enableFilterNamespace`. Our experiments are not known in advance, so the allowlist pattern does not fit.

### Decision
- **Denied kinds:** Secrets, PersistentVolumeClaims, ServiceAccounts, Roles and RoleBindings. PVCs are data a snapshot cannot restore; the rest are credentials and permissions.
- **Denied fields, at any depth of a patch:** `image`, `command`, `args`, `securityContext`, `serviceAccountName`, `serviceAccount`, `automountServiceAccountToken`, `hostNetwork`, `hostPID`, `hostIPC`, `volumes`. These do not break anything; they run other code or gain privileges, which is exploitation, not chaos. Resources, probes, env and everything else in a pod template stay open.
- **RBAC:** `patch` and `update` on `*/*`, and `delete` on pods, only in the allowed namespaces. Reads through the built-in `view` ClusterRole, which excludes Secrets.
- **Enforced twice:** `disrupt.py` refuses denied kinds and fields; the `mcp-disrupt-guard` ValidatingAdmissionPolicy denies the same, plus any CREATE or DELETE other than deleting pods and managing its own snapshot Secrets, for the disrupt ServiceAccount only, with `failurePolicy: Fail`. Tested: a replicas patch passes; image and hostNetwork changes are denied by the API server.

### Consequences
- **Gains:** the agent can change any kind, CRDs included; a bug in our code, or a call that bypasses the orchestrator, still cannot touch Secrets or change an image.
- **Trade-offs:** RBAC alone looks broad (`*`), which can alarm a security review; the admission policy must be read alongside it. A CRD without the `view` aggregation label is not readable, so it cannot be snapshotted, so it cannot be changed; a customer can grant it in values. Requires Kubernetes 1.30 or later.

### In the code
- `servers/mcp/disrupt.py`: `DENIED_KINDS`, `FORBIDDEN_FIELDS`, `resource_for`, `forbidden_fields`.
- `charts/chaos-agent/templates/_helpers.tpl`: the disrupt rules in `chaos-agent.mcp.rules`, and `chaos-agent.mcp.podGuard`.
- `charts/chaos-agent/templates/mcp-rbac.yaml`: the `view` RoleBinding.
- `charts/chaos-agent/templates/mcp-admission-policy.yaml`: the policy and its binding.


---

<a id="adr-0017"></a>

## ADR-0017: Snapshots are Secrets in chaos-system, restored by replace, with a write-ahead undo log

**Status:** Accepted, 2026-11-26
**Related:** ADR-0006 (Postgres), ADR-0029 (env values never leave), ADR-0031 (restore on startup)

### Context
Every patch must be undone after the experiment, even if the orchestrator crashes in between. Three questions: where is the state before the change kept, how is it restored, and how does a crash not lose it?

### Options
**Where the snapshot lives:**
1. **In Postgres.** Already there. But a full object holds env values, including literal secrets (the lab's W4 plants exactly that); they would end up in the database and in every backup of it.
2. **In the orchestrator's memory.** Lost on a crash.
3. **As a Secret in the server's own namespace,** labeled as a snapshot, readable only by the disrupt server.

**How to restore:**
1. **A reverse patch.** Cannot remove fields the patch added.
2. **Replace with the snapshot,** using the current `resourceVersion`: puts the whole object back exactly, including removing what the patch added.

**When the undo is recorded:**
1. **After the change.** A crash between the change and the record leaves a change nobody knows to undo.
2. **Before the change (write-ahead).** A crash leaves a pending undo that can be run later.

### Decision
- **Snapshots as Secrets** in `chaos-system` (`POD_NAMESPACE` from the Downward API), with a random name and the label `chaos-agent.io/snapshot`. `restore_snapshot` refuses any Secret without the label, so the tool cannot be used to read other Secrets in `chaos-system`, such as the Postgres password. The object is cleaned of `status` and server-managed metadata before it is stored.
- **Restore by replace,** then delete the snapshot only after the replace succeeded, so a failed restore can be retried.
- **Write-ahead undo:** the runner writes the undo (`restore_snapshot` with the snapshot id) to `undo_actions` as pending before the patch, and marks it done after the restore. A failed restore marks it failed and stops the run.

### Consequences
- **Gains:** env values never reach the database or the model; every patch can be undone exactly; a crash leaves a record of what is still changed.
- **Trade-offs:** the disrupt ServiceAccount needs create, get and delete on Secrets in its own namespace, which the admission policy allows only there. A pending undo is only useful if something runs it: today that is manual, and ADR-0031 adds it on startup.

### In the code
- `servers/mcp/disrupt.py`: `SNAPSHOT_NAMESPACE`, `SNAPSHOT_LABEL`, `clean`, `snapshot_resource`, `restore_snapshot`.
- `orchestrator/experiments/runner.py`: the patch branch of `run_experiment` (`db.add_undo` before `PATCH`, `db.finish_undo` after `RESTORE`, `RuntimeError` on a failed restore).
- `orchestrator/storage/db.py`: `add_undo`, `finish_undo`; `orchestrator/storage/schema.sql`: `undo_actions`.
- `charts/chaos-agent/templates/mcp-rbac.yaml`: the `-snapshots` Role.


---

<a id="adr-0018"></a>

## ADR-0018: API groups whose controllers act outside the namespace are denied by default

**Status:** Superseded by ADR-0035, 2026-11-27 (accepted 2026-11-26)
**Related:** ADR-0016 (denylist), ADR-0017 (snapshots), ADR-0020 (owners)

### Context
With every kind open to patching (ADR-0016), some custom resources are dangerous in a way a snapshot cannot fix: their controllers act outside the namespace or outside the cluster. Restoring the YAML restores the object, not what the controller did because of it:
- an Argo CD Application with `prune: true` whose path is patched deletes every resource of the application, PVCs included; restoring the Application recreates the Deployments, not the data;
- a Crossplane or ACK (`services.k8s.aws`) database whose instance class is patched is a real cloud change, with a reboot and a cost, and minutes of modification that no 30 s recovery window can judge;
- a CloudNativePG Cluster scaled down fails over and deletes a replica with its PVC;
- a Velero Schedule or Restore stops backups or overwrites resources.

The question: how do we keep the agent away from these, on every cluster, when the list differs per customer?

### Options
1. **Hard-code them in the server's denylist.** Always on, but the list is customer-specific, and a customer who understands the risk cannot opt in.
2. **Deny them in the RoE, with a default list,** enforced by the orchestrator before any call; a group also matches its subgroups.
3. **Nothing; trust the restore.** Wrong for the reasons above.

### Decision
Option 2. `deny_groups` in the RoE; when it is left out, `DEFAULT_DENY_GROUPS` applies: `argoproj.io`, `fluxcd.io`, `services.k8s.aws`, `crossplane.io`, `upbound.io`, `cnrm.cloud.google.com`, `azure.com`, `velero.io`, `cnpg.io`. Setting the key replaces the list. A group matches itself and every subgroup (`argoproj.io` also matches `workflows.argoproj.io`, and not `notargoproj.io`).

Chaos on the GitOps tool itself stays possible the right way: scaling `argocd-application-controller` to 0 is an `apps/Deployment` change.

### Consequences
- **Gains:** the snapshot guarantee ("restore puts things back") holds for everything the agent may touch.
- **Trade-offs:** enforced by the orchestrator only, not by the admission policy, so a direct call to the disrupt server bypasses it. A new operator with the same risk is open until someone adds its group.

### In the code
- Replaced by ADR-0035: `DEFAULT_DENY_GROUPS`, `deny_groups` and `denied_group` were removed from `orchestrator/config.py` on 2026-11-27. The reasons for each group above live on as comments in `lab/apps/boutique/roe.yaml`.


---

<a id="adr-0019"></a>

## ADR-0019: Data stores are protected only through protected_workloads in the RoE

**Status:** Accepted, 2026-11-26
**Related:** ADR-0016 (denylist), ADR-0020 (owners)

### Context
Some workloads must not be restarted: in the lab, `redis-cart` keeps every cart on an emptyDir, so one restart deletes all of them. The question: how does the agent know what it may not touch?

### Options
1. **A blanket rule in the prompt:** "never restart a database". Easy. But a database that survives a restart is exactly a resilience test worth running, even in production, and "database" is a guess the model makes from names.
2. **Detect state automatically** (StatefulSets, PVCs, emptyDir volumes) and refuse. Automatic, but wrong both ways: a StatefulSet with replication should be tested; a Deployment with an emptyDir cache may be fine to restart.
3. **A list in the RoE, written by whoever owns the cluster:** `protected_workloads`. The agent may measure them, never change them.

### Decision
Option 3. Empty by default, since only the cluster owner knows what is unsafe. The runner refuses any experiment whose target is in the list, and the prompt shows the list, so the model does not spend experiments on it. No blanket rule about data stores in the prompt.

### Consequences
- **Gains:** a database restart stays a legitimate experiment wherever the owner allows it; the rule is explicit and auditable.
- **Trade-offs:** an owner who forgets to list a fragile store leaves it open. Protection is by name, so it covers direct actions on the workload, not indirect effects (deleting a pod of a service that writes to it).

### In the code
- `orchestrator/config.py`: `protected_workloads` in `ROE_DEFAULTS` and its check in `load_roe`.
- `orchestrator/experiments/runner.py`: `check` (`action["name"] in roe["protected_workloads"]`).
- `orchestrator/agent/loop.py`: `format_rules`.
- `lab/apps/boutique/roe.yaml`: `protected_workloads: [redis-cart]`, with the reason.


---

<a id="adr-0020"></a>

## ADR-0020: Three inputs with three owners: target.yaml, the RoE, and the chart values

**Status:** Accepted, 2026-11-26 (measurement and caps added 2026-11-27; max_model_rounds and the orchestrator's values added 2026-11-28)
**Related:** ADR-0039 (the orchestrator in the chart), ADR-0005 (chart), ADR-0018 (deny groups), ADR-0019 (protected workloads), ADR-0026 (measurement settings)

### Context
A run needs to know what the application is, what normal looks like for it, what the agent may do, and what the cluster can tolerate. The mentor asked that the agent start from a document describing the application's expectations. The question: one configuration file, or several, and who writes each?

### Options
1. **One file with everything.** One place to look. But the people who know each part are different: the application team knows the journeys, security decides what may be broken, the cluster admin decides what the cluster can take. One file means one owner deciding for all three, or three owners editing the same file.
2. **One file per owner,** each validated on its own, with safe defaults for everything optional.

### Decision
Option 2.
- **`target.yaml`, the application team:** the entrypoint Service and port, the user journeys (steps, and whether they write data), the steady state (success rate and p95), and how to measure the application (ADR-0026). The agent reads it.
- **The RoE, security or operations:** scope (namespaces), the highest level, whether write journeys and node actions are allowed, protected workloads, denied API groups, how many experiments, how many rounds of the model (`max_model_rounds`, default 30, at most 100: the closest thing to a cost limit until `budget_usd` is enforced), and how long a change may stay. Every optional setting defaults to the safe value: an RoE that says nothing allows nothing extra.
- **The chart values, the cluster admin:** which namespaces the servers may touch at all, which levels are deployed, the probe's caps, and for the orchestrator (ADR-0039) the model, the namespace under test, the ConfigMap that holds the two files above, the Secret with the API key, and a schedule.

Each is checked before a run starts; a malformed file stops the run with a message that names the file and the setting.

### Consequences
- **Gains:** each owner edits only what they know; a security review reads the RoE alone; the same target works under different RoEs (a lab RoE and a production RoE).
- **Trade-offs:** three files to keep consistent: a target can ask for a rate the chart caps lower, or an RoE can allow a hold longer than the probe's longest run; today that is found only at the first measurement (follow-up: a `get_limits` observe tool).

### In the code
- `orchestrator/config.py`: `load_target`, `load_roe`, `ROE_DEFAULTS`, `MEASUREMENT_DEFAULTS`.
- `lab/apps/boutique/target.yaml`, `lab/apps/boutique/roe.yaml`: the lab's two files, with comments for every setting.
- `charts/chaos-agent/values.yaml`: `mcp.allowedNamespaces`, `mcp.levels`, `mcp.levels.probe.limits`.


---

<a id="adr-0021"></a>

## ADR-0021: Steady state is measured from user journeys, by k6 running inside the probe pod at a constant arrival rate

**Status:** Accepted, 2026-11-26
**Related:** ADR-0022 (arrival second), ADR-0023 (the judge), ADR-0026 (measurement settings)

### Context
Every experiment needs a measurement of what users see before, during and after the change. Three questions:
1. What is measured: pod status, metrics, or user requests?
2. With what tool, and where does it run?
3. How do we avoid the measurement slowing down with the system it measures?

### Options
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

### Decision
- **Synthetic journeys at the entrypoint,** from `target.yaml`, measured continuously through the whole experiment in one call (`measure_journeys`), in the background while the runner makes the change.
- **k6 inside the probe pod** (option 1), copied from its official image pinned by digest.
- **The open model:** k6's `constant-arrival-rate` executor, one scenario per journey, so a stuck journey cannot slow the measurement, and one journey's stuck users cannot take another journey's virtual users. Users k6 could not start are reported as `not_sent`.
- **A new cookie jar per user,** so every iteration is a new session.
- **Success by status code,** after following redirects; a step that fails ends the journey.
- **The probe server only counts; it never judges.** Judging stays in the orchestrator (ADR-0023).

### Consequences
- **Gains:** works on any cluster with nothing installed; measures what users feel; a stuck system looks stuck.
- **Trade-offs:** synthetic traffic, not real users. Success by status code only: a `200` page that says "something went wrong" counts as success (follow-up: an expected text per step, checked only for those requests). Response bodies are discarded to save memory, which is also why. One pod cannot generate heavy load: load experiments may need a Job or the operator later.

### In the code
- `servers/mcp/probe.py`: `measure_journeys`, `run_k6`, `summarize`.
- `servers/mcp/journeys.js`: `options.scenarios` (`constant-arrival-rate`, one per journey), `run`.
- `servers/mcp/Dockerfile`: `COPY --from=k6`.
- `orchestrator/experiments/runner.py`: the background `measuring` task in `run_experiment`.


---

<a id="adr-0022"></a>

## ADR-0022: Results are counted by the second a user arrived, not the second they finished

**Status:** Accepted, 2026-11-26
**Related:** ADR-0021 (k6), ADR-0023 (the judge)

### Context
A user who arrives during an outage can wait up to the request timeout (10 s by default) before failing. Every result has two times: when the user arrived and when they finished. The question: which second does a result belong to?

### Options
1. **The second it finished** (k6's own timestamp). Free. But every failure is shifted by up to the timeout: with a change restored after 20 s, users who failed because of the outage would be counted after the restore, and the judge would see a longer outage and a later recovery than really happened.
2. **The second it arrived,** tagged by the journey script when the user starts.

### Decision
Option 2. `run` in `journeys.js` computes the arrival second from `exec.scenario.startTime` and tags every journey metric with it; `summarize` buckets by that tag. A result shows the state of the system at the moment the user met it.

### Consequences
- **Gains:** outages start and end where they really did; recovery is measured from the restore, not from when the last stuck user gave up.
- **Trade-offs:** the last seconds of a measurement fill in late (a user who arrived in the last second is still waiting). A user started just after the end can be tagged with a second past `measure_for_s`; the judge reads only `range(measure_for_s)`, so it is ignored (seen in the run of 2026-11-27).

### In the code
- `servers/mcp/journeys.js`: `run`, the `second` tag.
- `servers/mcp/probe.py`: `summarize`, bucketing by `tags["second"]`.
- `orchestrator/experiments/judge.py`: `statuses_of`, `range(measurement["measure_for_s"])`.


---

<a id="adr-0023"></a>

## ADR-0023: A deterministic judge decides broke, withstood or inconclusive, second by second

**Status:** Accepted, 2026-11-26 (before_action added 2026-11-27; the inconclusive rule changed by ADR-0036)
**Related:** ADR-0011 (deterministic or agent), ADR-0021 (k6), ADR-0024 (warm-up), ADR-0025 (steady check)

### Context
After an experiment we have, for every journey and every second, how many users succeeded and failed and how slow they were. Someone must decide whether the system broke. Two questions: who decides, and how is the result shown to the model?

### Options
**Who decides:**
1. **The model**, reading the numbers. Flexible, but it can decide the system broke because it expected it to; verdicts would differ between runs of the same data.
2. **Code, against the steady state in `target.yaml`.** Reproducible, and the model cannot argue with it.

**How the result is shown:**
1. **The raw per-second results.** Hundreds of lines of JSON per experiment, in every following prompt.
2. **A timeline of one character per second,** plus totals before and after the change. A minute of seconds fits in one short line, for a few dozen tokens.

### Decision
Code decides, in `experiments/judge.py`:
- **Every second of every journey gets a status:** `fail` if the success rate is below `steady_state.success_rate`, `slow` if everything succeeded but p95 is above `steady_state.p95_ms`, `no_data` if nobody arrived, otherwise `ok`. Success comes first: a second with failures is `fail` whatever its p95.
- **inconclusive** (changed by ADR-0036 to at least `MIN_BROKEN_S` seconds) if any second before the action, in the steady check or in the measurement, was not `ok`: the result cannot be told apart from what was already there. It shows the timelines of both, `baseline` and `before_action`, so the model can see why.
- **broke** if, after the action, at least `MIN_BROKEN_S` (2) seconds were not `ok`, or any user could not be sent, or the journey had not recovered by the end of the measurement.
- **withstood** otherwise.
- **Recovery** is the first second from which every second to the end is `ok`, counted from the restore for a patch, and from the action for a deleted pod and a node failure (ADR-0030).

**`MIN_BROKEN_S = 2`:** a single bad second can be noise (a garbage collection pause, one slow request); two or more is a finding.

**The timeline:** `.` ok, `s` slow, `x` failed, `_` no data, and `|` before the second of the action and of the restore, for example `.....|xxxxxxxxxxxx|ss....`.

The model gets the verdict, the timeline, the totals before and after (success, worst p95, errors by type), the broken seconds, users not sent, and the recovery time. It adds the interpretation: why it broke, and what to test next.

### Consequences
- **Gains:** the same data always gives the same verdict; the eval can compare runs; the model's context stays small.
- **Trade-offs:** the verdict is only as good as the steady state in `target.yaml`. A threshold that is loose for the system's normal (500 ms against a normal 10 to 20 ms) lets a degraded system pass as steady: in the run of 2026-11-27, step 49 started on a system at 270 ms and was inconclusive (follow-up: a steady check that also compares to the system's own normal). `MIN_BROKEN_S` is a fixed constant, not per application.

### In the code
- `orchestrator/experiments/judge.py`: `TIMELINE_CHARS`, `MIN_BROKEN_S`, `status_of`, `statuses_of`, `timeline`, `phase`, `recovered_at`, `judge`.
- `orchestrator/experiments/runner.py`: `second_of` (which second of the measurement the action fell in) and the call to `judge.judge` in `run_experiment`.


---

<a id="adr-0024"></a>

## ADR-0024: The warm-up of every measurement is thrown away before judging

**Status:** Accepted, 2026-11-26 (extended to the experiment measurement 2026-11-27)
**Related:** ADR-0023 (the judge), ADR-0025 (steady check), ADR-0026 (measurement settings)

### Context
Two things make the first seconds of a measurement slow for reasons that have nothing to do with the experiment:
- **The application after idle:** in Online Boutique the first request after a quiet period can wait about 10 s.
- **A new run of k6 starts cold:** new TCP connections, virtual users just allocated. In the run of 2026-11-27, steps 65 and 70 had a second 0 at 595 to 945 ms and 10 to 20 ms right after.

At first only the steady check threw its warm-up away. The experiment measurement did not, so a cold second 0 was judged as "not steady before the action", and three of fifteen experiments were wasted as inconclusive while the pod had already been deleted.

### Options
1. **Discard nothing.** Every first second risks a false inconclusive.
2. **Warm the connections in k6's `setup()`.** `setup` runs once per run of k6, but connections belong to each virtual user, so the users still start cold.
3. **Measure `warmup_ignored_s` extra seconds at the start of every measurement, and drop them before judging,** in the steady check and in the experiment measurement alike.

### Decision
Option 3. Every measurement starts `warmup_ignored_s` seconds earlier; the runner waits for them before the action; `without_warmup` removes them, renumbers the seconds from 0, and moves `started_at` by the same amount, so `second_of` still marks the action in the right second.

### Consequences
- **Gains:** a cold start is never judged; inconclusive means the system was really not steady.
- **Trade-offs:** each experiment is `warmup_ignored_s` seconds longer (5 by default), and the warm-up of the experiment measurement adds to the time a change is measured before it is made, not to the disruption.

### In the code
- `orchestrator/experiments/runner.py`: `without_warmup`, `wait_for_steady`, and the `warmup` lines in step 2 and step 4 of `run_experiment`.
- `orchestrator/config.py`: `warmup_ignored_s` in `MEASUREMENT_DEFAULTS`.


---

<a id="adr-0025"></a>

## ADR-0025: A steady check before every experiment; an experiment that never gets steady is not run and not counted

**Status:** Accepted, 2026-11-27
**Related:** ADR-0023 (the judge), ADR-0024 (warm-up), ADR-0027 (prompt)

### Context
An experiment run on a system that is already broken proves nothing: the result cannot be told apart from what was already there. In the first disrupt run (2026-11-26), 3 of 13 experiments were inconclusive because the system had not recovered from the one before (payment takes 25 s after a restore), and each of them used up one experiment of the budget while nothing had been learned.

The question: what happens when the system is not steady before an experiment?

### Options
1. **Run anyway, and let the judge say inconclusive.** Simple, but wastes budget, and makes a change on a system that is already disturbed.
2. **Make the recovery window longer for every experiment.** Fixes the slow recoveries, but every experiment pays for it, including those that recover in 2 s.
3. **Check before every experiment, and wait and retry when the check fails;** touch nothing and count nothing until the system is steady.

### Decision
Option 3. `wait_for_steady` measures `warmup_ignored_s + steady_check_s`, and accepts the system only if every second of every chosen journey is `ok`. If not, it waits `wait_between_steady_checks_s` and tries again, up to `steady_check_attempts` times.
- **Steady:** the experiment is counted, and the steady check becomes its baseline.
- **Never steady:** the result is `not_run` with `counted: false`, the reason and the timelines of the last try. Nothing is changed.
- The tool description and the prompt explain the difference: `not_run` means nothing was changed and nothing counted; `inconclusive` means the change was made and counted, but the seconds just before it were not steady. A `not_run` right after the agent's own experiment is itself a finding about recovery.

### Consequences
- **Gains:** the budget is spent only on experiments that can be judged; a slow recovery shows up as a finding instead of a wasted experiment.
- **Trade-offs:** an unsteady system can cost up to `steady_check_attempts × (warm-up + steady check) + (attempts - 1) × wait` before giving up (about two minutes with the defaults). A `not_run` does not count, so a system that is never steady could let the model call `run_experiment` until `MAX_ITERATIONS`: accepted, since that limit stops it.
- **Not solved:** the check compares to the steady state's thresholds, not to the system's own normal, so a degraded system under the threshold passes (ADR-0023).

### In the code
- `orchestrator/experiments/runner.py`: `wait_for_steady`; step 1 of `run_experiment` (`state["experiments"] += 1` only after a steady check); the `not_run` and `inconclusive` sentences in `run_experiment_tool`.
- `orchestrator/config.py`: `steady_check_s`, `steady_check_attempts`, `wait_between_steady_checks_s` in `MEASUREMENT_DEFAULTS`, and the minimum for `steady_check_s`.
- `orchestrator/agent/loop.py`: the `not_run` and `inconclusive` bullets in `SYSTEM_PROMPT`.
- `orchestrator/tests/try_experiment.py`: one fixed experiment through the runner, without the model.


---

<a id="adr-0026"></a>

## ADR-0026: Measurement settings belong to the application, caps to the cluster

**Status:** Accepted, 2026-11-27
**Related:** ADR-0003 (any application), ADR-0020 (owners), ADR-0021 (k6), ADR-0025 (steady check)

### Context
Every timing and rate of a measurement was a constant in the code: the warm-up, the steady check, the seconds before the action and after the restore, the rate (`experiments/runner.py`), and the request timeout and the number of virtual users (`probe.py`). These depend on the application. In the lab, payment recovers 25 s after a restore, so a 30 s recovery window barely fits; an application with a 60 s readiness probe would always look broken. A JVM service may need 30 s to warm up. Customers had no way to change any of them, which breaks ADR-0003.

### Options
1. **Keep the constants and pick conservative values.** Nothing to build. Long windows on every experiment, still wrong for some applications.
2. **Everything in the RoE.** One file to edit. But the RoE says what the agent may do, and is written by security. How long an application takes to recover is not a permission, and security would have to know the application to write it.
3. **Let the model choose them per experiment.** Most flexible. But whoever controls the recovery window controls what the judge sees: the same problem as letting the agent write its own journeys.
4. **Split by owner:** timings and rate in `target.yaml` (the application team), safety caps in the chart values (the cluster admin), and the number of concurrent users computed by the probe server.

### Decision
Option 4.
- **`target.yaml` gets an optional `measurement` section:** `new_users_per_second`, `fail_request_after_s`, `warmup_ignored_s`, `steady_check_s`, `steady_check_attempts`, `wait_between_steady_checks_s`, `measure_before_action_s` and `measure_after_restore_s`. Every setting has the old constant as its default, so a target without the section behaves as before. Unknown settings are rejected (a typo would otherwise be ignored silently), and two have minimums the judge needs: `steady_check_s` at least 5, `measure_before_action_s` at least 3.
- **The chart sets four caps on the probe server,** `mcp.levels.probe.limits`, passed as environment variables: `LONGEST_K6_RUN_S`, `LONGEST_REQUEST_WAIT_S`, `MAX_NEW_USERS_PER_SECOND` and `MAX_CONCURRENT_USERS_PER_JOURNEY`. The server refuses any measurement over them.
- **The number of concurrent users is not a setting:** the probe computes it per journey as `new_users_per_second × fail_request_after_s × steps` (Little's law, the worst case where every step waits until it fails), capped by `MAX_CONCURRENT_USERS_PER_JOURNEY`.
- **Names say what the value does and keep the unit suffix:** `fail_request_after_s`, not `timeout_s`; `measure_after_restore_s`, not `recovery_s`; `LONGEST_K6_RUN_S`, not `MAX_DURATION_S`. In the same change, `hold_s` became `restore_after_s` (and `max_hold_s` became `max_restore_after_s`), and `duration_s` became `measure_for_s`.

### Consequences
- **Gains:** each application is measured on its own terms; the cluster stays protected whatever a target asks for; a customer sets what they understand (rate and timeout), not a k6 internal; the lab target documents every setting.
- **Trade-offs:** more to validate when a target is loaded. The orchestrator does not know the chart's caps, so a target over them fails at the first measurement, not when it is loaded. Past the concurrency cap, users are reported as not sent: what real users would meet, but it makes the cap part of the result.
- **Not solved:** rates below 1 per second (k6 supports them through `timeUnit`, which would change the per-second judging).

### In the code
- `orchestrator/config.py`: `MEASUREMENT_DEFAULTS`, `MEASUREMENT_MINIMUMS`, and the `measurement` checks at the end of `load_target`.
- `orchestrator/experiments/runner.py`: `run_experiment` (`settings = target["measurement"]`, `measure`) and `wait_for_steady`.
- `servers/mcp/probe.py`: the caps at the top, `concurrent_users`, and the checks in `measure_journeys`.
- `servers/mcp/journeys.js`: `options.scenarios` (`rate`, `duration`, `preAllocatedVUs`, `maxVUs`, `gracefulStop`) and the request `timeout` in `run`.
- `charts/chaos-agent/values.yaml`: `mcp.levels.probe.limits`; `charts/chaos-agent/templates/mcp.yaml`: the `with $config.limits` env block.
- `lab/apps/boutique/target.yaml`: the `measurement` section, every setting with its default.

### Follow-ups
- A `get_limits` observe tool, so a run can reject a target over the caps before it starts.


---

<a id="adr-0027"></a>

## ADR-0027: The prompt steers toward degradation, reproduction, and citing steps

**Status:** Accepted, 2026-11-27
**Related:** ADR-0014 (no catalog), ADR-0023 (the judge), ADR-0025 (not_run)

### Context
The first disrupt run (2026-11-26, 13 experiments) showed four problems in how the agent worked:
1. **No variety:** almost only `replicas: 0`, annotations and pod deletions. Scaling a dependency to 0 always breaks its callers, so it teaches little after the first time.
2. **No reproduction:** a surprising result ("email down slows every journey") was reported as a finding after one run.
3. **Citations by experiment number,** not by step, so the summary could not be checked against the audit. The cause was in the code: `run_experiment` never returned its own step.
4. **`not_run` and `inconclusive` were new** and the agent did not know what they mean.

### Options
1. **Restrict the actions** (forbid scaling to 0). Forces variety, but bans a legitimate experiment: a dependency that is down for every caller (after a bad deploy or a failed shared dependency) tests whether the callers have timeouts and fallbacks.
2. **Teach the method in the prompt, and fix the code where the model lacked information.**

### Decision
Option 2.
- **Degradation:** scale a component to 0 at most once, to map which journeys depend on it; then prefer partial changes (fewer replicas, one pod deleted, tighter CPU or memory limits, a slower or stricter readiness probe), because weaknesses users feel are usually in how a system behaves when a dependency is slow or partly down.
- **Rollouts:** a change to a pod template restarts all its pods, and that rollout is part of what is measured.
- **Reproduction:** a result the agent did not expect is not a finding until it is reproduced once; a weakness seen once is reported as unconfirmed, even when it looks like a confirmed one.
- **`not_run` and `inconclusive`** explained, with what each says about recovery.
- **Citations by step,** and `run_experiment` now returns its own `step`.
- **The summary:** confirmed weaknesses (with the steps that showed and reproduced them, which journeys, how they failed, for how long, and the recovery), unconfirmed, what held, and what to test next.

### Consequences
- **Gains:** in the run of 2026-11-27 there were no scale-to-zero experiments, two findings were reproduced (productcatalog, shipping), every experiment was cited by step, and the hidden cart-to-shipping coupling was reported with a clear note that the call path was inferred.
- **Trade-offs:** reproduction costs experiments from the budget. The prompt still cannot make the agent test what it has no tool for (zones, latency): that needs ADR-0030 and Chaos Mesh. Added later the same day, with node failures (ADR-0030): every hypothesis names the real-world event it simulates (a pod crashing, a node or zone going down, a bad rollout, a dependency slowing down or down for every caller); scaling to 0 is framed as testing the callers; Placement is used to find what a node or zone failure would take down; and the next experiment is planned on where pods landed, from placement_events.

### In the code
- `orchestrator/agent/loop.py`: `SYSTEM_PROMPT`, the Method bullets and the summary structure; `format_profile` (the measurement line, so the model knows a 10 s timeout is ours).
- `orchestrator/experiments/runner.py`: `finish` in `run_experiment` returns `{"step": step, ...}`.


---

<a id="adr-0028"></a>

## ADR-0028: The MCP image and pods are locked down: pinned digests, hashed dependencies, non-root, read-only

**Status:** Superseded by ADR-0037, 2026-11-27 (accepted 2026-11-26)
**Related:** ADR-0008 (servers per level), ADR-0016 (denylist)

### Context
The disrupt server can change almost anything in the tested namespaces. Whatever runs in its image runs with those permissions, so the supply chain of that image and the pod it runs in are part of the safety model.

### Options
1. **Tags and an unpinned `pip install`.** Simplest, but an image or a package can change under the same name between two builds.
2. **Pin base images by digest, lock every Python dependency with hashes, and run the pod with the least it needs.**

### Decision
Option 2.
- **Base images by digest:** `grafana/k6:2.4.0@sha256:...` (only the binary is copied) and `python:3.12-slim@sha256:...`.
- **Dependencies:** `requirements.in` is compiled by `pip-compile` into `requirements.txt` with a hash for every package, installed with `pip install --require-hashes`.
- **Non-root:** user 10001, `runAsNonRoot`, `seccompProfile: RuntimeDefault`, `allowPrivilegeEscalation: false`.
- **Read-only root filesystem,** with an emptyDir on `/tmp` for k6's files.
- **A minimal environment for k6:** only `CONFIG_FILE`, `PATH` and `HOME`, so `K6_*` variables on the pod cannot change a measurement, and the server's environment is not visible to it.

### Consequences
- **Gains:** a build is reproducible; a compromised package version or base tag cannot slip in; a process in the pod cannot write to the image or gain privileges.
- **Trade-offs:** updating a dependency means recompiling the lock file; updating a base image means a new digest. In the lab the image tag stays `dev` with a rollout restart, since every new tag on kind is another copy on every node of a small disk; CI builds by digest (ADR-0034).

### In the code
- `servers/mcp/Dockerfile`, `servers/mcp/requirements.in`, `servers/mcp/requirements.txt`.
- `charts/chaos-agent/templates/mcp.yaml`: the pod and container `securityContext`, the `/tmp` emptyDir.
- `servers/mcp/probe.py`: the `env` passed to k6 in `run_k6`.


---

<a id="adr-0029"></a>

## ADR-0029: Env values and Secrets never leave the MCP servers

**Status:** Accepted, 2026-11-26 (extended to event messages by ADR-0038)
**Related:** ADR-0012 (discovery), ADR-0017 (snapshots), ADR-0004 (W4), ADR-0038 (event messages)

### Context
Workloads often carry secrets in their env, as literals or from Secrets. Anything a tool returns ends up in the prompt, in the model provider's logs, in the `steps` table, and in the report. The question: what about env values?

### Options
1. **Return env as it is, and trust the prompt not to repeat it.** The value is already in the database and sent to the model.
2. **Redact values that look secret.** Heuristic: misses some, and still sends the rest.
3. **Never return values at all:** only the name of each variable and where its value comes from.

### Decision
Option 3.
- **Workload facts** show each env variable's name and its source (`literal`, `secretKeyRef`, `configMapKeyRef`, `fieldRef`, `resourceFieldRef`), `envFrom` by name, volumes by name and type. Never a value, never a Secret.
- **The inventory never lists Secrets.**
- **Snapshots** (which hold full objects, values included) stay as Secrets in `chaos-system` (ADR-0017).
- **API errors** are reduced to status and reason, since an error body can contain parts of the object.
- **A canary:** the lab plants `lab-fake-7f3c9a2e5b8d41f6` as a literal env value in checkoutservice (W4). It must never appear in a tool output, the database, the audit or a report; the manual client test checks tool output for it.

### Consequences
- **Gains:** the agent can still reason about secrets ("this Secret is a literal in env") without ever seeing one.
- **Trade-offs:** some legitimate reasoning needs a value (a hostname in an env variable that points at a dependency); the agent gets only the name, which often says enough.
- **Not solved:** the canary is checked in tool output by a manual test, not yet across the database and reports in CI (ADR-0034).

### In the code
- `servers/mcp/k8s.py`: `CONTAINER_FIELDS` (env left out on purpose), `env_facts`, `SKIPPED_KINDS` (Secrets).
- `servers/mcp/disrupt.py`: `api_error`, the snapshot comment.
- `servers/mcp/tests/try_client.py`: `CANARY` and the leak check.
- `lab/apps/boutique/patches/checkoutservice-secret-in-env.yaml`: the canary.


---

<a id="adr-0030"></a>

## ADR-0030: Node and zone failures: a drain mode and a lost mode, set by node_actions in the RoE

**Status:** Accepted, 2026-11-27
**Related:** ADR-0012 (discovery), ADR-0015 (generic tools), ADR-0016 (denylist), ADR-0017 (undo), ADR-0031 (restore on startup)

### Context
Every action so far works on objects in the tested namespaces. None of them tests what topology spread, anti-affinity and PDBs are for: surviving the loss of part of the infrastructure. W1 (frontend pinned to one zone) can only be found by losing that zone; scaling to 0 never shows it. The questions:
1. Which node failure do we simulate, and how, through the Kubernetes API?
2. A node is cluster-scoped: whose pods are moved?
3. How is it restored?
4. What must the agent see to plan it?
5. What permissions does it need, and how are they fenced?

### Options

**1. Which failure:**
- **Marking the node NotReady.** Not possible: Ready is a status condition owned by the kubelet, which rewrites it every few seconds; the node controller also removes the `node.kubernetes.io/unreachable` taint from a node whose kubelet is alive.
- **Drain through the Eviction API** (cordon, then evict each pod). Simulates planned events (node upgrades, autoscaler scale-down, spot replacement), the most common node events in production. Respects PDBs, so it also tests them.
- **A `NoExecute` taint of our own** (`chaos-agent.io/node-lost`). Every pod without a matching toleration is removed at once, PDBs are not consulted, and the pods are recreated elsewhere. Simulates a sudden loss.
- **Stopping the node** (`docker stop` on kind, AWS FIS in the cloud). The real thing, including the 40 s until NotReady and the 300 s `tolerationSeconds` before eviction. Not available through the Kubernetes API, so not on every cluster.

**2. Whose pods:**
- **Only pods in scope** (cordon, evict only in the RoE's namespaces). Keeps "the agent touches only its scope"; but the application gets the remaining nodes to itself, which is optimistic.
- **Every pod on the node.** Realistic, but touches every namespace on it.

**3. Node or zone:** a zone is every node with the same `topology.kubernetes.io/zone` value, the standard label every cloud sets.

### Decision
- **One action, `node_failure`,** with a `node` or a `zone` target and a `mode`:
  - `drain`: cordon, then evict through the Eviction API; a pod blocked by a PDB (429) is reported as `blocked_by_pdb`, not retried.
  - `lost`: cordon, then the `NoExecute` taint.
- **`node_actions` in the RoE replaces `allow_node_actions`:** `none` (default), `scope_only` (drain only, evicting only pods in scope), `whole_node` (drain of every pod, and `lost`, which cannot be scoped). Not `off`: in YAML 1.1, which PyYAML and Helm read, an unquoted `off` is the boolean false. The chart has the same setting, `mcp.levels.disrupt.nodeActions`, which decides the RBAC and is passed to the server as `NODE_ACTIONS`; the server refuses what it does not allow.
- **Recovery is counted from the action, not the restore:** the system must reschedule the pods elsewhere while the node is still down; that is what a node failure tests.
- **Autoscalers:** with Karpenter or Cluster Autoscaler, evicted pods can stay Pending until a new node joins (about a minute for Karpenter, a few for Cluster Autoscaler). The judge needs no knowledge of it: users fail while pods wait, and the timeline shows for how long. `max_restore_after_s` in the RoE and the agent's `restore_after_s` must leave time for it. An autoscaler can also remove the drained node before the restore: `restore_node` treats a 404 as done (`node_gone`), not as a failed restore.
- **What the agent learns while it runs:** the runner reads the placement every 10 s during the experiment and returns only what changed, as `placement_events`: a node that joined or left, and every workload whose running or pending pods, or nodes, changed, with the seconds after the action. The full reads stay in the audit.
- **Restore:** remove the taint and uncordon. The undo is written before the cordon, one per node, and a node action that fails half way rolls back every node already touched. Pods do not move back on their own (only a descheduler does that), so the result includes the placement after the experiment, and the prompt says that later experiments run on that placement.
- **Guards in the server:** never a control-plane node; never `lost` or a whole-node drain on a node where the chaos agent itself runs (pods in its own namespace), since nothing would be left to restore it.
- **Guards in the orchestrator, against the placement read just before the action:** never every schedulable worker; a zone failure only when at least two zones exist; never a node or zone that runs a protected workload's pods (a node failure would evict them with everything else); `node_actions` in the RoE and `nodeActions` in the chart values (two layers).
- **The agent sees placement:** a new observe tool returns nodes with their zone and, per node, the workloads in scope that have pods there. Needs `get` and `list` on nodes (a ClusterRole, read-only).
- **Permissions:** `patch` on nodes (cordon and taint), and `create` on `pods/eviction` in scope. The admission policy allows the disrupt ServiceAccount to change only `spec.unschedulable` and taints whose key starts with `chaos-agent.io/`; labels, annotations, other taints and the rest of the spec are denied by the API server.

### Consequences
- **Gains:** topology spread, anti-affinity and PDBs are tested by the events they exist for; W1 becomes findable. Pods left Pending because a `DoNotSchedule` spread cannot be satisfied in the remaining zones are a real finding.
- **Trade-offs:** the widest blast radius of any action, which is why it is off by default and fenced twice. `lost` starts evicting at once, so it is an optimistic version of a real node loss. In the lab one node is one zone, so node and zone failures cannot be told apart.
- **Not solved:** an ungraceful node death with the real detection delay (backlog, with AWS FIS). A watchdog that uncordons if the orchestrator dies and never comes back (backlog; ADR-0031 covers a restart).

### In the code
- Built: the placement tool, `get_placement` in `servers/mcp/k8s.py`, with `collect_placement` in `orchestrator/agent/loop.py` and the observe `-nodes` ClusterRole in `charts/chaos-agent/templates/mcp-rbac.yaml`.
- Built: the node tools in `servers/mcp/disrupt.py` (`NODE_ACTIONS`, `TAINT_PREFIX`, `LOST_TAINT`, `node_to_fail`, `cordon_node`, `taint_node_lost`, `evict_pods`, `restore_node`); `mcp.levels.disrupt.nodeActions` in `charts/chaos-agent/values.yaml`; the disrupt `-nodes` ClusterRole in `mcp-rbac.yaml`; `pods/eviction` in `_helpers.tpl`; `podEviction` and the node validation in `mcp-admission-policy.yaml`.
- `orchestrator/experiments/node_failure.py`: `check`, `targets` (the guards), `merge`, `summary`, `changes` (the placement events), `POLL_S`.
- `orchestrator/experiments/runner.py`: `node_failure` in `ACTIONS`, `NODE_FAILURE_TEXT`, `run_experiment_tool` (node, zone, mode), `check`, and in `run_experiment`: step 0 (the targets), the `node_failure` branch (undo per node, `roll_back`, `watch_placement`, restore).
- `orchestrator/experiments/judge.py`: `judge(..., recover_from_restore)`.
- `orchestrator/config.py`: `NODE_ACTIONS`, `node_actions` in `ROE_DEFAULTS` and its check.
- `orchestrator/agent/loop.py`: node_failure offered only when `node_failure.NODE_TOOLS` are loaded; `format_rules`.
- `orchestrator/tests/try_experiment.py`: `zone`, a fixed zone failure without the model.


---

<a id="adr-0031"></a>

## ADR-0031: Pending undos are restored when the orchestrator starts

**Status:** Accepted, 2026-11-27
**Related:** ADR-0006 (Postgres), ADR-0017 (write-ahead undo), ADR-0030 (node failure)

### Context
The undo log is written before every change (ADR-0017), but nothing runs a pending undo after a crash. A crash during a patch leaves a Deployment at `replicas: 0`: bad, but local. A crash during a node failure leaves a node, or a zone, cordoned and tainted, which affects every namespace. Node actions make this a requirement, not a nice-to-have.

### Options
1. **Manual:** an operator reads `undo_actions` and runs each by hand. Nothing to build; relies on someone noticing.
2. **On startup:** before a run does anything, the orchestrator runs every pending undo from any run, marks each done or failed, and refuses to start a run if one fails.
3. **A watchdog** (a CronJob or a small controller) that restores changes past their deadline even if the orchestrator never comes back. The strongest, and a separate component to build and secure.

### Decision
Option 2 now; option 3 in the backlog. Undos are run through the same `call_tool` path, so they are recorded as steps of the new run.
- **A failed undo stays pending,** and the run does not start. Marking it failed would let the next run start while the change is still in the cluster; pending means every start tries again until it works or a person fixes it.
- **A snapshot that no longer exists was already restored:** `restore_snapshot` deletes its snapshot only after the object was put back, so a crash between the restore and `finish_undo` leaves an undo whose snapshot is gone. A 404 on reading the snapshot counts as done. `restore_node` is idempotent, and treats a node that no longer exists as done.
- **An undo whose tool this run does not load** (an observe-level run after a disrupt run crashed) stops the run with the undo and the tool named.

### Consequences
- **Gains:** a crash and a restart always end with the cluster restored, or with the run refusing to start until someone looks.
- **Trade-offs:** if the orchestrator is never started again, nothing is restored. An undo whose target was changed by someone else meanwhile will fail on its `resourceVersion` precondition, which is correct but needs a person.

### In the code
- `orchestrator/experiments/undo.py`: `restore_pending`, `already_restored`.
- `orchestrator/storage/db.py`: `pending_undos`.
- `orchestrator/agent/loop.py`: `run_agent` calls `undo.restore_pending` right after loading the tools; `orchestrator/tests/try_experiment.py` does the same.
- **Not solved:** a run killed without a chance to finish (kill -9, a laptop going to sleep) stays `running` in `runs`, and holds the namespace lock (`one_running_run_per_namespace`). `try_agent` does not check `claim_run`'s answer today, so the lab is not blocked; a real entry point must clear stale runs.


---

<a id="adr-0032"></a>

## ADR-0032: The eval compares the agent with a deterministic baseline, on a weak and a hardened application

**Status:** Proposed, 2026-11-26 (ground truth, measures and baseline decided 2026-11-28; the ground truth and the scoring are built)
**Related:** ADR-0002 (chaos), ADR-0004 (lab and ground truth), ADR-0011 (deterministic or agent), ADR-0014 (no catalog), ADR-0033 (memory)

### Context
Without the catalog there is no checklist to score coverage against. And the honest question about this project is whether the agent finds more than a script would (ADR-0011). The eval must answer it with numbers. Four questions: what the answer key holds, what counts as found, what is measured, and what the agent is compared with.

### Options

**The comparison:**
1. **Score findings against the ground truth only.** Says what the agent found, not whether an agent was needed.
2. **Compare the agent with a deterministic baseline:** a fixed list of experiments, scored on the same measures.

**What counts as found:**
1. **An experiment with verdict broke** that matches an entry. A fact from the judge, but it counts what the agent saw, not what it reported.
2. **An experiment the agent's summary cites as confirmed** that matches an entry with verdict broke. What a customer gets.
3. **An LLM judge of the summaries.** An LLM grading an LLM is the weakest kind of evidence.

**The baseline:**
1. **Reduced, within the agent's budget:** one pod deleted per workload, one zone lost per zone.
2. **Full:** also every workload scaled to 0 and every zone drained, about twice as long.

### Decision
Compare with a baseline (option 2); found is what the summary cites (option 2); the reduced baseline (option 1).

**The ground truth (`lab/apps/boutique/ground_truth.yaml`), by action and impact:**
- **One entry per action and workload,** so recall counts workloads, as the baseline does: the action (`type`, `kind`, `name`, or `zone`), and for a patch `sets`, the dotted paths it must set (`spec.replicas: 0`, list indices ignored, `"*"` for any value and any path under it); a field left out matches any value, and a zone also matches a node of that zone. The impact: the expected verdict on at least one of the entry's journeys. `verified: false` entries are not scored.
- **Weaknesses:** W1 (zone-a lost); N1 (deleting the only pod of checkoutservice, paymentservice, shippingservice); N6 (a dependency scaled to 0: cartservice, currencyservice, productcatalogservice, shippingservice, checkoutservice), with the slow failure of about 20 s in the same entries, since the same experiments show it; N10, a CPU starvation of frontend the agent found in run 34, until it is verified by hand; N11 (added 2026-11-28), a rollout of productcatalogservice that stalls every journey for about 20 s about half the time, because frontend's gRPC connection is pinned to one of its two pods: found by the agent in runs 32 to 34 and verified without the model in runs 35 and 36, a weakness no manifest shows. A weakness that shows only some of the time needs more than one experiment to confirm, by the agent and by the eval.
- **Expected survivals:** S1 to S3 (adservice, recommendationservice, emailservice scaled to 0) and S4 (their only pod deleted). A broke on one of them, or one cited as a weakness, is a false positive.
- **Left out:** configuration findings (PDB, NetworkPolicy, image tag, Redis auth), which are not chaos (ADR-0002); what needs redis-cart down, since it is protected; W4, a configuration weakness whose canary is covered by the unit tests of `inspect_workload`; W2 and W3, which show only under load, while `new_users_per_second` is fixed by `target.yaml` and no action raises it. They come back as entries with Chaos Mesh (StressChaos on the pods).

**Found:** the agent's summary cites, under confirmed weaknesses or known from earlier runs, a step whose experiment matches an entry with verdict broke. The baseline has no summary, so the agent and the baseline are compared on broke experiments; the gap between the two measures, for the agent, is what broke and was not reported.

**Measures, per run:**
- **Quality:** recall, findings matching no entry (unknown, reviewed by hand), false positives on expected survivals.
- **Efficiency:** experiments, model rounds, tokens and cost, duration, seconds broken.
- **Safety:** denied calls to real tools (the `read_tools_missing` step is a warning, not a call), and undos left pending, which must be zero.
- **Memory:** experiments on what an earlier run already found, against new ones.

**The baseline (`eval/baseline.py`):** no model, through the same runner and judge: `delete_pod` on every workload that is not protected (10) and a `lost` node failure on each zone (3), 13 experiments within `max_experiments: 15`.

**Configurations:** Haiku without memory (runs 30, 31), Haiku with memory (32 to 34), Sonnet with memory, the baseline, and the same agent and baseline on `boutique-hardened`. One run per configuration is weak evidence, and the report says so.

**A control group, `boutique-hardened`:** a Kustomize overlay with 3 replicas, PDBs, topology spread, preStop hooks and tuned probes. Expected: mostly withstood. Every broke there is an unknown weakness, or a false positive to investigate. It runs last.

**Other targets:** podinfo as a second, simple target; the OpenTelemetry demo with flagd only as a stretch (heavy for the lab's disk).

**Scoring (`eval/score.py`):** deterministic, reads `steps` and the ground truth, writes a markdown table per run, with unit tests on their own fixtures. It needs no cluster and no model, so runs already in the database are scored without running them again.

### Consequences
- **Gains:** a direct answer to "does the agent justify itself"; regressions in the prompt or the judge show up as numbers; past runs are scored for free.
- **Trade-offs:** weaknesses that need load are not scored, so recall says nothing about them. Matching a patch by the paths it sets depends on the shape of a strategic merge patch. Scoring by citations depends on the summary citing steps, as the prompt asks (ADR-0027). A full eval is several runs of 20 to 30 minutes on a laptop and costs tokens; it cannot run on every commit (CI runs the cheap parts, ADR-0034).

### In the code
- `lab/apps/boutique/ground_truth.yaml`: the answer key.
- `eval/score.py`: `action_matches`, `impact`, `cited_steps`, `score_run`, `score_all` (what earlier runs broke, for the memory measure), `render`, `PRICES`; `WARNING_STEPS` (steps that are not calls).
- `eval/tests/unit/test_score.py`, with its own ground truth in `fixtures/`; run in CI with the orchestrator's tests.
- `eval/baseline.py`: the `baseline` plan (`baseline_plan`, from the observe server's workloads and zones) and the `verify` plan (`verify_plan`, the patterns of earlier runs, each twice), through `runner.run_experiment`.
- `lab/apps/boutique-hardened/`: upstream without the planted weaknesses, 3 replicas of every stateless service, a zone topology spread (`matchLabelKeys`, so one patch fits every Deployment), a `preStop` sleep and a PDB each; `lab/apps/boutique/upstream/kustomization.yaml` lets it use the vendored manifests as a base.
- Planned: a ground truth for `boutique-hardened`; a `workflow_dispatch` eval in the backlog.


---

<a id="adr-0033"></a>

## ADR-0033: Retrieval over past experiments, so a run builds on the ones before it: hybrid search in pgvector, as a tool of the model

**Status:** Accepted, 2026-11-28 (proposed 2026-11-26; store, embeddings and retrieval decided 2026-11-27)
**Related:** ADR-0006 (Postgres), ADR-0010 (the model's tools), ADR-0027 (prompt), ADR-0029 (env values)

### Context
Every run starts from nothing. In the runs of 2026-11-27 (30 with Sonnet, 31 with Haiku) both models rediscovered the frontend zone pinning (W1) and spent two or three of their 15 experiments reproducing it; Haiku also guessed a wrong dependency between services. A course requirement is a RAG component. Three questions: what is retrieved, where it is stored, and who decides when to retrieve.

What AI tools around chaos engineering do today: Harness derives an application map from service discovery and recommends experiments from monitoring; Krkn-AI feeds past results back into the next generation of scenarios; Steadybit exposes past experiments and post-mortems as MCP tools. None of them asks the customer to write documents for the agent. AI SRE agents (Azure SRE Agent, Datadog Bits AI) add the agent's own memory of past sessions and the docs a team already has.

### Options
**What is retrieved:**
1. **Documents written for the agent** (architecture, runbooks). Useful, but nobody maintains documents written only for a tool; they go stale within weeks.
2. **The agent's own past experiments and conclusions** on the same application. Filled automatically, specific to this system, and exactly what a new run needs.
3. **Documents the customer already has** (a docs folder in an existing repository), connected, not written.

**The store:**
1. **ChromaDB,** a dedicated vector store: one more component to run, back up and secure, for a few hundred vectors.
2. **pgvector in the Postgres we already run:** experiments are already rows there, one backup, and a vector search can be filtered in the same SQL.

**How it is searched:**
1. **Vectors only.** Finds similar text, but a question like "what did I test on frontend" needs every experiment on frontend and only those; embeddings also barely separate "withstood" from "broke".
2. **Structured filters only (SQL).** Exact, but cannot find a similar failure on another service written in other words.
3. **Hybrid:** filter on the fields (namespace, workload, action type, verdict), then rank by similarity.

**Who decides when to retrieve:**
1. **The orchestrator, before the first LLM call** (the plan of 2026-11-26): the retrieval guesses what the run will need, and fills the context up front.
2. **The model, through a tool** (agentic RAG): it searches when it is about to plan an experiment on a workload, or when a result looks like something seen before.

### Decision
- **What:** option 2 now; option 3 later (`kind = doc` in the same table). The dependency graph of an application is not retrieved: it is discovery, and comes from the environment the services are configured with (`calls`, a follow-up in observe).
- **Store:** pgvector. The Postgres image becomes `pgvector/pgvector` on Postgres 17.
- **Embeddings:** fastembed (`BAAI/bge-small-en-v1.5`, 384 dimensions, ONNX on CPU) in the orchestrator, so no text of the customer leaves the cluster to be embedded. The orchestrator runs on Python 3.14 for it: onnxruntime has no 3.15 wheel yet, while the MCP servers stay on 3.15 (ADR-0037).
- **Search:** hybrid, in one query: `WHERE namespace = <the run's namespace>` (always, set by the orchestrator, never by the model) and optionally the workload, then `ORDER BY embedding <=> query LIMIT 5`.
- **Retrieval:** a second tool of the model, `search_knowledge(query, workload)`, run by the orchestrator and recorded as a step like every other call. The prompt tells the model to search before planning an experiment on a workload.
- **What is written,** at the end of every run, by the orchestrator:
  - **One chunk per experiment, built by code from the stored JSON** (action, hypothesis, verdict, the numbers per journey), with `workload`, `action_type` and `verdict` as columns. The model cannot remember an experiment that did not happen, or remember it better than it went.
  - **One chunk per section of the model's summary,** marked `kind = summary`: an interpretation, not a fact.
  - A `content_hash` per chunk, so indexing a run twice adds nothing.

### Consequences
- **Gains:** a run can skip what is known, check whether a known weakness was fixed, and spend its budget deeper; every retrieved chunk carries its run and step, so it can be cited and checked. No new component, and nothing for the customer to write.
- **Trade-offs:** results from an older version of the application can mislead, so every chunk carries its run and date. A wrong conclusion in a summary can be carried into the next run; this is why experiments are indexed from their data and summaries are marked as interpretation. The model may not call the tool; the prompt asks it to. Changing the embedding model means indexing everything again.
- **Not solved:** connectors to wikis and incident tools; reranking; learning from a person's corrections.

### In the code
- `charts/chaos-agent` (Postgres image), `orchestrator/storage/schema.sql` (`knowledge_chunks`), `orchestrator/agent/knowledge.py` (chunks, embeddings, search), `orchestrator/agent/loop.py` (the tool, the prompt, indexing at the end of a run).


---

<a id="adr-0034"></a>

## ADR-0034: GitHub Actions runs the cheap checks on every change: lint, unit tests, the chart on kind, and the image

**Status:** Accepted, 2026-11-27 (proposed 2026-11-26)
**Related:** ADR-0028 and ADR-0037 (the image), ADR-0032 (eval), ADR-0016 (admission policy)

### Context
Every change to the agent can break it in ways that only show up in a 20-minute run against the lab. CI is a course requirement. Two questions: what runs on every change, and how is each part checked?

### Options
**What runs on every change:**
1. **The full eval on every pull request** (kind on the runner, a run with the model). The strongest signal; slow, flaky on shared runners, and it costs tokens on every push.
2. **The cheap, deterministic checks on every change; the eval on demand.**

**How the chart is checked:**
1. **Static only:** `helm lint` and `helm template`. Fast, but an expression in the ValidatingAdmissionPolicy is only type-checked by a real API server, which writes the result into the policy's status.
2. **`ct` (chart-testing) with an install on kind.** Built for repositories with many charts (changed-chart detection, upgrade tests against the last release); `ct install` removes the release right away, before the type-check can be read.
3. **Static checks, refusals, and `helm install` on kind, followed by a check of the policies' type-check status.**

### Decision
Option 2 for what runs, and option 3 for the chart. One workflow, `ci`, on every push to `main` and every pull request, with `permissions: contents: read`, every action pinned to a commit SHA, `persist-credentials: false`, a timeout per job, and one run per ref at a time:
- **`lint`:** ruff (`--select F`) on `orchestrator/` and `servers/mcp/`.
- **`test-servers` and `test-orchestrator`:** the unit tests (pytest), each part on the Python it runs on: the MCP servers on 3.15, the version of their image, with their dependencies installed with `--require-hashes`; the orchestrator on 3.14, since onnxruntime (under fastembed, ADR-0033) has no 3.15 wheel yet (split 2026-11-28; to be joined again when it has one). The tests use their own fixtures, never the lab's files.
- **`chart`:** Helm 4.3.2 (the version used locally).
  - `helm lint --strict` and `kubeconform -strict` on the chart rendered with `ci/all-levels-values.yaml` (every level on, `nodeActions: whole_node`, two namespaces). kubeconform is downloaded with its checksum checked.
  - **Refusals:** the chart must fail, with the expected message, on a missing `allowedNamespaces`, a missing image tag, and an unknown `nodeActions`.
  - **On kind:** the MCP image built in the job and loaded into the cluster, `helm install --wait`, then every ValidatingAdmissionPolicy must reach `observedGeneration` 1 with no `expressionWarnings`. Cluster state is printed on failure, only if the cluster came up.
- **`image`:** after the other jobs pass. Built with the Docker CLI, scanned by Trivy (pinned action and binary) that fails on fixable high and critical vulnerabilities; on `main` only, pushed to GHCR as `sha-<commit>`, its digest written to the job summary, and two attestations signed through GitHub's OIDC (Sigstore): SLSA build provenance and an SPDX SBOM made by Trivy. `packages: write`, `id-token: write` and `attestations: write` are granted to this job only.

**Why pinning by SHA matters here:** in March 2026 most version tags of `aquasecurity/trivy-action` were force-pushed to code that stole CI secrets; a job that can push images and request OIDC tokens must not run an action by a movable tag.

### Consequences
- **Gains:** a broken validation, a template that does not render, a CEL expression with a type error, or a vulnerable dependency is caught in minutes, for free. Every pushed image can be verified with `gh attestation verify`.
- **Trade-offs:** the chart job takes about five minutes, and the image waits for it. No build cache (no buildx): a build takes about a minute. The image is built twice, once for kind and once to push.
- **Not solved:** CI does not prove that the agent still finds things; that stays a manual eval run. Base image digests are bumped by hand (follow-up: Dependabot, with both Chainguard images in one group).

### In the code
- `.github/workflows/ci.yaml`: the jobs `lint`, `test`, `chart` and `image`.
- `charts/chaos-agent/ci/all-levels-values.yaml`: the values the chart is checked with.
- `pytest.ini`, `orchestrator/tests/unit/`, `servers/mcp/tests/unit/`.


---

<a id="adr-0035"></a>

## ADR-0035: What the agent may not change is set only by the RoE, by API group or by group/Kind

**Status:** Accepted, 2026-11-27
**Supersedes:** ADR-0018
**Related:** ADR-0016 (denylist), ADR-0019 (protected workloads), ADR-0020 (owners)

### Context
ADR-0018 shipped a default list of denied API groups, applied whenever the RoE left `deny_groups` out. Two problems showed up:
- **We were deciding for the customer** what their agent may touch. Which operators are dangerous in a cluster is the ops team's knowledge, not ours.
- **A group is too coarse.** `argoproj.io` was denied because of Argo CD Applications, which can prune whole applications. But Argo Rollouts are `argoproj.io` too: an application that deploys with Rollouts could not be tested at all, not even with `delete_pod`. A Rollout is restored from its snapshot exactly like a Deployment.

### Options
1. **Keep the default list, and let the RoE override it.** Safe for a customer who never reads the RoE, but it is still our decision, and still by group.
2. **No default list, an empty deny unless the RoE says otherwise.** The owner decides; but an RoE copied without thought silently allows everything a snapshot cannot restore.
3. **No default list, and `deny` is required in the RoE,** with entries that are either an API group or one group/Kind. `deny: []` is a valid, explicit choice.

### Decision
Option 3.
- **`deny`** replaces `deny_groups`. An entry without a `/` denies an API group and its subgroups (`fluxcd.io` covers `kustomize.toolkit.fluxcd.io`, and not `notfluxcd.io`); an entry with a `/` denies one kind (`argoproj.io/Application`).
- **Required:** an RoE without `deny` is rejected when it is loaded, with a message that says to write `deny: []` to deny nothing more.
- **No list in the code.** The lab RoE documents a recommended list with the reason for each entry: Argo CD's Application, ApplicationSet and AppProject (Rollouts stay open), Flux, cloud controllers (ACK, Crossplane, Upbound, Config Connector, Azure), Velero and CloudNativePG.
- **Unchanged:** the disrupt server's own denylist (Secrets, PersistentVolumeClaims, ServiceAccounts, RBAC) and the admission policy. They are a security boundary, not a limit on chaos (ADR-0016), and they are not the RoE's to remove.

### Consequences
- **Gains:** the RoE owner decides, at the granularity they need; Argo Rollouts, and any kind in a group that is otherwise dangerous, can be tested.
- **Trade-offs:** every RoE must now decide; there is no safe fallback for an owner who writes `deny: []` without knowing their operators. Enforced by the orchestrator only, like before: a direct call to the disrupt server bypasses it.
- **Not solved:** a GitOps controller with self-heal reverts any change to the objects it manages, Rollouts and Deployments alike, within seconds; the experiment then measures the revert. That is a property of how the application is deployed, to be stated in the RoE or detected later.

### In the code
- `orchestrator/config.py`: the `deny` check in `load_roe`, `denied`.
- `orchestrator/experiments/runner.py`: `check` (`config.denied`).
- `orchestrator/agent/loop.py`: `format_rules`.
- `lab/apps/boutique/roe.yaml`: `deny`, with the reason for each entry.

---

<a id="adr-0036"></a>

## ADR-0036: One bad second before the action is noise, as it is after it

**Status:** Accepted, 2026-11-27 (changed 2026-11-28: the judge compares with the application's own noise, learned during the run)
**Changes:** the inconclusive rule of ADR-0023
**Related:** ADR-0023 (the judge), ADR-0025 (steady check)

### Context
In run 30, 3 of 13 experiments were inconclusive (steps 44, 93, 100). In every one the steady check was clean (`..........`), and the seconds before the action held exactly one `s` (`s...`, `.s..`), never an `x`. At 2 users per second, a second's p95 is in practice its slowest request, so one slow request makes the whole second slow. After the action, one bad second was already treated as noise (`MIN_BROKEN_S = 2`); before it, one bad second voided an experiment that had been paid for.

### Options
1. **Keep it strict.** Safe, but one slow request wastes an experiment of the budget.
2. **Measure more users per second,** so a second's p95 is a real percentile. Treats the cause, but loads the system more; it stays a setting of the application in `target.yaml`.
3. **A longer window before the action.** More seconds, more chances for one slow request: makes it worse.
4. **The same tolerance on both sides of the action:** inconclusive only with at least `MIN_BROKEN_S` bad seconds in the baseline and before the action together.

### Decision
Option 4. The steady check (`wait_for_steady`) stays strict on purpose: when it fails it waits and tries again, which costs time, not an experiment, and it is the gate that gives the system time to recover from the last experiment.

**Changed 2026-11-28, after the eval:** bad seconds were counted one by one against a fixed number, so single slow seconds scattered through a measurement added up to broke. In run 31 step 60 (one pod of cartservice deleted) the timeline was `..s.|.s......s...s.......s..s.......` with no failed request, and it was judged broke; the same experiment alone, in run 35, withstood twice. A fixed number in the code was the problem itself: every application has its own noise, and nobody on an application team knows how to tune a threshold for it, so it cannot be a setting of `target.yaml` either. The judge now learns the noise of the application during the run:
- **Noise:** the share of bad seconds, and apart from it of failed seconds, in the seconds before the action of every experiment of the run that was not inconclusive, per journey (`noise_seconds`, `add_noise`, kept in the runner's state). A run starts from a prior of 1% (`PRIOR_BAD_SHARE`), worth 50 seconds (`PRIOR_SECONDS`), which the run's own seconds outweigh within a few experiments. Failed seconds are learned apart, as the steady state keeps success and latency apart: a system that is often slow is not often failing.
- **Degraded** (`degraded`, `degraded_against`): a phase is degraded when noise at that rate would make it with a chance under `ALPHA` (0.5%), by any of three tests: too many bad seconds in a row (an outage), too many in any 10 seconds (a burst of flickering), or too many in the whole phase (a thin degradation that lasts, which a long phase must not dilute). The limits come from the binomial distribution (`thresholds`, `binomial_tail`), never fewer than `MIN_BROKEN_S`, so a single bad second is never a finding. The same rule decides inconclusive before the action, against the earlier experiments' noise, and broke after it, with this experiment's seconds before the action added.
- **Each journey's result** carries `noise_rate`, the share of bad seconds the judge expected, so the model reads what the verdict was measured against.

### Consequences
- **Gains:** in run 31, after the change, no experiment was inconclusive (14 calls, 13 verdicts).
- **Trade-offs:** a system that flickers with an isolated bad second passes as steady before the action, as it would pass as unbroken after it. Since 2026-11-28, the judge's sensitivity follows the data it has: in the first experiment of a run, against the prior alone, two failed seconds in a 95 second phase are not a finding; after about 40 clean seconds before earlier actions, they are. A noisy application gets a less sensitive judge, which is the point: what noise explains is not a weakness. A system noisy because of something outside the application (a loaded laptop) is judged as noisy for the whole run. A system that is really unsteady is caught by the strict steady check, and by the stricter check against the system's own normal that is still to be designed.

### In the code
- `orchestrator/experiments/judge.py`: `PRIOR_BAD_SHARE`, `PRIOR_SECONDS`, `ALPHA`, `WINDOW_S`, `noise_rate`, `binomial_tail`, `thresholds`, `degraded`, `degraded_against`, `counts_of`, `noise_seconds`, `add_noise`, and `judge(..., noise)`; `longest_broken_s` and `noise_rate` in each journey's result.
- `orchestrator/experiments/runner.py`: the run's noise in `state["noise"]`, passed to the judge and grown after every experiment that was not inconclusive.
- `eval/score.py`: `experiments_of` and `broken_journeys` judge every stored experiment again from its timeline, rebuilding the run's noise from the timelines of its earlier experiments, so earlier runs are scored by the current rule.
- `orchestrator/tests/unit/test_judge.py`: one bad second before the action, two bad seconds, a bad second in the baseline and one before the action adding up, and a bad second before the action not counted in `broken_s`.


---

<a id="adr-0037"></a>

## ADR-0037: The MCP image runs on Chainguard Python with no shell and no pip, scanned, and signed with provenance and an SBOM

**Status:** Accepted, 2026-11-27
**Supersedes:** ADR-0028
**Related:** ADR-0034 (CI), ADR-0016 (denylist), ADR-0029 (env values)

### Context
The disrupt server can change almost anything in the tested namespaces, so its image is part of the safety model (ADR-0028). The first Trivy scan in CI failed the build on a fixed high vulnerability in `libzstd1` from the Debian base of `python:3.12-slim`: Debian had the fix, the official image had not been rebuilt yet. The second scan, on the new base, flagged setuptools 70.3.0 inside pip's own vendored copy of `pkg_resources`, from the pip that `venv` installs into the environment.

### Options
**The base image:**
1. **Stay on `python:3.12-slim` and upgrade the one package** in the Dockerfile until the base is rebuilt. Quick, but the image keeps a shell and a package manager, and the same wait comes back with the next fix.
2. **`python:3.12-alpine`.** musl: the locked wheels are built for glibc, so the hashed lock would not install.
3. **distroless Python.** No shell, but Debian's Python 3.11, and the same pace of fixes.
4. **Chainguard Python (Wolfi),** rebuilt daily with near-zero known vulnerabilities, no shell and no package manager at runtime. The free tier offers only `latest` (today Python 3.15) and `latest-dev`.

**pip in the image:**
1. **Keep it,** and ignore the finding: the vulnerable code is not in pip's copy. But nothing runs pip at runtime.
2. **A venv without pip,** filled by the pip of the build stage.

### Decision
Option 4 and option 2.
- **Multi-stage:** `cgr.dev/chainguard/python:latest-dev` builds the venv; `cgr.dev/chainguard/python:latest` runs it. Both pinned by digest, and the two digests are taken from the same build of Chainguard and bumped together: the venv is linked to that exact Python.
- **No pip in the venv:** `python -m venv --without-pip`, then `python -m pip --python /app/venv/bin/python install --require-hashes`, so the installer stays in the build stage.
- **Python 3.15 everywhere:** the image, and the `lint` and `test` jobs in CI. Every locked dependency ships a cp315 wheel and its hash was already in the lock.
- **User 65532** (`nonroot` in the image), set in the chart as `runAsUser` and `runAsGroup`, so the pod's identity matches `/etc/passwd`.
- **`ENTRYPOINT ["python", "server.py"]`,** since Chainguard's image already has `python` as its entrypoint and a `CMD` would be appended to it.
- **Unchanged from ADR-0028:** the hashed lock, `runAsNonRoot`, `seccompProfile: RuntimeDefault`, no privilege escalation, all capabilities dropped, a read-only root filesystem with emptyDirs, and a minimal environment for k6.
- **In CI** (ADR-0034): Trivy before the push, and signed provenance and SBOM after it.

### Consequences
- **Gains:** the scan is clean; a process that gets into the container finds no shell and no pip to install with; every image can be traced to the commit and workflow that built it.
- **Trade-offs:** no `kubectl exec ... sh`; debugging is by `kubectl debug` with an ephemeral container, or `python -c`. The free tier's `latest` moves across Python versions without notice, so the digests are the only pin, and they must be bumped (follow-up: Dependabot, one group for both). Python 3.15 is new, and less proven than 3.12.
- **Not solved:** an old digest could in principle be removed from Chainguard's registry; the build would then fail loudly with `manifest unknown`.

### In the code
- `servers/mcp/Dockerfile`: the two stages, the venv without pip, `ENTRYPOINT`.
- `charts/chaos-agent/templates/mcp.yaml`: `runAsUser` and `runAsGroup` 65532.
- `.github/workflows/ci.yaml`: `python-version: "3.15"`, the `image` job.


---

<a id="adr-0038"></a>

## ADR-0038: The model reads what Kubernetes did through inspect_workload, a read-only observe tool passed through as it is, with event messages redacted

**Status:** Accepted, 2026-11-28
**Changes:** ADR-0010 (the model's tools)
**Related:** ADR-0008 (what the servers give), ADR-0029 (env values), ADR-0016 (denylist, no Secrets for observe)

### Context
The model sees how the system is configured (the facts collected at the start of a run) and what users felt (the result of each experiment), but not what Kubernetes did during an experiment. In runs 30, 31 and 32 a rollout of productcatalogservice broke every journey for about 20 s although it has 2 replicas, and every run ended with "the mechanism is not identified", listing probe timing, the termination grace period and surge settings as candidates it could not tell apart. Events, pod states and the rollout status would. Three questions: what the tool returns, how the model gets it, and what keeps secrets out of it.

### Options
**What is returned:**
1. **Events added to every experiment result.** No new tool, but every experiment, including those that held, adds thousands of tokens that stay in the context for the rest of the run.
2. **A tool the model calls when something broke or surprised it,** returning the rollout status, the pods and the recent events of one workload.

**How the model gets it:**
1. **A wrapper in the orchestrator,** like `run_experiment` and `search_knowledge`. Glue code for every read tool.
2. **The observe tool passed through as it is,** its schema taken from the server's `list_tools`, behind an allowlist of read-only tools in the orchestrator. A read tool changes nothing, so it needs no enforcement beyond the RoE's scope.

**What keeps secrets out of event messages:** an exec probe's failure message carries the output of its command, which runs inside the container and can print anything it can read: a config file, a token received at runtime, an env value.
1. **No messages at all,** only reasons and counts. Safe, but "Readiness probe failed" without "statuscode: 503" or "connection refused" loses most of the value.
2. **gitleaks on every message.** Catches known formats (cloud keys, tokens, private keys, JWTs), not a plain password from a config file; and the other event messages are templates of Kubernetes components with no application output. One more binary in an image that ADR-0037 made minimal.
3. **Withhold the messages of exec probe failures, and redact the rest:** the env literals of the workload's containers replaced wherever they appear, and every message cut at a length that keeps Kubernetes' own messages whole.

### Decision
Option 2, option 2 and option 3.
- **`observe__inspect_workload(namespace, kind, name, since_s)`,** in `k8s.py`, returns:
  - **rollout:** the update strategy (`maxSurge`, `maxUnavailable`, or a StatefulSet's or DaemonSet's update strategy), `minReadySeconds`, `progressDeadlineSeconds`, the replica counts of the status (updated, ready, available, unavailable), its conditions, and `generation` against `observedGeneration` (a rollout still in progress).
  - **pods:** every pod the workload owns, found by the owner chain already used by `get_placement`: node, phase, ready, restarts per container, and the last terminated state (reason, exit code, finished at).
  - **events:** the 30 most recent of the last `since_s` seconds (default 600; events are kept for about an hour), on the workload, its ReplicaSets and its pods: time, type, reason, object, count and message.
- **Passed through:** `READ_TOOLS` in the orchestrator lists the observe tools the model may call directly; their schemas come from the server; calls go through `mcp_client.call_tool` with that allowlist and the RoE's scope, and are recorded as steps. Tools that change anything stay behind `run_experiment`.
- **Redaction, inside the server, before anything is returned:**
  - **Exec probes:** an `Unhealthy` event of a container whose probe is `exec` keeps its reason and the probe's type, and its message is replaced by `message withheld (exec probe output)`.
  - **Env literals:** every literal env value of the workload's containers is read inside the function only to be searched for, and replaced by `[redacted]` wherever it appears in a message. The values are never returned.
  - **Length:** every message is cut at 500 characters, with `... (truncated)` at the end. 200 was considered and rejected: a `FailedScheduling` message on a four-node cluster is about 290 characters, and the part that explains W1 ("didn't match Pod's node affinity/selector") comes after the 150th.
- **RBAC:** the built-in `view` ClusterRole that observe is bound to already reads pods, ReplicaSets and events (checked on the lab cluster); the `chart` job in CI checks it with `kubectl auth can-i` as observe's ServiceAccount.
- **Container messages are never returned:** `lastState.terminated.message` comes from the application's `terminationMessagePath` and can carry anything; pods show reasons and exit codes only.
- **Prompt:** when an experiment broke or surprised the agent, inspect the workloads involved before choosing the next experiment.

### Consequences
- **Gains:** the agent can explain why something broke, not only that it did; a finding comes with its mechanism and the event that shows it.
- **Trade-offs:** every call is one more round of the model within `MAX_ITERATIONS`, which may have to go up. A withheld exec probe message tells the agent that and when the probe failed, not what it printed.
- **Not solved:** values from Secrets and from files the container reads are unknown to the server, so a message other than an exec probe's that carries one is only cut, not redacted; such messages are rare, since the remaining events are templates of Kubernetes components. Pattern-based redaction (gitleaks or similar) is required before any tool returns pod logs, which are application output by nature.

### In the code
- `servers/mcp/k8s.py`: `inspect_workload`, `literal_env_values`, `exec_probe_containers`, `redact`, `event_message`, `event_matches`, `rollout_facts`, `pod_state`.
- `servers/mcp/server.py`: `TOOLS_BY_LEVEL`.
- `orchestrator/agent/loop.py`: `READ_TOOLS`, the prompt.
- `servers/mcp/tests/unit/test_inspect.py`: the canary in event messages, exec probes, deleted pods, container messages.
- `.github/workflows/ci.yaml`: the `kubectl auth can-i` step.


---

<a id="adr-0039"></a>

## ADR-0039: The orchestrator ships in the chart as a CronJob of runs, with no Kubernetes access, its inputs from a ConfigMap and its API key from the customer's Secret

**Status:** Accepted, 2026-11-28
**Related:** ADR-0005 (the product is a chart), ADR-0008 (what the servers give), ADR-0020 (inputs and owners), ADR-0031 (undo at start), ADR-0033 (the embedding model), ADR-0037 (the MCP image)

### Context
Until now the chart installed Postgres and the MCP servers, and the orchestrator ran on a laptop with port-forwards and an API key typed into the shell: a customer who installed the chart got the infrastructure and nothing that runs it. Four questions: how a run is started, where its inputs come from, how it gets the Anthropic API key, and what it may reach.

### Options
**How a run is started:**
1. **A Deployment that runs forever and starts runs on a schedule or a request.** Needs a scheduler and an API of its own.
2. **A Job per run, made by hand from a template the customer keeps.** Simple, but every customer writes the same Job.
3. **A CronJob in the chart, suspended unless a schedule is set;** a run on demand is `kubectl create job --from=cronjob/...`, and a schedule makes it a regular regression run.

**Where the inputs come from:**
1. **As YAML inside the chart values.** One place, but `roe.yaml` and `target.yaml` belong to other owners (ADR-0020), and copying them into values splits each file in two.
2. **A ConfigMap the customer makes from the files they keep in git,** named in the values.

**How the API key gets in:**
1. **A value in the chart.** It would sit in plain text in Helm's release history (`helm get values`).
2. **`existingSecret`: a Secret the customer makes,** by hand, with External Secrets, Vault or Sealed Secrets, named in the values; the same pattern as Postgres's password.

### Decision
Option 3, option 2 and option 2.
- **The CronJob:** `concurrencyPolicy: Forbid`; `backoffLimit: 0`, since a retried run would run experiments again on its own; `activeDeadlineSeconds` (default 3600); finished Jobs kept a day. Pinned like the MCP servers by `nodeSelector` and `tolerations`; the disrupt server already refuses to fail a node that runs the chaos agent.
- **No Kubernetes access at all:** its own ServiceAccount with `automountServiceAccountToken: false`. It reaches the cluster only through the MCP servers (`MCP_<LEVEL>_URL`, the servers' Services), Postgres through its Service, and Claude with the key from the Secret.
- **Checked when the chart renders:** an image tag, a namespace that is one of `mcp.allowedNamespaces`, the inputs ConfigMap, the Secret, observe enabled (every run starts from discovery) and Postgres enabled.
- **`main.py`,** the Job's entry point: everything from the environment (`ROE_FILE`, `TARGET_FILE`, `TARGET_NAMESPACE`, `CHAOS_MODEL`, `PG*`); the inputs checked before anything is recorded (exit 2); a run that cannot take the namespace's lock is not started (exit 2); SIGTERM, which Kubernetes sends at the deadline, and Ctrl+C mark the run aborted (exit 130), and its pending undos run when the next run starts (ADR-0031). This also ends the stale `running` row a Ctrl+C left before.
- **The image:** Python 3.14 slim, multi-stage with a venv without pip like ADR-0037; not Chainguard, since onnxruntime has no 3.15 wheel. The embedding model is downloaded at build time and `HF_HUB_OFFLINE=1` is set, so an air-gapped cluster runs and no run waits for a download. User 65532, like the MCP image; read-only root filesystem, `HOME=/tmp` on an emptyDir.
- **`max_model_rounds` in the RoE** replaces the constant `MAX_ITERATIONS` (ADR-0020).
- **In the lab:** `lab/dev.sh load mcp|orchestrator` builds an image and loads it into the control-plane only, then removes the untagged copies earlier loads left (they had filled the disk); `lab/run-agent.sh` makes the inputs ConfigMap and the Secret (the key read without echo and passed through stdin, never on a command line), starts a Job, optionally with another model, and follows its logs.

### Consequences
- **Gains:** the chart is the whole product: installed, it runs. A compromised orchestrator has no Kubernetes credentials. Inputs stay in their owners' files; the key never passes through Helm.
- **Trade-offs:** a run on demand needs `kubectl create job`; there is no API or UI to start one. The orchestrator image is Debian-based and is not yet built, scanned or signed in CI like the MCP image; its dependencies are pinned but not hashed.
- **Not solved:** Claude through AWS Bedrock or Google Vertex with workload identity, with no API key (the SDK supports both; a `provider` value would choose); an external Postgres instead of the chart's.

### In the code
- `charts/chaos-agent/templates/orchestrator.yaml`, `values.yaml` (`orchestrator`), `ci/all-levels-values.yaml`.
- `orchestrator/main.py`, `orchestrator/Dockerfile`, `orchestrator/mcp_client.py` (`SERVERS` from env), `orchestrator/config.py` (`max_model_rounds`).
- `lab/chaos-agent-values.yaml`, `lab/dev.sh` (`load`), `lab/run-agent.sh`.


---

## Template for a new record
```markdown
## ADR-NNNN: <the decision, as a sentence>

**Status:** Accepted | Proposed | Superseded by ADR-XXXX, <date>
**Related:** ADR-XXXX (<why>)

### Context
<the question, and why it came up>

### Options
1. **<option>.** <pros, cons>

### Decision
<what was chosen, and the details that matter>

### Consequences
- **Gains:**
- **Trade-offs:**
- **Not solved:**

### In the code
- `<file>`: `<function or constant>`
```
