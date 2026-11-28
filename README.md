# Chaos Agent

An AI agent that tests the resilience of an application on Kubernetes. Within Rules of Engagement set by the cluster's owners, it decides what to break, runs each experiment under control, measures what users would feel, and reports which weaknesses it confirmed, with the experiments that prove them.

It is built to work on any application on any cluster: everything specific to an application is in that application's `target.yaml`, and the judge learns the application's own noise during the run.

## One run

1. **Discovery.** The orchestrator collects the facts itself (`get_inventory`, `get_workloads`, `get_placement`) and puts them in the prompt with their step numbers.
2. **The model plans.** Claude, through the API, has three tools: `run_experiment`, `search_knowledge` (its memory of earlier runs) and `observe__inspect_workload` (read-only: rollout status, restarts, events). It forms a hypothesis and chooses one change.
3. **The orchestrator runs the experiment:**
   - checks it against the Rules of Engagement;
   - waits until every user journey is steady, measured with k6;
   - takes a snapshot of what will change and writes the undo to the database before acting;
   - acts: patches a resource (replicas, resources, probes, a rollout), deletes a pod, or fails a node or a zone (drain or lost);
   - keeps measuring, restores the change after `restore_after_s`, and measures the recovery.
4. **The judge decides** broke, withstood or inconclusive, in code, from the measurements. The model reads the verdict and a one-line timeline per journey, and chooses the next experiment.
5. **The summary** lists confirmed weaknesses, each citing its steps. The run's experiments and summary are indexed into the memory for the next run.

## Running it

```bash
lab/up.sh                                  # the kind cluster, the app, Prometheus, Grafana and the chart
lab/run-agent.sh                           # one run, as a Job from the chart's CronJob (Sonnet by default)
MODEL=claude-haiku-5-5 lab/run-agent.sh    # a cheaper run
lab/watch-run.sh                           # follow a run in the terminal
kubectl -n monitoring port-forward svc/grafana 3000:80   # or follow it on the dashboard
lab/eval-night.sh check && lab/eval-night.sh run         # the whole eval, unattended
```

The API key is asked for once with `read -s` and kept in a Secret; it never appears on a command line.

## Inputs, each with its owner

- **`target.yaml`** (the application team): the user journeys k6 runs, the steady state (success rate and p95), and the measurement timings.
- **`roe.yaml`** (security or operations): the namespaces in scope, the highest action level, node actions, protected workloads, what may never be changed, and the limits per run (experiments, model rounds, restore time).
- **The chart values** (the cluster admin): caps the probe server enforces whatever a run asks for (longest k6 run, users per second, request timeout).

## Safety

- **Three permission levels, three pods.** One MCP server codebase is deployed as observe, probe and disrupt, each with its own ServiceAccount. A run gets only the tools of its level.
- **Every call goes through the orchestrator,** which rejects tools the run does not have and namespaces outside the scope, and records the call before it runs, denied calls included.
- **What may never change:** Secrets, PersistentVolumeClaims, ServiceAccounts and RBAC, and the images, commands, security context and volumes of pods, always; plus the API groups and kinds the RoE denies (GitOps, cloud resources, backups, database operators). The disrupt server refuses them, and a ValidatingAdmissionPolicy enforces the same list in the API server.
- **Protected workloads** are measured and never changed (in the lab, redis-cart, whose carts live on an emptyDir).
- **Undo:** every change has a snapshot (a Secret in `chaos-system`) and an undo row written before the change. Undos left pending by a crash run when the next run starts.
- **Env values and Secret values never leave the MCP servers:** tools return names and sources only, and event messages are redacted. A canary value planted in the lab is checked by unit tests.

## Measuring and judging

- **k6** runs inside the probe pod at a constant arrival rate, so it works on any cluster with no operator. Results are counted by the second users arrived.
- **Steady check:** before every experiment, every second of every journey must be steady, or the check waits and tries again. A system that never gets steady is `not_run`: nothing is changed and nothing is counted.
- **The judge** gives every second a status against the steady state (`.` ok, `s` slow, `x` failed, `_` no data). It learns the application's own noise during the run, from the seconds before each action, and calls a phase degraded only when that noise would make it with a chance under 0.5%: too many bad seconds in a row, in a 10 second window, or in the whole phase. A single bad second is never a finding.

## Memory

Every experiment is stored as a chunk built by code from its data, so the model cannot remember an experiment better than it went; summary sections are stored apart, marked as interpretation. Search is hybrid in pgvector: filtered by namespace and workload, ranked by similarity, with embeddings computed inside the cluster (fastembed). The model searches before planning experiments on a workload, and cites what it reuses as run and step.

## What the chart installs (`charts/chaos-agent`)

- The three MCP servers, on a Chainguard Python image with no shell, scanned, signed and shipped with an SBOM and provenance.
- The orchestrator as a CronJob that stays suspended: one run is one Job, with no Kubernetes access of its own.
- Postgres with pgvector: runs, every step (the audit log and the checkpoint), the undo log, the measurements and the memory.
- Optionally, a Grafana dashboard and a Postgres datasource for the customer's Grafana sidecars: what the agent says and does, what users saw per second, every verdict, the model's tokens and cost, and every earlier run.

## The lab (`lab/`)

- **kind** with one control-plane and three workers, each in its own zone, so node and zone failures can be tested on a laptop. Prometheus and Grafana run on the control-plane, outside the blast radius.
- **Online Boutique** (11 services, gRPC), vendored unchanged, with every change as a Kustomize patch: frontend pinned to one zone, an aggressive liveness probe, a tight CPU limit and a Secret in env. Real weaknesses of upstream (single replicas, a slow failure of about 20 seconds when a dependency disappears) were audited first.
- **`boutique-hardened`:** the same app with 3 replicas, zone spread, PDBs, preStop hooks and no planted weaknesses: the eval's control group.
- **`ground_truth.yaml`:** the answer key the agent never sees, used only by the eval.

## Eval (`eval/`)

The agent is scored against the ground truth and compared with a deterministic baseline (one pod deleted per workload, one zone lost per zone) on the weak and the hardened app: what it found and cited, what broke and was not reported, false positives, cost, and safety (denied calls, pending undos). `score.py` judges every stored experiment again with the current judge, so earlier runs are scored by the current rules. Results and how to read them: [`eval/README.md`](eval/README.md) and [`eval/results.md`](eval/results.md).

## CI (`.github/workflows/ci.yaml`)

On every change: ruff, the unit tests of the servers, the orchestrator and the eval, helm lint and kubeconform, a check that the chart refuses unsafe values, an install on kind with a type check of every admission policy, and the MCP image built, scanned with Trivy, pushed to GHCR with its SBOM and provenance.

## Decisions

Every design decision, with the options and why: [`docs/architecture-decisions.md`](docs/architecture-decisions.md).

## Backlog

- Chaos Mesh (CPU stress, network faults) and a load experiment, for weaknesses that show only under load.
- A steady check that also compares with the system's own normal, not only with the steady state.
- Attributing a broke to the environment from node CPU in Prometheus.
- A role for every run level: observe as an assessment to approve before a disrupt run, probe as a load test.
- A read-only Postgres role for Grafana, and k6 points live to the second through remote write.
- Short-lived ServiceAccount tokens per run; AWS chaos with FIS; database chaos at protocol level.
