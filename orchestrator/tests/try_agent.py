"""First run of the agent loop against Online Boutique, observe level only."""
import asyncio

import agent
import db

MODEL = "claude-haiku-5-5"
ROE = {"scope": {"namespaces": ["boutique"]}}
TASK = ("Map the workloads in namespace 'boutique' and list the resilience risks "
        "you can see from their configuration.")


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
        print()
        rows = conn.execute(
            "SELECT seq, kind, name, allowed, tokens_in, tokens_out FROM steps WHERE run_id = %s ORDER BY seq",
            (run_id,),
        )
        for row in rows:
            print(row)


asyncio.run(main())