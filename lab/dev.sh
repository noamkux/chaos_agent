#!/usr/bin/env bash
# Runs everything a local orchestrator run needs, in the background, from one terminal:
# port-forwards to Postgres (5432), the probe server (8082) and the disrupt server (8083), and the
# observe server from the source on this machine (8081). Restarts all of them on every "up", so a
# port-forward left behind by a restarted pod, or an observe server running old code, cannot linger.
#
# Usage:
#   lab/dev.sh up        start (or restart) everything, then check every server's tools
#   lab/dev.sh status    show what listens and which tools each server exposes
#   lab/dev.sh down      stop everything
#   eval "$(lab/dev.sh env)"   set the PG* variables for the orchestrator in this shell
#
# Settings: NAMESPACE (chaos-system), RELEASE (chaos-agent), ALLOWED_NAMESPACES (boutique),
# PYTHON (python3). Logs go to $LOG_DIR (/tmp/chaos-agent-dev).
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NAMESPACE="${NAMESPACE:-chaos-system}"
RELEASE="${RELEASE:-chaos-agent}"
ALLOWED_NAMESPACES="${ALLOWED_NAMESPACES:-boutique}"
PYTHON="${PYTHON:-python3}"
LOG_DIR="${LOG_DIR:-/tmp/chaos-agent-dev}"

# name, local port, Service, Service port
FORWARDS=(
  "postgres 5432 $RELEASE-postgresql 5432"
  "probe 8082 $RELEASE-mcp-probe 8081"
  "disrupt 8083 $RELEASE-mcp-disrupt 8081"
)
OBSERVE_PORT=8081
PORTS=(5432 8082 8083 "$OBSERVE_PORT")

# The pid of whatever listens on a local port, or nothing. Never fails: with set -e and pipefail, a
# grep that finds nothing would otherwise stop the whole script without a word.
listener() {
  ss -ltnpH "sport = :$1" 2>/dev/null | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2 || true
}

stop_all() {
  for port in "${PORTS[@]}"; do
    pid="$(listener "$port")"
    if [ -n "$pid" ]; then
      kill "$pid" 2>/dev/null || true
      echo "stopped pid $pid on port $port"
    fi
  done
  # Port-forwards whose pod is gone no longer listen, but may still be running.
  pkill -f "port-forward svc/$RELEASE-" 2>/dev/null || true
}

wait_for_port() {
  local port="$1" name="$2"
  for _ in $(seq 1 30); do
    [ -n "$(listener "$port")" ] && return 0
    sleep 0.5
  done
  echo "ERROR: $name did not start listening on $port; see $LOG_DIR/$name.log" >&2
  tail -5 "$LOG_DIR/$name.log" >&2
  return 1
}

# Every MCP server's tools, so a server running old code shows at once.
show_tools() {
  (cd "$REPO_DIR/servers/mcp" && "$PYTHON" - <<'PY'
import asyncio
from mcp import Client

async def main():
    for level, port in [("observe", 8081), ("probe", 8082), ("disrupt", 8083)]:
        try:
            async with Client(f"http://127.0.0.1:{port}/mcp") as client:
                tools = sorted(t.name for t in (await client.list_tools()).tools)
            print(f"{level:8} {port}: {', '.join(tools)}")
        except Exception as error:
            print(f"{level:8} {port}: NOT REACHABLE ({type(error).__name__})")

asyncio.run(main())
PY
  )
}

up() {
  mkdir -p "$LOG_DIR"
  stop_all
  kubectl -n "$NAMESPACE" rollout status deploy "$RELEASE-mcp-probe" "$RELEASE-mcp-disrupt" --timeout=120s >/dev/null
  for forward in "${FORWARDS[@]}"; do
    read -r name port service service_port <<< "$forward"
    nohup kubectl -n "$NAMESPACE" port-forward "svc/$service" "$port:$service_port" \
      > "$LOG_DIR/$name.log" 2>&1 &
  done
  (cd "$REPO_DIR/servers/mcp" && LEVEL=observe ALLOWED_NAMESPACES="$ALLOWED_NAMESPACES" PORT="$OBSERVE_PORT" \
    nohup "$PYTHON" server.py > "$LOG_DIR/observe.log" 2>&1 &)
  for forward in "${FORWARDS[@]}"; do
    read -r name port _ _ <<< "$forward"
    wait_for_port "$port" "$name"
  done
  wait_for_port "$OBSERVE_PORT" observe
  echo "everything is up; logs in $LOG_DIR"
  show_tools
}

status() {
  for port in "${PORTS[@]}"; do
    pid="$(listener "$port")"
    echo "port $port: ${pid:+listening, pid $pid}${pid:-NOT listening}"
  done
  show_tools
}

env_vars() {
  # The password is read from the cluster on every call and never written to a file.
  local password
  password="$(kubectl -n "$NAMESPACE" get secret "$RELEASE-postgresql" -o jsonpath='{.data.password}' | base64 -d)"
  printf 'export PGHOST=127.0.0.1 PGPORT=5432 PGDATABASE=chaos PGUSER=chaos PGPASSWORD=%q\n' "$password"
}

case "${1:-}" in
  up) up ;;
  status) status ;;
  down) stop_all ;;
  env) env_vars ;;
  *) echo "usage: $0 up | status | down | env" >&2; exit 2 ;;
esac
