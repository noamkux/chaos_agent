"""Judging an experiment: decide from the measurements, not from the model, whether the system broke.

Terms used in this file:
- measurement: what measure_journeys returns: {"measure_for_s", "not_sent", "seconds": [...]}, where each
  entry of seconds is {"second": n, "journeys": {name: second_result}}.
- second_result: what happened to one journey in one second, by the second users arrived:
  {"ok": 2, "failed": 0, "p95_ms": 85, "errors": {"timeout": 1}}.
- steady_state: from target.yaml, what normal looks like: {"success_rate": 0.99, "p95_ms": 500}.
- status: one second of one journey judged against the steady state: ok, slow, fail or no_data.
- statuses: the status of every second of a measurement, in order.

Flow: judge() takes the baseline and the measurement of one experiment. For each journey it gets the
statuses of every second (statuses_of, which calls status_of). If at least MIN_BROKEN_S seconds before
the action were not ok, the result is inconclusive. Otherwise it builds the timeline the model reads, the totals before and
after the action (phase), and when the journey recovered (recovered_at), and decides broke or withstood.
"""
import math

# One character per status in the timeline the model reads: a minute of seconds fits in one short line.
TIMELINE_CHARS = {"ok": ".", "slow": "s", "fail": "x", "no_data": "_"}

# A single bad second is never a finding on its own (a GC pause, one slow request).
MIN_BROKEN_S = 2

# Every application has its own noise: how often a second is bad with nothing changed. The judge learns
# it during the run, from the seconds before the action of every experiment, and calls a phase degraded
# only when noise at that rate would make it with a chance under ALPHA (ADR-0036). Failed seconds are
# learned apart from bad ones, as the steady state keeps success and latency apart: a system that is
# often slow is not often failing, so two failed seconds can be a finding where two slow ones are noise. Nothing here is set
# per application: the prior is what a run starts from, worth PRIOR_SECONDS of measurement, and the
# run's own seconds outweigh it within a few experiments.
PRIOR_BAD_SHARE = 0.01
PRIOR_SECONDS = 50
ALPHA = 0.005
# The window in which scattered bad seconds count together, so a burst inside a long phase is not diluted.
WINDOW_S = 10


def status_of(second_result, steady_state):
    """Judge one second of one journey against the steady state.

    Args:
        second_result: {"ok", "failed", "p95_ms", "errors"} for one journey in one second, or None
            when no user of that journey arrived in that second.
        steady_state: {"success_rate", "p95_ms"} from target.yaml.

    Returns:
        "fail" if the success rate is below the steady state, "slow" if every journey succeeded but
        p95 is above it, "no_data" if nobody arrived, "ok" otherwise.
    """
    if not second_result or second_result["ok"] + second_result["failed"] == 0:
        return "no_data"
    success = second_result["ok"] / (second_result["ok"] + second_result["failed"])
    if success < steady_state["success_rate"]:
        return "fail"
    if second_result["p95_ms"] is not None and second_result["p95_ms"] > steady_state["p95_ms"]:
        return "slow"
    return "ok"


def statuses_of(measurement, journey, steady_state):
    """Judge every second of a measurement for one journey.

    Args:
        measurement: what measure_journeys returned.
        journey: the journey's name from target.yaml, for example "home".
        steady_state: {"success_rate", "p95_ms"} from target.yaml.

    Returns:
        A list with one status per second, from second 0 to measure_for_s - 1. A second with no result
        is "no_data", so the list always has measure_for_s entries.
    """
    results = {s["second"]: s["journeys"].get(journey) for s in measurement["seconds"]}
    return [status_of(results.get(second), steady_state) for second in range(measurement["measure_for_s"])]


def timeline(statuses, marks):
    """Turn statuses into the one-line picture the model reads.

    Args:
        statuses: from statuses_of.
        marks: seconds to mark with | before them: the second of the action and of the restore.

    Returns:
        A string with one character per second (see TIMELINE_CHARS), for example "...|xxx|s...".
    """
    return "".join(("|" if second in marks else "") + TIMELINE_CHARS[status]
                   for second, status in enumerate(statuses))


def phase(measurement, journey, start, end):
    """Add up one journey over a range of seconds.

    Args:
        measurement: what measure_journeys returned.
        journey: the journey's name from target.yaml.
        start: the first second to include.
        end: the second after the last one to include.

    Returns:
        {"success": share of journeys that succeeded, or None if none ran, "worst_p95_ms": the highest
        p95 of any second, "errors": count of each error type}.
    """
    ok = failed = worst_p95 = 0
    errors = {}
    for s in measurement["seconds"]:
        result = s["journeys"].get(journey)
        if result is None or not start <= s["second"] < end:
            continue
        ok += result["ok"]
        failed += result["failed"]
        worst_p95 = max(worst_p95, result["p95_ms"] or 0)
        for error, count in result["errors"].items():
            errors[error] = errors.get(error, 0) + count
    total = ok + failed
    return {"success": round(ok / total, 3) if total else None, "worst_p95_ms": worst_p95, "errors": errors}


def longest_bad_run(statuses):
    """The most seconds in a row that were not ok."""
    longest = current = 0
    for status in statuses:
        current = current + 1 if status != "ok" else 0
        longest = max(longest, current)
    return longest


def most_bad_in_window(statuses, window=WINDOW_S):
    """The most bad seconds in any window of that many seconds (the whole phase, if it is shorter)."""
    bad = [status != "ok" for status in statuses]
    return max((sum(bad[start:start + window]) for start in range(max(len(bad) - window, 0) + 1)), default=0)


def noise_rate(bad, seconds):
    """The share of bad seconds expected with nothing changed: the run's own seconds before the action,
    added to the prior."""
    return (bad + PRIOR_BAD_SHARE * PRIOR_SECONDS) / (seconds + PRIOR_SECONDS)


def binomial_tail(k, n, p):
    """The chance of at least k bad seconds out of n, when each is bad with chance p on its own."""
    if k <= 0:
        return 1.0
    if k > n:
        return 0.0
    log_p, log_q = math.log(p), math.log1p(-p)
    below = sum(math.exp(math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1)
                         + i * log_p + (n - i) * log_q) for i in range(k))
    return max(0.0, 1.0 - below)


def thresholds(length, p):
    """What noise at rate p makes in a phase of that many seconds with a chance under ALPHA, for each of
    the three tests: bad seconds in a row, bad seconds in one window, and bad seconds in the whole phase.
    Each is at least MIN_BROKEN_S."""
    run = MIN_BROKEN_S
    # Union bound: a run of that length can start at any of the phase's seconds.
    while run <= length and length * p ** run >= ALPHA:
        run += 1
    window = min(WINDOW_S, length)
    windows = max(length - window + 1, 1)
    in_window = MIN_BROKEN_S
    while in_window <= window and windows * binomial_tail(in_window, window, p) >= ALPHA:
        in_window += 1
    total = MIN_BROKEN_S
    while total <= length and binomial_tail(total, length, p) >= ALPHA:
        total += 1
    return {"in_a_row": run, "in_window": in_window, "in_phase": total}


def degraded(statuses, p):
    """Whether a phase of a journey was worse than the application's own noise, at rate p: too many bad
    seconds in a row (an outage), too many in one window (a burst of flickering), or too many in the whole
    phase (a thin degradation that lasts, which a long phase must not dilute)."""
    if not statuses:
        return False
    limit = thresholds(len(statuses), p)
    return (longest_bad_run(statuses) >= limit["in_a_row"]
            or most_bad_in_window(statuses) >= limit["in_window"]
            or sum(status != "ok" for status in statuses) >= limit["in_phase"])


def counts_of(statuses):
    """(bad, failed, seconds) of some seconds of one journey."""
    return (sum(status != "ok" for status in statuses), sum(status == "fail" for status in statuses), len(statuses))


def noise_seconds(measurement, journeys, steady_state, action_second):
    """The seconds before the action of one experiment, per journey, as (bad, failed, seconds): what the run
    adds to its noise after an experiment that was not inconclusive."""
    return {journey: counts_of(statuses_of(measurement, journey, steady_state)[:action_second])
            for journey in journeys}


def add_noise(noise, counts):
    """The run's noise with one experiment's seconds before the action added."""
    total = dict(noise)
    for journey, added in counts.items():
        total[journey] = tuple(old + new for old, new in zip(total.get(journey, (0, 0, 0)), added))
    return total


def degraded_against(statuses, noise):
    """Whether some seconds of a journey were worse than its noise (bad, failed, seconds): in bad seconds
    against the bad noise, or in failed seconds against the failed noise."""
    bad, failed, seconds = noise
    only_failed = [status if status == "fail" else "ok" for status in statuses]
    return degraded(statuses, noise_rate(bad, seconds)) or degraded(only_failed, noise_rate(failed, seconds))


def recovered_at(statuses, start):
    """Find when a journey was back to normal for good.

    Args:
        statuses: from statuses_of.
        start: the first second it could recover: the restore for a patch, the action for a deleted pod.

    Returns:
        The first second at or after start from which every second to the end is "ok", or None if the
        last second is still not "ok" (it did not recover within the measurement).
    """
    for second in range(len(statuses) - 1, start - 1, -1):
        if statuses[second] != "ok":
            return second + 1 if second + 1 < len(statuses) else None
    return start


def judge(baseline, measurement, journeys, steady_state, action_second, restore_second=None,
          recover_from_restore=True, noise=None):
    """Decide the result of one experiment.

    Args:
        baseline: measure_journeys before the experiment, without the warm-up seconds.
        measurement: measure_journeys during the experiment, started before the action.
        journeys: the names of the journeys the experiment measured.
        steady_state: {"success_rate", "p95_ms"} from target.yaml.
        action_second: the second of the measurement in which the action ran.
        restore_second: the second of the restore, or None for an action with nothing to restore.
        recover_from_restore: count recovery from the restore (a patch, which the system cannot heal
            on its own) or, when False, from the action (a node failure, which it must heal while the
            node is still down).
        noise: per journey (bad, failed, seconds) before the action of the run's earlier experiments.

    Returns:
        {"verdict": "inconclusive", "reason", "baseline" and "before_action": timeline per journey} if
        the seconds before the action, the baseline and the measurement together, were degraded against
        the noise of the earlier experiments. Otherwise {"verdict": "broke" or "withstood", "journeys":
        per journey its timeline, baseline and after_action totals, broken_s (every bad second after the
        action), longest_broken_s (the most in a row), noise_rate (the share of bad seconds the judge
        expected from noise), not_sent and recovered_after_s}.
        broke means the seconds after the action were degraded against the noise, this experiment's
        seconds before the action included, or journeys were not sent. A journey still broken at the
        end is degraded too, since its last seconds are bad in a row.
    """
    noise = noise or {}
    results = {}
    for journey in journeys:
        statuses = statuses_of(measurement, journey, steady_state)
        before = statuses_of(baseline, journey, steady_state) + statuses[:action_second]
        earlier = noise.get(journey, (0, 0, 0))
        if degraded_against(before, earlier):
            return {"verdict": "inconclusive",
                    "reason": f"journey '{journey}' was not steady before the action",
                    "baseline": {j: timeline(statuses_of(baseline, j, steady_state), set()) for j in journeys},
                    "before_action": {j: timeline(statuses_of(measurement, j, steady_state)[:action_second], set())
                                      for j in journeys}}
        # A patch is restored before the system can recover; a deleted pod is replaced on its own,
        # and a failed node's pods must be rescheduled elsewhere while it is still down.
        recover_from = restore_second if restore_second is not None and recover_from_restore else action_second
        recovered = recovered_at(statuses, recover_from)
        results[journey] = {
            "timeline": timeline(statuses, {action_second, restore_second} - {None}),
            "baseline": phase(baseline, journey, 0, baseline["measure_for_s"]),
            "after_action": phase(measurement, journey, action_second, len(statuses)),
            "broken_s": sum(status != "ok" for status in statuses[action_second:]),
            "longest_broken_s": longest_bad_run(statuses[action_second:]),
        }
        noise_now = tuple(old + new for old, new in zip(earlier, counts_of(statuses[:action_second])))
        results[journey] |= {
            "noise_rate": round(noise_rate(noise_now[0], noise_now[2]), 3),
            "degraded": degraded_against(statuses[action_second:], noise_now),
            "not_sent": measurement["not_sent"].get(journey, 0),
            "recovered_after_s": None if recovered is None else recovered - recover_from,
        }
    broke = any(r.pop("degraded") or r["not_sent"] for r in results.values())
    return {"verdict": "broke" if broke else "withstood", "journeys": results}