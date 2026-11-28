#!/usr/bin/env bash
# Starts one run of the agent in the cluster, the way a customer runs it (ADR-0039): the inputs
# ConfigMap from lab/apps/boutique, the Secret with the Anthropic API key (asked for once, never
# echoed, never on a command line), then a Job from the chart's CronJob, and its logs.
#
# Usage: lab/run-agent.sh                      a run with the chart's model (Sonnet)
#        MODEL=claude-haiku-5-5 lab/run-agent.sh   a cheaper run while developing
# Follow it live in another terminal with lab/watch-run.sh. Ctrl+C here stops following, not the run.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NAMESPACE="${NAMESPACE:-chaos-system}"
RELEASE="${RELEASE:-chaos-agent}"
APP_DIR="$REPO_DIR/lab/apps/boutique"
INPUTS="chaos-agent-boutique-inputs"
SECRET="chaos-agent-anthropic"

# The inputs, from the files in git, applied so a change to roe.yaml or target.yaml reaches the next run.
kubectl -n "$NAMESPACE" create configmap "$INPUTS" \
  --from-file=roe.yaml="$APP_DIR/roe.yaml" --from-file=target.yaml="$APP_DIR/target.yaml" \
  --dry-run=client -o yaml | kubectl apply -f - >/dev/null

if ! kubectl -n "$NAMESPACE" get secret "$SECRET" >/dev/null 2>&1; then
  read -rsp "Anthropic API key (kept in Secret $NAMESPACE/$SECRET): " key
  echo
  # Through stdin, not --from-literal: a literal would show in the process list while kubectl runs.
  printf '%s' "$key" | kubectl -n "$NAMESPACE" create secret generic "$SECRET" --from-file=api-key=/dev/stdin >/dev/null
  unset key
fi

job="run-$(date +%Y%m%d-%H%M%S)"
spec="$(kubectl -n "$NAMESPACE" create job "$job" --from="cronjob/$RELEASE-orchestrator" --dry-run=client -o json)"
if [[ -n "${MODEL:-}" ]]; then
  spec="$(jq --arg model "$MODEL" '(.spec.template.spec.containers[0].env[] | select(.name == "CHAOS_MODEL")).value = $model' <<< "$spec")"
fi
kubectl -n "$NAMESPACE" apply -f - <<< "$spec" >/dev/null
echo "job $job started${MODEL:+ with $MODEL}"

kubectl -n "$NAMESPACE" wait --for=condition=Ready "pod" -l "job-name=$job" --timeout=180s >/dev/null || true
kubectl -n "$NAMESPACE" logs -f "job/$job"
