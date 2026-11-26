"""First run of the agent loop against Online Boutique, observe level only."""
import asyncio

import agent
import db

MODEL = "claude-haiku-5-5"
ROE = {"scope": {"namespaces": ["boutique"]}}
TASK = ("Test the resilience of namespace 'boutique'. Work through every check in the catalog "
        "that applies to it, within this run's level, and report the result of each check.")


async def main():
    with db.connect() as conn:
        run_id = db.create_run(conn, "boutique", MODEL, "observe", ROE, 1)
        db.claim_run(conn, run_id)
        try:
            summary = await agent.run_agent(conn, run_id, MODEL, "observe", ROE["scope"]["namespaces"], TASK)
            db.finish_run(conn, run_id, "completed")
        except Exception as exc:
            db.finish_run(conn, run_id, "failed", str(exc))
            raise

        print(summary)
        print_run(conn, run_id)


def table(title, headers, rows):
    """Print rows as an aligned text table under a title."""
    print(f"\n== {title} ({len(rows)}) ==")
    if not rows:
        return
    rows = [[("" if cell is None else str(cell)) for cell in row] for row in rows]
    widths = [max(len(str(h)), *(len(row[i]) for row in rows)) for i, h in enumerate(headers)]
    print("  ".join(str(h).ljust(w) for h, w in zip(headers, widths)))
    print("  ".join("-" * w for w in widths))
    for row in rows:
        print("  ".join(cell.ljust(w) for cell, w in zip(row, widths)))


def print_run(conn, run_id):
    """Print what the run did: findings, rejected reports, tool calls and token usage."""
    findings = conn.execute(
        """
        SELECT status, check_name, component, dependency, severity, evidence->'steps'
        FROM findings WHERE run_id = %s
        ORDER BY array_position(ARRAY['confirmed', 'survived', 'not_proven', 'inconclusive'], status),
                 check_name, component
        """,
        (run_id,),
    ).fetchall()
    table("Findings", ["status", "check", "component", "dependency", "severity", "evidence"], findings)

    rejected = conn.execute(
        "SELECT step, output->>'error' FROM steps "
        "WHERE run_id = %s AND name = 'report_finding' AND NOT allowed ORDER BY step",
        (run_id,),
    ).fetchall()
    table("Rejected reports", ["step", "error"], rejected)

    calls = conn.execute(
        "SELECT name, count(*), count(*) FILTER (WHERE NOT allowed) FROM steps "
        "WHERE run_id = %s AND kind = 'tool' GROUP BY name ORDER BY min(step)",
        (run_id,),
    ).fetchall()
    table("Tool calls", ["tool", "calls", "rejected"], calls)

    usage = conn.execute(
        "SELECT step, tokens_in, cache_read_tokens, cache_write_tokens, tokens_out FROM steps "
        "WHERE run_id = %s AND kind = 'llm' ORDER BY step",
        (run_id,),
    ).fetchall()
    table("LLM calls", ["step", "uncached in", "cache read", "cache write", "out"], usage)
    uncached, read, write, out = (sum(row[i] or 0 for row in usage) for i in range(1, 5))
    print(f"total: input {uncached + read + write} ({read} from cache, {write} written, "
          f"{uncached} uncached), output {out}")


asyncio.run(main())