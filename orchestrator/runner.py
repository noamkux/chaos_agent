"""Running one experiment: check it against the RoE, measure a baseline, make the change with a snapshot
written first, measure through it, restore, and judge. The model plans; this code executes."""
import asyncio
import json
import time

import db
import experiment
import run_config
import tools

RUN_EXPERIMENT_NAME = "run_experiment"
ACTIONS = ["patch", "delete_pod"]

MEASURE = "probe__measure_journeys"
SNAPSHOT = "disrupt__snapshot_resource"
PATCH = "disrupt__patch_resource"
RESTORE = "disrupt__restore_snapshot"
DELETE_POD = "disrupt__delete_pod"

# Every server tool an experiment needs; run_experiment is offered only when all of them are loaded.
EXPERIMENT_TOOLS = {MEASURE, SNAPSHOT, PATCH, RESTORE, DELETE_POD}

# The timings and the rate of every measurement come from target.yaml (measurement), loaded by run_config.


def run_experiment_tool(namespaces, journey_names):
    """The run_experiment tool for one run, with the run's namespaces and the profile's journeys as enums."""
    return {
        "name": RUN_EXPERIMENT_NAME,
        "description": (
            "Run one chaos experiment and get its measured result. The orchestrator checks that the system "
            "is steady, makes the change, keeps measuring the journeys you chose, restores the change after "
            "restore_after_s seconds, and judges the result against the steady state: broke, withstood or "
            "inconclusive. If the system does not get steady before the change, nothing is changed and the "
            "experiment is not counted: not_run. "
            "Actions: patch (a strategic merge patch on any object in scope; it is snapshotted first and "
            "restored after restore_after_s) and delete_pod (one running pod of a workload; its controller replaces "
            "it, nothing is restored). The timeline has one character per second: . ok, s slow, x failed, "
            "_ no answer, | the action and the restore."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "hypothesis": {"type": "string", "description": "What you expect to happen, and why."},
                "action": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": ACTIONS},
                        "namespace": {"type": "string", "enum": namespaces},
                        "kind": {"type": "string", "description": "group/Kind, for example apps/Deployment."},
                        "name": {"type": "string"},
                        "patch": {"type": "object", "description": "For type patch: the strategic merge patch."},
                    },
                    "required": ["type", "namespace", "kind", "name"],
                },
                "journeys": {"type": "array", "items": {"type": "string", "enum": journey_names},
                             "description": "The journeys to measure, from the profile."},
                "restore_after_s": {"type": "integer",
                                    "description": "For patch: seconds the change stays in place before it is restored."},
            },
            "required": ["hypothesis", "action", "journeys"],
        },
    }


def check(args, roe, target, done):
    """Every rule an experiment must pass before anything is touched. Returns an error, or None."""
    action = args.get("action") or {}
    names = args.get("journeys") or []
    profile = {j["name"]: j for j in target["journeys"]}
    if not str(args.get("hypothesis", "")).strip():
        return "hypothesis must not be empty"
    if done >= roe["max_experiments"]:
        return f"the run already ran its {roe['max_experiments']} experiments"
    if action.get("type") not in ACTIONS:
        return f"action.type must be one of {ACTIONS}"
    if action.get("namespace") not in roe["scope"]["namespaces"]:
        return f"namespace '{action.get('namespace')}' is out of scope"
    kind = str(action.get("kind", ""))
    if "/" not in kind or not action.get("name"):
        return "action needs kind as group/Kind and a name"
    if run_config.denied_group(kind, roe["deny_groups"]):
        return f"kind '{kind}' is in an API group the Rules of Engagement deny"
    if action["name"] in roe["protected_workloads"]:
        return f"'{action['name']}' is protected by the Rules of Engagement: measure it, never change it"
    if not names or any(name not in profile for name in names):
        return f"journeys must be names from the profile: {sorted(profile)}"
    if not roe["allow_write_journeys"] and any(profile[name].get("writes") for name in names):
        return "journeys that write data are not allowed by the Rules of Engagement"
    if action["type"] == "patch":
        if not isinstance(action.get("patch"), dict) or not action["patch"]:
            return "a patch action needs a non-empty patch"
        restore_after = args.get("restore_after_s")
        if not run_config.positive_int(restore_after) or restore_after > roe["max_restore_after_s"]:
            return f"restore_after_s must be 1 to {roe['max_restore_after_s']}"
    return None


def without_warmup(measurement, warmup):
    """A steady check without its warm-up seconds, renumbered from 0."""
    return {"measure_for_s": measurement["measure_for_s"] - warmup,
            "not_sent": measurement["not_sent"],
            "seconds": [{**s, "second": s["second"] - warmup}
                        for s in measurement["seconds"] if s["second"] >= warmup]}


async def wait_for_steady(measure, journeys, steady, settings):
    """Measure until every second of every journey is steady, up to steady_check_attempts times, waiting
    between tries so a system still recovering from the last experiment gets time. Returns the steady
    measurement without its warm-up (None if the system never got steady), the step of every try, and
    what went wrong in the last try."""
    warmup = settings["warmup_ignored_s"]
    steps = []
    problem = {}
    for attempt in range(settings["steady_check_attempts"]):
        if attempt:
            await asyncio.sleep(settings["wait_between_steady_checks_s"])
        measured = await measure(warmup + settings["steady_check_s"])
        steps.append(measured["step"])
        if measured["is_error"]:
            return None, steps, {"reason": f"steady check failed: {measured['content']}"}
        check = without_warmup(measured["content"], warmup)
        statuses = {j: experiment.statuses_of(check, j, steady) for j in journeys}
        if all(status == "ok" for per_journey in statuses.values() for status in per_journey):
            return check, steps, {}
        problem = {"reason": f"not steady after {attempt + 1} steady checks",
                   "last_check": {j: experiment.timeline(per_journey, set()) for j, per_journey in statuses.items()}}
    return None, steps, problem


def second_of(moment, measurement):
    """The second of the measurement in which a moment fell. k6 starts about a second after started_at,
    so one second is taken off: marking an action early is safe, marking it late would put its first
    broken second before it and turn the experiment inconclusive."""
    return max(1, int(moment - measurement["started_at"]) - 1)


async def run_experiment(conn, run_id, server_tools, roe, target, namespace, state, args):
    """Run one experiment from the model's plan. Recorded in steps as run_experiment, with every server call
    as its own step. Returns JSON text for the tool_result."""
    error = check(args, roe, target, state["experiments"])
    step_id, _ = db.start_step(conn, run_id, RUN_EXPERIMENT_NAME, args, allowed=error is None)
    if error:
        db.finish_step(conn, step_id, {"error": error})
        return json.dumps({"error": error})

    scope = roe["scope"]["namespaces"]
    action = args["action"]
    journeys = {j["name"]: j["steps"] for j in target["journeys"] if j["name"] in args["journeys"]}
    steady = target["steady_state"]
    entry = target["entrypoint"]
    settings = target["measurement"]
    restore_after = args.get("restore_after_s", 0) if action["type"] == "patch" else 0
    target_args = {"namespace": action["namespace"], "kind": action["kind"], "name": action["name"]}

    async def call(name, call_args):
        return json.loads(await tools.call_tool(conn, run_id, server_tools, scope, name, call_args))

    def measure(seconds):
        return call(MEASURE, {"namespace": namespace, "service": entry["service"], "port": entry["port"],
                              "journeys": journeys, "measure_for_s": seconds,
                              "new_users_per_second": settings["new_users_per_second"],
                              "fail_request_after_s": settings["fail_request_after_s"]})

    def finish(result):
        db.finish_step(conn, step_id, result)
        return json.dumps(result)

    # 1. Steady check: nothing is touched, and the experiment is not counted, until the system is steady.
    baseline, check_steps, problem = await wait_for_steady(measure, list(journeys), steady, settings)
    steps = {"steady_checks": check_steps}
    if baseline is None:
        return finish({"verdict": "not_run", "counted": False, **problem, "steps": steps})
    state["experiments"] += 1

    # 2. Measure in the background, through the action, the time it stays and the recovery.
    before_action = settings["measure_before_action_s"]
    measuring = asyncio.create_task(measure(before_action + restore_after + settings["measure_after_restore_s"]))
    await asyncio.sleep(before_action)
    restore_time = None

    # 3. The action. For a patch, the snapshot and its undo are written before the change.
    if action["type"] == "patch":
        snap = await call(SNAPSHOT, target_args)
        if snap["is_error"]:
            measuring.cancel()
            return finish({"error": f"snapshot failed: {snap['content']}", "steps": {**steps, "snapshot": snap["step"]}})
        undo = {"tool": RESTORE, "args": {"snapshot_id": snap["content"]["snapshot_id"]}}
        undo_id = db.add_undo(conn, run_id, step_id, undo)
        changed = await call(PATCH, {**target_args, "patch": action["patch"],
                                     "resource_version": snap["content"]["resource_version"]})
        action_time = time.time()
        steps |= {"snapshot": snap["step"], "action": changed["step"]}
        if changed["is_error"]:
            # Nothing changed: restoring only deletes the snapshot.
            await call(RESTORE, undo["args"])
            db.finish_undo(conn, undo_id, "done")
            measuring.cancel()
            return finish({"error": f"patch rejected: {changed['content']}", "steps": steps})
        await asyncio.sleep(restore_after)
        restored = await call(RESTORE, undo["args"])
        steps["restore"] = restored["step"]
        if restored["is_error"]:
            db.finish_undo(conn, undo_id, "failed")
            measuring.cancel()
            finish({"error": f"restore failed: {restored['content']}", "steps": steps})
            raise RuntimeError(f"restore failed for {action['kind']} {action['name']}; undo {undo_id} is still pending")
        db.finish_undo(conn, undo_id, "done")
        restore_time = time.time()
    else:
        deleted = await call(DELETE_POD, target_args)
        action_time = time.time()
        steps["action"] = deleted["step"]
        if deleted["is_error"]:
            measuring.cancel()
            return finish({"error": f"delete_pod failed: {deleted['content']}", "steps": steps})

    # 4. Judge, once the measurement is complete.
    measured = await measuring
    steps["measurement"] = measured["step"]
    if measured["is_error"]:
        return finish({"verdict": "inconclusive", "reason": f"measurement failed: {measured['content']}",
                       "steps": steps})
    measurement = measured["content"]
    result = experiment.judge(baseline, measurement, list(journeys), steady,
                              second_of(action_time, measurement),
                              second_of(restore_time, measurement) if restore_time else None)
    return finish({**result, "steps": steps})