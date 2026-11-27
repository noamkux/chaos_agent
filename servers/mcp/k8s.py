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

def namespaced_kinds():
    """Every namespaced kind the API server can list, at its preferred version, keyed by group/Kind."""
    dynamic_client.resources.invalidate_cache()
    kinds = {}
    for resource in dynamic_client.resources.search():
        if isinstance(resource, ResourceList) or not getattr(resource, "preferred", False):
            continue
        if not resource.namespaced or "list" not in (resource.verbs or []):
            continue
        kinds[f"{resource.group or 'core'}/{resource.kind}"] = resource
    return kinds

def listable_kinds():
    """Every namespaced kind the inventory lists: namespaced_kinds() without SKIPPED_KINDS."""
    return {kind: resource for kind, resource in namespaced_kinds().items() if kind not in SKIPPED_KINDS}

def container_facts(container):
    """The settings resilience checks read from one container, as in the workload's YAML."""
    data = serialize(container)
    return {field: data[field] for field in CONTAINER_FIELDS if field in data}

def env_facts(container):
    """Names and sources of a container's environment variables. Values never leave this function."""
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
    """The facts resilience checks read from a workload, in Kubernetes field names."""
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


# The standard labels every cloud provider and kind set on nodes.
ZONE_LABEL = "topology.kubernetes.io/zone"
CONTROL_PLANE_LABEL = "node-role.kubernetes.io/control-plane"

def node_facts(node):
    """A node's zone and whether pods can run on it."""
    labels = node.metadata.labels or {}
    ready = next((c.status == "True" for c in node.status.conditions or [] if c.type == "Ready"), False)
    return {
        "name": node.metadata.name,
        "zone": labels.get(ZONE_LABEL),
        "control_plane": CONTROL_PLANE_LABEL in labels,
        "schedulable": not node.spec.unschedulable,
        "ready": ready,
        "taints": sorted(f"{t.key}:{t.effect}" for t in node.spec.taints or []),
    }

def kind_of(api_version, kind):
    """group/Kind from an apiVersion and a kind: apps/v1 and Deployment give apps/Deployment, v1 and Pod give core/Pod."""
    group = api_version.rpartition("/")[0] or "core"
    return f"{group}/{kind}"

def controller_of(references):
    """The controlling owner in a list of ownerReferences, as (apiVersion, kind, name), or None.
    Takes the dicts of an object read with the dynamic client (camelCase keys)."""
    reference = next((r for r in references or [] if r.get("controller")), None)
    return reference and (reference["apiVersion"], reference["kind"], reference["name"])

def top_owner(namespace, pod, owners_cache):
    """The workload at the top of a pod's ownerReferences, as (group/Kind, name): the object that no
    controller owns. Works for any controller: a Deployment through its ReplicaSet, an Argo Rollout,
    a CronJob through its Job, an operator's custom resource. A pod with no owner is its own workload.
    If an owner cannot be read, the chain stops at the last owner that is known."""
    reference = controller_of(serialize(pod.metadata).get("ownerReferences"))
    if reference is None:
        return "core/Pod", pod.metadata.name
    while True:
        if reference not in owners_cache:
            api_version, kind, name = reference
            try:
                resource = dynamic_client.resources.get(api_version=api_version, kind=kind)
                owner = dynamic_client.get(resource, name=name, namespace=namespace).to_dict()
                owners_cache[reference] = controller_of(owner["metadata"].get("ownerReferences"))
            except Exception:
                # An owner we cannot read (no permission, a kind the API no longer serves) ends the chain.
                owners_cache[reference] = None
        parent = owners_cache[reference]
        if parent is None:
            api_version, kind, name = reference
            return kind_of(api_version, kind), name
        reference = parent

def get_placement(namespace: str) -> dict[str, list]:
    """Where the workloads of a namespace run: every node of the cluster with its zone, and the node and zone of every pod of each workload.

    "nodes" has every node: its zone (from the topology.kubernetes.io/zone label, null if the node has
    none), whether it is a control-plane node, whether new pods can be scheduled on it, whether it is
    Ready, and its taints as key:effect. If nodes cannot be read, "nodes" is empty and
    "nodes_unreadable" has the reason.
    "workloads" has every workload with pods in the namespace, found by following each pod's
    ownerReferences to the top (apps/Deployment, argoproj.io/Rollout, batch/CronJob, any operator's
    kind; core/Pod for a pod no controller owns), and for each pod its node, zone and phase. A pod
    with node null is not scheduled yet (Pending).
    """
    check_scope(namespace)
    result = {"nodes": [], "workloads": []}
    try:
        nodes = [node_facts(n) for n in core.list_node().items]
    except ApiException as error:
        nodes = []
        result["nodes_unreadable"] = f"{error.status} {error.reason}"
    result["nodes"] = sorted(nodes, key=lambda n: n["name"])
    zone_of = {n["name"]: n["zone"] for n in nodes}

    owners_cache = {}
    pods_of = {}
    for pod in core.list_namespaced_pod(namespace).items:
        workload = top_owner(namespace, pod, owners_cache)
        node = pod.spec.node_name
        pods_of.setdefault(workload, []).append(
            {"node": node, "zone": zone_of.get(node), "phase": pod.status.phase})
    result["workloads"] = [{"kind": kind, "name": name,
                            "pods": sorted(pods, key=lambda p: (p["node"] or "", p["phase"]))}
                           for (kind, name), pods in sorted(pods_of.items())]
    return result
