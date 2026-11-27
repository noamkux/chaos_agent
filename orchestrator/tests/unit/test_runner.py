"""The rules every experiment must pass before anything is touched, and the warm-up cut."""
import pytest

import runner


def experiment(**action):
    """A valid patch experiment, with action fields overridden."""
    return {"hypothesis": "web holds with one replica fewer",
            "action": {"type": "patch", "namespace": "shop", "kind": "apps/Deployment", "name": "web",
                       "patch": {"spec": {"replicas": 1}}, **action},
            "journeys": ["home"], "restore_after_s": 30}


def test_a_valid_patch_passes(roe, target):
    assert runner.check(experiment(), roe, target, done=0) is None


@pytest.mark.parametrize("change, message", [
    ({"hypothesis": " "}, "hypothesis"),
    ({"journeys": []}, "journeys must be names"),
    ({"journeys": ["nope"]}, "journeys must be names"),
    ({"restore_after_s": 0}, "restore_after_s must be 1 to 90"),
    ({"restore_after_s": 91}, "restore_after_s must be 1 to 90"),
    ({"restore_after_s": "30"}, "restore_after_s must be 1 to 90"),
])
def test_experiment_rules(roe, target, change, message):
    assert message in runner.check({**experiment(), **change}, roe, target, done=0)


@pytest.mark.parametrize("action, message", [
    ({"type": "rm -rf"}, "action.type"),
    ({"namespace": "kube-system"}, "out of scope"),
    ({"kind": "Deployment"}, "group/Kind"),
    ({"kind": "argoproj.io/Application"}, "denied"),
    ({"kind": "kustomize.toolkit.fluxcd.io/Kustomization"}, "denied"),
    ({"name": "db"}, "protected"),
    ({"patch": {}}, "non-empty patch"),
])
def test_action_rules(roe, target, action, message):
    assert message in runner.check(experiment(**action), roe, target, done=0)


def test_the_budget_is_enforced(roe, target):
    assert "already ran its 5" in runner.check(experiment(), roe, target, done=5)


def test_write_journeys_need_the_roe(roe, target):
    assert runner.check({**experiment(), "journeys": ["checkout"]}, roe, target, 0) is None
    no_writes = {**roe, "allow_write_journeys": False}
    assert "write data" in runner.check({**experiment(), "journeys": ["checkout"]}, no_writes, target, 0)


def test_a_deleted_pod_needs_no_restore_time(roe, target):
    args = {**experiment(type="delete_pod"), "restore_after_s": None}
    assert runner.check(args, roe, target, 0) is None


def test_node_failure_rules(roe, target):
    zone = {"hypothesis": "losing zone-a", "action": {"type": "node_failure", "zone": "zone-a", "mode": "drain"},
            "journeys": ["home"], "restore_after_s": 60}
    assert runner.check(zone, roe, target, 0) is None
    lost = {**zone, "action": {**zone["action"], "mode": "lost"}}
    assert "whole_node" in runner.check(lost, roe, target, 0)
    assert "not allowed" in runner.check(zone, {**roe, "node_actions": "none"}, target, 0)


def test_without_warmup():
    measurement = {"started_at": 100.0, "measure_for_s": 5, "not_sent": {"home": 0},
                   "seconds": [{"second": s, "journeys": {}} for s in range(5)]}
    cut = runner.without_warmup(measurement, 2)
    assert cut["measure_for_s"] == 3
    assert cut["started_at"] == 102.0
    assert [s["second"] for s in cut["seconds"]] == [0, 1, 2]


def test_the_schema_offers_node_failure_only_when_allowed():
    def offered(node_actions):
        action = runner.run_experiment_tool(["shop"], ["home"], node_actions)["input_schema"]["properties"]["action"]
        return action["properties"]["type"]["enum"], action["properties"].get("mode", {}).get("enum")
    assert offered("none") == (["patch", "delete_pod"], None)
    assert offered("scope_only") == (["patch", "delete_pod", "node_failure"], ["drain"])
    assert offered("whole_node")[1] == ["drain", "lost"]
