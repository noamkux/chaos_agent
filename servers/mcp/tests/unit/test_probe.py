"""The probe server without k6 or a cluster: reading k6's output, p95, how many users run at once, and
every input it refuses before k6 starts."""
import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from mcp.server.mcpserver.exceptions import ToolError

import probe

OUT_JSON = Path(__file__).resolve().parent / "fixtures" / "out.json"


def test_summarize_reads_k6_output():
    summary = probe.summarize(OUT_JSON, ["home", "checkout"])
    by_second = {s["second"]: s["journeys"] for s in summary["seconds"]}
    assert by_second[0]["home"] == {"ok": 2, "failed": 0, "errors": {}, "p95_ms": 30}
    # Grouped by the second users arrived, not the second they finished (10:00:11 for the timeout).
    assert by_second[1]["checkout"] == {"ok": 0, "failed": 2, "errors": {"timeout": 1, "http 500": 1},
                                        "p95_ms": 10002}
    assert summary["not_sent"] == {"home": 0, "checkout": 2}


@pytest.mark.parametrize("values, expected", [([5], 5), ([1, 2, 3, 4], 4), (list(range(1, 101)), 95)])
def test_p95_nearest_rank(values, expected):
    assert probe.p95(values) == expected


def test_concurrent_users_per_journey(monkeypatch):
    journeys = {"home": [{}], "checkout": [{}, {}]}
    assert probe.concurrent_users(journeys, 2, 10) == {"home": 20, "checkout": 40}
    monkeypatch.setattr(probe, "MAX_CONCURRENT_USERS_PER_JOURNEY", 30)
    assert probe.concurrent_users(journeys, 2, 10) == {"home": 20, "checkout": 30}


@pytest.mark.parametrize("journeys, message", [
    ({}, "must not be empty"),
    ({"home": []}, "has no steps"),
    ({"home": [{"method": "GTE", "path": "/"}]}, "a method and a path"),
    # A path that does not start with / could send the request to another host.
    ({"home": [{"method": "GET", "path": "@evil.com/x"}]}, "a method and a path"),
])
def test_check_journeys(journeys, message):
    with pytest.raises(ToolError, match=message):
        probe.check_journeys(journeys)


@pytest.fixture
def service(monkeypatch):
    """A Service web:8080 in shop, instead of the API."""
    svc = SimpleNamespace(spec=SimpleNamespace(ports=[SimpleNamespace(port=8080)]))
    monkeypatch.setattr(probe.core, "read_namespaced_service", lambda name, namespace: svc)


def test_service_url(service):
    assert probe.service_url("shop", "web", 8080) == "http://web.shop.svc:8080"
    with pytest.raises(ToolError, match="not declared"):
        probe.service_url("shop", "web", 9090)
    with pytest.raises(ToolError, match="out of scope"):
        probe.service_url("kube-system", "web", 8080)


@pytest.mark.parametrize("change, message", [
    ({"measure_for_s": 0}, "measure_for_s"),
    ({"measure_for_s": probe.LONGEST_K6_RUN_S + 1}, "measure_for_s"),
    ({"new_users_per_second": probe.MAX_NEW_USERS_PER_SECOND + 1}, "new_users_per_second"),
    ({"fail_request_after_s": probe.LONGEST_REQUEST_WAIT_S + 1}, "fail_request_after_s"),
])
def test_caps_refuse_before_k6_starts(service, monkeypatch, change, message):
    monkeypatch.setattr(probe, "run_k6", lambda config: pytest.fail("k6 must not start"))
    args = {"namespace": "shop", "service": "web", "port": 8080, "journeys": {"home": [{"method": "GET", "path": "/"}]},
            "measure_for_s": 15, "new_users_per_second": 2, "fail_request_after_s": 10, **change}
    with pytest.raises(ToolError, match=message):
        asyncio.run(probe.measure_journeys(**args))
