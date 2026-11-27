"""Node and zone failures: which nodes an experiment takes down, the checks it must pass first, and what
moved in the cluster while it ran. The runner executes them; this module decides and describes."""

PLACEMENT = "observe__get_placement"
CORDON = "disrupt__cordon_node"
TAINT_LOST = "disrupt__taint_node_lost"
EVICT = "disrupt__evict_pods"
RESTORE_NODE = "disrupt__restore_node"
# Every server tool a node failure needs; the action is offered only when all of them are loaded.
NODE_TOOLS = {PLACEMENT, CORDON, TAINT_LOST, EVICT, RESTORE_NODE}

# drain: planned (an upgrade, a scale-down): cordon, then evict through the Eviction API, PDBs respected.
# lost: sudden (the node dies): cordon, then a NoExecute taint that removes every pod at once.
MODES = ["drain", "lost"]

# Seconds between two reads of the placement while an experiment runs: often enough to see pods go
# Pending and a new node join, rare enough to keep the audit small.
POLL_S = 10


def check(action, roe):
    """The rules a node failure must pass before anything is read or touched. Returns an error, or None."""
    if roe["node_actions"] == "none":
        return "node failures are not allowed by the Rules of Engagement (node_actions: none)"
    if action.get("mode") not in MODES:
        return f"a node_failure needs mode, one of {MODES}"
    if action["mode"] == "lost" and roe["node_actions"] != "whole_node":
        return "mode lost reaches every pod on the node, which needs node_actions: whole_node"
    if bool(action.get("node")) == bool(action.get("zone")):
        return "a node_failure needs either node or zone, not both"
    return None


def merge(contents):
    """One placement for the whole scope, from get_placement's answer for each namespace."""
    nodes, workloads, unreadable = {}, [], None
    for namespace, content in contents.items():
        nodes |= {n["name"]: n for n in content["nodes"]}
        workloads += [{"namespace": namespace, **w} for w in content["workloads"]]
        unreadable = unreadable or content.get("nodes_unreadable")
    return {"nodes": nodes, "workloads": workloads, "nodes_unreadable": unreadable}


def targets(action, placement, roe):
    """The nodes an experiment takes down, after every check that needs the current placement.
    Returns (nodes, None) or (None, error)."""
    if placement["nodes_unreadable"]:
        return None, f"nodes cannot be read ({placement['nodes_unreadable']}): no node failure without them"
    workers = {name: n for name, n in placement["nodes"].items() if not n["control_plane"]}
    if action.get("node"):
        if action["node"] not in placement["nodes"]:
            return None, f"node '{action['node']}' does not exist"
        if action["node"] not in workers:
            return None, f"node '{action['node']}' is a control-plane node"
        chosen = [action["node"]]
    else:
        zones = {n["zone"] for n in workers.values() if n["zone"]}
        if action["zone"] not in zones:
            return None, f"zone '{action['zone']}' has no worker nodes; zones: {sorted(zones)}"
        if len(zones) < 2:
            return None, "a zone failure needs at least two zones, so the pods have somewhere to go"
        chosen = sorted(name for name, n in workers.items() if n["zone"] == action["zone"])
    # Somewhere must stay open, or a failure only measures that nothing can run.
    if not any(n["schedulable"] for name, n in workers.items() if name not in chosen):
        return None, "this would leave no schedulable worker node"
    # A protected workload's pods would be evicted with everything else on the node.
    hit = sorted({w["name"] for w in placement["workloads"] if w["name"] in roe["protected_workloads"]
                  and any(p["node"] in chosen for p in w["pods"])})
    if hit:
        return None, f"protected workloads run on {chosen}: {hit}; choose a node or zone without them"
    return chosen, None


def summary(placement):
    """What a placement says, in the terms changes are reported in."""
    return {
        "nodes": {name: n["zone"] for name, n in placement["nodes"].items()},
        "workloads": {f"{w['namespace']}/{w['kind']}/{w['name']}": {
            "running": sum(p["phase"] == "Running" for p in w["pods"]),
            "pending": sum(p["phase"] == "Pending" for p in w["pods"]),
            "nodes": sorted({p["node"] for p in w["pods"] if p["node"]}),
        } for w in placement["workloads"]},
    }


def changes(before, after, after_action_s):
    """What changed between two placements, as events for the model: only differences, never the whole
    placement. A node that joined or left the cluster (an autoscaler adding one, or removing the one we
    drained), and every workload whose running or pending pods, or nodes, changed."""
    events = []
    old, new = summary(before), summary(after)
    for name in sorted(new["nodes"].keys() - old["nodes"].keys()):
        events.append({"after_action_s": after_action_s, "node_added": name, "zone": new["nodes"][name]})
    for name in sorted(old["nodes"].keys() - new["nodes"].keys()):
        events.append({"after_action_s": after_action_s, "node_removed": name})
    for workload in sorted(old["workloads"].keys() | new["workloads"].keys()):
        now = new["workloads"].get(workload, {"running": 0, "pending": 0, "nodes": []})
        if now != old["workloads"].get(workload):
            events.append({"after_action_s": after_action_s, "workload": workload, **now})
    return events
