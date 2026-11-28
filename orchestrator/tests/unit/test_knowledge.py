"""The chunks the agent remembers: one per judged experiment, one per section of a summary, and the
search_knowledge tool the model reads them with."""
import asyncio
import json
from datetime import datetime, timezone

import pytest

import knowledge

WHEN = datetime(2026, 11, 27, 17, 48, tzinfo=timezone.utc)
JOURNEY = {"timeline": "..|xx|..", "after_action": {"success": 0.29, "worst_p95_ms": 10002,
                                                     "errors": {"timeout": 103, "network error 1212": 24}},
           "broken_s": 72, "not_sent": 0, "recovered_after_s": 73}


def step(number, action, output, hypothesis="it breaks"):
    return {"step": number, "started_at": WHEN, "input": {"action": action, "hypothesis": hypothesis},
            "output": output}


PATCH = {"type": "patch", "namespace": "boutique", "kind": "apps/Deployment", "name": "emailservice",
         "patch": {"spec": {"replicas": 0}}}
DRAIN = {"type": "node_failure", "mode": "drain", "zone": "zone-a"}


def test_a_judged_experiment_is_one_chunk_with_its_facts():
    [chunk] = knowledge.experiment_chunks(31, "boutique", [step(97, PATCH, {"verdict": "broke", "journeys": {"home": JOURNEY}})])
    assert chunk["kind"] == "experiment" and chunk["run_id"] == 31 and chunk["step"] == 97
    assert chunk["workloads"] == ["apps/Deployment/emailservice"]
    assert chunk["action_type"] == "patch" and chunk["verdict"] == "broke"
    assert chunk["content"].startswith("run 31 step 97 (2026-11-27): patch of apps/Deployment emailservice")
    assert "home: success 0.29, broken 72s, recovered after 73s, worst p95 10002 ms, " \
           "errors network error 1212 24, timeout 103" in chunk["content"]


def test_experiments_that_changed_nothing_are_not_remembered():
    steps = [step(1, PATCH, {"verdict": "not_run", "reason": "never steady"}),
             step(2, PATCH, {"error": "denied"}),
             step(3, PATCH, None)]
    assert knowledge.experiment_chunks(31, "boutique", steps) == []


def test_an_inconclusive_experiment_keeps_its_reason():
    [chunk] = knowledge.experiment_chunks(30, "boutique", [step(44, PATCH, {"verdict": "inconclusive",
                                                                            "reason": "journey 'cart' was not steady"})])
    assert "Reason: journey 'cart' was not steady." in chunk["content"]


def test_a_node_failure_remembers_every_workload_whose_pods_moved():
    events = [{"workload": "boutique/apps/Deployment/frontend", "running": 0, "pending": 2},
              {"workload": "boutique/apps/Deployment/frontend", "running": 2, "pending": 0},
              {"workload": "boutique/apps/Deployment/cartservice", "running": 1, "pending": 0}]
    [chunk] = knowledge.experiment_chunks(31, "boutique", [step(5, DRAIN, {"verdict": "broke", "placement_events": events})])
    assert chunk["workloads"] == ["apps/Deployment/cartservice", "apps/Deployment/frontend"]
    assert "node_failure (drain) of zone zone-a" in chunk["content"]


def test_a_summary_is_one_chunk_per_section():
    summary = "I ran 13 experiments.\n\n## Confirmed\n- frontend is pinned\n\n### Unconfirmed\n- cart\n\n## Next\n- payment"
    chunks = knowledge.summary_chunks(31, "boutique", summary)
    assert [c["content"].split("\n", 1)[0] for c in chunks] == [
        'run 31 summary, section "Summary" (the agent\'s interpretation):',
        'run 31 summary, section "Confirmed" (the agent\'s interpretation):',
        'run 31 summary, section "Unconfirmed" (the agent\'s interpretation):',
        'run 31 summary, section "Next" (the agent\'s interpretation):']
    assert all(c["kind"] == "summary" and c["workloads"] == [] for c in chunks)


def test_an_empty_summary_has_no_chunks():
    assert knowledge.summary_chunks(31, "boutique", "") == []


def test_the_same_run_gives_the_same_hashes():
    steps = [step(97, PATCH, {"verdict": "withstood", "journeys": {"home": JOURNEY}})]
    first = knowledge.experiment_chunks(31, "boutique", steps)
    again = knowledge.experiment_chunks(31, "boutique", steps)
    assert [c["content_hash"] for c in first] == [c["content_hash"] for c in again]


class Recorder:
    """db.start_step and db.finish_step without Postgres: keeps what was recorded."""

    def __init__(self):
        self.started, self.finished = [], []

    def start_step(self, conn, run_id, name, args, allowed):
        self.started.append((name, args, allowed))
        return 1, 7

    def finish_step(self, conn, step_id, output):
        self.finished.append(output)


@pytest.fixture
def recorder(monkeypatch):
    recorder = Recorder()
    monkeypatch.setattr(knowledge.db, "start_step", recorder.start_step)
    monkeypatch.setattr(knowledge.db, "finish_step", recorder.finish_step)
    return recorder


WORKLOADS = ["apps/Deployment/frontend"]


@pytest.mark.parametrize("args, error", [
    ({"query": "  "}, "query must be a sentence"),
    ({"query": "zone loss", "workload": "frontend"}, "unknown workload"),
])
def test_a_bad_search_is_refused_and_recorded(recorder, args, error):
    output = json.loads(asyncio.run(knowledge.search_knowledge(None, 1, "boutique", WORKLOADS, args)))
    assert error in output["error"] and output["step"] == 7
    assert recorder.started[0][2] is False


def test_a_search_uses_the_runs_namespace_and_is_recorded(recorder, monkeypatch):
    calls = []
    monkeypatch.setattr(knowledge, "search", lambda conn, namespace, query, workload: calls.append(
        (namespace, query, workload)) or [{"run_id": 31, "step": 97, "kind": "experiment", "content": "x", "distance": 0.27}])
    args = {"query": "zone loss", "workload": "apps/Deployment/frontend", "namespace": "kube-system"}
    output = json.loads(asyncio.run(knowledge.search_knowledge(None, 1, "boutique", WORKLOADS, args)))
    assert calls == [("boutique", "zone loss", "apps/Deployment/frontend")]
    assert output["results"][0]["step"] == 97 and recorder.finished[0]["results"] == output["results"]
