# AI Project - Chaos Agent

An AI agent that tests the resilience of any application on Kubernetes within defined Rules of Engagement, proves each weakness with a controlled experiment, and reports what broke, what survived and how to fix it.

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
- `findings`: what the agent found, confirmed or survived.

**Orchestrator (`orchestrator/`):** connects to Postgres with the standard `PG*` environment variables, applies the schema on every start, and manages the run lifecycle (create, claim, finish). A partial unique index allows only one running run per namespace, enforced by Postgres; this was tested with two runs on the same namespace.