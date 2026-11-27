"""Disrupt tools: change the system under test, always after a snapshot that can restore it. Called only by the orchestrator."""
import base64
import json
import os
import uuid
from typing import Any

from kubernetes.client.exceptions import ApiException
from mcp.server.mcpserver.exceptions import ToolError

from kubernetes import client

from k8s import CONTROL_PLANE_LABEL, core, dynamic_client, namespaced_kinds, serialize
from scope import check_scope

# Kinds that can never be changed: data that cannot be restored, and credentials and permissions.
# Everything else, custom resources included, may be patched.
DENIED_KINDS = {
    "core/Secret", "core/PersistentVolumeClaim", "core/ServiceAccount",
    "rbac.authorization.k8s.io/Role", "rbac.authorization.k8s.io/RoleBinding",
}

# Fields a patch may never contain, at any depth: they would run other code or gain privileges.
FORBIDDEN_FIELDS = {
    "image", "command", "args", "securityContext", "serviceAccountName", "serviceAccount",
    "automountServiceAccountToken", "hostNetwork", "hostPID", "hostIPC", "volumes",
}

# Snapshots hold full objects, env values included, so they stay in Kubernetes as Secrets in the
# server's own namespace: never in the database and never shown to the agent.
SNAPSHOT_NAMESPACE = os.environ.get("POD_NAMESPACE", "chaos-system")
SNAPSHOT_LABEL = "chaos-agent.io/snapshot"


def resource_for(kind):
    """The dynamic resource of any namespaced kind that is not denied, or a ToolError."""
    if kind in DENIED_KINDS:
        raise ToolError(f"kind '{kind}' can never be changed")
    resource = namespaced_kinds().get(kind)
    if resource is None:
        raise ToolError(f"kind '{kind}' is not a namespaced kind served by this cluster")
    return resource


def api_error(action, error):
    """A ToolError with the status and reason only; the body can echo parts of the object."""
    return ToolError(f"{action}: {error.status} {error.reason}")


def forbidden_fields(value):
    """Every forbidden field name found anywhere in a patch."""
    found = set()
    if isinstance(value, dict):
        for key, inner in value.items():
            if key in FORBIDDEN_FIELDS:
                found.add(key)
            found |= forbidden_fields(inner)
    elif isinstance(value, list):
        for inner in value:
            found |= forbidden_fields(inner)
    return found


def clean(obj):
    """The object as it can be written back: without status and server-managed metadata."""
    obj.pop("status", None)
    for field in ("resourceVersion", "uid", "creationTimestamp", "generation", "managedFields", "selfLink"):
        obj["metadata"].pop(field, None)
    return obj


def snapshot_resource(namespace: str, kind: str, name: str) -> dict[str, Any]:
    """Save the full object before it is changed. Returns the snapshot id and the resourceVersion the patch must match."""
    check_scope(namespace)
    resource = resource_for(kind)
    try:
        obj = dynamic_client.get(resource, name=name, namespace=namespace).to_dict()
    except ApiException as error:
        raise api_error(f"read {kind} {name}", error)
    version = obj["metadata"]["resourceVersion"]
    snapshot_id = f"chaos-undo-{uuid.uuid4().hex[:12]}"
    body = {"metadata": {"name": snapshot_id, "labels": {SNAPSHOT_LABEL: "true"}},
            "type": "Opaque",
            "stringData": {"kind": kind, "object": json.dumps(clean(obj))}}
    try:
        core.create_namespaced_secret(SNAPSHOT_NAMESPACE, body)
    except ApiException as error:
        raise api_error("save snapshot", error)
    return {"snapshot_id": snapshot_id, "resource_version": version}


def patch_resource(namespace: str, kind: str, name: str, patch: dict[str, Any],
                   resource_version: str) -> dict[str, Any]:
    """Apply a strategic merge patch, only if the object has not changed since its snapshot."""
    check_scope(namespace)
    resource = resource_for(kind)
    found = forbidden_fields(patch)
    if found:
        raise ToolError(f"a patch may not contain {sorted(found)}")
    if set(patch.get("metadata", {})) - {"labels", "annotations"}:
        raise ToolError("in metadata, a patch may change only labels and annotations")
    # resourceVersion in the patch is a precondition: the API server rejects it if the object changed.
    body = {**patch, "metadata": {**patch.get("metadata", {}), "resourceVersion": resource_version}}
    try:
        result = dynamic_client.patch(resource, body=body, name=name, namespace=namespace,
                                      content_type="application/strategic-merge-patch+json")
    except ApiException as error:
        if error.status != 415:
            raise api_error(f"patch {kind} {name}", error)
        # Custom resources do not support strategic merge; a JSON merge patch replaces lists whole.
        try:
            result = dynamic_client.patch(resource, body=body, name=name, namespace=namespace,
                                          content_type="application/merge-patch+json")
        except ApiException as error:
            raise api_error(f"patch {kind} {name}", error)
    return {"kind": kind, "name": name, "resource_version": result.metadata.resourceVersion}


def restore_snapshot(snapshot_id: str) -> dict[str, Any]:
    """Put an object back exactly as it was in its snapshot, then delete the snapshot."""
    try:
        secret = core.read_namespaced_secret(snapshot_id, SNAPSHOT_NAMESPACE)
    except ApiException as error:
        raise api_error(f"read snapshot {snapshot_id}", error)
    if (secret.metadata.labels or {}).get(SNAPSHOT_LABEL) != "true":
        raise ToolError(f"'{snapshot_id}' is not a snapshot")
    kind = base64.b64decode(secret.data["kind"]).decode()
    obj = json.loads(base64.b64decode(secret.data["object"]))
    namespace, name = obj["metadata"]["namespace"], obj["metadata"]["name"]
    check_scope(namespace)
    resource = resource_for(kind)
    try:
        current = dynamic_client.get(resource, name=name, namespace=namespace)
        obj["metadata"]["resourceVersion"] = current.metadata.resourceVersion
        dynamic_client.replace(resource, body=obj, name=name, namespace=namespace)
        core.delete_namespaced_secret(snapshot_id, SNAPSHOT_NAMESPACE)
    except ApiException as error:
        raise api_error(f"restore {kind} {name}", error)
    return {"restored": f"{kind} {name}", "namespace": namespace}


def delete_pod(namespace: str, kind: str, name: str) -> dict[str, Any]:
    """Delete one running pod of a workload, found by the workload's selector. Its controller replaces it."""
    check_scope(namespace)
    resource = resource_for(kind)
    try:
        workload = dynamic_client.get(resource, name=name, namespace=namespace).to_dict()
        labels = (workload.get("spec", {}).get("selector") or {}).get("matchLabels")
        if not labels:
            raise ToolError(f"{kind} {name} has no spec.selector.matchLabels to find its pods")
        selector = ",".join(f"{key}={value}" for key, value in labels.items())
        pods = core.list_namespaced_pod(namespace, label_selector=selector).items
        running = sorted(pod.metadata.name for pod in pods if pod.status.phase == "Running")
        if not running:
            raise ToolError(f"{kind} {name} has no running pod")
        core.delete_namespaced_pod(running[0], namespace)
    except ApiException as error:
        raise api_error(f"delete a pod of {kind} {name}", error)
    return {"deleted_pod": running[0], "running_before": len(running)}


# Node actions, set by the cluster admin in the chart values (mcp.levels.disrupt.nodeActions):
# none, scope_only (cordon, and evict only pods in the allowed namespaces), or whole_node (evict every
# pod on the node, and the lost-node taint, which cannot be limited to a namespace).
NODE_ACTIONS = os.environ.get("NODE_ACTIONS", "none")
# Every taint this server adds starts with this prefix, and the admission policy allows it to add or
# remove no other taint.
TAINT_PREFIX = "chaos-agent.io/"
# NoExecute removes, at once, every pod without a matching toleration: a node lost without warning.
LOST_TAINT = {"key": TAINT_PREFIX + "node-lost", "effect": "NoExecute"}


def node_to_fail(name, whole_node):
    """The node, after the checks every node action needs. Refuses a control-plane node, and for an
    action that reaches every pod on the node, a node where the chaos agent itself runs: if its
    servers or database were evicted, nothing would be left to restore the node."""
    if NODE_ACTIONS not in ("scope_only", "whole_node"):
        raise ToolError("node actions are not enabled for this server (mcp.levels.disrupt.nodeActions)")
    if whole_node and NODE_ACTIONS != "whole_node":
        raise ToolError("this action reaches every pod on the node, which needs nodeActions: whole_node")
    try:
        node = core.read_node(name)
        if CONTROL_PLANE_LABEL in (node.metadata.labels or {}):
            raise ToolError(f"node {name} is a control-plane node")
        if whole_node:
            ours = core.list_namespaced_pod(SNAPSHOT_NAMESPACE, field_selector=f"spec.nodeName={name}").items
            if ours:
                raise ToolError(f"node {name} runs the chaos agent itself ({SNAPSHOT_NAMESPACE})")
    except ApiException as error:
        raise api_error(f"read node {name}", error)
    return node


def cordon_node(node: str) -> dict[str, Any]:
    """Mark a node unschedulable, so no new pod lands on it. Returns whether it already was, for the restore."""
    current = node_to_fail(node, whole_node=False)
    was_unschedulable = bool(current.spec.unschedulable)
    try:
        core.patch_node(node, {"spec": {"unschedulable": True},
                               "metadata": {"resourceVersion": current.metadata.resource_version}})
    except ApiException as error:
        raise api_error(f"cordon {node}", error)
    return {"node": node, "was_unschedulable": was_unschedulable}


def taint_node_lost(node: str) -> dict[str, Any]:
    """Add the lost-node NoExecute taint: every pod without a matching toleration is removed at once,
    from every namespace, and PodDisruptionBudgets are not consulted, as when a node dies."""
    current = node_to_fail(node, whole_node=True)
    taints = [serialize(t) for t in current.spec.taints or []]
    if not any(t["key"] == LOST_TAINT["key"] for t in taints):
        taints.append(LOST_TAINT)
    try:
        # Taints have no merge key: the list is sent whole, with resourceVersion as a precondition.
        core.patch_node(node, {"spec": {"taints": taints},
                               "metadata": {"resourceVersion": current.metadata.resource_version}})
    except ApiException as error:
        raise api_error(f"taint {node}", error)
    return {"node": node, "taint": f"{LOST_TAINT['key']}:{LOST_TAINT['effect']}"}


def evict_pods(node: str, namespaces: list[str] | None = None) -> dict[str, Any]:
    """Evict the pods on a node through the Eviction API, as kubectl drain does: PodDisruptionBudgets are
    respected, and a pod they protect is reported as blocked, not retried. Only the pods in the given
    namespaces, or every pod on the node when namespaces is left out (needs nodeActions: whole_node).
    DaemonSet pods and static pods are left alone, as kubectl drain leaves them."""
    node_to_fail(node, whole_node=namespaces is None)
    for namespace in namespaces or []:
        check_scope(namespace)
    selector = f"spec.nodeName={node}"
    try:
        if namespaces is None:
            pods = core.list_pod_for_all_namespaces(field_selector=selector).items
        else:
            pods = [p for ns in namespaces for p in core.list_namespaced_pod(ns, field_selector=selector).items]
    except ApiException as error:
        raise api_error(f"list pods on {node}", error)
    result = {"node": node, "evicted": [], "blocked_by_pdb": [], "failed": {}}
    for pod in pods:
        owner = next((o for o in pod.metadata.owner_references or [] if o.controller), None)
        static = "kubernetes.io/config.mirror" in (pod.metadata.annotations or {})
        if (owner and owner.kind == "DaemonSet") or static or pod.metadata.deletion_timestamp:
            continue
        name = f"{pod.metadata.namespace}/{pod.metadata.name}"
        eviction = client.V1Eviction(metadata=client.V1ObjectMeta(name=pod.metadata.name,
                                                                  namespace=pod.metadata.namespace))
        try:
            core.create_namespaced_pod_eviction(pod.metadata.name, pod.metadata.namespace, eviction)
            result["evicted"].append(name)
        except ApiException as error:
            if error.status == 429:
                result["blocked_by_pdb"].append(name)
            else:
                result["failed"][name] = f"{error.status} {error.reason}"
    return result


def restore_node(node: str, was_unschedulable: bool) -> dict[str, Any]:
    """Undo a node action: remove every taint this server added, and make the node schedulable again
    unless it was already unschedulable before. Works whatever nodeActions is, so a change can always
    be undone. Evicted pods do not move back: only a descheduler moves running pods."""
    try:
        current = core.read_node(node)
    except ApiException as error:
        if error.status == 404:
            # An autoscaler (Karpenter, Cluster Autoscaler) removed the drained node: nothing is left to undo.
            return {"node": node, "node_gone": True}
        raise api_error(f"restore {node}", error)
    try:
        taints = [serialize(t) for t in current.spec.taints or []]
        kept = [t for t in taints if not t["key"].startswith(TAINT_PREFIX)]
        core.patch_node(node, {"spec": {"unschedulable": was_unschedulable, "taints": kept or None},
                               "metadata": {"resourceVersion": current.metadata.resource_version}})
    except ApiException as error:
        raise api_error(f"restore {node}", error)
    return {"node": node, "unschedulable": was_unschedulable, "taints_removed": len(taints) - len(kept)}
