#!/usr/bin/env bash
# Creates the chaos-lab kind cluster, verifies zones, and installs Prometheus and the chaos-agent chart.
set -euo pipefail

CLUSTER_NAME="chaos-lab"
ZONE_LABEL="topology.kubernetes.io/zone"
PROMETHEUS_CHART_VERSION="30.0.0"
GRAFANA_CHART_VERSION="12.5.0"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
CHAOS_NAMESPACE="chaos-system"

# 1. Prerequisites
for tool in docker kind kubectl helm; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "ERROR: $tool is not installed" >&2
    exit 1
  fi
done

# kind nodes share the host's inotify limits; low values make pods fail randomly
# i notify is a mechanisem where process ask the kernal for a notifecation when a file is opend
min_watches=524288
min_instances=512
watches=$(sysctl -n fs.inotify.max_user_watches)
instances=$(sysctl -n fs.inotify.max_user_instances)

if [ "$watches" -lt "$min_watches" ] || [ "$instances" -lt "$min_instances" ]; then
  echo "ERROR: inotify limits too low (watches=$watches, instances=$instances)" >&2
  echo "Fix: see https://kind.sigs.k8s.io/docs/user/known-issues/#pod-errors-due-to-too-many-open-files" >&2
  exit 1
fi

# 2. Create the cluster only if it doesn't exist yet
if kind get clusters 2>/dev/null | grep -qx "$CLUSTER_NAME"; then
  echo "Cluster $CLUSTER_NAME already exists, skipping creation"
else
  kind create cluster --config "$SCRIPT_DIR/kind-config.yaml" --wait 120s
fi

kubectl config use-context "kind-$CLUSTER_NAME" >/dev/null
kubectl wait --for=condition=Ready nodes --all --timeout=120s

# 3. Verify: every worker has a zone, and there are exactly 3 distinct zones
zones=$(kubectl get nodes -l '!node-role.kubernetes.io/control-plane' --no-headers \
  -o custom-columns='ZONE:.metadata.labels.topology\.kubernetes\.io/zone')

if echo "$zones" | grep -q '<none>'; then
  echo "ERROR: a worker node has no $ZONE_LABEL label" >&2
  exit 1
fi

zone_count=$(echo "$zones" | sort -u | wc -l)
if [ "$zone_count" -ne 3 ]; then
  echo "ERROR: expected 3 zones, found $zone_count" >&2
  exit 1
fi

# 4. Prometheus (simulates the target's existing monitoring)
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts \
  --force-update >/dev/null
helm repo update prometheus-community >/dev/null

helm upgrade --install prometheus prometheus-community/prometheus \
  --namespace monitoring --create-namespace \
  --version "$PROMETHEUS_CHART_VERSION" \
  -f "$SCRIPT_DIR/prometheus-values.yaml" \
  --wait --timeout 5m

# 4b. Grafana (simulates the target's existing Grafana); it loads the chart's dashboard from chaos-system.
helm repo add grafana-community https://grafana-community.github.io/helm-charts --force-update >/dev/null
helm repo update grafana-community >/dev/null
helm upgrade --install grafana grafana-community/grafana \
  --namespace monitoring --create-namespace \
  --version "$GRAFANA_CHART_VERSION" \
  -f "$SCRIPT_DIR/grafana-values.yaml" \
  --wait --timeout 5m

# 5. chaos-agent chart (installed the same way a customer would, with lab-specific values)
helm upgrade --install chaos-agent "$REPO_DIR/charts/chaos-agent" \
  --namespace "$CHAOS_NAMESPACE" --create-namespace \
  -f "$SCRIPT_DIR/chaos-agent-values.yaml" \
  --wait --timeout 5m

# A new release creates the Postgres Secret during the install; the Grafana datasource is rendered from
# it (lookup), so one more upgrade adds it.
helm upgrade chaos-agent "$REPO_DIR/charts/chaos-agent" \
  --namespace "$CHAOS_NAMESPACE" -f "$SCRIPT_DIR/chaos-agent-values.yaml" --wait --timeout 5m

echo "Lab $CLUSTER_NAME is ready:"
kubectl get nodes -L "$ZONE_LABEL"
kubectl -n monitoring get pods -o wide
kubectl -n "$CHAOS_NAMESPACE" get pods -o wide
