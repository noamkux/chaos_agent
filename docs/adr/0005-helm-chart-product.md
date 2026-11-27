# ADR-0005: The product is a Helm chart, and the lab installs it like a customer

**Status:** Accepted, 2026-11-24
**Related:** ADR-0006 (Postgres), ADR-0008 (MCP servers per level), ADR-0020 (owners)

## Context
Everything the agent needs in a cluster (the MCP servers, their permissions, the database, the admission policy) has to be installed somewhere. The question: how does it get into a customer's cluster, and how does the lab get it?

## Options
1. **Plain manifests (`kubectl apply -f`).** No tooling. But every customer edits YAML by hand for namespaces, images and levels, and upgrades are manual.
2. **An operator with its own CRDs.** The most "Kubernetes-native". But it is far more code, needs cluster-admin to install the CRDs, and is out of reach in the time available.
3. **A Helm chart.** The common way to ship a product to Kubernetes: values for what differs per customer, `helm upgrade` for upgrades, templates for repeated objects (one Deployment per level).

## Decision
Option 3. `charts/chaos-agent` holds everything in `chaos-system`. The lab installs it with `helm upgrade --install` and only its own values file, `lab/chaos-agent-values.yaml`, exactly as a customer would.

What differs per customer is in the values: the namespaces the servers may touch (`mcp.allowedNamespaces`, required), which levels are deployed (`mcp.levels.*.enabled`), the probe's caps (`mcp.levels.probe.limits`), images, resources and placement. The chart refuses to render without `mcp.allowedNamespaces` or an image tag.

## Consequences
- **Gains:** one artifact to install; the lab tests the real install path, so a broken template shows up in the lab first; `helm lint` and `helm template` can run in CI.
- **Trade-offs:** the logic in templates (one Role per level per namespace, the CEL in the admission policy) is harder to read and test than code. The orchestrator still runs on the laptop, not from the chart, until it becomes a Job (backlog).

## In the code
- `charts/chaos-agent/values.yaml`: every setting a customer can change.
- `charts/chaos-agent/templates/mcp.yaml`: the `fail` and `required` checks at the top.
- `lab/up.sh`: step 5, the chart installed with `lab/chaos-agent-values.yaml`.
