#!/usr/bin/env bash
# Follows an agent run live, as a stream you can scroll back through: every step is printed once, in
# order, as soon as it finishes. The model's words in full and the experiments it plans, the verdict and
# timeline of every experiment, the other tool calls, and the undo log as it is written and run.
# Reads Postgres through kubectl exec, so it needs no local Postgres client. Stops when the run ends.
#
# Usage: lab/watch-run.sh [run_id]    (default: the latest run; INTERVAL in seconds, default 3)
set -euo pipefail

NAMESPACE="${NAMESPACE:-chaos-system}"
POD="${POD:-chaos-agent-postgresql-0}"
INTERVAL="${INTERVAL:-3}"

sql() {
  kubectl -n "$NAMESPACE" exec "$POD" -- psql -U chaos -d chaos -X -q -A -t -P pager=off -c "$1"
}

RUN="${1:-$(sql 'SELECT max(id) FROM runs')}"
if ! [[ "$RUN" =~ ^[0-9]+$ ]]; then
  echo "no run to follow (got '$RUN')" >&2
  exit 1
fi

STATE="$(mktemp -d)"
trap 'rm -rf "$STATE"' EXIT
echo "following run $RUN (Ctrl+C stops watching, not the run)"

while true; do
  last="$(cat "$STATE/last_step" 2>/dev/null || echo 0)"
  {
    sql "SELECT json_build_object('type', 'run', 'status', status, 'error', error) FROM runs WHERE id = $RUN"
    sql "SELECT json_build_object('type', 'step', 'step', step, 'at', to_char(started_at, 'HH24:MI:SS'),
           'kind', kind, 'name', name, 'allowed', allowed, 'finished', finished_at IS NOT NULL,
           'input', input, 'output', output, 'tokens_in', tokens_in, 'tokens_out', tokens_out, 'cache_read', cache_read_tokens)
         FROM steps WHERE run_id = $RUN AND step > $last ORDER BY step"
    sql "SELECT json_build_object('type', 'undo', 'id', id, 'status', status, 'tool', action->>'tool',
           'args', action->'args')
         FROM undo_actions WHERE run_id = $RUN ORDER BY id"
  } > "$STATE/rows"

  python3 - "$STATE" <<'PY'
import json
import shutil
import sys
import textwrap
from pathlib import Path

state = Path(sys.argv[1])
width = min(shutil.get_terminal_size((120, 40)).columns, 140)
bold, dim, red, green, reset = ("\033[1m", "\033[2m", "\033[31m", "\033[32m", "\033[0m") if sys.stdout.isatty() else ("",) * 5


def load(name, default):
    path = state / name
    return json.loads(path.read_text()) if path.exists() else default


def save(name, value):
    (state / name).write_text(json.dumps(value))


def wrapped(text, indent="  "):
    """Every line of the model's text wrapped to the terminal, keeping its blank lines and bullets."""
    for line in text.splitlines() or [""]:
        print(textwrap.fill(line, width, initial_indent=indent, subsequent_indent=indent + "  ") if line.strip() else "")


def compact(value, limit=None):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return text if limit is None or len(text) <= limit else text[:limit] + " ..."


def experiment(result):
    """The verdict, then one line and the timeline for every journey."""
    colour = red if result["verdict"] == "broke" else green if result["verdict"] == "withstood" else ""
    print(f"  {colour}{bold}verdict: {result['verdict']}{reset}")
    for journey, facts in (result.get("journeys") or {}).items():
        after = facts.get("after_action") or {}
        print(f"  {journey}: success {after.get('success')}, broken {facts.get('broken_s')}s, "
              f"recovered after {facts.get('recovered_after_s')}s, worst p95 {after.get('worst_p95_ms')} ms, "
              f"errors {compact(after.get('errors') or {})}")
        if facts.get("timeline"):
            print(f"    {dim}{facts['timeline']}{reset}")
    for key in ("reason", "nodes", "evictions"):
        if result.get(key):
            print(f"  {key}: {compact(result[key], 400)}")
    # An inconclusive verdict carries the seconds that were not steady instead of journeys.
    for part in ("baseline", "before_action"):
        if result["verdict"] == "inconclusive" and isinstance(result.get(part), dict):
            for journey, line in result[part].items():
                print(f"  {part} {journey}: {dim}{line}{reset}")


def knowledge(results):
    """A search_knowledge result: one line per chunk, closest first, with the first line of its text."""
    if not results:
        print(f"  {dim}nothing found{reset}")
    for hit in results:
        # The first line of a chunk already names its run and step, or its run and summary section.
        first = hit["content"].splitlines()[0] if hit.get("content") else ""
        line = f"  {hit.get('distance'):<5}  {hit.get('kind'):<10}  {first}"
        print(line if len(line) <= width else line[:width - 4] + " ...")


def step(row):
    header = f"{bold}── step {row['step']}  {row['at']}  {row['name']}{reset}"
    output = row.get("output")
    if row["kind"] == "llm":
        print(f"\n{header}  {dim}({row.get('tokens_in')} in, {row.get('cache_read') or 0} from cache, "
              f"{row.get('tokens_out')} out){reset}")
        for block in output or []:
            if block.get("type") == "text":
                wrapped(block["text"])
            elif block.get("type") == "tool_use":
                print(f"  {bold}→ {block['name']}{reset}")
                for line in json.dumps(block.get("input"), indent=2, ensure_ascii=False).splitlines():
                    print(f"    {line}")
        return
    print(f"\n{header}" + ("" if row["allowed"] else f"  {red}{bold}DENIED{reset}"))
    if row.get("input"):
        print(f"  {dim}input: {compact(row['input'], 300)}{reset}")
    if not isinstance(output, dict):
        print(f"  {compact(output, 500)}")
    elif "verdict" in output:
        experiment(output)
    elif isinstance(output.get("results"), list):
        knowledge(output["results"])
    elif "added" in output:
        print(f"  added {output['added']} chunks to what later runs can search")
    elif output.get("denied") or output.get("error"):
        print(f"  {red}{output.get('denied') or output.get('error')}{reset}")
    elif output.get("is_error"):
        print(f"  {red}error: {compact(output.get('content'), 800)}{reset}")
    else:
        print(f"  ok: {compact(output.get('content', output), 300)}")


rows = [json.loads(line) for line in (state / "rows").read_text().splitlines() if line.strip()]
last = load("last_step", 0)
announced = load("announced", None)
for row in (r for r in rows if r["type"] == "step"):
    if not row["finished"]:
        if announced != row["step"]:
            print(f"\n{dim}── step {row['step']}  {row['at']}  {row['name']}  running ...{reset}")
            save("announced", row["step"])
        break
    step(row)
    last = row["step"]
save("last_step", last)

undos = load("undos", {})
for row in (r for r in rows if r["type"] == "undo"):
    key = str(row["id"])
    if undos.get(key) != row["status"]:
        colour = green if row["status"] == "done" else red if row["status"] == "failed" else ""
        print(f"  {colour}undo {row['id']} {row['status']}: {row['tool']} {compact(row['args'], 200)}{reset}")
        undos[key] = row["status"]
save("undos", undos)

run = next((r for r in rows if r["type"] == "run"), None)
if run and run["status"] not in ("queued", "running"):
    print(f"\n{bold}run {run['status']}{reset}" + (f": {run['error']}" if run.get("error") else ""))
    (state / "ended").touch()
PY

  [[ -e "$STATE/ended" ]] && exit 0
  sleep "$INTERVAL"
done
