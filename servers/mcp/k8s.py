"""Kubernetes tools."""
from kubernetes import client, config

from scope import check_scope

try:
    config.load_incluster_config()
except config.ConfigException:
    config.load_kube_config()

apps = client.AppsV1Api()


def get_workloads(namespace: str) -> list[dict]:
    """List Deployments and StatefulSets in a namespace with their resilience-relevant settings."""
    check_scope(namespace)
    workloads = [summarize(d, "Deployment") for d in apps.list_namespaced_deployment(namespace).items]
    workloads += [summarize(s, "StatefulSet") for s in apps.list_namespaced_stateful_set(namespace).items]
    return workloads


def summarize(workload, kind):
    """Keep only the settings that resilience checks look at."""
    pod = workload.spec.template.spec
    container = pod.containers[0]
    return {
        "kind": kind,
        "name": workload.metadata.name,
        "replicas": workload.spec.replicas,
        "ready_replicas": workload.status.ready_replicas or 0,
        "image": container.image,
        "readiness_probe": container.readiness_probe is not None,
        "liveness_probe": container.liveness_probe is not None,
        "requests": container.resources.requests or {},
        "limits": container.resources.limits or {},
        "node_affinity": pod.affinity is not None and pod.affinity.node_affinity is not None,
        "topology_spread": bool(pod.topology_spread_constraints),
        "empty_dir_volumes": [v.name for v in pod.volumes or [] if v.empty_dir is not None],
    }

