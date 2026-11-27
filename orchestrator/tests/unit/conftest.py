"""Shared fixtures: the tests' own RoE and target.yaml, loaded the way a run loads them."""
from pathlib import Path

import pytest

import run_config

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def roe():
    return run_config.load_roe(FIXTURES / "roe.yaml")


@pytest.fixture
def target():
    return run_config.load_target(FIXTURES / "target.yaml")
