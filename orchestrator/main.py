"""One run of the agent, as the chart's Job runs it (ADR-0039).

Everything comes from the environment, so the same image runs in any cluster:
- ROE_FILE, TARGET_FILE: the Rules of Engagement and the application's profile (a mounted ConfigMap).
- TARGET_NAMESPACE: the namespace of the application under test, one of the RoE's scope.
- CHAOS_MODEL: the Claude model.
- ANTHROPIC_API_KEY (from a Secret), PG* (Postgres), MCP_<LEVEL>_URL (the servers).

Exit codes: 0 completed, 1 failed, 2 not started (bad inputs, or another run holds the namespace),
130 interrupted (SIGTERM from Kubernetes at the Job's deadline, or Ctrl+C). An interrupted run is
marked aborted; whatever it left changed is undone when the next run starts (ADR-0031).
"""
import asyncio
import os
import signal
import sys

from agent import loop
from storage import db
import config

TASK = ("Find the weaknesses of the application in namespace '{namespace}' by running experiments, "
        "and report them.")


def inputs():
    """The run's inputs from the environment, checked before anything is recorded."""
    roe = config.load_roe(os.environ["ROE_FILE"])
    target = config.load_target(os.environ["TARGET_FILE"])
    namespace = os.environ["TARGET_NAMESPACE"]
    if namespace not in roe["scope"]["namespaces"]:
        raise ValueError(f"TARGET_NAMESPACE '{namespace}' is not in the RoE's scope {roe['scope']['namespaces']}")
    return roe, target, namespace, os.environ["CHAOS_MODEL"]


async def run(conn, run_id, model, roe, target, namespace):
    """Run the agent; SIGTERM cancels it the way Ctrl+C does, so both end in the same place."""
    task = asyncio.current_task()
    asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, task.cancel)
    return await loop.run_agent(conn, run_id, model, roe, target, namespace, TASK.format(namespace=namespace))


def main():
    try:
        roe, target, namespace, model = inputs()
    except (KeyError, ValueError) as error:
        print(f"not started: {error}", file=sys.stderr)
        return 2
    with db.connect() as conn:
        db.apply_schema(conn)
        run_id = db.create_run(conn, namespace, model, roe["max_level"], roe, 1, profile=target)
        if not db.claim_run(conn, run_id):
            db.finish_run(conn, run_id, "aborted", "another run holds this namespace")
            print(f"run {run_id} not started: another run is running on {namespace}", file=sys.stderr)
            return 2
        print(f"run {run_id} on {namespace} with {model}", flush=True)
        try:
            summary = asyncio.run(run(conn, run_id, model, roe, target, namespace))
        except (KeyboardInterrupt, asyncio.CancelledError):
            conn.rollback()
            db.finish_run(conn, run_id, "aborted", "interrupted; its pending undos run when the next run starts")
            print(f"run {run_id} interrupted", file=sys.stderr)
            return 130
        except Exception as error:
            conn.rollback()
            db.finish_run(conn, run_id, "failed", f"{type(error).__name__}: {error}")
            raise
        db.finish_run(conn, run_id, "completed")
        print(summary, flush=True)
        return 0


if __name__ == "__main__":
    sys.exit(main())
