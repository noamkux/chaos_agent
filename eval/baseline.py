"""Fixed experiments without the model, through the same runner and judge as the agent (ADR-0032).

Three plans:
- baseline: what a script would run, within the agent's budget: one pod deleted of every workload that is
  not protected, then a lost node failure of every zone. The workloads and zones come from the observe
  server, so the plan fits any application, not only the lab's.
- verify: the patterns that earlier runs found and the ground truth does not hold yet, each run twice so a
  result is reproduced before it becomes an entry: deleting the only pod of an optional dependency, a
  rollout, a starved optional dependency against the same dependency down, and one pod of two deleted.
- checks: two questions the runs left open. Does frontend break with half its CPU limit, as run 34 found,
  or only because the change rolls it out (the same rollout without the CPU change is the control)? And
  is home slow after a pod is deleted because the application depends on it, or because the new pod
  takes CPU from a lab whose nodes share one laptop (deleting the pod of emailservice, which home does
  not call)?

Every plan is a run of its own in the database, with model "baseline" or "verify", so eval/score.py scores
it like any run. Usage, from the repository root, with lab/dev.sh up and its PG* variables:
    python3 eval/baseline.py verify
    python3 eval/baseline.py verify --all-journeys --only productcatalogservice
    python3 eval/baseline.py checks
    python3 eval/baseline.py baseline
"""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "orchestrator"))
import config  # noqa: E402
import mcp_client  # noqa: E402
from experiments import runner, undo  # noqa: E402
from storage import db  # noqa: E402

APP_DIR = ROOT / "lab/apps/boutique"
WORKLOAD_KINDS = {"apps/Deployment", "apps/StatefulSet"}
RESTORE_AFTER_S = 60


def delete_pod(namespace, name, journeys, kind="apps/Deployment"):
    return {"hypothesis": f"Deleting one pod of {name} is not felt by users.",
            "action": {"type": "delete_pod", "namespace": namespace, "kind": kind, "name": name},
            "journeys": journeys}


def patch(namespace, name, body, journeys, hypothesis):
    return {"hypothesis": hypothesis,
            "action": {"type": "patch", "namespace": namespace, "kind": "apps/Deployment", "name": name,
                       "patch": body},
            "journeys": journeys, "restore_after_s": RESTORE_AFTER_S}


def verify_plan(namespace):
    """The experiments that check what earlier runs found, each twice except the control."""
    rollout = {"spec": {"template": {"metadata": {"annotations": {"chaos-agent.io/verify": str(int(time.time()))}}}}}
    starve = {"spec": {"template": {"spec": {"containers": [
        {"name": "server", "resources": {"limits": {"cpu": "10m"}, "requests": {"cpu": "10m"}}}]}}}}
    down = {"spec": {"replicas": 0}}
    twice = [
        delete_pod(namespace, "adservice", ["home", "product"]),
        patch(namespace, "productcatalogservice", rollout, ["home", "product"],
              "A rollout of productcatalogservice, one pod at a time, is not felt by users."),
        patch(namespace, "recommendationservice", starve, ["home", "product"],
              "recommendationservice starved of CPU is not felt: frontend renders without it, as when it is down."),
        delete_pod(namespace, "cartservice", ["home", "cart"]),
    ]
    control = patch(namespace, "recommendationservice", down, ["home", "product"],
                    "recommendationservice down is not felt: frontend renders without it.")
    return [e for e in twice for _ in range(2)] + [control]


def checks_plan(namespace):
    """The experiments for the questions earlier runs left open: frontend with half its CPU limit twice,
    the same rollout without the CPU change as its control, and the pod of emailservice deleted three
    times while only home is measured."""
    everything = ["home", "product", "cart", "checkout"]
    # Upstream frontend requests 100m and is limited to 200m: half its limit, not a starvation.
    half_cpu = {"spec": {"template": {"spec": {"containers": [
        {"name": "server", "resources": {"limits": {"cpu": "100m"}}}]}}}}
    rollout = {"spec": {"template": {"metadata": {"annotations": {"chaos-agent.io/checks": str(int(time.time()))}}}}}
    return [
        patch(namespace, "frontend", half_cpu, everything,
              "frontend with half its CPU limit, its request, still serves every journey."),
        patch(namespace, "frontend", half_cpu, everything,
              "frontend with half its CPU limit, its request, still serves every journey."),
        patch(namespace, "frontend", rollout, everything,
              "A rollout of frontend alone, the control for its CPU limit, is not felt by users."),
    ] + [delete_pod(namespace, "emailservice", ["home"]) for _ in range(3)]


async def baseline_plan(conn, run_id, tools, roe, target):
    """One pod deleted of every workload not protected, then every zone lost."""
    namespace = roe["scope"]["namespaces"][0]
    journeys = [j["name"] for j in target["journeys"]]

    async def read(tool):
        out = json.loads(await mcp_client.call_tool(conn, run_id, tools, roe["scope"]["namespaces"], tool,
                                                    {"namespace": namespace}))
        if out["is_error"]:
            raise RuntimeError(f"{tool} failed: {out['content']}")
        return out["content"]

    workloads = (await read("observe__get_workloads"))["result"]
    placement = await read("observe__get_placement")
    plan = [delete_pod(namespace, w["name"], journeys, w["kind"]) for w in sorted(workloads, key=lambda w: w["name"])
            if w["kind"] in WORKLOAD_KINDS and w["name"] not in roe["protected_workloads"]]
    zones = sorted({n["zone"] for n in placement["nodes"] if n.get("zone") and not n.get("control_plane")})
    plan += [{"hypothesis": f"Losing {zone} is not felt by users: every workload runs in another zone too.",
              "action": {"type": "node_failure", "zone": zone, "mode": "lost"},
              "journeys": journeys, "restore_after_s": RESTORE_AFTER_S} for zone in zones]
    return plan[:roe["max_experiments"]]


def report(result):
    """One line per journey: its timeline and how long it was broken."""
    print(f"  step {result.get('step')}: {result.get('verdict') or result.get('error')}")
    if result.get("reason"):
        print(f"    {result['reason']}")
    for name, facts in sorted((result.get("journeys") or {}).items()):
        print(f"    {name:9} {facts['timeline']}  broken {facts['broken_s']}s, "
              f"recovered after {facts['recovered_after_s']}s, errors {facts['after_action'].get('errors')}")


async def main(argv=None):
    parser = argparse.ArgumentParser(description="Fixed experiments without the model (ADR-0032).")
    parser.add_argument("plan", choices=["baseline", "verify", "checks"])
    parser.add_argument("--app-dir", type=Path, default=APP_DIR)
    parser.add_argument("--all-journeys", action="store_true",
                        help="measure every journey of target.yaml in every experiment, as the agent does")
    parser.add_argument("--only", help="run only the verify or checks experiments on this workload")
    args = parser.parse_args(argv)
    roe = config.load_roe(args.app_dir / "roe.yaml")
    target = config.load_target(args.app_dir / "target.yaml")
    scope = roe["scope"]["namespaces"]
    with db.connect() as conn:
        run_id = db.create_run(conn, scope[0], args.plan, roe["max_level"], roe, 0, profile=target)
        if not db.claim_run(conn, run_id):
            raise SystemExit(f"run {run_id}: another run holds {scope[0]}")
        print(f"run {run_id}: {args.plan}")
        try:
            tools = {t["name"] for t in await mcp_client.load_tools(roe["max_level"])}
            missing = runner.EXPERIMENT_TOOLS - tools
            if missing:
                raise RuntimeError(f"server tools missing: {sorted(missing)}")
            await undo.restore_pending(conn, run_id, tools, scope)
            if args.plan in ("verify", "checks"):
                plan = verify_plan(scope[0]) if args.plan == "verify" else checks_plan(scope[0])
                if args.only:
                    plan = [e for e in plan if e["action"]["name"] == args.only]
                if args.all_journeys:
                    plan = [{**e, "journeys": [j["name"] for j in target["journeys"]]} for e in plan]
            else:
                plan = await baseline_plan(conn, run_id, tools, roe, target)
            state = {"experiments": 0}
            for number, experiment in enumerate(plan, 1):
                print(f"\n{number}/{len(plan)} {json.dumps(experiment['action'])}")
                report(json.loads(await runner.run_experiment(conn, run_id, tools, roe, target, scope[0],
                                                              state, experiment)))
            db.finish_run(conn, run_id, "completed")
        except BaseException as error:
            db.finish_run(conn, run_id, "aborted" if isinstance(error, KeyboardInterrupt) else "failed", str(error))
            raise
    print(f"\nscore it: python3 eval/score.py {run_id}")


if __name__ == "__main__":
    asyncio.run(main())
