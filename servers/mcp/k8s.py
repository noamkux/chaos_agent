"""Kubernetes tools."""
from datetime import datetime, timedelta, timezone
from typing import Any

from kubernetes import client, config, dynamic
from kubernetes.client.exceptions import ApiException
from kubernetes.dynamic.resource import ResourceList

from mcp.server.mcpserver.exceptions import ToolError
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
    """The settings resilience checks read from one container (a dict, as in the workload's YAML)."""
    return {field: container[field] for field in CONTAINER_FIELDS if field in container}

def env_facts(container):
    """Names and sources of a container's environment variables. Values never leave this function."""
    # env: variables defined one by one, each with its own name.
    # Looks at where each value comes from: written in the spec (literal) or a reference (valueFrom).
    # Returns name and source only; var.value is never read, so a secret cannot be returned by mistake.
    env = []
    for var in container.get("env") or []:
        if "valueFrom" not in var:
            source = "literal"
        else:
            source = next(iter(var["valueFrom"]))
        env.append({"name": var["name"], "source": source})

    # envFrom: every key of a whole ConfigMap or Secret loaded as variables; no variable names here.
    # Looks at which kind of source is loaded and its name.
    # Returns the source kind and name only; the keys and values inside are not read.
    env_from = []
    for item in container.get("envFrom") or []:
        source = "secretRef" if "secretRef" in item else "configMapRef"
        env_from.append({"source": source, "name": item[source].get("name")})

    # Leave out empty lists, so a container without variables adds nothing to the output.
    facts = {"env": env, "envFrom": env_from}
    return {key: value for key, value in facts.items() if value}

def pod_template(obj):
    """The pod template of a workload of any kind, or None: spec.template (Deployments, StatefulSets,
    DaemonSets, Jobs, Argo Rollouts, most operators) or spec.jobTemplate.spec.template (CronJobs)."""
    spec = obj.get("spec") or {}
    template = spec.get("template") or (spec.get("jobTemplate") or {}).get("spec", {}).get("template")
    return template if isinstance(template, dict) and isinstance(template.get("spec"), dict) else None

def get_workloads(namespace: str) -> list[dict]:
    """List every workload in a namespace, of any kind with a pod template (Deployments, StatefulSets, DaemonSets, CronJobs, Argo Rollouts, an operator's custom resources), with the facts resilience checks read from each one.

    Fields use the Kubernetes names, as in the workload's YAML. A field that is not set is left
    out: a container with no livenessProbe field has no liveness probe.
    For a DaemonSet, replicas is the number of pods that should run, one per eligible node; a kind
    with no replica count (a CronJob) has no replicas field. A workload another one controls (a
    CronJob's Job) is left out: it is part of its owner.
    Environment variables show only the name and where the value comes from (literal,
    secretKeyRef, configMapKeyRef, fieldRef, resourceFieldRef), never the value; envFrom lists
    whole ConfigMaps or Secrets by name. Volumes show only name and type.
    Not included at all: container command, args and ports, and the values of any variable.
    """
        
    check_scope(namespace)
    workloads = []
    for kind, resource in sorted(listable_kinds().items()):
        try:
            items = dynamic_client.get(resource, namespace=namespace).items
        except ApiException:
            # get_inventory reports the kinds that cannot be read; nothing is known about them here.
            continue
        for item in items:
            obj = item.to_dict()
            # A workload another one controls (a CronJob's Job) is part of its owner, not one of its own.
            if any(o.get("controller") for o in obj["metadata"].get("ownerReferences") or []):
                continue
            if pod_template(obj) is not None:
                workloads.append(summarize(obj, kind))
    return workloads

def summarize(workload, kind):
    """The facts resilience checks read from a workload (a dict of any kind), in Kubernetes field names."""
    template = pod_template(workload)
    pod = template["spec"]
    spec, status = workload.get("spec") or {}, workload.get("status") or {}
    if kind == "apps/DaemonSet":
        # One pod per eligible node: there is no spec.replicas, the controller sets the count.
        replicas = status.get("desiredNumberScheduled")
        ready = status.get("numberReady")
    else:
        # None for a kind with no replica count (a CronJob); left out of the result.
        replicas = spec.get("replicas")
        ready = status.get("readyReplicas", 0) if replicas is not None else None
    summary = {
        "kind": kind,
        "name": workload["metadata"]["name"],
        "replicas": replicas,
        "readyReplicas": ready,
        "labels": (template.get("metadata") or {}).get("labels") or {},
        **{field: pod[field] for field in POD_FIELDS if field in pod},
        # Volume type only (emptyDir, persistentVolumeClaim, secret, ...), not its settings.
        "volumes": [{"name": v["name"], "type": next(key for key in v if key != "name")}
                    for v in pod.get("volumes", [])],
        "initContainers": [{**container_facts(c), **env_facts(c)} for c in pod.get("initContainers") or []],
        "containers": [{**container_facts(c), **env_facts(c)} for c in pod.get("containers") or []],
    }
    # Leave out empty lists and dicts, and a replica count the kind does not have; replicas 0 and
    # false values stay, they are facts.
    return {key: value for key, value in summary.items() if value not in ([], {}) and value is not None}

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


# ---------- inspect_workload (ADR-0038) ----------

EVENTS_LIMIT = 30
EVENT_MESSAGE_LIMIT = 500
SINCE_S_LIMITS = (60, 3600)
REDACTED = "[redacted]"
EXEC_PROBE_WITHHELD = "message withheld (exec probe output)"
PROBES = ("readinessProbe", "livenessProbe", "startupProbe")
# Literal env values shorter than this are not searched for: "true", "8080" or "info" would be
# replaced all over Kubernetes' own messages, and a secret that short is not one.
MIN_REDACTED_LENGTH = 6


def pod_containers(pod_spec):
    """Every container of a pod spec, init containers included."""
    return (pod_spec.get("initContainers") or []) + (pod_spec.get("containers") or [])


def literal_env_values(pod_spec):
    """The literal env values of a pod spec, only to be searched for in messages and replaced. They are
    never returned (ADR-0029). Numbers are left out: they appear in messages for other reasons (ports,
    counts) and are not secrets."""
    values = set()
    for container in pod_containers(pod_spec):
        for var in container.get("env") or []:
            value = var.get("value")
            if isinstance(value, str) and len(value) >= MIN_REDACTED_LENGTH and not value.isdigit():
                values.add(value)
    return values


def exec_probe_containers(pod_spec):
    """The names of the containers with at least one exec probe: their probe failures carry the output of
    a command run inside the container, which can print anything it can read."""
    return {c["name"] for c in pod_containers(pod_spec) if any("exec" in (c.get(p) or {}) for p in PROBES)}


def redact(text, secrets):
    """A message with every known literal env value replaced, cut at EVENT_MESSAGE_LIMIT characters.
    Redacting comes first, so a value cut in two by the limit is already gone."""
    text = text or ""
    for secret in sorted(secrets, key=len, reverse=True):
        text = text.replace(secret, REDACTED)
    if len(text) > EVENT_MESSAGE_LIMIT:
        text = text[:EVENT_MESSAGE_LIMIT] + "... (truncated)"
    return text


def container_of(field_path):
    """The container an event is about, from its involvedObject.fieldPath: spec.containers{server} gives
    server. None when the event is about the whole object."""
    if field_path and "{" in field_path and field_path.endswith("}"):
        return field_path[field_path.index("{") + 1:-1]
    return None


def event_message(event, secrets, exec_containers):
    """The message of an event as the agent may see it. A probe failure of a container with an exec probe
    is withheld whole; when the container is not named, any exec probe in the workload withholds it."""
    if event.get("reason") == "Unhealthy" and exec_containers:
        container = container_of((event.get("involvedObject") or {}).get("fieldPath"))
        if container is None or container in exec_containers:
            return EXEC_PROBE_WITHHELD
    return redact(event.get("message"), secrets)


def event_time(event):
    """When an event last happened, as an ISO string: lastTimestamp, or eventTime for events written
    through events.k8s.io, or firstTimestamp."""
    return event.get("lastTimestamp") or event.get("eventTime") or event.get("firstTimestamp") or ""


def event_matches(event, workload_kind, workload_name, owned_names, pod_prefixes):
    """True if an event is about the workload, an object it owns (its ReplicaSets), or one of its pods,
    including pods already deleted, matched by the name prefix their owner gives them."""
    involved = event.get("involvedObject") or {}
    kind, name = involved.get("kind"), involved.get("name") or ""
    if kind == workload_kind.split("/")[-1] and name == workload_name:
        return True
    if name in owned_names:
        return True
    return kind == "Pod" and any(name.startswith(prefix) for prefix in pod_prefixes)


def event_facts(event, secrets, exec_containers):
    """One event for the agent: when, Normal or Warning, why, about which object, how many times, and its
    message after redaction."""
    involved = event.get("involvedObject") or {}
    facts = {"time": event_time(event), "type": event.get("type"), "reason": event.get("reason"),
             "object": f"{involved.get('kind')}/{involved.get('name')}", "count": event.get("count") or 1,
             "message": event_message(event, secrets, exec_containers)}
    return {key: value for key, value in facts.items() if value not in (None, "")}


def rollout_facts(obj, secrets):
    """How a workload rolls out and where its rollout stands: the update strategy, the replica counts of
    its status, its conditions, and whether the controller has seen the latest change."""
    spec, status, metadata = obj.get("spec") or {}, obj.get("status") or {}, obj.get("metadata") or {}
    facts = {
        "strategy": spec.get("strategy") or spec.get("updateStrategy"),
        "minReadySeconds": spec.get("minReadySeconds"),
        "progressDeadlineSeconds": spec.get("progressDeadlineSeconds"),
        "replicas": spec.get("replicas"),
        **{field: status.get(field) for field in ("updatedReplicas", "readyReplicas", "availableReplicas",
                                                    "unavailableReplicas")},
        "generation": metadata.get("generation"),
        "observedGeneration": status.get("observedGeneration"),
        "conditions": [{"type": c.get("type"), "status": c.get("status"), "reason": c.get("reason"),
                        "message": redact(c.get("message"), secrets)} for c in status.get("conditions") or []],
    }
    return {key: value for key, value in facts.items() if value not in (None, [], {})}


def pod_state(pod):
    """One pod for the agent: node, phase, whether it is ready or being deleted, and per container whether
    it is ready, its restarts, its current state and its last termination. Reasons and exit codes only:
    a container's own messages can carry the application's output, so they are never returned."""
    status, metadata = pod.get("status") or {}, pod.get("metadata") or {}
    ready = next((c.get("status") == "True" for c in status.get("conditions") or [] if c.get("type") == "Ready"),
                 False)
    containers = []
    for container in (status.get("initContainerStatuses") or []) + (status.get("containerStatuses") or []):
        state = container.get("state") or {}
        current = next(iter(state), None)
        facts = {"name": container.get("name"), "ready": container.get("ready"),
                 "restarts": container.get("restartCount", 0), "state": current,
                 "reason": (state.get(current) or {}).get("reason") if current else None}
        last = (container.get("lastState") or {}).get("terminated")
        if last:
            facts["last_terminated"] = {key: last.get(key) for key in ("reason", "exitCode", "finishedAt")
                                        if last.get(key) is not None}
        containers.append({key: value for key, value in facts.items() if value is not None})
    facts = {"name": metadata.get("name"), "node": (pod.get("spec") or {}).get("nodeName"),
             "phase": status.get("phase"), "ready": ready, "deleting": bool(metadata.get("deletionTimestamp")),
             "containers": containers}
    return {key: value for key, value in facts.items() if value is not None}


def inspect_workload(namespace: str, kind: str, name: str, since_s: int = 600) -> dict[str, Any]:
    """What Kubernetes did with one workload: how it rolls out and where its rollout stands, the state of its pods, and its recent events. Use it after an experiment broke or surprised you, to find the mechanism.

    kind is group/Kind, as in the workload list (apps/Deployment, argoproj.io/Rollout). since_s is how
    far back events are read, 60 to 3600 seconds (default 600); Kubernetes keeps events for about an
    hour.
    "rollout": the update strategy (maxSurge and maxUnavailable for a Deployment), minReadySeconds,
    progressDeadlineSeconds, the replica counts of the status, its conditions, and generation against
    observedGeneration (different while a rollout is still being taken in).
    "pods": every pod the workload owns now: node, phase, ready, deleting, and per container ready,
    restarts, current state with its reason, and the reason, exit code and time of its last termination.
    "events": up to 30 of the most recent events on the workload, its ReplicaSets and its pods (also
    pods already deleted), oldest first: time, type, reason, object, count and message. Messages are cut
    at 500 characters; known env values in them are replaced by [redacted]; the probe failures of a
    container with an exec probe have their message withheld, since it is the output of a command run
    inside the container. Container messages and logs are never returned.
    """
    check_scope(namespace)
    if kind in SKIPPED_KINDS:
        raise ToolError(f"kind '{kind}' is not a workload")
    if not isinstance(since_s, int) or not SINCE_S_LIMITS[0] <= since_s <= SINCE_S_LIMITS[1]:
        raise ToolError(f"since_s must be between {SINCE_S_LIMITS[0]} and {SINCE_S_LIMITS[1]} seconds")
    resource = namespaced_kinds().get(kind)
    if resource is None:
        raise ToolError(f"kind '{kind}' is not a namespaced kind served by this cluster")
    try:
        obj = dynamic_client.get(resource, name=name, namespace=namespace).to_dict()
    except ApiException as error:
        raise ToolError(f"read {kind} {name}: {error.status} {error.reason}")
    template = pod_template(obj)
    if template is None:
        raise ToolError(f"{kind} {name} has no pod template")
    pod_spec = template["spec"]
    secrets = literal_env_values(pod_spec)
    exec_containers = exec_probe_containers(pod_spec)

    owners_cache = {}
    pods = [serialize(p) for p in core.list_namespaced_pod(namespace).items
            if top_owner(namespace, p, owners_cache) == (kind, name)]
    # The ReplicaSets this workload controls (a Deployment, an Argo Rollout): their names are the prefix
    # of every pod they created, including pods already deleted by a rollout.
    owned = [rs.metadata.name for rs in apps.list_namespaced_replica_set(namespace).items
             if (controller_of(serialize(rs.metadata).get("ownerReferences")) or (None, None, None))[1:]
             == (kind.split("/")[-1], name)]
    pod_prefixes = [f"{rs}-" for rs in owned] or [f"{name}-"]

    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=since_s)).isoformat()
    events = [serialize(e) for e in core.list_namespaced_event(namespace).items]
    events = [e for e in events if event_matches(e, kind, name, set(owned), pod_prefixes)
              and event_time(e) >= cutoff[:19]]
    events = sorted(events, key=event_time)[-EVENTS_LIMIT:]
    return {"rollout": rollout_facts(obj, secrets),
            "pods": [pod_state(p) for p in sorted(pods, key=lambda p: p["metadata"]["name"])],
            "events": [event_facts(e, secrets, exec_containers) for e in events]}
