"""Loading and checking the RoE and target.yaml: the safe defaults, and every malformed value a run must
refuse before it starts. The files are the tests' own fixtures, never the lab's."""
from pathlib import Path

import pytest
import yaml

import config

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def write(tmp_path, name, data):
    """A YAML file with this data, for the loaders."""
    path = tmp_path / name
    path.write_text(yaml.safe_dump(data))
    return path


def fixture_roe():
    return yaml.safe_load((FIXTURES / "roe.yaml").read_text())


def fixture_target():
    return yaml.safe_load((FIXTURES / "target.yaml").read_text())


# ---------- the RoE

def test_roe_loads_as_written():
    roe = config.load_roe(FIXTURES / "roe.yaml")
    assert roe["scope"]["namespaces"] == ["shop"]
    assert roe["node_actions"] == "scope_only"
    assert roe["protected_workloads"] == ["db"]
    assert roe["max_restore_after_s"] == 90
    assert roe["deny"] == ["argoproj.io/Application", "fluxcd.io"]


def test_roe_defaults_allow_nothing_extra(tmp_path):
    roe = config.load_roe(write(tmp_path, "roe.yaml",
                                    {"scope": {"namespaces": ["app"]}, "max_level": "probe", "deny": []}))
    assert roe["allow_write_journeys"] is False
    assert roe["node_actions"] == "none"
    assert roe["protected_workloads"] == []
    assert roe["max_experiments"] == 10
    assert roe["max_model_rounds"] == 30


def test_roe_without_deny_is_refused(tmp_path):
    data = fixture_roe()
    del data["deny"]
    with pytest.raises(ValueError, match="deny is required"):
        config.load_roe(write(tmp_path, "roe.yaml", data))


@pytest.mark.parametrize("change, message", [
    ({"scope": {"namespaces": []}}, "scope.namespaces"),
    ({"max_level": "destroy"}, "max_level"),
    ({"allow_write_journeys": "false"}, "allow_write_journeys"),
    # YAML 1.1 reads an unquoted off as the boolean false: it must not pass for "none".
    ({"node_actions": False}, "node_actions"),
    ({"node_actions": "off"}, "node_actions"),
    ({"max_experiments": 0}, "max_experiments"),
    ({"max_model_rounds": 0}, "max_model_rounds"),
    ({"max_model_rounds": 101}, "max_model_rounds must be at most 100"),
    ({"max_restore_after_s": True}, "max_restore_after_s"),
    ({"deny": "argoproj.io"}, "deny must be a list"),
    ({"protected_workloads": [""]}, "protected_workloads"),
])
def test_malformed_roe_is_refused(tmp_path, change, message):
    with pytest.raises(ValueError, match=message):
        config.load_roe(write(tmp_path, "roe.yaml", {**fixture_roe(), **change}))


@pytest.mark.parametrize("kind, deny, expected", [
    ("argoproj.io/Application", ["argoproj.io/Application"], True),
    ("argoproj.io/Rollout", ["argoproj.io/Application"], False),
    ("kustomize.toolkit.fluxcd.io/Kustomization", ["fluxcd.io"], True),
    ("notfluxcd.io/Thing", ["fluxcd.io"], False),
    ("apps/Deployment", [], False),
])
def test_denied(kind, deny, expected):
    assert config.denied(kind, deny) is expected


# ---------- target.yaml

def test_target_without_measurement_gets_every_default():
    target = config.load_target(FIXTURES / "target.yaml")
    assert target["measurement"] == config.MEASUREMENT_DEFAULTS
    assert target["entrypoint"] == {"service": "web", "port": 8080}


def test_measurement_defaults_fill_what_is_left_out(tmp_path):
    data = fixture_target()
    data["measurement"] = {"measure_after_restore_s": 60}
    target = config.load_target(write(tmp_path, "target.yaml", data))
    assert target["measurement"]["measure_after_restore_s"] == 60
    assert target["measurement"]["warmup_ignored_s"] == config.MEASUREMENT_DEFAULTS["warmup_ignored_s"]


@pytest.mark.parametrize("measurement, message", [
    # A typo would otherwise be ignored, and the default used without anyone knowing.
    ({"measure_after_restor_s": 60}, "not a known setting"),
    ({"measure_before_action_s": 1}, "at least 3"),
    ({"steady_check_s": 4}, "at least 5"),
    ({"new_users_per_second": True}, "whole number"),
    ({"fail_request_after_s": "10"}, "whole number"),
])
def test_malformed_measurement_is_refused(tmp_path, measurement, message):
    data = {**fixture_target(), "measurement": measurement}
    with pytest.raises(ValueError, match=message):
        config.load_target(write(tmp_path, "target.yaml", data))


@pytest.mark.parametrize("change, message", [
    ({"entrypoint": {"service": "frontend", "port": "80"}}, "entrypoint"),
    ({"journeys": []}, "at least one journey"),
    ({"journeys": [{"name": "a", "steps": [{"method": "GET", "path": "/"}]}] * 2}, "unique name"),
    ({"journeys": [{"name": "a", "steps": [{"method": "GET", "path": "@evil.com/"}]}]}, "starting with /"),
    ({"steady_state": {"success_rate": 1.5, "p95_ms": 500}}, "success_rate"),
])
def test_malformed_target_is_refused(tmp_path, change, message):
    with pytest.raises(ValueError, match=message):
        config.load_target(write(tmp_path, "target.yaml", {**fixture_target(), **change}))


@pytest.mark.parametrize("value, expected", [(1, True), (0, False), (-3, False), (True, False), ("5", False), (2.0, False)])
def test_positive_int(value, expected):
    assert config.positive_int(value) is expected
