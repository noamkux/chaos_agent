#!/usr/bin/env bash
# The overnight eval (ADR-0032): every configuration several times, on a laptop left alone, so the
# results are not shaped by other work on the same CPU. Run it from a terminal you leave open.
#
# Usage: lab/eval-night.sh check   checks everything the night needs, changes nothing in the cluster
#        lab/eval-night.sh run     the whole night (about 8 hours), most important first:
#          1. boutique-hardened, the control group: baseline, Sonnet 4 times (its own memory, from empty)
#          2. boutique: baseline, Sonnet 5 times (memory from empty, so each run remembers the ones
#             before it), the checks plan, the productcatalogservice rollout twice (verify, 2 each)
#          3. boutique: Haiku 3 times (its own memory, from empty), a second baseline
#        Then every series of the night is scored into score.md in the log folder, each against the
#        ground truth of its own app, so recall so far reads as what that series knows after each run.
#
# Memory: the agent's memory is the rows of knowledge_chunks for the namespace, and the hardened app runs
# in the same namespace. So before each series the rows are moved to a table of their own
# (knowledge_chunks_night_<stamp>_<series>), and at the end the weak app's Sonnet memory is put back:
# memory built by the current judge. Nothing is dropped; the tables of earlier memory stay.
#
# Ctrl+C once: stops after the current step, then puts the weak app and the memory back. Ctrl+C twice:
# exits at once and prints what is still running. Every step's child ignores Ctrl+C, so a run is never
# cut in the middle of an experiment.
# Logs: ~/chaos-night/<stamp>/: night.log, steps.tsv (start, end, step, result, the run it made),
# vmstat.log and docker-stats.log (the laptop's load, to check a broke against a CPU spike), and one log
# per step.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
NAMESPACE="boutique"
SYSTEM_NAMESPACE="chaos-system"
RELEASE="chaos-agent"
CONTEXT="kind-chaos-lab"
PG_POD="$RELEASE-postgresql-0"
WEAK="$REPO_DIR/lab/apps/boutique"
HARDENED="$REPO_DIR/lab/apps/boutique-hardened"
WEAK_TRUTH="$WEAK/ground_truth.yaml"
HARDENED_TRUTH="$HARDENED/ground_truth.yaml"
HAIKU="claude-haiku-5-5"
MIN_FREE_KB=$((1500 * 1024))
JOB_TIMEOUT_S=$((65 * 60))     # the chart's activeDeadlineSeconds is 3600
SETTLE_S=90                    # after the app is healthy, before the next step
STAMP="${STAMP:-$(date +%Y%m%d_%H%M)}"
LOG_DIR="${LOG_DIR:-$HOME/chaos-night/$STAMP}"
PYTHON_SCORE="$REPO_DIR/.venv/bin/python"

STOP=0
FORCE=0
APP="weak"               # which app is in the cluster
CURRENT_MEMORY=""         # the table this series' memory is saved to when it ends
FINAL_MEMORY=""           # the table put back into knowledge_chunks at the end
START_RUN=0

log() { echo "$(date '+%F %T') $*" | tee -a "$LOG_DIR/night.log"; }
die() { log "ERROR: $*"; exit 1; }

# SQL in the Postgres pod, with the pod's own credentials: the password never leaves it.
sql() {
  kubectl --context "$CONTEXT" -n "$SYSTEM_NAMESPACE" exec -i "$PG_POD" -c postgres -- sh -c \
    'PGPASSWORD="$POSTGRES_PASSWORD" psql -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -qAt' <<< "$1"
}

on_interrupt() {
  if [ "$STOP" -eq 0 ]; then
    STOP=1
    log "Ctrl+C: stopping after the current step, then putting the weak app and the memory back (Ctrl+C again to exit now)"
  else
    FORCE=1
    log "Ctrl+C twice: exiting now. Still running: $(jobs -p | tr '\n' ' ')"
    log "Still to do by hand: lab/apps is '$APP'; the memory is in knowledge_chunks, the series table is '${CURRENT_MEMORY:-none}', the one to put back is '${FINAL_MEMORY:-none}'"
    exit 130
  fi
}

# Runs one step in the background with Ctrl+C ignored, and waits for it; a Ctrl+C while waiting only
# sets STOP. Returns the step's exit status.
run_child() {
  local out="$1"; shift
  ( trap '' INT TERM; exec "$@" ) >> "$out" 2>&1 < /dev/null &
  local pid=$! rc=0
  while true; do
    wait "$pid"; rc=$?
    kill -0 "$pid" 2>/dev/null || break
  done
  return "$rc"
}

last_run() { sql "SELECT coalesce(max(id), 0) FROM runs" 2>/dev/null || echo "?"; }

# One step of the night, recorded in steps.tsv with its times, so a verdict can be put beside the load.
step() {
  local name="$1"; shift
  STEP_NO=$((STEP_NO + 1))
  local out start rc before after run="-"
  out="$LOG_DIR/$(printf '%02d' "$STEP_NO")-$name.log"
  start="$(date -Is)"
  before="$(last_run)"
  log "step $STEP_NO $name: start"
  "$@" "$out"; rc=$?
  after="$(last_run)"
  # The run this step made, if it made one: a step that switches apps or fails early makes none.
  if [[ "$before" =~ ^[0-9]+$ && "$after" =~ ^[0-9]+$ ]] && [ "$after" -gt "$before" ]; then run="$after"; fi
  printf '%s\t%s\t%s\t%s\t%s\n' "$start" "$(date -Is)" "$name" "$([ "$rc" -eq 0 ] && echo ok || echo "failed($rc)")" "$run" \
    >> "$LOG_DIR/steps.tsv"
  log "step $STEP_NO $name: $([ "$rc" -eq 0 ] && echo "done" || echo "FAILED ($rc), see $out")"
  return "$rc"
}
STEP_NO=0

pending_undos() { sql "SELECT count(*) FROM undo_actions WHERE status = 'pending'"; }

# Every node schedulable and without a chaos taint, every workload ready, no pending undo; then a pause
# so the laptop settles after the pods that just started.
healthy() {
  local out="$1"
  for _ in $(seq 1 20); do
    local bad
    bad="$(kubectl --context "$CONTEXT" get nodes -o json | jq -r '.items[] | select(
      .spec.unschedulable == true
      or any(.spec.taints[]?; .key | startswith("chaos-agent.io/"))
      or any(.status.conditions[]; .type == "Ready" and .status != "True")) | .metadata.name')"
    if [ -z "$bad" ] && TIMEOUT=60 "$SCRIPT_DIR/health-check.sh" "$NAMESPACE" >> "$out" 2>&1; then
      local pending; pending="$(pending_undos)"
      if [ "$pending" != "0" ]; then
        echo "pending undos: $pending" >> "$out"
        return 1
      fi
      sleep "$SETTLE_S"
      return 0
    fi
    echo "$(date '+%T') not healthy yet; nodes: ${bad:-ok}" >> "$out"
    sleep 30
  done
  return 1
}

rolled_out() {
  local out="$1" deployment
  for deployment in $(kubectl --context "$CONTEXT" -n "$NAMESPACE" get deployments -o name); do
    kubectl --context "$CONTEXT" -n "$NAMESPACE" rollout status "$deployment" --timeout=10m >> "$out" 2>&1 || return 1
  done
}

to_hardened() {
  local out="$1"
  kubectl --context "$CONTEXT" apply -k "$HARDENED" --dry-run=server >> "$out" 2>&1 || return 1
  APP="hardened"
  kubectl --context "$CONTEXT" apply -k "$HARDENED" >> "$out" 2>&1 || return 1
  rolled_out "$out" && healthy "$out"
}

to_weak() {
  local out="$1"
  kubectl --context "$CONTEXT" apply -k "$WEAK" >> "$out" 2>&1 || return 1
  kubectl --context "$CONTEXT" -n "$NAMESPACE" delete pdb -l chaos-lab/hardened=true --ignore-not-found >> "$out" 2>&1 || return 1
  APP="weak"
  rolled_out "$out" && healthy "$out"
}

# Moves the namespace's memory into a new table of its own (a CREATE without IF NOT EXISTS, so a table is
# never filled twice), leaving knowledge_chunks empty for the namespace.
save_memory() {
  local table="$1" out="$2"
  sql "BEGIN;
       CREATE TABLE $table (LIKE knowledge_chunks);
       INSERT INTO $table SELECT * FROM knowledge_chunks WHERE namespace = '$NAMESPACE';
       DELETE FROM knowledge_chunks WHERE namespace = '$NAMESPACE';
       COMMIT;
       SELECT '$table: ' || count(*) || ' rows' FROM $table;" >> "$out" 2>&1
}

restore_memory() {
  local table="$1" out="$2"
  sql "INSERT INTO knowledge_chunks OVERRIDING SYSTEM VALUE SELECT * FROM $table ON CONFLICT DO NOTHING;
       SELECT 'knowledge_chunks: ' || count(*) || ' rows' FROM knowledge_chunks WHERE namespace = '$NAMESPACE';" >> "$out" 2>&1
}

memory_series() {
  CURRENT_MEMORY="knowledge_chunks_night_${STAMP}_$1"
}

end_series() {
  local out="$1"
  save_memory "$CURRENT_MEMORY" "$out" && CURRENT_MEMORY=""
}

agent_run() {
  local model="$1" out="$2" job
  run_child "$out" env ${model:+MODEL="$model"} "$SCRIPT_DIR/run-agent.sh"
  job="$(grep -o 'job run-[0-9-]*' "$out" | tail -1 | cut -d' ' -f2)"
  [ -n "$job" ] || return 1
  # The logs can stop before the Job ends; the Job's status is what counts.
  local deadline=$((SECONDS + JOB_TIMEOUT_S))
  while [ "$SECONDS" -lt "$deadline" ]; do
    local status
    status="$(kubectl --context "$CONTEXT" -n "$SYSTEM_NAMESPACE" get job "$job" \
      -o jsonpath='{.status.succeeded}/{.status.failed}' 2>/dev/null)"
    case "$status" in
      1/*) echo "job $job complete" >> "$out"; return 0 ;;
      */1) echo "job $job failed" >> "$out"; return 1 ;;
    esac
    sleep 30
  done
  # A Job still running holds the namespace: nothing else may start, so the night stops here.
  echo "job $job still running after ${JOB_TIMEOUT_S}s" >> "$out"
  STOP=1
  return 1
}

fixed_run() {
  local out="${*: -1}"
  run_child "$out" "$SCRIPT_DIR/dev.sh" up || return 1
  eval "$("$SCRIPT_DIR/dev.sh" env)"
  # No subshell around it: a subshell would die on Ctrl+C while its child runs on.
  run_child "$out" python3 "$REPO_DIR/eval/baseline.py" "${@:1:$#-1}"
}

# The experiments of one step; the night stops when a step fails in a way that leaves the lab unknown.
do_step() {
  [ "$STOP" -eq 0 ] || return 1
  step "$@"
  local rc=$?
  if [ "$rc" -ne 0 ] || [ "$STOP" -ne 0 ]; then
    local health
    health="$LOG_DIR/$(printf '%02d' "$STEP_NO")-health.log"
    healthy "$health" || { log "the lab is not healthy after $1, see $health: stopping the night"; STOP=1; }
  fi
  return 0
}

start_load_log() {
  vmstat -t 5 > "$LOG_DIR/vmstat.log" 2>&1 &
  LOAD_PIDS="$!"
  (
    while true; do
      echo "== $(date -Is)"
      # shellcheck disable=SC2046  # one argument per container name
      docker stats --no-stream --format '{{.Name}} {{.CPUPerc}} {{.MemUsage}}' \
        $(docker ps --format '{{.Names}}' | grep '^chaos-lab-') 2>&1
      sleep 25
    done
  ) > "$LOG_DIR/docker-stats.log" 2>&1 &
  LOAD_PIDS="$LOAD_PIDS $!"
}

# Whatever happened, the night ends with the weak app in the cluster and the memory put back.
finish() {
  local out="$LOG_DIR/99-finish.log"
  trap '' INT
  [ "$FORCE" -eq 0 ] || return
  log "finishing: the weak app and the memory"
  if [ "$APP" != "weak" ]; then
    if [ "$(pending_undos)" = "0" ]; then
      to_weak "$out" || log "ERROR: going back to the weak app failed, see $out"
    else
      log "ERROR: pending undos in the database; not switching apps. lab/apps is still '$APP'"
    fi
  fi
  if [ -n "$CURRENT_MEMORY" ]; then
    end_series "$out" || log "ERROR: saving the memory of the series failed, see $out"
  fi
  if [ -n "$FINAL_MEMORY" ]; then
    restore_memory "$FINAL_MEMORY" "$out" && log "memory: $FINAL_MEMORY is back in knowledge_chunks" \
      || log "ERROR: putting the memory back failed, see $out"
  fi
  if [ -s "$LOG_DIR/steps.tsv" ] && [ -x "$PYTHON_SCORE" ]; then
    "$SCRIPT_DIR/dev.sh" up >> "$out" 2>&1
    eval "$("$SCRIPT_DIR/dev.sh" env)"
    : > "$LOG_DIR/score.md"
    score_series "The hardened app, the control group" '^hardened-' "$HARDENED_TRUTH" "$out"
    score_series "The weak app, Sonnet, memory from empty" '^weak-sonnet-' "$WEAK_TRUTH" "$out"
    score_series "The weak app, Haiku, memory from empty" '^weak-haiku-' "$WEAK_TRUTH" "$out"
    score_series "The weak app, without a model (baselines, checks, rollout)" '^weak-(baseline|checks|verify)' "$WEAK_TRUTH" "$out"
    log "scores in $LOG_DIR/score.md"
  fi
  # shellcheck disable=SC2086
  kill ${LOAD_PIDS:-} 2>/dev/null
  log "night over"
}

# One table per series: the runs the steps whose names match made, against that app's ground truth.
score_series() {
  local title="$1" pattern="$2" truth="$3" out="$4" runs
  runs="$(awk -F'\t' -v p="$pattern" '$3 ~ p && $5 ~ /^[0-9]+$/ {print $5}' "$LOG_DIR/steps.tsv" | tr '\n' ' ')"
  [ -n "$runs" ] || return 0
  printf '## %s\n\n' "$title" >> "$LOG_DIR/score.md"
  # shellcheck disable=SC2086  # one argument per run
  if (cd "$REPO_DIR" && "$PYTHON_SCORE" eval/score.py $runs --ground-truth "$truth") >> "$LOG_DIR/score.md" 2>> "$out"; then
    printf '\n' >> "$LOG_DIR/score.md"
  else
    log "ERROR: scoring $title (runs $runs) failed, see $out"
  fi
}

check() {
  local ok=1
  need() { if ! "$@" >/dev/null 2>&1; then echo "FAIL: $*"; ok=0; else echo "ok:   $*"; fi; }
  for tool in kubectl jq docker vmstat python3 systemd-inhibit; do need command -v "$tool"; done
  need [ "$(kubectl config current-context)" = "$CONTEXT" ]
  need [ "$(df --output=avail -k "$HOME" | tail -1)" -ge "$MIN_FREE_KB" ]
  need kubectl --context "$CONTEXT" -n "$SYSTEM_NAMESPACE" get secret "$RELEASE-anthropic"
  need kubectl --context "$CONTEXT" -n "$SYSTEM_NAMESPACE" get cronjob "$RELEASE-orchestrator"
  need [ -z "$(kubectl --context "$CONTEXT" -n "$SYSTEM_NAMESPACE" get jobs -o json | jq -r '.items[] | select((.status.active // 0) > 0) | .metadata.name')" ]
  need sql "SELECT 1"
  need [ "$(pending_undos)" = "0" ]
  need [ "$(sql "SELECT count(*) FROM runs WHERE status = 'running'")" = "0" ]
  # Going back to the weak app removes the hardened fields only if the app was applied with kubectl apply.
  need [ -n "$(kubectl --context "$CONTEXT" -n "$NAMESPACE" get deployment frontend -o jsonpath='{.metadata.annotations.kubectl\.kubernetes\.io/last-applied-configuration}')" ]
  need kubectl --context "$CONTEXT" apply -k "$HARDENED" --dry-run=server
  need python3 -c "import mcp, psycopg, yaml"
  need "$PYTHON_SCORE" -c "import psycopg, yaml"
  need [ -f "$HARDENED_TRUTH" ]
  need env TIMEOUT=30 "$SCRIPT_DIR/health-check.sh" "$NAMESPACE"
  echo "memory rows now: $(sql "SELECT count(*) FROM knowledge_chunks WHERE namespace = '$NAMESPACE'")"
  echo "last run: $(last_run)"
  [ "$ok" -eq 1 ] && echo "ready for the night" || { echo "not ready"; return 1; }
}

night() {
  mkdir -p "$LOG_DIR"
  trap on_interrupt INT TERM
  trap finish EXIT
  check > "$LOG_DIR/00-check.log" 2>&1 || die "the check failed, see $LOG_DIR/00-check.log"
  START_RUN="$(last_run)"
  start_load_log
  log "night $STAMP, after run $START_RUN, logs in $LOG_DIR"

  # The memory as it is now, built by the old judge, kept apart for the whole night.
  memory_series before
  FINAL_MEMORY="$CURRENT_MEMORY"
  end_series "$LOG_DIR/00-memory.log" || die "saving the memory failed, see $LOG_DIR/00-memory.log"

  # 1. The control group, with its own memory.
  memory_series hardened
  do_step to-hardened to_hardened
  if [ "$APP" = "hardened" ] && [ "$STOP" -eq 0 ]; then
    do_step hardened-baseline fixed_run baseline
    for i in 1 2 3 4; do do_step "hardened-sonnet-$i" agent_run ""; done
  fi
  [ "$STOP" -eq 0 ] && { end_series "$LOG_DIR/memory-hardened.log" || STOP=1; }
  [ "$STOP" -eq 0 ] || return
  if [ "$APP" = "hardened" ]; then
    if [ "$(pending_undos)" = "0" ]; then
      do_step to-weak to_weak
      [ "$APP" = "weak" ] || STOP=1
    else
      log "pending undos after the hardened series: stopping"; STOP=1
    fi
  fi
  [ "$STOP" -eq 0 ] || return

  # 2. The weak app, Sonnet with memory from empty: this series' memory is what the night leaves.
  memory_series sonnet
  FINAL_MEMORY="$CURRENT_MEMORY"
  do_step weak-baseline fixed_run baseline
  for i in 1 2 3 4 5; do do_step "weak-sonnet-$i" agent_run ""; done
  do_step weak-checks fixed_run checks
  for i in 1 2; do do_step "weak-verify-rollout-$i" fixed_run verify --all-journeys --only productcatalogservice; done
  [ "$STOP" -eq 0 ] && { end_series "$LOG_DIR/memory-sonnet.log" || STOP=1; }
  [ "$STOP" -eq 0 ] || return

  # 3. Haiku with its own memory from empty, and a second baseline.
  memory_series haiku
  for i in 1 2 3; do do_step "weak-haiku-$i" agent_run "$HAIKU"; done
  [ "$STOP" -eq 0 ] && { end_series "$LOG_DIR/memory-haiku.log" || STOP=1; }
  do_step weak-baseline-2 fixed_run baseline
}

case "${1:-}" in
  check) mkdir -p "$LOG_DIR" && check ;;
  run)
    # Keep the laptop awake for the whole night.
    if [ -z "${EVAL_NIGHT_INHIBITED:-}" ]; then
      EVAL_NIGHT_INHIBITED=1 exec systemd-inhibit --what=sleep:idle \
        --who=chaos-agent --why="overnight eval" "$0" run
    fi
    night ;;
  *) echo "usage: $0 check | run" >&2; exit 2 ;;
esac
