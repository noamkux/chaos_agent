"""The judge: every second judged against the steady state, the timeline, recovery, and each verdict."""
import pytest

import experiment

STEADY = {"success_rate": 0.99, "p95_ms": 500}
OK, SLOW, FAIL = (2, 0, 20), (2, 0, 900), (0, 2, 10000)


def measurement(seconds, not_sent=0, journey="home"):
    """A measurement with one (ok, failed, p95_ms) per second for one journey; None is a second nobody arrived in."""
    return {"measure_for_s": len(seconds), "not_sent": {journey: not_sent},
            "seconds": [{"second": i, "journeys": {journey: {"ok": s[0], "failed": s[1], "errors": {}, "p95_ms": s[2]}}}
                        for i, s in enumerate(seconds) if s is not None]}


@pytest.mark.parametrize("second, expected", [
    (None, "no_data"),
    ({"ok": 0, "failed": 0, "p95_ms": None}, "no_data"),
    ({"ok": 2, "failed": 0, "p95_ms": 20}, "ok"),
    ({"ok": 2, "failed": 0, "p95_ms": 900}, "slow"),
    # Success comes first: a second with failures is fail whatever its p95.
    ({"ok": 1, "failed": 1, "p95_ms": 20}, "fail"),
])
def test_status_of(second, expected):
    assert experiment.status_of(second, STEADY) == expected


def test_statuses_cover_every_second_and_ignore_late_ones():
    m = measurement([OK, None, OK])
    m["seconds"].append({"second": 3, "journeys": {"home": {"ok": 1, "failed": 0, "errors": {}, "p95_ms": 9}}})
    assert experiment.statuses_of(m, "home", STEADY) == ["ok", "no_data", "ok"]


def test_timeline_marks_action_and_restore():
    assert experiment.timeline(["ok", "fail", "fail", "slow", "ok"], {1, 3}) == ".|xx|s."


@pytest.mark.parametrize("statuses, start, expected", [
    (["ok", "fail", "ok", "ok"], 1, 2),
    (["ok", "fail", "ok", "fail"], 1, None),
    (["ok", "ok", "ok"], 1, 1),
])
def test_recovered_at(statuses, start, expected):
    assert experiment.recovered_at(statuses, start) == expected


BASELINE = measurement([OK] * 5)


def test_withstood():
    result = experiment.judge(BASELINE, measurement([OK] * 10), ["home"], STEADY, action_second=3)
    assert result["verdict"] == "withstood"


def test_one_bad_second_is_noise():
    result = experiment.judge(BASELINE, measurement([OK] * 4 + [FAIL] + [OK] * 5), ["home"], STEADY, 3)
    assert result["verdict"] == "withstood"
    assert result["journeys"]["home"]["broken_s"] == 1


def test_two_bad_seconds_broke():
    result = experiment.judge(BASELINE, measurement([OK] * 4 + [FAIL, SLOW] + [OK] * 4), ["home"], STEADY, 3)
    assert result["verdict"] == "broke"
    assert result["journeys"]["home"]["broken_s"] == experiment.MIN_BROKEN_S


def test_users_not_sent_broke():
    result = experiment.judge(BASELINE, measurement([OK] * 10, not_sent=3), ["home"], STEADY, 3)
    assert result["verdict"] == "broke"


def test_no_recovery_by_the_end_broke():
    result = experiment.judge(BASELINE, measurement([OK] * 9 + [FAIL]), ["home"], STEADY, 3)
    assert result["verdict"] == "broke"
    assert result["journeys"]["home"]["recovered_after_s"] is None


def test_one_bad_second_before_the_action_is_noise():
    result = experiment.judge(BASELINE, measurement([OK, SLOW, OK] + [OK] * 7), ["home"], STEADY, 3)
    assert result["verdict"] == "withstood"


def test_not_steady_before_the_action_is_inconclusive_and_shows_why():
    result = experiment.judge(BASELINE, measurement([SLOW, OK, FAIL] + [OK] * 7), ["home"], STEADY, 3)
    assert result["verdict"] == "inconclusive"
    assert result["before_action"] == {"home": "s.x"}
    assert result["baseline"] == {"home": "....."}


def test_bad_seconds_in_the_baseline_and_before_the_action_add_up():
    baseline = measurement([OK, OK, SLOW, OK, OK])
    result = experiment.judge(baseline, measurement([OK, SLOW, OK] + [OK] * 7), ["home"], STEADY, 3)
    assert result["verdict"] == "inconclusive"


def test_one_bad_second_before_the_action_does_not_count_as_broken():
    result = experiment.judge(BASELINE, measurement([SLOW, OK, OK] + [OK] * 3 + [FAIL] + [OK] * 3),
                              ["home"], STEADY, 3)
    assert result["verdict"] == "withstood"
    assert result["journeys"]["home"]["broken_s"] == 1


def test_recovery_from_the_restore_or_from_the_action():
    m = measurement([OK] * 3 + [FAIL] * 4 + [OK] * 5)
    patch = experiment.judge(BASELINE, m, ["home"], STEADY, action_second=3, restore_second=5)
    node = experiment.judge(BASELINE, m, ["home"], STEADY, action_second=3, restore_second=5,
                            recover_from_restore=False)
    assert patch["journeys"]["home"]["recovered_after_s"] == 2
    assert node["journeys"]["home"]["recovered_after_s"] == 4
