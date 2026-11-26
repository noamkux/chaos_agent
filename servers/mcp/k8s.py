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
# Turns API objects into dicts with the Kubernetes field names, without fields that are None.
serialize = apps.api_client.sanitize_for_serialization

# Container fields passed to the agent. An allowlist: env is left out on purpose (see env_facts).
CONTAINER_FIELDS = ["name", "image", "imagePullPolicy", "resources", "readinessProbe",
                    "livenessProbe", "startupProbe", "lifecycle", "securityContext",
                    "volumeMounts"]

# Pod fields passed to the agent. An allowlist, like CONTAINER_FIELDS.
POD_FIELDS = ["serviceAccountName", "automountServiceAccountToken", "securityContext",
              "hostNetwork", "hostPID", "hostIPC", "nodeSelector", "affinity",
              "topologySpreadConstraints", "terminationGracePeriodSeconds"]


def container_facts(container):
    """The settings resilience checks read from one container, as in the workload's YAML.

    Args:
        container: a V1Container from the pod template.

    Returns:
        A dict with the CONTAINER_FIELDS that are set.
    """
    data = serialize(container)
    return {field: data[field] for field in CONTAINER_FIELDS if field in data}

def env_facts(container):
    """Names and sources of a container's environment variables. Values never leave this function.

    Args:
        container: a V1Container from the pod template.

    Returns:
        A dict with "env": a list of {"name", "source"}, where source is "literal" for a value
        written in the spec or the valueFrom type (secretKeyRef, configMapKeyRef, fieldRef,
        resourceFieldRef); and "envFrom": a list of {"source", "name"} for a whole ConfigMap
        (configMapRef) or Secret (secretRef). Empty lists are left out.
    """
    # env: variables defined one by one, each with its own name.
    # Looks at where each value comes from: written in the spec (literal) or a reference (valueFrom).
    # Returns name and source only; var.value is never read, so a secret cannot be returned by mistake.
    env = []
    for var in container.env or []:
        if var.value_from is None:
            source = "literal"
        else:
            source = next(iter(serialize(var.value_from)))
        env.append({"name": var.name, "source": source})

    # envFrom: every key of a whole ConfigMap or Secret loaded as variables; no variable names here.
    # Looks at which kind of source is loaded and its name.
    # Returns the source kind and name only; the keys and values inside are not read.
    env_from = []
    for item in container.env_from or []:
        source = "secretRef" if item.secret_ref else "configMapRef"
        ref = item.secret_ref or item.config_map_ref
        env_from.append({"source": source, "name": ref.name})

    # Leave out empty lists, so a container without variables adds nothing to the output.
    facts = {"env": env, "envFrom": env_from}
    return {key: value for key, value in facts.items() if value}

def get_workloads(namespace: str) -> list[dict]:
    """List the Deployments, StatefulSets and DaemonSets in a namespace, with the facts resilience checks read from each one.

    Fields use the Kubernetes names, as in the workload's YAML. A field that is not set is left
    out: a container with no livenessProbe field has no liveness probe.
    For a DaemonSet, replicas is the number of pods that should run, one per eligible node.
    Environment variables show only the name and where the value comes from (literal,
    secretKeyRef, configMapKeyRef, fieldRef, resourceFieldRef), never the value; envFrom lists
    whole ConfigMaps or Secrets by name. Volumes show only name and type.
    Not included at all: container command, args and ports, and the values of any variable.
    """
        
    check_scope(namespace)
    workloads = [summarize(d, "Deployment") for d in apps.list_namespaced_deployment(namespace).items]
    workloads += [summarize(s, "StatefulSet") for s in apps.list_namespaced_stateful_set(namespace).items]
    workloads += [summarize(d, "DaemonSet") for d in apps.list_namespaced_daemon_set(namespace).items]
    return workloads

def summarize(workload, kind):
    """The facts resilience checks read from a workload, in Kubernetes field names.

    Args:
        workload: a Deployment, StatefulSet or DaemonSet object from the Kubernetes API.
        kind: "Deployment", "StatefulSet" or "DaemonSet"; objects in list responses do not carry their kind.

    Returns:
        A dict with the workload's replicas, pod labels, POD_FIELDS that are set, volumes
        (name and type), and every container with container_facts and env_facts.
    """
    template = workload.spec.template
    pod = serialize(template.spec)
    if kind == "DaemonSet":
        # One pod per eligible node: there is no spec.replicas, the controller sets the count.
        replicas = workload.status.desired_number_scheduled
        ready = workload.status.number_ready
    else:
        replicas = workload.spec.replicas
        ready = workload.status.ready_replicas or 0
    summary = {
        "kind": kind,
        "name": workload.metadata.name,
        "replicas": replicas,
        "readyReplicas": ready,
        "labels": template.metadata.labels or {},
        **{field: pod[field] for field in POD_FIELDS if field in pod},
        # Volume type only (emptyDir, persistentVolumeClaim, secret, ...), not its settings.
        "volumes": [{"name": v["name"], "type": next(key for key in v if key != "name")}
                    for v in pod.get("volumes", [])],
        "initContainers": [{**container_facts(c), **env_facts(c)}
                           for c in template.spec.init_containers or []],
        "containers": [{**container_facts(c), **env_facts(c)} for c in template.spec.containers],
    }
    # Leave out empty lists and dicts; replicas 0 and false values stay, they are facts.
    return {key: value for key, value in summary.items() if value not in ([], {})}

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