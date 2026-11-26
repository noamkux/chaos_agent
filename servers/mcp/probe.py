"""Probe tools: send requests to the application and measure what a user sees. They never change anything."""
import asyncio
import json
import math
import os
import tempfile
import time
from pathlib import Path

from kubernetes.client.exceptions import ApiException
from mcp.server.mcpserver.exceptions import ToolError

from k8s import core
from scope import check_scope

JOURNEYS_SCRIPT = Path(__file__).parent / "journeys.js"

# Caps enforced by the server. The Rules of Engagement can lower them, never raise them.
MAX_DURATION_S = 300
MAX_RATE = 10
MAX_VUS = 50
TIMEOUT_S = 10
METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"}


def service_url(namespace, service, port):
    """The base URL of a Service port, after checking that the Service exists and declares the port."""
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
                                           config["duration_s"] + 2 * config["timeout_s"] + 30)
    except asyncio.TimeoutError:
        process.kill()
        raise ToolError("k6 did not finish in time")
    if process.returncode != 0:
        raise ToolError(f"k6 failed: {stderr.decode()[-500:]}")
    return out_file


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


async def measure_journeys(namespace: str, service: str, port: int,
                           journeys: dict[str, list[dict]], duration_s: int, rate: int) -> dict:
    """Run every journey at a fixed rate for duration_s seconds, as new users, and report each second of arrival: journeys that succeeded, failed, p95 latency and errors."""
    base_url = service_url(namespace, service, port)
    check_journeys(journeys)
    if not 0 < duration_s <= MAX_DURATION_S or not 0 < rate <= MAX_RATE:
        raise ToolError(f"duration_s must be 1 to {MAX_DURATION_S} and rate 1 to {MAX_RATE}")
    config = {"base_url": base_url, "journeys": journeys, "rate": rate, "duration_s": duration_s,
              "max_vus": MAX_VUS, "timeout_s": TIMEOUT_S}
    # k6 starts measuring within about a second of this time.
    started_at = time.time()
    out_file = await run_k6(config)
    try:
        summary = summarize(out_file, journeys)
    finally:
        out_file.unlink()
        out_file.with_name("config.json").unlink()
        out_file.parent.rmdir()
    return {"started_at": started_at, "rate": rate, "duration_s": duration_s, **summary}