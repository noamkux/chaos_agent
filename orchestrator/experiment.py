"""Judging an experiment: decide from the measurements, not from the model, whether the system broke.

Terms used in this file:
- measurement: what measure_journeys returns: {"duration_s", "not_sent", "seconds": [...]}, where each
  entry of seconds is {"second": n, "journeys": {name: second_result}}.
- second_result: what happened to one journey in one second, by the second users arrived:
  {"ok": 2, "failed": 0, "p95_ms": 85, "errors": {"timeout": 1}}.
- steady_state: from target.yaml, what normal looks like: {"success_rate": 0.99, "p95_ms": 500}.
- status: one second of one journey judged against the steady state: ok, slow, fail or no_data.
- statuses: the status of every second of a measurement, in order.

Flow: judge() takes the baseline and the measurement of one experiment. For each journey it gets the
statuses of every second (statuses_of, which calls status_of). If any second before the action was not
ok, the result is inconclusive. Otherwise it builds the timeline the model reads, the totals before and
after the action (phase), and when the journey recovered (recovered_at), and decides broke or withstood.
"""

# One character per status in the timeline the model reads: a minute of seconds fits in one short line.
TIMELINE_CHARS = {"ok": ".", "slow": "s", "fail": "x", "no_data": "_"}

# A single bad second can be noise (a GC pause, one slow request). Two or more is a finding.
MIN_BROKEN_S = 2


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
        A list with one status per second, from second 0 to duration_s - 1. A second with no result
        is "no_data", so the list always has duration_s entries.
    """
    results = {s["second"]: s["journeys"].get(journey) for s in measurement["seconds"]}
    return [status_of(results.get(second), steady_state) for second in range(measurement["duration_s"])]


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


def judge(baseline, measurement, journeys, steady_state, action_second, restore_second=None):
    """Decide the result of one experiment.

    Args:
        baseline: measure_journeys before the experiment, without the warm-up seconds.
        measurement: measure_journeys during the experiment, started before the action.
        journeys: the names of the journeys the experiment measured.
        steady_state: {"success_rate", "p95_ms"} from target.yaml.
        action_second: the second of the measurement in which the action ran.
        restore_second: the second of the restore, or None for an action with nothing to restore.

    Returns:
        {"verdict": "inconclusive", "reason", "baseline": timeline per journey} if any second before
        the action was not ok. Otherwise {"verdict": "broke" or "withstood", "journeys": per journey
        its timeline, baseline and after_action totals, broken_s, not_sent and recovered_after_s}.
        broke means at least MIN_BROKEN_S bad seconds after the action, journeys not sent, or no
        recovery by the end of the measurement.
    """
    results = {}
    for journey in journeys:
        statuses = statuses_of(measurement, journey, steady_state)
        before = statuses_of(baseline, journey, steady_state) + statuses[:action_second]
        if any(status != "ok" for status in before):
            return {"verdict": "inconclusive",
                    "reason": f"journey '{journey}' was not steady before the action",
                    "baseline": {j: timeline(statuses_of(baseline, j, steady_state), set()) for j in journeys}}
        # A patch is restored before the system can recover; a deleted pod is replaced on its own.
        recover_from = restore_second if restore_second is not None else action_second
        recovered = recovered_at(statuses, recover_from)
        results[journey] = {
            "timeline": timeline(statuses, {action_second, restore_second} - {None}),
            "baseline": phase(baseline, journey, 0, baseline["duration_s"]),
            "after_action": phase(measurement, journey, action_second, len(statuses)),
            "broken_s": sum(status != "ok" for status in statuses[action_second:]),
            "not_sent": measurement["not_sent"].get(journey, 0),
            "recovered_after_s": None if recovered is None else recovered - recover_from,
        }
    broke = any(r["broken_s"] >= MIN_BROKEN_S or r["not_sent"] or r["recovered_after_s"] is None
                for r in results.values())
    return {"verdict": "broke" if broke else "withstood", "journeys": results}