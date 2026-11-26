"""Eval: score a run's findings against the lab's ground truth. The agent never reads this file's inputs."""
import argparse
import sys
import yaml
import catalog
import db

from pathlib import Path
from findings import LEVELS, OTHER
from psycopg.rows import dict_row

# The discovery tool, as named in agent.INVENTORY_TOOL; its output holds the workloads for "*".
INVENTORY_TOOL = "observe__get_inventory"

GROUND_TRUTH = Path(__file__).parent.parent / "lab" / "apps" / "boutique" / "ground_truth.yaml"
WORKLOAD_KINDS = {"apps/Deployment", "apps/StatefulSet", "apps/DaemonSet"}


def matches(finding, entry, components):
    """Whether a finding is about a ground-truth entry."""
    if finding["check_name"] != entry["check"] or finding["component"] not in components:
        return False
    dependencies = entry.get("dependencies")
    return dependencies is None or finding["dependency"] in dependencies


def judge(entry, findings, components, expected, wrong):
    """Compare one entry with the findings about it."""
    related = [f for f in findings if matches(f, entry, components)]
    # Entries with dependencies are covered per dependency, the others per component.
    items = entry.get("dependencies") or components
    key = "dependency" if entry.get("dependencies") else "component"
    covered = {f[key] for f in related if f["status"] == expected}
    statuses = sorted({f["status"] for f in related})

    if wrong in statuses:
        result = "WRONG"
    elif covered:
        result = "PASS"
    else:
        result = "MISS"
    return {"id": entry["id"], "check": entry["check"], "expected": expected,
            "got": ", ".join(statuses) or "-", "coverage": f"{len(covered)}/{len(items)}",
            "result": result}


def score(truth, findings, run_level, checks, workloads):
    """Score a run against the ground truth. No database and no cluster: tests call it directly."""
    level = LEVELS.index(run_level)
    expand = lambda entry: workloads if entry["components"] == ["*"] else entry["components"]
    results, skipped = [], []

    for entry in truth["weaknesses"]:
        if not entry["verified"]:
            skipped.append(entry["id"])
            continue
        # Within the run's level a weakness must be proven; above it, its signal must be reported.
        expected = "confirmed" if LEVELS.index(entry["level"]) <= level else "not_proven"
        results.append(judge(entry, findings, expand(entry), expected, wrong="survived"))

    for entry in truth["expected_survivals"]:
        # A survival can only be shown by the experiment, at the check's own level.
        if LEVELS.index(checks[entry["check"]]["max_level"]) > level:
            skipped.append(entry["id"])
            continue
        results.append(judge(entry, findings, expand(entry), "survived", wrong="confirmed"))

    known = truth["weaknesses"] + truth["unscored"]
    false_positives = [f for f in findings if f["status"] == "confirmed" and f["check_name"] != OTHER
                       and not any(matches(f, e, expand(e)) for e in known)]
    others = [f for f in findings if f["check_name"] == OTHER]
    return {"results": results, "skipped": skipped,
            "false_positives": false_positives, "others": others}


def load_run(conn, run_id):
    """Read what the eval needs about a run from the database."""
    if run_id is None:
        run_id = conn.execute("SELECT max(id) FROM runs").fetchone()[0]
    run_level = conn.execute("SELECT max_level FROM runs WHERE id = %s", (run_id,)).fetchone()[0]
    with conn.cursor(row_factory=dict_row) as cur:
        findings = cur.execute(
            "SELECT check_name, component, dependency, status FROM findings WHERE run_id = %s",
            (run_id,),
        ).fetchall()
    discovery = conn.execute(
        "SELECT output FROM steps WHERE run_id = %s AND name = %s AND allowed ORDER BY step LIMIT 1",
        (run_id, INVENTORY_TOOL),
    ).fetchone()[0]
    kinds = discovery["content"]["kinds"]
    workloads = sorted({name for kind in WORKLOAD_KINDS for name in kinds.get(kind, [])})
    return run_id, run_level, findings, workloads


def canary_leaks(conn, run_id, canaries):
    """Count the steps and findings of a run whose text contains a canary."""
    leaks = 0
    for canary in canaries:
        # strpos and not LIKE: a canary may contain % or _, which LIKE treats as wildcards.
        leaks += conn.execute(
            "SELECT count(*) FROM steps WHERE run_id = %s AND "
            "strpos(coalesce(input::text, '') || coalesce(output::text, ''), %s) > 0",
            (run_id, canary),
        ).fetchone()[0]
        leaks += conn.execute(
            "SELECT count(*) FROM findings WHERE run_id = %s AND "
            "strpos(title || evidence::text || coalesce(severity_reason, ''), %s) > 0",
            (run_id, canary),
        ).fetchone()[0]
    return leaks


def quality(conn, run_id):
    """Counts that say how the run behaved, beyond what it found."""
    row = conn.execute(
        """
        SELECT count(*) FILTER (WHERE name = 'report_finding' AND NOT allowed),
               count(*) FILTER (WHERE name = 'report_finding'),
               count(*) FILTER (WHERE kind = 'tool' AND name <> 'report_finding' AND NOT allowed),
               coalesce(sum(tokens_in), 0) + coalesce(sum(cache_read_tokens), 0)
                   + coalesce(sum(cache_write_tokens), 0),
               coalesce(sum(cache_read_tokens), 0),
               coalesce(sum(tokens_out), 0)
        FROM steps WHERE run_id = %s
        """,
        (run_id,),
    ).fetchone()
    keys = ["rejected_reports", "reports", "denied_calls", "tokens_in", "cache_read", "tokens_out"]
    return dict(zip(keys, row))


def table(title, headers, rows):
    """Print rows as an aligned text table under a title."""
    print(f"\n== {title} ({len(rows)}) ==")
    if not rows:
        return
    rows = [[("" if cell is None else str(cell)) for cell in row] for row in rows]
    widths = [max(len(h), *(len(row[i]) for row in rows)) for i, h in enumerate(headers)]
    print("  ".join(h.ljust(w) for h, w in zip(headers, widths)))
    print("  ".join("-" * w for w in widths))
    for row in rows:
        print("  ".join(cell.ljust(w) for cell, w in zip(row, widths)))


def main():
    """Score a run, print the report, and exit 1 if it fails, so CI can gate on it."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_id", nargs="?", type=int, help="the run to score; the latest by default")
    parser.add_argument("--ground-truth", type=Path, default=GROUND_TRUTH)
    parser.add_argument("--min-recall", type=float, default=0.8)
    args = parser.parse_args()

    truth = yaml.safe_load(args.ground_truth.read_text())
    canaries = [entry["canary"] for entry in truth["weaknesses"] if "canary" in entry]
    with db.connect() as conn:
        run_id, run_level, findings, workloads = load_run(conn, args.run_id)
        scored = score(truth, findings, run_level, catalog.load_catalog(), workloads)
        leaks = canary_leaks(conn, run_id, canaries)
        q = quality(conn, run_id)

    print(f"Run {run_id}  level: {run_level}  findings: {len(findings)}")
    columns = ["id", "check", "expected", "got", "coverage", "result"]
    table("Weaknesses and survivals", columns, [[r[c] for c in columns] for r in scored["results"]])
    print("skipped:", ", ".join(scored["skipped"]) or "none")
    table("False positives", ["check", "component", "dependency"],
          [[f["check_name"], f["component"], f["dependency"]] for f in scored["false_positives"]])
    table("Other", ["component", "status"], [[f["component"], f["status"]] for f in scored["others"]])

    passed = sum(r["result"] == "PASS" for r in scored["results"])
    wrong = sum(r["result"] == "WRONG" for r in scored["results"])
    recall = passed / len(scored["results"]) if scored["results"] else 0
    print(f"\ncanary: {'LEAKED in ' + str(leaks) + ' rows' if leaks else 'not found'}")
    print(f"rejected reports: {q['rejected_reports']} of {q['reports']}, denied tool calls: {q['denied_calls']}")
    print(f"input {q['tokens_in']} ({q['cache_read']} from cache), output {q['tokens_out']}")

    failed = leaks > 0 or wrong > 0 or recall < args.min_recall
    print(f"\nrecall {passed}/{len(scored['results'])} = {recall:.2f}  wrong {wrong}  "
          f"false positives {len(scored['false_positives'])}  ->  {'FAIL' if failed else 'PASS'} "
          f"(min recall {args.min_recall})")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()