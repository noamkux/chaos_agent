"""Score agent runs against the ground truth (ADR-0032), from what the database already holds.

Terms used in this file:
- entry: one record of ground_truth.yaml, a weakness or an expected survival, with the action that shows
  it and the impact it has.
- experiment: one run_experiment step that changed something (verdict broke, withstood or inconclusive).
- broken journey: a journey of an experiment whose seconds after the action were degraded against the
  run's noise, by the judge's own rule (judge.degraded), or whose users were not sent. It is judged again
  from the stored timeline, with the noise of the run's earlier experiments rebuilt from their timelines,
  so runs judged by an earlier rule are scored by the current one.
- cited step: a step the agent's summary cites under confirmed weaknesses or known from earlier runs.
- recall so far: what this run and the runs before it in the same table found, together. A run with
  memory skips what is already known on purpose, so its own recall falls as the memory grows; recall so
  far is what the series as a whole knows after it. Score one series per table for it to mean that.

Flow: load_runs reads every run of the namespace up to the last one asked for, so the memory measure
knows what earlier runs found. score_run scores one run: it matches every experiment to the entries, reads
the citations from the summary, and adds the efficiency and safety numbers. render writes one markdown
table of all the runs asked for, then the details of each.

Usage, from the repository root, with the PG* variables of the chart's Postgres:
    python eval/score.py 30 31 32 33 34 > eval/results.md
    python eval/score.py 40 41 --ground-truth lab/apps/boutique-hardened/ground_truth.yaml
"""
import argparse
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "orchestrator"))
from experiments import judge

GROUND_TRUTH = ROOT / "lab/apps/boutique/ground_truth.yaml"
COUNTED_VERDICTS = {"broke", "withstood", "inconclusive"}
# Steps recorded as not allowed that are warnings of the orchestrator, not calls of the agent.
WARNING_STEPS = {"read_tools_missing"}

# Dollars per million tokens: input, output, cache read, cache write (5 minutes). Haiku 5.5 costs five
# times more for a prompt over 100,000 tokens. A model not listed gets no cost.
PRICES = {
    "claude-haiku-5-5": (0.10, 0.50, 0.01, 0.125),
    "claude-sonnet-5-5": (2.00, 10.00, 0.10, 2.50),
}
LONG_PROMPT = {"claude-haiku-5-5": (100_000, 5)}

SECTIONS = [("unconfirmed", None), ("confirmed", "cited"), ("known from earlier", "cited"),
            ("what held", None), ("held", None), ("what i would test", None),
            ("what you would test", None), ("next", None)]


def load_ground_truth(path):
    """The ground truth, with weaknesses and expected survivals."""
    with open(path) as f:
        return yaml.safe_load(f)


def flatten(value, prefix=""):
    """Every leaf of a patch as (dotted path, value). Lists add no index, so the containers of a pod
    template are spec.template.spec.containers.resources.limits.cpu, whichever container it is."""
    if isinstance(value, dict):
        return [leaf for key, child in value.items()
                for leaf in flatten(child, f"{prefix}.{key}" if prefix else str(key))]
    if isinstance(value, list):
        return [leaf for child in value for leaf in flatten(child, prefix)]
    return [(prefix, value)]


QUANTITY_SUFFIXES = {"m": 0.001, "Ki": 2**10, "Mi": 2**20, "Gi": 2**30, "K": 1e3, "M": 1e6, "G": 1e9}


def quantity(value):
    """A Kubernetes quantity as a number: 20m is 0.02, 64Mi is 67108864. None if it is not one."""
    text = str(value)
    for suffix, factor in sorted(QUANTITY_SUFFIXES.items(), key=lambda item: -len(item[0])):
        if text.endswith(suffix):
            text, scale = text[: -len(suffix)], factor
            break
    else:
        scale = 1
    try:
        return float(text) * scale
    except ValueError:
        return None


def value_matches(wanted, value):
    """Whether a patch's value is what an entry wants: equal, any ("*"), or at most a quantity ("<=20m")."""
    if wanted == "*":
        return True
    if isinstance(wanted, str) and wanted.startswith("<="):
        limit, actual = quantity(wanted[2:]), quantity(value)
        return limit is not None and actual is not None and actual <= limit
    return value == wanted


def action_matches(expected, action, zone_of):
    """Whether an experiment's action is the entry's action: every field the entry gives must be equal,
    sets must be set by the patch ("*" for any value, or for any path under it, "<=20m" for a quantity at
    most that), and a zone also matches a single node of that zone."""
    for field, value in expected.items():
        if field == "sets":
            leaves = flatten(action.get("patch") or {})
            for path, wanted in value.items():
                # "*" matches any value, and anything under the path: annotations: "*" is any annotation.
                if not any((p == path and value_matches(wanted, v))
                           or (wanted == "*" and p.startswith(path + ".")) for p, v in leaves):
                    return False
        elif field == "zone" and action.get("zone") is None and action.get("node"):
            if zone_of.get(action["node"]) != value:
                return False
        elif action.get(field) != value:
            return False
    return True


STATUS_OF_CHAR = {char: status for status, char in judge.TIMELINE_CHARS.items()}


def before_action(timeline):
    """The statuses of the seconds before the action, from a stored timeline: the action is the first |."""
    return [STATUS_OF_CHAR[char] for char in timeline.partition("|")[0]]


def after_action(timeline):
    """The statuses of the seconds from the action on, from a stored timeline."""
    return [STATUS_OF_CHAR[char] for char in timeline.partition("|")[2] if char != "|"]


def broken_journeys(result, noise=None):
    """The journeys that broke in one experiment, judged again by the judge's current rule against the
    noise of the run's earlier experiments. A result stored without timelines keeps its own numbers."""
    noise = noise or {}
    broken = set()
    for name, facts in (result.get("journeys") or {}).items():
        if facts.get("not_sent"):
            broken.add(name)
        elif "timeline" in facts:
            earlier = noise.get(name, (0, 0, 0))
            now = tuple(old + new for old, new in zip(earlier, judge.counts_of(before_action(facts["timeline"]))))
            if judge.degraded_against(after_action(facts["timeline"]), now):
                broken.add(name)
        elif facts.get("broken_s", 0) >= judge.MIN_BROKEN_S:
            broken.add(name)
    return broken


def noise_of(result):
    """What one experiment adds to the run's noise: its seconds before the action, per journey."""
    return {name: judge.counts_of(before_action(facts["timeline"]))
            for name, facts in (result.get("journeys") or {}).items() if "timeline" in facts}


def impact(entry, experiment):
    """What an experiment showed about an entry: "broke" if a journey of the entry broke, "withstood" if
    the experiment measured a journey of the entry and none of them broke, None if it measured none of
    them or could not be judged."""
    if experiment["verdict"] not in ("broke", "withstood"):
        return None
    journeys = set(entry["impact"]["journeys"])
    measured = journeys & set(experiment["result"].get("journeys") or {})
    if not measured:
        return None
    return "broke" if measured & experiment["broken"] else "withstood"


def node_zones(rows):
    """The zone of every node, from any tool output in the run that lists nodes with their zone (the
    placement the orchestrator reads before the first call of the model and before a node failure)."""
    zones = {}

    def walk(value):
        if isinstance(value, dict):
            nodes = value.get("nodes")
            if isinstance(nodes, list):
                for node in nodes:
                    if isinstance(node, dict) and node.get("name") and node.get("zone"):
                        zones[node["name"]] = node["zone"]
            elif isinstance(nodes, dict):
                for name, node in nodes.items():
                    if isinstance(node, dict) and node.get("zone"):
                        zones[name] = node["zone"]
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    for row in rows:
        if row["kind"] == "tool":
            walk(row["output"])
    return zones


def experiments_of(rows):
    """The run's experiments that changed something, in order, judged again with the run's noise as it
    grew experiment by experiment, as the judge learns it during a run."""
    found, noise = [], {}
    for row in rows:
        if row["kind"] == "tool" and row["name"] == "run_experiment" and row["allowed"]:
            result = row["output"] or {}
            verdict = result.get("verdict")
            if verdict in ("broke", "withstood"):
                broken = broken_journeys(result, noise)
                verdict = "broke" if broken else "withstood"
                noise = judge.add_noise(noise, noise_of(result))
            if verdict in COUNTED_VERDICTS:
                found.append({"step": row["step"], "action": (row["input"] or {}).get("action") or {},
                              "verdict": verdict, "stored_verdict": result["verdict"], "result": result,
                              "broken": broken if verdict in ("broke", "withstood") else set()})
    return found


def summary_of(rows):
    """The model's last text: its summary. Empty for a run without a model (the baseline)."""
    llm = [row for row in rows if row["kind"] == "llm"]
    if not llm:
        return None
    return "\n".join(block.get("text", "") for block in (llm[-1]["output"] or []) if block.get("type") == "text")


def section_of(line):
    """The summary section a heading line opens, or False if the line is not a heading."""
    stripped = line.strip()
    if not (stripped.startswith(("#", "**")) or stripped.endswith(":")):
        return False
    text = re.sub(r"^[#*\s\d.)]+", "", stripped).rstrip("*: ").lower()
    if len(text) > 60:
        return False
    for keyword, section in SECTIONS:
        if text.startswith(keyword):
            return section
    return False


CITATION = re.compile(r"(?:\brun\s+(\d+)\W{0,3})?\bsteps?\s+(\d+(?:\s*(?:,\s*and|,|and|&)\s*\d+)*)", re.IGNORECASE)


def cited_steps(summary, run_id):
    """The steps of this run cited under confirmed weaknesses or known from earlier runs. A citation of
    another run ("run 32 step 40") is left out: only this run's own experiments are scored."""
    steps, section = set(), None
    for line in summary.splitlines():
        opened = section_of(line)
        if opened is not False:
            section = opened
            continue
        if section != "cited":
            continue
        for run, numbers in CITATION.findall(line):
            if run and int(run) != run_id:
                continue
            steps.update(int(n) for n in re.findall(r"\d+", numbers))
    return steps


def cost_usd(model, rows):
    """What the run's model calls cost, from their tokens, or None for a model with no price."""
    if model not in PRICES:
        return None
    total = 0.0
    for row in rows:
        if row["kind"] != "llm":
            continue
        tokens = [row.get("tokens_in") or 0, row.get("tokens_out") or 0,
                  row.get("cache_read_tokens") or 0, row.get("cache_write_tokens") or 0]
        prompt = tokens[0] + tokens[2] + tokens[3]
        threshold, factor = LONG_PROMPT.get(model, (None, 1))
        scale = factor if threshold and prompt > threshold else 1
        total += sum(t * p * scale for t, p in zip(tokens, PRICES[model])) / 1_000_000
    return round(total, 4)


def score_run(run, rows, pending_undos, truth, known_before):
    """Every measure of one run. known_before holds the weaknesses earlier runs on the namespace broke."""
    zone_of = node_zones(rows)
    experiments = experiments_of(rows)
    weaknesses = [e for e in truth["weaknesses"] if e.get("verified", True)]
    unverified = [e for e in truth["weaknesses"] if not e.get("verified", True)]
    survivals = truth.get("expected_survivals") or []
    trivial = truth.get("trivial") or []
    summary = summary_of(rows)
    cited = cited_steps(summary, run["id"]) if summary is not None else set()

    def showing(entries, experiment):
        return [e for e in entries if action_matches(e["action"], experiment["action"], zone_of)
                and impact(e, experiment) == "broke"]

    found_broke, found_cited, false_broke, false_cited, unknown, unverified_hits = set(), set(), set(), set(), [], set()
    tested, trivial_steps = set(), []
    repeats = 0
    for experiment in experiments:
        if experiment["verdict"] in ("broke", "withstood"):
            tested.update(e["id"] for e in weaknesses if action_matches(e["action"], experiment["action"], zone_of))
        weak = showing(weaknesses, experiment)
        false = showing(survivals, experiment)
        is_cited = experiment["step"] in cited
        found_broke.update(e["id"] for e in weak)
        false_broke.update(e["id"] for e in false)
        unverified_hits.update(e["id"] for e in showing(unverified, experiment))
        if is_cited:
            found_cited.update(e["id"] for e in weak)
        if is_cited and any(action_matches(e["action"], experiment["action"], zone_of) for e in survivals):
            false_cited.update(e["id"] for e in survivals
                               if action_matches(e["action"], experiment["action"], zone_of))
        # A change that breaks any service by design is not an unknown finding; a weakness it shows still counts.
        is_trivial = any(action_matches(t["action"], experiment["action"], zone_of) for t in trivial)
        if is_trivial and not weak:
            trivial_steps.append(experiment["step"])
        if experiment["verdict"] == "broke" and not weak and not false and not is_trivial \
                and not showing(unverified, experiment):
            unknown.append({"step": experiment["step"], "action": experiment["action"], "cited": is_cited,
                            "journeys": sorted(experiment["broken"])})
        if any(e["id"] in known_before and action_matches(e["action"], experiment["action"], zone_of)
               for e in weaknesses):
            repeats += 1

    llm = [row for row in rows if row["kind"] == "llm"]
    duration = (run["finished_at"] - run["started_at"]).total_seconds() if run.get("finished_at") and run.get("started_at") else None
    return {
        "run": run["id"], "model": run["model"], "status": run["status"],
        "weaknesses": len(weaknesses),
        "tested": sorted(tested),
        "trivial": trivial_steps,
        "found_cited": sorted(found_cited) if summary is not None else None,
        "found_broke": sorted(found_broke),
        "false_cited": sorted(false_cited) if summary is not None else None,
        "false_broke": sorted(false_broke),
        "unknown": unknown,
        "unverified": sorted(unverified_hits),
        "experiments": len(experiments),
        "not_run": sum(1 for row in rows if row["name"] == "run_experiment"
                       and (row["output"] or {}).get("verdict") == "not_run"),
        "inconclusive": sum(1 for e in experiments if e["verdict"] == "inconclusive"),
        "rejudged": sum(1 for e in experiments if e["verdict"] != e["stored_verdict"]),
        "rounds": len(llm),
        "tokens_in": sum((r.get("tokens_in") or 0) + (r.get("cache_read_tokens") or 0)
                         + (r.get("cache_write_tokens") or 0) for r in llm),
        "tokens_out": sum(r.get("tokens_out") or 0 for r in llm),
        "cost_usd": cost_usd(run["model"], rows) if llm else 0.0,
        "duration_min": round(duration / 60, 1) if duration is not None else None,
        "broken_s": sum(max([f.get("broken_s", 0) for f in (e["result"].get("journeys") or {}).values()] or [0])
                        for e in experiments),
        "denied": sum(1 for row in rows if not row["allowed"] and row["name"] not in WARNING_STEPS),
        "pending_undos": pending_undos,
        "repeats": repeats,
        "new": len(experiments) - repeats,
    }


def describe(action):
    """One short line for an experiment's action."""
    if action.get("type") == "node_failure":
        return f"node_failure {action.get('mode', 'drain')} of {action.get('zone') or action.get('node')}"
    patch = ", ".join(f"{p}={v}" for p, v in flatten(action.get("patch") or {}))
    return f"{action.get('type')} {action.get('name')}" + (f" ({patch})" if patch else "")


def render(scores):
    """One markdown table of every run, then what each run found, missed and got wrong."""
    def ids(value):
        return "n/a" if value is None else (", ".join(value) or "none")

    def recall(found, total):
        return "n/a" if found is None else f"{len(found)}/{total}"

    rows = [
        ("Model", lambda s: s["model"]),
        ("Status", lambda s: s["status"]),
        ("Weaknesses tested at all", lambda s: f"{len(s['tested'])}/{s['weaknesses']}"),
        ("Recall, cited in the summary", lambda s: recall(s["found_cited"], s["weaknesses"])),
        ("Recall, experiments that broke", lambda s: recall(s["found_broke"], s["weaknesses"])),
        ("Recall so far, cited (this run and the ones before it here)",
         lambda s: recall(s.get("so_far_cited"), s["weaknesses"])),
        ("Recall so far, experiments that broke", lambda s: recall(s.get("so_far_broke"), s["weaknesses"])),
        ("Unknown findings (to review)", lambda s: str(len(s["unknown"]))),
        ("Trivial experiments (break by design)", lambda s: str(len(s["trivial"]))),
        ("False positives, cited", lambda s: "n/a" if s["false_cited"] is None else str(len(s["false_cited"]))),
        ("False positives, broke", lambda s: str(len(s["false_broke"]))),
        ("Experiments", lambda s: str(s["experiments"])),
        ("Inconclusive", lambda s: str(s["inconclusive"])),
        ("Broke when run, withstood by the current judge", lambda s: str(s["rejudged"])),
        ("Not run (never steady)", lambda s: str(s["not_run"])),
        ("Model rounds", lambda s: str(s["rounds"])),
        ("Tokens in / out", lambda s: f"{s['tokens_in']:,} / {s['tokens_out']:,}"),
        ("Cost (USD)", lambda s: "n/a" if s["cost_usd"] is None else f"{s['cost_usd']:.2f}"),
        ("Duration (min)", lambda s: "n/a" if s["duration_min"] is None else str(s["duration_min"])),
        ("Seconds broken", lambda s: str(s["broken_s"])),
        ("Denied calls", lambda s: str(s["denied"])),
        ("Pending undos (must be 0)", lambda s: str(s["pending_undos"])),
        ("Experiments on known weaknesses / new", lambda s: f"{s['repeats']} / {s['new']}"),
    ]
    lines = ["| | " + " | ".join(f"run {s['run']}" for s in scores) + " |",
             "|---|" + "---|" * len(scores)]
    lines += [f"| {name} | " + " | ".join(value(s) for s in scores) + " |" for name, value in rows]
    for s in scores:
        lines += ["", f"### Run {s['run']}", "",
                  f"- Tested: {ids(s['tested'])}",
                  f"- Found, cited: {ids(s['found_cited'])}",
                  f"- Found, broke: {ids(s['found_broke'])}",
                  f"- Found so far, cited: {ids(s.get('so_far_cited'))}",
                  f"- False positives: cited {ids(s['false_cited'])}; broke {ids(s['false_broke'])}",
                  f"- Unverified entries shown: {ids(s['unverified'])}",
                  f"- Trivial experiments: {', '.join(f'step {n}' for n in s['trivial']) or 'none'}"]
        for u in s["unknown"]:
            lines.append(f"- Unknown, step {u['step']}{' (cited)' if u['cited'] else ''}: "
                         f"{describe(u['action'])}, broke {', '.join(u['journeys'])}")
    return "\n".join(lines) + "\n"


def load_runs(conn, namespace, last):
    """Every run of the namespace up to the last one asked for, with its steps and pending undos."""
    runs = []
    for r in conn.execute("SELECT id, model, status, started_at, finished_at FROM runs "
                          "WHERE namespace = %s AND id <= %s ORDER BY id", (namespace, last)).fetchall():
        run = {"id": r[0], "model": r[1], "status": r[2], "started_at": r[3], "finished_at": r[4]}
        steps = [{"step": s[0], "kind": s[1], "name": s[2], "input": s[3], "output": s[4], "allowed": s[5],
                  "tokens_in": s[6], "tokens_out": s[7], "cache_read_tokens": s[8], "cache_write_tokens": s[9]}
                 for s in conn.execute(
                     "SELECT step, kind, name, input, output, allowed, tokens_in, tokens_out, "
                     "cache_read_tokens, cache_write_tokens FROM steps WHERE run_id = %s ORDER BY step",
                     (run["id"],)).fetchall()]
        pending = conn.execute("SELECT count(*) FROM undo_actions WHERE run_id = %s AND status = 'pending'",
                               (run["id"],)).fetchone()[0]
        runs.append((run, steps, pending))
    return runs


def score_all(runs, truth, wanted):
    """Score every run in order, so each knows what the earlier ones broke, and keep the ones asked for,
    each with what it and the ones asked for before it found together (recall so far). Cited so far is
    n/a until a run with a summary."""
    known, scores = set(), []
    so_far_cited, so_far_broke, any_summary = set(), set(), False
    for run, steps, pending in runs:
        score = score_run(run, steps, pending, truth, known)
        known.update(score["found_broke"])
        if run["id"] in wanted:
            if score["found_cited"] is not None:
                any_summary = True
                so_far_cited.update(score["found_cited"])
            so_far_broke.update(score["found_broke"])
            score["so_far_cited"] = sorted(so_far_cited) if any_summary else None
            score["so_far_broke"] = sorted(so_far_broke)
            scores.append(score)
    return scores


def main(argv=None):
    """Score the runs given on the command line and print the markdown."""
    parser = argparse.ArgumentParser(description="Score runs against the ground truth (ADR-0032).")
    parser.add_argument("runs", nargs="+", type=int)
    parser.add_argument("--ground-truth", default=GROUND_TRUTH)
    args = parser.parse_args(argv)
    import psycopg
    truth = load_ground_truth(args.ground_truth)
    with psycopg.connect() as conn:
        runs = load_runs(conn, truth["namespace"], max(args.runs))
    print(render(score_all(runs, truth, set(args.runs))), end="")


if __name__ == "__main__":
    main()
