"""Kubernetes tools."""
from kubernetes import client, config

from scope import check_scope

try:
    config.load_incluster_config()
except config.ConfigException:
    config.load_kube_config()
# Deployments, StatefulSets
apps = client.AppsV1Api()
# Services, Pods, Events
core = client.CoreV1Api()
# Ingress, NetworkPolicy
networking = client.NetworkingV1Api()

def get_workloads(namespace: str) -> list[dict]:
    """List Deployments and StatefulSets in a namespace with their resilience-relevant settings."""
    check_scope(namespace)
    workloads = [summarize(d, "Deployment") for d in apps.list_namespaced_deployment(namespace).items]
    workloads += [summarize(s, "StatefulSet") for s in apps.list_namespaced_stateful_set(namespace).items]
    return workloads

def summarize(workload, kind):
    """Keep only the settings that resilience checks look at.

    Args:
        workload: a Deployment or StatefulSet object from the Kubernetes API.
        kind: "Deployment" or "StatefulSet"; objects in list responses do not carry their kind.
    """
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

def get_inventory(namespace: str) -> dict[str, list[str]]:
    """List the names of the Deployments, StatefulSets, Services and Ingresses in a namespace.

    Only these four kinds are listed. An empty list means none of that kind exists;
    any other kind (PodDisruptionBudget, NetworkPolicy, ...) is not covered by this tool.
    """
    check_scope(namespace)
    return {
        "Deployment": names(apps.list_namespaced_deployment(namespace)),
        "StatefulSet": names(apps.list_namespaced_stateful_set(namespace)),
        "Service": names(core.list_namespaced_service(namespace)),
        "Ingress": names(networking.list_namespaced_ingress(namespace)),
    }

def names(resource_list):
    """Sorted names from a Kubernetes list response.

    Args:
        resource_list: the response of a list_namespaced_* call.
    """
    return sorted(item.metadata.name for item in resource_list.items)