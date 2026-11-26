"""Kubernetes tools."""
from kubernetes import client, config, dynamic
from kubernetes.client.exceptions import ApiException
from kubernetes.dynamic.resource import ResourceList

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

# Lists any kind, including CRDs, found through the API server's discovery.
dynamic_client = dynamic.DynamicClient(apps.api_client)


# Container fields passed to the agent. An allowlist: env is left out on purpose (see env_facts).
CONTAINER_FIELDS = ["name", "image", "imagePullPolicy", "resources", "readinessProbe",
                    "livenessProbe", "startupProbe", "lifecycle", "securityContext",
                    "volumeMounts"]

# Pod fields passed to the agent. An allowlist, like CONTAINER_FIELDS.
POD_FIELDS = ["serviceAccountName", "automountServiceAccountToken", "securityContext",
              "hostNetwork", "hostPID", "hostIPC", "nodeSelector", "affinity",
              "topologySpreadConstraints", "terminationGracePeriodSeconds"]

# Kinds left out of the inventory. Secrets are never read. The rest are created by
# controllers, change all the time, and their content comes from dedicated tools.
SKIPPED_KINDS = {
    "core/Secret",
    "core/Pod", "apps/ReplicaSet", "apps/ControllerRevision",
    "core/Endpoints", "discovery.k8s.io/EndpointSlice",
    "core/Event", "events.k8s.io/Event",
    "coordination.k8s.io/Lease",
}

def listable_kinds():
    """Every namespaced kind the API server can list, at its preferred version.

    Returns:
        A dict from "group/Kind" (core/Service, apps/Deployment) to its dynamic Resource,
        without SKIPPED_KINDS.
    """
    dynamic_client.resources.invalidate_cache()
    kinds = {}
    for resource in dynamic_client.resources.search():
        if isinstance(resource, ResourceList) or not getattr(resource, "preferred", False):
            continue
        if not resource.namespaced or "list" not in (resource.verbs or []):
            continue
        kind = f"{resource.group or 'core'}/{resource.kind}"
        if kind not in SKIPPED_KINDS:
            kinds[kind] = resource
    return kinds

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
    workloads = [summarize(d, "apps/Deployment") for d in apps.list_namespaced_deployment(namespace).items]
    workloads += [summarize(s, "apps/StatefulSet") for s in apps.list_namespaced_stateful_set(namespace).items]
    workloads += [summarize(d, "apps/DaemonSet") for d in apps.list_namespaced_daemon_set(namespace).items]
    return workloads

def summarize(workload, kind):
    """The facts resilience checks read from a workload, in Kubernetes field names.

    Args:
        workload: a Deployment, StatefulSet or DaemonSet object from the Kubernetes API.
        kind: "apps/Deployment", "apps/StatefulSet" or "apps/DaemonSet", the same names as in
            get_inventory; objects in list responses do not carry their kind.

    Returns:
        A dict with the workload's replicas, pod labels, POD_FIELDS that are set, volumes
        (name and type), and every container with container_facts and env_facts.
    """
    template = workload.spec.template
    pod = serialize(template.spec)
    if kind == "apps/DaemonSet":
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

def get_inventory(namespace: str) -> dict[str, dict]:
    """List the names of every kind of object in a namespace, including custom resources (CRDs), keyed by group/Kind: core/Service, apps/Deployment, policy/PodDisruptionBudget.

    "kinds" has every kind with at least one object. A kind that is not in "kinds" and not in
    "unreadable" has no objects in this namespace.
    "unreadable" has the kinds that could not be read, with the reason; nothing is known about them.
    Never listed, by design: core/Secret, and objects that controllers create from other
    objects (core/Pod, apps/ReplicaSet, apps/ControllerRevision, core/Endpoints,
    discovery.k8s.io/EndpointSlice, core/Event, events.k8s.io/Event, coordination.k8s.io/Lease).
    """
    check_scope(namespace)
    kinds = {}
    unreadable = {}
    for kind, resource in sorted(listable_kinds().items()):
        try:
            items = dynamic_client.get(resource, namespace=namespace).items
        except ApiException as error:
            # Status and reason only: the error body can echo parts of the request or object.
            unreadable[kind] = f"{error.status} {error.reason}"
            continue
        if items:
            kinds[kind] = sorted(item.metadata.name for item in items)
    return {"kinds": kinds, "unreadable": unreadable}

