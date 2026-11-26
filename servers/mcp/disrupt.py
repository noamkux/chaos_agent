"""Disrupt tools: change the system under test, always after a snapshot that can restore it. Called only by the orchestrator."""
import base64
import json
import os
import uuid
from typing import Any

from kubernetes.client.exceptions import ApiException
from mcp.server.mcpserver.exceptions import ToolError

from k8s import core, dynamic_client, namespaced_kinds
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