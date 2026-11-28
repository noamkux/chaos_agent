"""The entry point of the chart's Job: its inputs come from the environment and are checked first."""
from pathlib import Path

import pytest

import main

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def environment(monkeypatch):
    monkeypatch.setenv("ROE_FILE", str(FIXTURES / "roe.yaml"))
    monkeypatch.setenv("TARGET_FILE", str(FIXTURES / "target.yaml"))
    monkeypatch.setenv("CHAOS_MODEL", "claude-haiku-5-5")
    return monkeypatch


def test_the_inputs_come_from_the_environment(environment):
    environment.setenv("TARGET_NAMESPACE", "shop")
    roe, target, namespace, model = main.inputs()
    assert namespace == "shop" and model == "claude-haiku-5-5" and roe["max_model_rounds"] == 30


def test_a_namespace_outside_the_scope_is_not_started(environment):
    environment.setenv("TARGET_NAMESPACE", "kube-system")
    with pytest.raises(ValueError, match="not in the RoE's scope"):
        main.inputs()


def test_a_missing_input_is_not_started_and_nothing_is_recorded(environment, monkeypatch):
    monkeypatch.delenv("TARGET_NAMESPACE", raising=False)
    monkeypatch.setattr(main.db, "connect", lambda: pytest.fail("connected to Postgres"))
    assert main.main() == 2
