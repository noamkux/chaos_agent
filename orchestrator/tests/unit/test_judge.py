"""The judge: every second judged against the steady state, the timeline, recovery, and each verdict."""
import pytest

from experiments import judge

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
    assert judge.status_of(second, STEADY) == expected


def test_statuses_cover_every_second_and_ignore_late_ones():
    m = measurement([OK, None, OK])
    m["seconds"].append({"second": 3, "journeys": {"home": {"ok": 1, "failed": 0, "errors": {}, "p95_ms": 9}}})
    assert judge.statuses_of(m, "home", STEADY) == ["ok", "no_data", "ok"]


def test_timeline_marks_action_and_restore():
    assert judge.timeline(["ok", "fail", "fail", "slow", "ok"], {1, 3}) == ".|xx|s."


@pytest.mark.parametrize("statuses, start, expected", [
    (["ok", "fail", "ok", "ok"], 1, 2),
    (["ok", "fail", "ok", "fail"], 1, None),
    (["ok", "ok", "ok"], 1, 1),
])
def test_recovered_at(statuses, start, expected):
    assert judge.recovered_at(statuses, start) == expected


BASELINE = measurement([OK] * 5)


def test_withstood():
    result = judge.judge(BASELINE, measurement([OK] * 10), ["home"], STEADY, action_second=3)
    assert result["verdict"] == "withstood"


def test_one_bad_second_is_noise():
    result = judge.judge(BASELINE, measurement([OK] * 4 + [FAIL] + [OK] * 5), ["home"], STEADY, 3)
    assert result["verdict"] == "withstood"
    assert result["journeys"]["home"]["broken_s"] == 1


def test_two_bad_seconds_broke():
    result = judge.judge(BASELINE, measurement([OK] * 4 + [FAIL, SLOW] + [OK] * 4), ["home"], STEADY, 3)
    assert result["verdict"] == "broke"
    assert result["journeys"]["home"]["broken_s"] == judge.MIN_BROKEN_S


def test_users_not_sent_broke():
    result = judge.judge(BASELINE, measurement([OK] * 10, not_sent=3), ["home"], STEADY, 3)
    assert result["verdict"] == "broke"


def test_no_recovery_by_the_end_broke():
    result = judge.judge(BASELINE, measurement([OK] * 8 + [FAIL, FAIL]), ["home"], STEADY, 3)
    assert result["verdict"] == "broke"
    assert result["journeys"]["home"]["recovered_after_s"] is None


def test_one_bad_last_second_is_noise():
    result = judge.judge(BASELINE, measurement([OK] * 9 + [FAIL]), ["home"], STEADY, 3)
    assert result["verdict"] == "withstood"


# Run 31 step 60: single slow seconds all through the measurement, no failed request.
SCATTERED = [OK, SLOW, OK, OK, OK, OK, OK, OK, SLOW, OK, OK, OK, SLOW] + [OK] * 7
# A run where about one second in six was slow before the action of every experiment.
NOISY_RUN = {"home": (10, 0, 60)}


def test_scattered_slow_seconds_are_noise_in_a_noisy_run():
    result = judge.judge(BASELINE, measurement([OK] * 3 + SCATTERED), ["home"], STEADY, 3, noise=NOISY_RUN)
    assert result["verdict"] == "withstood"
    assert result["journeys"]["home"]["broken_s"] == 3
    assert result["journeys"]["home"]["longest_broken_s"] == 1
    assert result["journeys"]["home"]["noise_rate"] == pytest.approx(10.5 / 113, abs=0.001)


def test_the_same_seconds_are_degraded_in_a_quiet_run():
    quiet = {"home": (0, 0, 200)}
    result = judge.judge(BASELINE, measurement([OK] * 3 + SCATTERED), ["home"], STEADY, 3, noise=quiet)
    assert result["verdict"] == "broke"


def test_two_bad_seconds_in_a_row_are_noise_in_a_noisy_run():
    m = measurement([OK] * 4 + [FAIL, SLOW] + [OK] * 4)
    assert judge.judge(BASELINE, m, ["home"], STEADY, 3, noise=NOISY_RUN)["verdict"] == "withstood"


def test_the_run_noise_decides_before_the_action_too():
    m = measurement([SLOW, OK, SLOW] + [OK] * 7)
    assert judge.judge(BASELINE, m, ["home"], STEADY, 3)["verdict"] == "inconclusive"
    assert judge.judge(BASELINE, m, ["home"], STEADY, 3, noise={"home": (30, 0, 60)})["verdict"] == "withstood"


def test_flickering_broke():
    after = [SLOW, OK, OK, OK] * 5
    result = judge.judge(BASELINE, measurement([OK] * 3 + after), ["home"], STEADY, 3)
    assert result["verdict"] == "broke"
    assert result["journeys"]["home"]["longest_broken_s"] == 1


def test_a_long_phase_does_not_dilute_a_lasting_degradation():
    # Twenty minutes, one second in six slow, against a run that is slow one second in a hundred:
    # never two in a row and never three in ten, but far more than noise makes.
    after = ["slow"] + ["ok"] * 5
    assert judge.degraded(after * 200, 0.01)
    assert not judge.degraded(after * 200, 1 / 6)


def test_a_burst_late_in_a_long_phase_is_caught():
    statuses = ["ok"] * 1200 + ["slow", "ok", "slow", "ok", "slow", "ok", "slow"]
    assert judge.degraded(statuses, 0.01)


@pytest.mark.parametrize("statuses, p, expected", [
    ([], 0.01, False),
    (["ok", "slow", "ok", "ok", "ok"], 0.01, False),
    (["ok", "slow", "fail", "ok", "ok", "ok", "ok", "ok"], 0.01, True),
    (["ok", "slow", "fail", "ok", "ok", "ok", "ok", "ok"], 0.2, False),
])
def test_degraded(statuses, p, expected):
    assert judge.degraded(statuses, p) is expected


def test_noise_rate_starts_from_the_prior_and_follows_the_run():
    assert judge.noise_rate(0, 0) == pytest.approx(judge.PRIOR_BAD_SHARE)
    assert judge.noise_rate(100, 600) == pytest.approx(100.5 / 650)


def test_binomial_tail():
    assert judge.binomial_tail(0, 10, 0.1) == 1.0
    assert judge.binomial_tail(11, 10, 0.1) == 0.0
    assert judge.binomial_tail(1, 1, 0.3) == pytest.approx(0.3)
    assert judge.binomial_tail(2, 3, 0.5) == pytest.approx(0.5)


def test_noise_seconds_and_add_noise():
    m = measurement([OK, SLOW, OK, FAIL, OK])
    counts = judge.noise_seconds(m, ["home"], STEADY, action_second=3)
    assert counts == {"home": (1, 0, 3)}
    assert judge.add_noise({"home": (2, 1, 10)}, counts) == {"home": (3, 1, 13)}


def test_one_bad_second_before_the_action_is_noise():
    result = judge.judge(BASELINE, measurement([OK, SLOW, OK] + [OK] * 7), ["home"], STEADY, 3)
    assert result["verdict"] == "withstood"


def test_not_steady_before_the_action_is_inconclusive_and_shows_why():
    result = judge.judge(BASELINE, measurement([OK, SLOW, FAIL] + [OK] * 7), ["home"], STEADY, 3)
    assert result["verdict"] == "inconclusive"
    assert result["before_action"] == {"home": ".sx"}
    assert result["baseline"] == {"home": "....."}


def test_bad_seconds_in_the_baseline_and_before_the_action_add_up():
    baseline = measurement([OK, SLOW, OK, SLOW, OK])
    result = judge.judge(baseline, measurement([OK, SLOW, OK] + [OK] * 7), ["home"], STEADY, 3)
    assert result["verdict"] == "inconclusive"


def test_one_bad_second_before_the_action_does_not_count_as_broken():
    result = judge.judge(BASELINE, measurement([SLOW, OK, OK] + [OK] * 3 + [FAIL] + [OK] * 3),
                              ["home"], STEADY, 3)
    assert result["verdict"] == "withstood"
    assert result["journeys"]["home"]["broken_s"] == 1


def test_recovery_from_the_restore_or_from_the_action():
    m = measurement([OK] * 3 + [FAIL] * 4 + [OK] * 5)
    patch = judge.judge(BASELINE, m, ["home"], STEADY, action_second=3, restore_second=5)
    node = judge.judge(BASELINE, m, ["home"], STEADY, action_second=3, restore_second=5,
                            recover_from_restore=False)
    assert patch["journeys"]["home"]["recovered_after_s"] == 2
    assert node["journeys"]["home"]["recovered_after_s"] == 4


def test_failed_seconds_are_learned_apart_from_slow_ones():
    # A run often slow before the action, never failing: two slow seconds are noise, two failed are not.
    slow_run = {"home": (20, 0, 100)}
    slow = measurement([OK] * 4 + [SLOW, SLOW] + [OK] * 30)
    failed = measurement([OK] * 4 + [FAIL, FAIL] + [OK] * 30)
    assert judge.judge(BASELINE, slow, ["home"], STEADY, 3, noise=slow_run)["verdict"] == "withstood"
    assert judge.judge(BASELINE, failed, ["home"], STEADY, 3, noise=slow_run)["verdict"] == "broke"
