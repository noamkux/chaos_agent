"""The disrupt server's guards without a cluster: forbidden fields, what a snapshot keeps, and the node
actions' checks, evictions and restore."""
from types import SimpleNamespace as NS

import pytest
from kubernetes.client.exceptions import ApiException
from mcp.server.mcpserver.exceptions import ToolError

import disrupt


@pytest.mark.parametrize("patch, found", [
    ({"spec": {"replicas": 0}}, set()),
    ({"spec": {"template": {"spec": {"containers": [{"name": "web", "image": "evil"}]}}}}, {"image"}),
    ({"spec": {"template": {"spec": {"hostNetwork": True, "volumes": [{"hostPath": {"path": "/"}}]}}}},
     {"hostNetwork", "volumes"}),
    ({"spec": {"template": {"spec": {"containers": [{"name": "web", "resources": {"limits": {"cpu": "20m"}},
                                                     "env": [{"name": "A", "value": "b"}]}]}}}}, set()),
])
def test_forbidden_fields(patch, found):
    assert disrupt.forbidden_fields(patch) == found


def test_clean_keeps_what_can_be_written_back():
    obj = {"metadata": {"name": "web", "labels": {"a": "b"}, "uid": "1", "resourceVersion": "7",
                        "managedFields": [], "creationTimestamp": "x", "generation": 3},
           "spec": {"replicas": 2}, "status": {"readyReplicas": 2}}
    assert disrupt.clean(obj) == {"metadata": {"name": "web", "labels": {"a": "b"}}, "spec": {"replicas": 2}}


def node(labels=None, taints=None):
    return NS(metadata=NS(labels=labels or {}, resource_version="7"),
              spec=NS(unschedulable=None, taints=taints))


class SimpleCluster:
    """What the cluster fixture holds: the nodes, and every patch sent to them."""
    def __init__(self, nodes, patches):
        self.nodes, self.patches = nodes, patches


@pytest.fixture
def cluster(monkeypatch):
    """Nodes a1 (a worker) and cp (control-plane); the chaos agent's own pod runs on a2."""
    nodes = {"a1": node({"topology.kubernetes.io/zone": "zone-a"}), "a2": node(),
             "cp": node({"node-role.kubernetes.io/control-plane": ""})}
    patches = []

    def read_node(name):
        if name not in nodes:
            raise ApiException(status=404, reason="Not Found")
        return nodes[name]

    monkeypatch.setattr(disrupt.core, "read_node", read_node)
    monkeypatch.setattr(disrupt.core, "patch_node", lambda name, body: patches.append((name, body)))
    monkeypatch.setattr(disrupt.core, "list_namespaced_pod",
                        lambda ns, field_selector: NS(items=[1] if field_selector.endswith("a2") else []))
    return SimpleCluster(nodes, patches)


@pytest.mark.parametrize("mode, node_name, whole, message", [
    ("none", "a1", False, "not enabled"),
    ("scope_only", "a1", True, "whole_node"),
    ("whole_node", "cp", False, "control-plane"),
    # Evicting the agent's own servers would leave nothing to restore the node.
    ("whole_node", "a2", True, "runs the chaos agent itself"),
])
def test_node_guards(cluster, monkeypatch, mode, node_name, whole, message):
    monkeypatch.setattr(disrupt, "NODE_ACTIONS", mode)
    with pytest.raises(ToolError, match=message):
        disrupt.node_to_fail(node_name, whole_node=whole)


def test_cordon_records_the_state_before(cluster, monkeypatch):
    monkeypatch.setattr(disrupt, "NODE_ACTIONS", "scope_only")
    assert disrupt.cordon_node("a1") == {"node": "a1", "was_unschedulable": False}
    assert cluster.patches == [("a1", {"spec": {"unschedulable": True}, "metadata": {"resourceVersion": "7"}})]


def test_restore_removes_only_our_taints(cluster, monkeypatch):
    cluster.nodes["a1"].spec.taints = [NS(key="dedicated", effect="NoSchedule", value="gpu", time_added=None),
                                       NS(key="chaos-agent.io/node-lost", effect="NoExecute", value=None, time_added=None)]
    monkeypatch.setattr(disrupt, "serialize", lambda t: {k: v for k, v in vars(t).items() if v is not None})
    assert disrupt.restore_node("a1", was_unschedulable=False)["taints_removed"] == 1
    assert cluster.patches[-1][1]["spec"] == {"unschedulable": False,
                                              "taints": [{"key": "dedicated", "effect": "NoSchedule", "value": "gpu"}]}


def test_restore_of_a_removed_node_is_done(cluster):
    # An autoscaler removed the drained node: nothing is left to undo, and the run must not stop.
    assert disrupt.restore_node("gone", was_unschedulable=False) == {"node": "gone", "node_gone": True}


def test_evict_skips_daemonsets_and_static_pods_and_reports_pdbs(cluster, monkeypatch):
    monkeypatch.setattr(disrupt, "NODE_ACTIONS", "scope_only")

    def pod(name, owner=None, annotations=None):
        return NS(metadata=NS(namespace="shop", name=name, annotations=annotations, deletion_timestamp=None,
                              owner_references=[NS(kind=owner, controller=True)] if owner else None))

    pods = [pod("web-1", "ReplicaSet"), pod("web-2", "ReplicaSet"), pod("agent", "DaemonSet"),
            pod("static", annotations={"kubernetes.io/config.mirror": "x"})]
    monkeypatch.setattr(disrupt.core, "list_namespaced_pod", lambda ns, field_selector: NS(items=pods))

    def evict(name, namespace, body):
        if name == "web-2":
            raise ApiException(status=429, reason="Too Many Requests")

    monkeypatch.setattr(disrupt.core, "create_namespaced_pod_eviction", evict)
    result = disrupt.evict_pods("a1", ["shop"])
    assert result["evicted"] == ["shop/web-1"]
    assert result["blocked_by_pdb"] == ["shop/web-2"]
    with pytest.raises(ToolError, match="out of scope"):
        disrupt.evict_pods("a1", ["kube-system"])
