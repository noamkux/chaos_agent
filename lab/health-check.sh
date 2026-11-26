#!/usr/bin/env bash
# Checks that the lab app is healthy before a run or an eval: every Deployment and
# StatefulSet in the namespace has all its replicas ready. On a broken lab every
# experiment measures the breakage, not the weakness, so runs must not start on one.
#
# Usage: lab/health-check.sh [namespace]    (default: boutique; TIMEOUT in seconds, default 120)
set -euo pipefail

NAMESPACE="${1:-boutique}"
TIMEOUT="${TIMEOUT:-120}"

kubectl get namespace "$NAMESPACE" >/dev/null

deadline=$((SECONDS + TIMEOUT))
while true; do
  # Desired replicas against ready replicas; readyReplicas is absent (<none>) when none are ready.
  # A workload scaled to 0 on purpose wants nothing, so it is healthy.
  not_ready=$(kubectl -n "$NAMESPACE" get deployments,statefulsets --no-headers \
    -o custom-columns='NAME:.metadata.name,WANT:.spec.replicas,READY:.status.readyReplicas' \
    | awk '{ready = ($3 == "<none>") ? 0 : $3} $2 != 0 && ready != $2 {print "  " $1 " " ready "/" $2 " ready"}')

  if [ -z "$not_ready" ]; then
    echo "lab healthy: every workload in $NAMESPACE has all its replicas ready"
    exit 0
  fi
  if [ "$SECONDS" -ge "$deadline" ]; then
    echo "lab not healthy after ${TIMEOUT}s in namespace $NAMESPACE:" >&2
    echo "$not_ready" >&2
    echo "pods that are not running:" >&2
    kubectl -n "$NAMESPACE" get pods --no-headers | awk '$3 != "Running" && $3 != "Completed" {print "  " $0}' >&2
    exit 1
  fi
  sleep 5
done
