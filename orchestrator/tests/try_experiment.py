"""Manual check of the measurement chain against the lab, without the model: one measurement straight
from the probe server, then one fixed experiment through the runner, with the lab's target.yaml and RoE."""
import asyncio
import json
from pathlib import Path

import db
import run_config
import runner
import tools

LAB = Path(__file__).resolve().parents[2] / "lab" / "apps" / "boutique"

# A fixed, mild experiment: frontend has more than one replica, so this should withstand.
EXPERIMENT = {
    "hypothesis": "Deleting one frontend pod does not break home or product: the other replica serves them.",
    "action": {"type": "delete_pod", "namespace": "boutique", "kind": "apps/Deployment", "name": "frontend"},
    "journeys": ["home", "product"],
}


async def measure_once(conn, run_id, server_tools, scope, target):
    """One 15 second measurement of home, straight from the probe server."""
    settings = target["measurement"]
    entry = target["entrypoint"]
    home = {j["name"]: j["steps"] for j in target["journeys"] if j["name"] == "home"}
    output = json.loads(await tools.call_tool(conn, run_id, server_tools, scope, runner.MEASURE, {
        "namespace": "boutique", "service": entry["service"], "port": entry["port"], "journeys": home,
        "measure_for_s": 15, "new_users_per_second": settings["new_users_per_second"],
        "fail_request_after_s": settings["fail_request_after_s"]}))
    if output["is_error"]:
        print("measurement failed:", output["content"])
        return False
    content = output["content"]
    print(f"step {output['step']}: measure_for_s={content['measure_for_s']} not_sent={content['not_sent']}")
    for second in content["seconds"]:
        result = second["journeys"]["home"]
        print(f"  second {second['second']:>2}: ok={result['ok']} failed={result['failed']} "
              f"p95_ms={result['p95_ms']} errors={result['errors']}")
    return True


async def main():
    roe = run_config.load_roe(LAB / "roe.yaml")
    target = run_config.load_target(LAB / "target.yaml")
    scope = roe["scope"]["namespaces"]
    with db.connect() as conn:
        run_id = db.create_run(conn, "boutique", "try_experiment", roe["max_level"], roe, 1, profile=target)
        db.claim_run(conn, run_id)
        print(f"run {run_id}")
        try:
            server_tools = {t["name"] for t in await tools.load_tools(roe["max_level"])}
            missing = runner.EXPERIMENT_TOOLS - server_tools
            if missing:
                raise RuntimeError(f"server tools missing: {sorted(missing)}")

            print("\n1. The probe server alone")
            if not await measure_once(conn, run_id, server_tools, scope, target):
                raise RuntimeError("the probe server could not measure")

            print("\n2. One experiment through the runner")
            state = {"experiments": 0}
            result = json.loads(await runner.run_experiment(
                conn, run_id, server_tools, roe, target, "boutique", state, EXPERIMENT))
            print(json.dumps(result, indent=1))
            print("experiments counted:", state["experiments"])
            db.finish_run(conn, run_id, "completed")
        except Exception as exc:
            db.finish_run(conn, run_id, "failed", str(exc))
            raise


asyncio.run(main())
