"""Which nodes a node failure takes down, the checks against the current placement, and the events
reported while it runs."""
import pytest

import node_failure


def node(name, zone, control_plane=False, schedulable=True):
    return {"name": name, "zone": zone, "control_plane": control_plane, "schedulable": schedulable,
            "ready": True, "taints": []}


def workload(name, *pods, kind="apps/Deployment", namespace="shop"):
    return {"namespace": namespace, "kind": kind, "name": name,
            "pods": [{"node": n, "zone": z, "phase": phase} for n, z, phase in pods]}


def placement(nodes, workloads):
    return {"nodes": {n["name"]: n for n in nodes}, "workloads": workloads, "nodes_unreadable": None}


CLUSTER = placement(
    [node("cp", None, control_plane=True), node("a1", "zone-a"), node("a2", "zone-a"), node("b1", "zone-b")],
    [workload("web", ("a1", "zone-a", "Running"), ("a2", "zone-a", "Running")),
     workload("db", ("b1", "zone-b", "Running"), kind="apps/StatefulSet")])


@pytest.mark.parametrize("action, message", [
    ({"zone": "zone-a"}, "needs mode"),
    ({"node": "a1", "zone": "zone-a", "mode": "drain"}, "either node or zone"),
    ({"mode": "drain"}, "either node or zone"),
])
def test_check(roe, action, message):
    assert message in node_failure.check(action, roe)


def test_check_follows_node_actions(roe):
    assert node_failure.check({"zone": "zone-a", "mode": "drain"}, roe) is None
    assert "whole_node" in node_failure.check({"zone": "zone-a", "mode": "lost"}, roe)
    assert node_failure.check({"zone": "zone-a", "mode": "lost"}, {**roe, "node_actions": "whole_node"}) is None


def test_a_zone_is_every_worker_in_it(roe):
    assert node_failure.targets({"zone": "zone-a"}, CLUSTER, roe) == (["a1", "a2"], None)


@pytest.mark.parametrize("action, message", [
    ({"node": "zz"}, "does not exist"),
    ({"node": "cp"}, "control-plane"),
    ({"zone": "zone-z"}, "no worker nodes"),
    # db, which the fixture RoE protects, runs in zone-b.
    ({"zone": "zone-b"}, "protected workloads"),
    ({"node": "b1"}, "protected workloads"),
])
def test_targets_refused(roe, action, message):
    nodes, error = node_failure.targets(action, CLUSTER, roe)
    assert nodes is None and message in error


def test_one_zone_is_not_enough(roe):
    one_zone = placement([node("a1", "zone-a"), node("a2", "zone-a")], [])
    assert "two zones" in node_failure.targets({"zone": "zone-a"}, one_zone, roe)[1]


def test_somewhere_must_stay_schedulable(roe):
    cordoned = placement([node("a1", "zone-a"), node("b1", "zone-b", schedulable=False)], [])
    assert "no schedulable worker" in node_failure.targets({"node": "a1"}, cordoned, roe)[1]


def test_unreadable_nodes_refuse_everything(roe):
    blind = {**CLUSTER, "nodes_unreadable": "403 Forbidden"}
    assert "cannot be read" in node_failure.targets({"zone": "zone-a"}, blind, roe)[1]


def test_merge_joins_namespaces():
    merged = node_failure.merge({
        "shop": {"nodes": [node("a1", "zone-a")], "workloads": [{"kind": "apps/Deployment", "name": "web", "pods": []}]},
        "pay": {"nodes": [node("a1", "zone-a")], "workloads": [{"kind": "apps/Deployment", "name": "api", "pods": []}]},
    })
    assert list(merged["nodes"]) == ["a1"]
    assert {(w["namespace"], w["name"]) for w in merged["workloads"]} == {("shop", "web"), ("pay", "api")}


def test_no_change_no_events():
    assert node_failure.changes(CLUSTER, CLUSTER, 10) == []


def test_changes_report_only_what_moved():
    after = placement(
        [node("cp", None, control_plane=True), node("a2", "zone-a"), node("b1", "zone-b"), node("c1", "zone-c")],
        [workload("web", (None, None, "Pending"), ("c1", "zone-c", "Running")),
         workload("db", ("b1", "zone-b", "Running"), kind="apps/StatefulSet")])
    events = node_failure.changes(CLUSTER, after, 20)
    assert {"after_action_s": 20, "node_added": "c1", "zone": "zone-c"} in events
    assert {"after_action_s": 20, "node_removed": "a1"} in events
    assert {"after_action_s": 20, "workload": "shop/apps/Deployment/web", "running": 1, "pending": 1,
            "nodes": ["c1"]} in events
    # db did not move, so it is not reported.
    assert not any(e.get("workload", "").endswith("/db") for e in events)
