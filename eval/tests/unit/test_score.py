"""Unit tests for eval/score.py, on the tests' own ground truth and steps built here."""
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import score

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def truth():
    return score.load_ground_truth(FIXTURES / "ground_truth.yaml")


def journeys(**broken):
    """Per-journey results: a journey given True broke (5 bad seconds), False held."""
    return {name: {"broken_s": 5 if bad else 0, "not_sent": 0, "recovered_after_s": 3}
            for name, bad in broken.items()}


def experiment(step, action, verdict, **broken):
    return {"step": step, "kind": "tool", "name": "run_experiment", "allowed": True,
            "input": {"hypothesis": "h", "action": action, "journeys": list(broken)},
            "output": {"verdict": verdict, "journeys": journeys(**broken)}}


def llm(step, text="", tokens_in=1000, tokens_out=100):
    return {"step": step, "kind": "llm", "name": "claude-haiku-5-5", "allowed": True, "input": None,
            "output": [{"type": "text", "text": text}], "tokens_in": tokens_in, "tokens_out": tokens_out,
            "cache_read_tokens": 0, "cache_write_tokens": 0}


def run(run_id=7, model="claude-haiku-5-5"):
    start = datetime(2026, 11, 28, 12, 0)
    return {"id": run_id, "model": model, "status": "completed", "started_at": start,
            "finished_at": start + timedelta(minutes=20)}


SCALE_DB_PROXY = {"type": "patch", "kind": "apps/Deployment", "name": "db-proxy", "patch": {"spec": {"replicas": 0}}}


def test_flatten_drops_list_indices():
    patch = {"spec": {"template": {"spec": {"containers": [{"name": "s", "resources": {"limits": {"cpu": "50m"}}}]}}}}
    assert ("spec.template.spec.containers.resources.limits.cpu", "50m") in score.flatten(patch)


def test_sets_must_match_the_value_unless_any(truth):
    n6 = truth["weaknesses"][2]["action"]
    assert score.action_matches(n6, SCALE_DB_PROXY, {})
    assert not score.action_matches(n6, {**SCALE_DB_PROXY, "patch": {"spec": {"replicas": 1}}}, {})
    cpu = {"type": "patch", "kind": "apps/Deployment", "name": "web",
           "patch": {"spec": {"template": {"spec": {"containers": [{"resources": {"limits": {"cpu": "10m"}}}]}}}}}
    assert score.action_matches(truth["weaknesses"][3]["action"], cpu, {})


def test_a_field_left_out_matches_any_value_and_a_node_matches_its_zone(truth):
    w1 = truth["weaknesses"][0]["action"]
    assert score.action_matches(w1, {"type": "node_failure", "zone": "zone-a", "mode": "lost"}, {})
    assert score.action_matches(w1, {"type": "node_failure", "node": "worker", "mode": "drain"}, {"worker": "zone-a"})
    assert not score.action_matches(w1, {"type": "node_failure", "node": "worker2"}, {"worker2": "zone-b"})


def test_impact_only_on_the_entry_journeys(truth):
    n6 = truth["weaknesses"][2]
    rows = [experiment(5, SCALE_DB_PROXY, "broke", cart=True, home=False)]
    assert score.impact(n6, score.experiments_of(rows)[0]) == "withstood"
    rows = [experiment(5, SCALE_DB_PROXY, "broke", cart=True)]
    assert score.impact(n6, score.experiments_of(rows)[0]) is None


def test_citations_only_in_confirmed_and_known_and_only_this_run():
    summary = "\n".join([
        "## Confirmed weaknesses",
        "1. Zone loss takes the site down (steps 12, 14 and 20).",
        "**Known from earlier runs:**",
        "- api single replica: run 3 step 40, still there in step 22.",
        "## Unconfirmed weaknesses",
        "- maybe slow cart, step 30",
        "## What held",
        "- ads down, step 31",
    ])
    assert score.cited_steps(summary, run_id=7) == {12, 14, 20, 22}


def test_score_run(truth):
    rows = [
        {"step": 1, "kind": "tool", "name": "observe__get_placement", "allowed": True, "input": {},
         "output": {"content": {"nodes": [{"name": "worker", "zone": "zone-a"}]}}},
        {"step": 2, "kind": "tool", "name": "read_tools_missing", "allowed": False, "input": {}, "output": {}},
        llm(3),
        experiment(4, {"type": "node_failure", "node": "worker", "mode": "drain"}, "broke", home=True),
        experiment(5, {"type": "delete_pod", "kind": "apps/Deployment", "name": "api"}, "broke", cart=True),
        experiment(6, {**SCALE_DB_PROXY, "name": "ads"}, "broke", home=True),
        experiment(7, {"type": "delete_pod", "kind": "apps/Deployment", "name": "queue"}, "broke", cart=True),
        experiment(8, SCALE_DB_PROXY, "inconclusive", home=False),
        {"step": 9, "kind": "tool", "name": "run_experiment", "allowed": False, "input": {}, "output": {"error": "x"}},
        llm(10, "## Confirmed weaknesses\n- zone-a loss, step 4\n- ads, step 6\n"),
    ]
    s = score.score_run(run(), rows, 0, truth, known_before={"N1"})
    assert s["weaknesses"] == 3
    assert s["found_cited"] == ["W1"]
    assert s["found_broke"] == ["N1", "W1"]
    assert s["false_cited"] == ["S1"] and s["false_broke"] == ["S1"]
    assert [u["step"] for u in s["unknown"]] == [7]
    assert s["experiments"] == 5 and s["inconclusive"] == 1
    assert s["denied"] == 1
    assert s["repeats"] == 1 and s["new"] == 4
    assert s["rounds"] == 2 and s["duration_min"] == 20.0


def test_baseline_has_no_citations(truth):
    rows = [experiment(1, {"type": "delete_pod", "kind": "apps/Deployment", "name": "api"}, "broke", cart=True)]
    s = score.score_run(run(model="baseline"), rows, 0, truth, set())
    assert s["model"] == "baseline" and s["found_cited"] is None and s["found_broke"] == ["N1"]
    assert "n/a" in score.render([s])


def test_unverified_entries_are_not_scored_or_unknown(truth):
    cpu = {"type": "patch", "kind": "apps/Deployment", "name": "web",
           "patch": {"spec": {"template": {"spec": {"containers": [{"resources": {"limits": {"cpu": "10m"}}}]}}}}}
    s = score.score_run(run(), [experiment(1, cpu, "broke", home=True)], 0, truth, set())
    assert s["unverified"] == ["N10"] and s["unknown"] == [] and s["found_broke"] == []


def test_cost_uses_the_long_prompt_rate():
    short = score.cost_usd("claude-haiku-5-5", [llm(n, tokens_in=100_000, tokens_out=0) for n in range(10)])
    long = score.cost_usd("claude-haiku-5-5", [llm(1, tokens_in=200_000, tokens_out=0)])
    assert short == 0.10 and long == 0.10
    assert score.cost_usd("unknown-model", [llm(1)]) is None


def test_score_all_carries_what_earlier_runs_broke(truth):
    first = [experiment(1, {"type": "delete_pod", "kind": "apps/Deployment", "name": "api"}, "broke", cart=True)]
    second = [llm(1), experiment(2, {"type": "delete_pod", "kind": "apps/Deployment", "name": "api"}, "broke", cart=True)]
    scores = score.score_all([(run(1), first, 0), (run(2), second, 0)], truth, {2})
    assert [s["run"] for s in scores] == [2] and scores[0]["repeats"] == 1


def test_a_stored_broke_is_judged_again_from_its_timeline(truth):
    rows = [experiment(1, {"type": "delete_pod", "kind": "apps/Deployment", "name": "api"}, "broke", cart=True)]
    rows[0]["output"]["journeys"]["cart"]["timeline"] = "..s.|.s......s...s......."
    s = score.score_run(run(), rows, 0, truth, set())
    assert s["found_broke"] == [] and s["unknown"] == [] and s["rejudged"] == 1


def test_after_action_skips_the_marks():
    assert score.after_action("..|.xx|s.") == ["ok", "fail", "fail", "slow", "ok"]


def test_the_run_noise_grows_experiment_by_experiment(truth):
    # The first experiment's seconds before the action were noisy, so the same scattered seconds after
    # the second experiment's action are noise; on their own, against the prior, they are not.
    noisy = experiment(1, {"type": "delete_pod", "kind": "apps/Deployment", "name": "queue"}, "withstood", cart=False)
    noisy["output"]["journeys"]["cart"]["timeline"] = "s.s.s.s.ss.s.s.s.s.s|" + "." * 20
    second = experiment(2, {"type": "delete_pod", "kind": "apps/Deployment", "name": "api"}, "broke", cart=True)
    second["output"]["journeys"]["cart"]["timeline"] = "....|.s..s..s..s......"
    alone = score.experiments_of([second])[0]
    after_noise = score.experiments_of([noisy, second])[1]
    assert alone["verdict"] == "broke" and after_noise["verdict"] == "withstood"


def test_any_matches_every_path_under_it():
    rollout = {"type": "patch", "kind": "apps/Deployment", "name": "web",
               "patch": {"spec": {"template": {"metadata": {"annotations": {"chaos/rollout": "1"}}}}}}
    expected = {"type": "patch", "name": "web", "sets": {"spec.template.metadata.annotations": "*"}}
    assert score.action_matches(expected, rollout, {})
    assert not score.action_matches({**expected, "sets": {"spec.template.metadata.labels": "*"}}, rollout, {})
