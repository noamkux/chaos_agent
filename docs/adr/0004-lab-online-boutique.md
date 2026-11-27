# ADR-0004: The lab: Online Boutique on kind, with planted weaknesses and a ground truth

**Status:** Accepted, 2026-11-24
**Related:** ADR-0003 (any application), ADR-0032 (eval)

## Context
To develop and evaluate the agent we need a cluster and an application where we know the answers: which failures the system survives and which it does not. The question has three parts: which application, how to plant weaknesses in it, and how to record the answers.

## Options

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

## Decision
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

## Consequences
- **Gains:** a realistic application we did not write; every planted weakness is reviewable on its own; the answer key makes runs comparable.
- **Trade-offs:** Online Boutique is heavy for a laptop with limited disk. One node per zone means a node failure and a zone failure cannot be told apart in the lab. Some behaviors (such as a ~10 s stall on the first request after idle) are real but unplanned; the stall was left out of the ground truth on purpose, as an "unknown weakness" the agent might find.
- **Not solved:** the ground truth was written for the catalog era (checks and components) and must be rewritten by action and impact (ADR-0032).

## In the code
- `lab/up.sh`, `lab/kind-config.yaml`: the cluster with zone labels.
- `lab/apps/boutique/kustomization.yaml`: upstream, the patches and the replica counts.
- `lab/apps/boutique/patches/`: one file per planted weakness.
- `lab/apps/boutique/ground_truth.yaml`: the answer key.
- `lab/dependency-check.sh`, `lab/health-check.sh`: the manual checks used to verify the ground truth and the lab before a run.
