"""Running one experiment: check it against the RoE, measure a baseline, make the change with a snapshot
written first, measure through it, restore, and judge. The model plans; this code executes."""
import asyncio
import json
import time

from storage import db
from experiments import judge
from experiments import node_failure
import config
import mcp_client

RUN_EXPERIMENT_NAME = "run_experiment"
ACTIONS = ["patch", "delete_pod", "node_failure"]

MEASURE = "probe__measure_journeys"
SNAPSHOT = "disrupt__snapshot_resource"
PATCH = "disrupt__patch_resource"
RESTORE = "disrupt__restore_snapshot"
DELETE_POD = "disrupt__delete_pod"

# Every server tool an experiment needs; run_experiment is offered only when all of them are loaded.
EXPERIMENT_TOOLS = {MEASURE, SNAPSHOT, PATCH, RESTORE, DELETE_POD}

# The timings and the rate of every measurement come from target.yaml (measurement), loaded by run_config.


NODE_FAILURE_TEXT = (
    " node_failure (a node, or every node of a zone, taken down: mode drain cordons it and evicts its "
    "pods as an upgrade or a scale-down would, respecting PodDisruptionBudgets; mode lost cordons it and "
    "removes every pod at once, as when a node dies; it is restored after restore_after_s, and recovery "
    "is counted from the action, since the pods must be rescheduled elsewhere while the node is down; "
    "the result lists the evictions and placement_events: nodes that joined or left, for example from "
    "an autoscaler, and workloads whose running or pending pods or nodes changed). In a cluster with an "
    "autoscaler, restore_after_s must leave time for a new node to join.")


def run_experiment_tool(namespaces, journey_names, node_actions="none"):
    """The run_experiment tool for one run, with the run's namespaces and the profile's journeys as enums.
    node_failure is offered only when the RoE allows node actions and the node tools are loaded."""
    actions = ACTIONS if node_actions != "none" else [a for a in ACTIONS if a != "node_failure"]
    modes = node_failure.MODES if node_actions == "whole_node" else ["drain"]
    return {
        "name": RUN_EXPERIMENT_NAME,
        "description": (
            "Run one chaos experiment and get its measured result. The orchestrator checks that the system "
            "is steady, makes the change, keeps measuring the journeys you chose, restores the change after "
            "restore_after_s seconds, and judges the result against the steady state: broke, withstood or "
            "inconclusive. If the system does not get steady before the change, nothing is changed and the "
            "experiment is not counted: not_run. inconclusive means the change was made and "
            "counted, but a journey was not steady in the seconds just before it, so the result cannot be "
            "judged; its before_action timeline shows those seconds. "
            "Actions: patch (a strategic merge patch on any object in scope; it is snapshotted first and "
            "restored after restore_after_s), delete_pod (one running pod of a workload; its controller replaces "
            "it, nothing is restored)" + (NODE_FAILURE_TEXT if node_actions != "none" else ".") +
            " The timeline has one character per second: . ok, s slow, x failed, "
            "_ no answer, | the action and the restore."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "hypothesis": {"type": "string", "description": "What you expect to happen, and why."},
                "action": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": actions},
                        "namespace": {"type": "string", "enum": namespaces,
                                      "description": "For patch and delete_pod."},
                        "kind": {"type": "string",
                                 "description": "For patch and delete_pod: group/Kind, for example apps/Deployment."},
                        "name": {"type": "string", "description": "For patch and delete_pod."},
                        "patch": {"type": "object", "description": "For type patch: the strategic merge patch."},
                        **({"node": {"type": "string", "description": "For node_failure: one node, from Placement."},
                            "zone": {"type": "string", "description": "For node_failure: every worker node of a zone."},
                            "mode": {"type": "string", "enum": modes, "description": "For node_failure."}}
                           if node_actions != "none" else {}),
                    },
                    "required": ["type"],
                },
                "journeys": {"type": "array", "items": {"type": "string", "enum": journey_names},
                             "description": "The journeys to measure, from the profile."},
                "restore_after_s": {"type": "integer",
                                    "description": "For patch and node_failure: seconds the change stays in place before it is restored."},
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
    if action["type"] == "node_failure":
        # Which nodes, and whether protected workloads run on them, is checked against the placement
        # in run_experiment, just before anything is touched.
        error = node_failure.check(action, roe)
        if error:
            return error
    else:
        if action.get("namespace") not in roe["scope"]["namespaces"]:
            return f"namespace '{action.get('namespace')}' is out of scope"
        kind = str(action.get("kind", ""))
        if "/" not in kind or not action.get("name"):
            return "action needs kind as group/Kind and a name"
        if config.denied(kind, roe["deny"]):
            return f"kind '{kind}' is denied by the Rules of Engagement"
        if action["name"] in roe["protected_workloads"]:
            return f"'{action['name']}' is protected by the Rules of Engagement: measure it, never change it"
    if not names or any(name not in profile for name in names):
        return f"journeys must be names from the profile: {sorted(profile)}"
    if not roe["allow_write_journeys"] and any(profile[name].get("writes") for name in names):
        return "journeys that write data are not allowed by the Rules of Engagement"
    if action["type"] == "patch" and (not isinstance(action.get("patch"), dict) or not action["patch"]):
        return "a patch action needs a non-empty patch"
    if action["type"] in ("patch", "node_failure"):
        restore_after = args.get("restore_after_s")
        if not config.positive_int(restore_after) or restore_after > roe["max_restore_after_s"]:
            return f"restore_after_s must be 1 to {roe['max_restore_after_s']}"
    return None


def without_warmup(measurement, warmup):
    """A measurement without its warm-up seconds, renumbered from 0, with started_at moved to match."""
    return {"started_at": measurement["started_at"] + warmup,
            "measure_for_s": measurement["measure_for_s"] - warmup,
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
        statuses = {j: judge.statuses_of(check, j, steady) for j in journeys}
        if all(status == "ok" for per_journey in statuses.values() for status in per_journey):
            return check, steps, {}
        problem = {"reason": f"not steady after {attempt + 1} steady checks",
                   "last_check": {j: judge.timeline(per_journey, set()) for j, per_journey in statuses.items()}}
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
    step_id, step = db.start_step(conn, run_id, RUN_EXPERIMENT_NAME, args, allowed=error is None)
    if error:
        db.finish_step(conn, step_id, {"error": error})
        return json.dumps({"step": step, "error": error})

    scope = roe["scope"]["namespaces"]
    action = args["action"]
    journeys = {j["name"]: j["steps"] for j in target["journeys"] if j["name"] in args["journeys"]}
    steady = target["steady_state"]
    entry = target["entrypoint"]
    settings = target["measurement"]
    restore_after = args.get("restore_after_s", 0) if action["type"] in ("patch", "node_failure") else 0
    target_args = {"namespace": action.get("namespace"), "kind": action.get("kind"), "name": action.get("name")}

    async def call(name, call_args):
        return json.loads(await mcp_client.call_tool(conn, run_id, server_tools, scope, name, call_args))

    def measure(seconds):
        return call(MEASURE, {"namespace": namespace, "service": entry["service"], "port": entry["port"],
                              "journeys": journeys, "measure_for_s": seconds,
                              "new_users_per_second": settings["new_users_per_second"],
                              "fail_request_after_s": settings["fail_request_after_s"]})

    def finish(result):
        """Record the result, and return it to the model with the experiment's own step to cite."""
        db.finish_step(conn, step_id, result)
        return json.dumps({"step": step, **result})

    async def placement_now():
        """The current placement of the whole scope, or (None, error)."""
        contents, placement_steps = {}, []
        for ns in scope:
            read = await call(node_failure.PLACEMENT, {"namespace": ns})
            if read["is_error"]:
                return None, f"placement failed: {read['content']}"
            contents[ns] = read["content"]
            placement_steps.append(read["step"])
        return node_failure.merge(contents), placement_steps

    # 0. For a node failure: which nodes, checked against where pods run right now. Nothing is counted yet.
    if action["type"] == "node_failure":
        missing = node_failure.NODE_TOOLS - server_tools
        if missing:
            return finish({"error": f"node tools not loaded in this run: {sorted(missing)}"})
        before, placement_steps = await placement_now()
        if before is None:
            return finish({"error": placement_steps})
        nodes, error = node_failure.targets(action, before, roe)
        if error:
            return finish({"error": error, "steps": {"placement": placement_steps}})

    # 1. Steady check: nothing is touched, and the experiment is not counted, until the system is steady.
    baseline, check_steps, problem = await wait_for_steady(measure, list(journeys), steady, settings)
    steps = {"steady_checks": check_steps}
    if baseline is None:
        return finish({"verdict": "not_run", "counted": False, **problem, "steps": steps})
    state["experiments"] += 1

    # 2. Measure in the background, through the action, the time it stays and the recovery.
    # Its warm-up is thrown away before judging, as in the steady check: every run of k6 starts cold.
    warmup = settings["warmup_ignored_s"]
    before_action = settings["measure_before_action_s"]
    measuring = asyncio.create_task(
        measure(warmup + before_action + restore_after + settings["measure_after_restore_s"]))
    await asyncio.sleep(warmup + before_action)
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
    elif action["type"] == "node_failure":
        undos = {}

        async def roll_back(reason, failed_step):
            """Undo every node already touched, after a node action failed half way."""
            for node, undo_id in undos.items():
                restored = await call(node_failure.RESTORE_NODE, undo_args[node])
                db.finish_undo(conn, undo_id, "failed" if restored["is_error"] else "done")
            measuring.cancel()
            return finish({"error": reason, "steps": {**steps, "failed": failed_step}})

        # Every undo is written before its node is touched, so a crash leaves a record of it.
        undo_args = {node: {"node": node, "was_unschedulable": not before["nodes"][node]["schedulable"]}
                     for node in nodes}
        steps["action"] = []
        for node in nodes:
            undos[node] = db.add_undo(conn, run_id, step_id, {"tool": node_failure.RESTORE_NODE,
                                                             "args": undo_args[node]})
            cordoned = await call(node_failure.CORDON, {"node": node})
            steps["action"].append(cordoned["step"])
            if cordoned["is_error"]:
                return await roll_back(f"cordon {node} failed: {cordoned['content']}", cordoned["step"])
        evictions = {}
        for node in nodes:
            if action["mode"] == "lost":
                acted = await call(node_failure.TAINT_LOST, {"node": node})
            else:
                drain_args = {"node": node}
                if roe["node_actions"] == "scope_only":
                    drain_args["namespaces"] = scope
                acted = await call(node_failure.EVICT, drain_args)
                if not acted["is_error"]:
                    evictions[node] = {key: acted["content"][key] for key in ("evicted", "blocked_by_pdb", "failed")}
            steps["action"].append(acted["step"])
            if acted["is_error"]:
                return await roll_back(f"{action['mode']} {node} failed: {acted['content']}", acted["step"])
        action_time = time.time()

        # Watch where pods go while the nodes are down, and keep only what changed.
        placement_events = []
        steps["placement"] = []

        async def watch_placement():
            last = before
            while not measuring.done():
                await asyncio.sleep(node_failure.POLL_S)
                now, read_steps = await placement_now()
                if now is None:
                    continue
                steps["placement"] += read_steps
                placement_events.extend(node_failure.changes(last, now, round(time.time() - action_time)))
                last = now

        watching = asyncio.create_task(watch_placement())
        await asyncio.sleep(restore_after)
        steps["restore"] = []
        for node in nodes:
            restored = await call(node_failure.RESTORE_NODE, undo_args[node])
            steps["restore"].append(restored["step"])
            if restored["is_error"]:
                db.finish_undo(conn, undos[node], "failed")
                watching.cancel()
                measuring.cancel()
                finish({"error": f"restore of {node} failed: {restored['content']}", "steps": steps})
                raise RuntimeError(f"restore failed for node {node}; undo {undos[node]} is still pending")
            db.finish_undo(conn, undos[node], "done")
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
    if action["type"] == "node_failure":
        watching.cancel()
    steps["measurement"] = measured["step"]
    if measured["is_error"]:
        return finish({"verdict": "inconclusive", "reason": f"measurement failed: {measured['content']}",
                       "steps": steps})
    measurement = without_warmup(measured["content"], warmup)
    action_second = second_of(action_time, measurement)
    # The judge compares with the application's own noise, learned from the seconds before the action
    # of the run's experiments; an inconclusive one is left out, since its seconds were not normal.
    result = judge.judge(baseline, measurement, list(journeys), steady, action_second,
                              second_of(restore_time, measurement) if restore_time else None,
                              recover_from_restore=action["type"] != "node_failure",
                              noise=state.get("noise"))
    if result["verdict"] != "inconclusive":
        state["noise"] = judge.add_noise(state.get("noise", {}),
                                         judge.noise_seconds(measurement, list(journeys), steady, action_second))
    if action["type"] == "node_failure":
        result |= {"nodes": nodes, "mode": action["mode"], "placement_events": placement_events}
        if evictions:
            result["evictions"] = evictions
    return finish({**result, "steps": steps})