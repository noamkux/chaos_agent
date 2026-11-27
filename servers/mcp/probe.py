"""Probe tools: send requests to the application and measure what a user sees. They never change anything."""
import asyncio
import json
import math
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from kubernetes.client.exceptions import ApiException
from mcp.server.mcpserver.exceptions import ToolError

from k8s import core
from scope import check_scope

JOURNEYS_SCRIPT = Path(__file__).parent / "journeys.js"

# Caps set by the cluster admin in the chart values (mcp.levels.probe.limits) and enforced on every
# measurement, whatever target.yaml asks for. The defaults are for a run outside the chart.
LONGEST_K6_RUN_S = int(os.environ.get("LONGEST_K6_RUN_S", "300"))
LONGEST_REQUEST_WAIT_S = int(os.environ.get("LONGEST_REQUEST_WAIT_S", "30"))
MAX_NEW_USERS_PER_SECOND = int(os.environ.get("MAX_NEW_USERS_PER_SECOND", "10"))
MAX_CONCURRENT_USERS_PER_JOURNEY = int(os.environ.get("MAX_CONCURRENT_USERS_PER_JOURNEY", "50"))
METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"}


def service_url(namespace, service, port):
    """Checks that the service that was requested to be tested actially exsist"""
    check_scope(namespace)
    try:
        svc = core.read_namespaced_service(service, namespace)
    except ApiException as error:
        raise ToolError(f"service '{service}': {error.status} {error.reason}")
    if port not in [p.port for p in svc.spec.ports or []]:
        raise ToolError(f"port {port} is not declared by service '{service}'")
    return f"http://{service}.{namespace}.svc:{port}"


def check_journeys(journeys):
    """Reject journeys with a step that is not a known method and a path on this service."""
    if not journeys:
        raise ToolError("journeys must not be empty")
    for name, steps in journeys.items():
        if not steps:
            raise ToolError(f"journey '{name}' has no steps")
        for step in steps:
            if step.get("method") not in METHODS or not str(step.get("path", "")).startswith("/"):
                raise ToolError(f"journey '{name}': every step needs a method and a path starting with /")


async def run_k6(config):
    """Run journeys.js with this config and return the path of k6's JSON output, inside a temporary directory."""
    tmp = tempfile.mkdtemp(prefix="k6-")
    config_file = Path(tmp) / "config.json"
    out_file = Path(tmp) / "out.json"
    config_file.write_text(json.dumps(config))
    process = await asyncio.create_subprocess_exec(
        "k6", "run", "--quiet", "--no-usage-report", "--out", f"json={out_file}", str(JOURNEYS_SCRIPT),
        env={"CONFIG_FILE": str(config_file), "PATH": os.environ["PATH"], "HOME": tmp},
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
    try:
        _, stderr = await asyncio.wait_for(process.communicate(),
                                           config["measure_for_s"] + 2 * config["fail_request_after_s"] + 30)
    except asyncio.TimeoutError:
        process.kill()
        raise ToolError("k6 did not finish in time")
    if process.returncode != 0:
        raise ToolError(f"k6 failed: {stderr.decode()[-500:]}")
    return out_file


def concurrent_users(journeys, new_users_per_second, fail_request_after_s):
    """How many users each journey may have in flight at once. In the worst case every step waits until it
    fails while new users keep arriving, so a journey needs new_users_per_second x fail_request_after_s x
    its steps. Capped by MAX_CONCURRENT_USERS_PER_JOURNEY: past the cap, k6 reports the users it could not
    start as not sent, which is what real users would meet."""
    return {name: min(MAX_CONCURRENT_USERS_PER_JOURNEY, new_users_per_second * fail_request_after_s * len(steps))
            for name, steps in journeys.items()}


def p95(values):
    """The 95th percentile of a list of numbers, nearest rank."""
    ordered = sorted(values)
    return ordered[math.ceil(0.95 * len(ordered)) - 1]


def summarize(out_file, names):
    """Count k6's journey points by arrival second and journey: succeeded, failed, p95 and errors."""
    seconds = {}
    not_sent = dict.fromkeys(names, 0)
    with open(out_file) as lines:
        for line in lines:
            # A cheap filter first: most lines are k6's per-request metrics, which are not needed.
            if '"type":"Point"' not in line:
                continue
            if '"metric":"journey_' not in line and '"metric":"dropped_iterations"' not in line:
                continue
            point = json.loads(line)
            metric, tags = point["metric"], point["data"]["tags"]
            if metric == "dropped_iterations":
                not_sent[tags["scenario"]] += int(point["data"]["value"])
                continue
            bucket = seconds.setdefault(int(tags["second"]), {}).setdefault(
                tags["journey"], {"ok": 0, "failed": 0, "errors": {}, "durations": []})
            if metric == "journey_ok":
                bucket["ok"] += 1
            elif metric == "journey_failed":
                bucket["failed"] += 1
                bucket["errors"][tags["error"]] = bucket["errors"].get(tags["error"], 0) + 1
            else:
                bucket["durations"].append(point["data"]["value"])
    for per_journey in seconds.values():
        for bucket in per_journey.values():
            durations = bucket.pop("durations")
            bucket["p95_ms"] = round(p95(durations)) if durations else None
    return {"not_sent": not_sent,
            "seconds": [{"second": s, "journeys": seconds[s]} for s in sorted(seconds)]}


async def measure_journeys(namespace: str, service: str, port: int, journeys: dict[str, list[dict]],
                           measure_for_s: int, new_users_per_second: int,
                           fail_request_after_s: int) -> dict[str, Any]:
    """Run every journey for measure_for_s seconds with new_users_per_second new users each second, whatever the system does, and report each second of arrival: journeys that succeeded, failed, p95 latency and errors. A request with no answer after fail_request_after_s seconds fails."""
    base_url = service_url(namespace, service, port)
    check_journeys(journeys)
    if not 0 < measure_for_s <= LONGEST_K6_RUN_S:
        raise ToolError(f"measure_for_s must be 1 to {LONGEST_K6_RUN_S}")
    if not 0 < new_users_per_second <= MAX_NEW_USERS_PER_SECOND:
        raise ToolError(f"new_users_per_second must be 1 to {MAX_NEW_USERS_PER_SECOND}")
    if not 0 < fail_request_after_s <= LONGEST_REQUEST_WAIT_S:
        raise ToolError(f"fail_request_after_s must be 1 to {LONGEST_REQUEST_WAIT_S}")
    config = {"base_url": base_url, "journeys": journeys, "new_users_per_second": new_users_per_second,
              "measure_for_s": measure_for_s, "fail_request_after_s": fail_request_after_s,
              "concurrent_users": concurrent_users(journeys, new_users_per_second, fail_request_after_s)}
    # k6 starts measuring within about a second of this time.
    started_at = time.time()
    out_file = await run_k6(config)
    try:
        summary = summarize(out_file, journeys)
    finally:
        out_file.unlink()
        out_file.with_name("config.json").unlink()
        out_file.parent.rmdir()
    return {"started_at": started_at, "new_users_per_second": new_users_per_second,
            "measure_for_s": measure_for_s, **summary}