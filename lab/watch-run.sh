#!/usr/bin/env bash
# Follows an agent run live: the run, every step as it is recorded (the model's words for LLM steps,
# the verdict or error for experiments and tools), and its undo actions. Reads Postgres through
# kubectl exec, so it needs no local Postgres client.
#
# Usage: lab/watch-run.sh [run_id]    (default: the latest run; INTERVAL in seconds, default 3)
set -euo pipefail

NAMESPACE="${NAMESPACE:-chaos-system}"
POD="${POD:-chaos-agent-postgresql-0}"
INTERVAL="${INTERVAL:-3}"
RUN="${1:-(SELECT max(id) FROM runs)}"

sql() {
  kubectl -n "$NAMESPACE" exec "$POD" -- psql -U chaos -d chaos -X -q -P pager=off -c "$1"
}

while true; do
  clear
  sql "SELECT id, status, max_level, to_char(started_at, 'HH24:MI:SS') AS started, error
       FROM runs WHERE id = $RUN"
  sql "SELECT step, to_char(started_at, 'HH24:MI:SS') AS at, kind, name, allowed AS ok,
       CASE
         WHEN finished_at IS NULL THEN 'running...'
         WHEN kind = 'llm' THEN left(coalesce(
           jsonb_path_query_first(output, '\$[*] ? (@.type == \"text\").text') #>> '{}', '(tool calls only)'), 90)
         ELSE left(coalesce(output->>'verdict', output->>'error', output->>'denied',
           CASE WHEN output->>'is_error' = 'true' THEN 'error: ' || (output->>'content') ELSE 'ok' END), 90)
       END AS result
       FROM steps WHERE run_id = $RUN ORDER BY step DESC LIMIT 20"
  sql "SELECT id, status, action->'args'->>'snapshot_id' AS snapshot,
       to_char(created_at, 'HH24:MI:SS') AS created, to_char(done_at, 'HH24:MI:SS') AS done
       FROM undo_actions WHERE run_id = $RUN ORDER BY id DESC LIMIT 5"
  sleep "$INTERVAL"
done
