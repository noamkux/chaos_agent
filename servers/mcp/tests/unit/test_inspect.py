"""inspect_workload: what reaches the agent from events, pods and the rollout, and what never does."""
import k8s

CANARY = "lab-fake-7f3c9a2e5b8d41f6"
POD_SPEC = {"containers": [
    {"name": "server", "env": [{"name": "API_KEY", "value": CANARY}, {"name": "PORT", "value": "8080"},
                               {"name": "LEVEL", "value": "info"},
                               {"name": "DB_PASSWORD", "valueFrom": {"secretKeyRef": {"name": "db", "key": "p"}}}],
     "readinessProbe": {"grpc": {"port": 3550}}},
    {"name": "sidecar", "livenessProbe": {"exec": {"command": ["sh", "-c", "check"]}}}]}


def event(reason, message, kind="Pod", name="frontend-86449dcc4-g7fdx", field_path=None, time="2026-11-28T07:17:33+00:00"):
    involved = {"kind": kind, "name": name, **({"fieldPath": field_path} if field_path else {})}
    return {"reason": reason, "message": message, "type": "Warning", "involvedObject": involved,
            "lastTimestamp": time, "count": 3}


def test_literal_env_values_are_known_only_when_long_enough_and_not_numbers():
    assert k8s.literal_env_values(POD_SPEC) == {CANARY}


def test_the_canary_never_leaves_in_an_event_message():
    message = k8s.event_message(event("BackOff", f"failed: API_KEY={CANARY} rejected"), {CANARY}, set())
    assert CANARY not in message and "API_KEY=[redacted] rejected" in message


def test_the_probe_failure_of_an_exec_probe_container_is_withheld():
    secrets, exec_containers = k8s.literal_env_values(POD_SPEC), k8s.exec_probe_containers(POD_SPEC)
    assert exec_containers == {"sidecar"}
    withheld = event("Unhealthy", f"Liveness probe failed: db_password: s3cret {CANARY}",
                     field_path="spec.containers{sidecar}")
    assert k8s.event_message(withheld, secrets, exec_containers) == k8s.EXEC_PROBE_WITHHELD


def test_the_probe_failure_of_a_grpc_probe_container_keeps_its_message():
    kept = event("Unhealthy", "Readiness probe failed: timeout: failed to connect service",
                 field_path="spec.containers{server}")
    assert k8s.event_message(kept, set(), {"sidecar"}).startswith("Readiness probe failed: timeout")


def test_a_probe_failure_with_no_container_named_is_withheld_when_any_probe_is_exec():
    assert k8s.event_message(event("Unhealthy", "probe failed: output"), set(), {"sidecar"}) == k8s.EXEC_PROBE_WITHHELD


def test_long_messages_are_cut_after_redaction():
    message = k8s.redact(CANARY + "x" * 600, {CANARY})
    assert message.startswith(k8s.REDACTED) and message.endswith("... (truncated)")
    assert len(message) == k8s.EVENT_MESSAGE_LIMIT + len("... (truncated)")


def test_a_failed_scheduling_message_on_a_small_cluster_is_kept_whole():
    message = ("0/4 nodes are available: 1 node(s) had untolerated taint {node.kubernetes.io/unschedulable: }, "
               "1 node(s) had untolerated taint {node-role.kubernetes.io/control-plane: }, 2 node(s) didn't "
               "match Pod's node affinity/selector. preemption: 0/4 nodes are available: 4 Preemption is not "
               "helpful for scheduling.")
    assert k8s.redact(message, set()) == message


def test_events_of_the_workload_its_replicasets_and_its_pods_match_even_deleted_pods():
    owned = {"frontend-86449dcc4"}
    prefixes = ["frontend-86449dcc4-"]
    assert k8s.event_matches(event("ScalingReplicaSet", "", kind="Deployment", name="frontend"),
                             "apps/Deployment", "frontend", owned, prefixes)
    assert k8s.event_matches(event("SuccessfulCreate", "", kind="ReplicaSet", name="frontend-86449dcc4"),
                             "apps/Deployment", "frontend", owned, prefixes)
    assert k8s.event_matches(event("Killing", "", name="frontend-86449dcc4-gone1"),
                             "apps/Deployment", "frontend", owned, prefixes)
    assert not k8s.event_matches(event("Killing", "", name="frontend-external-5d9f-x"),
                                 "apps/Deployment", "frontend", owned, prefixes)


def test_rollout_facts_show_the_strategy_and_whether_a_rollout_is_in_progress():
    obj = {"metadata": {"generation": 5},
           "spec": {"replicas": 2, "strategy": {"type": "RollingUpdate",
                                                "rollingUpdate": {"maxSurge": "25%", "maxUnavailable": "25%"}}},
           "status": {"observedGeneration": 4, "updatedReplicas": 1, "readyReplicas": 2,
                      "conditions": [{"type": "Progressing", "status": "True", "reason": "ReplicaSetUpdated",
                                      "message": f"set by {CANARY}"}]}}
    facts = k8s.rollout_facts(obj, {CANARY})
    assert facts["strategy"]["rollingUpdate"]["maxUnavailable"] == "25%"
    assert (facts["generation"], facts["observedGeneration"]) == (5, 4)
    assert CANARY not in str(facts)


def test_pod_state_returns_reasons_and_exit_codes_never_container_messages():
    pod = {"metadata": {"name": "cart-1"}, "spec": {"nodeName": "chaos-lab-worker"},
           "status": {"phase": "Running", "conditions": [{"type": "Ready", "status": "False"}],
                      "containerStatuses": [{"name": "server", "ready": False, "restartCount": 2,
                                             "state": {"waiting": {"reason": "CrashLoopBackOff", "message": CANARY}},
                                             "lastState": {"terminated": {"reason": "OOMKilled", "exitCode": 137,
                                                                          "message": CANARY,
                                                                          "finishedAt": "2026-11-28T07:18:00Z"}}}]}}
    state = k8s.pod_state(pod)
    assert state["ready"] is False and state["containers"][0]["reason"] == "CrashLoopBackOff"
    assert state["containers"][0]["last_terminated"] == {"reason": "OOMKilled", "exitCode": 137,
                                                         "finishedAt": "2026-11-28T07:18:00Z"}
    assert CANARY not in str(state)
