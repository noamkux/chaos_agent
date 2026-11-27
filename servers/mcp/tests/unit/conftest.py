"""Lets the server's modules be imported with no cluster. k8s.py loads a kubeconfig the moment it is
imported, and scope.py reads ALLOWED_NAMESPACES: both get test values here, before any test module
imports them. The kubeconfig points at nothing; a test that reaches the API by mistake fails to connect,
and never touches a real cluster, even on a laptop whose own kubeconfig is set.
The dynamic client asks the API server what it serves the moment it is created, in k8s.py; here it is
replaced by an empty stand-in, and a test that needs it sets what it returns."""
import os
import tempfile
from types import SimpleNamespace

KUBECONFIG = """apiVersion: v1
kind: Config
clusters: [{name: none, cluster: {server: "https://127.0.0.1:1"}}]
users: [{name: none, user: {token: none}}]
contexts: [{name: none, context: {cluster: none, user: none}}]
current-context: none
"""

_file = tempfile.NamedTemporaryFile("w", suffix=".kubeconfig", delete=False)
_file.write(KUBECONFIG)
_file.close()
# Before kubernetes is imported: it reads KUBECONFIG once, when it loads.
os.environ["KUBECONFIG"] = _file.name
os.environ.pop("KUBERNETES_SERVICE_HOST", None)
os.environ["ALLOWED_NAMESPACES"] = "shop"

from kubernetes import dynamic  # noqa: E402

dynamic.DynamicClient = lambda api_client: SimpleNamespace()
