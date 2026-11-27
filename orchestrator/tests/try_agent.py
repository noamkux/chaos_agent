"""A run of the agent against Online Boutique, with the lab's target.yaml and Rules of Engagement."""
import asyncio
import os
import agent
import db

from pathlib import Path
import run_config

# Haiku while developing; CHAOS_MODEL=claude-sonnet-5-5 for the demo runs.
MODEL = os.environ.get("CHAOS_MODEL", "claude-haiku-5-5")
LAB = Path(__file__).resolve().parents[2] / "lab" / "apps" / "boutique"
TASK = "Find the weaknesses of the application in namespace 'boutique' by running experiments, and report them."


async def main():
    with db.connect() as conn:
        roe = run_config.load_roe(LAB / "roe.yaml")
        target = run_config.load_target(LAB / "target.yaml")
        run_id = db.create_run(conn, "boutique", MODEL, roe["max_level"], roe, 1, profile=target)
        db.claim_run(conn, run_id)
        try:
            summary = await agent.run_agent(conn, run_id, MODEL, roe, target, "boutique", TASK)
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
    """Print what the run did: tool calls and token usage."""
    experiments = conn.execute(
        "SELECT step, input->'action'->>'type', input->'action'->>'name', output->>'verdict', output->>'error' "
        "FROM steps WHERE run_id = %s AND name = 'run_experiment' ORDER BY step",
        (run_id,),
    ).fetchall()
    table("Experiments", ["step", "action", "target", "verdict", "error"], experiments)

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