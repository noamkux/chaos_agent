"""Run inputs: the application's profile (target.yaml) and the Rules of Engagement, checked before a run starts."""
from pathlib import Path

import yaml

LEVELS = ["observe", "probe", "disrupt"]
METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"}

# Used when the RoE leaves out deny_groups. Their controllers act outside the namespace or the cluster,
# where a snapshot cannot restore anything: GitOps, cloud resources, backups, database operators.
DEFAULT_DENY_GROUPS = ["argoproj.io", "fluxcd.io", "services.k8s.aws", "crossplane.io", "upbound.io",
                       "cnrm.cloud.google.com", "azure.com", "velero.io", "cnpg.io"]

# The safe value of every optional RoE setting: an RoE that says nothing allows nothing extra.
ROE_DEFAULTS = {"allow_write_journeys": False, "allow_node_actions": False,
                "max_experiments": 10, "max_hold_s": 60}


def load_yaml(path):
    """Read a YAML file that must hold a mapping."""
    data = yaml.safe_load(Path(path).read_text())
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a mapping at the top level")
    return data


def positive_int(value):
    """True for an int above 0; bool is excluded, because in Python True is an int."""
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def load_roe(path):
    """Load the Rules of Engagement, fill in the safe defaults, and reject anything malformed."""
    roe = {**ROE_DEFAULTS, **load_yaml(path)}
    namespaces = (roe.get("scope") or {}).get("namespaces")
    if not namespaces or not all(isinstance(n, str) and n for n in namespaces):
        raise ValueError(f"{path}: scope.namespaces must list at least one namespace")
    if roe.get("max_level") not in LEVELS:
        raise ValueError(f"{path}: max_level must be one of {LEVELS}")
    for key in ("allow_write_journeys", "allow_node_actions"):
        if not isinstance(roe[key], bool):
            raise ValueError(f"{path}: {key} must be true or false")
    for key in ("max_experiments", "max_hold_s"):
        if not positive_int(roe[key]):
            raise ValueError(f"{path}: {key} must be a whole number above 0")
    roe.setdefault("deny_groups", DEFAULT_DENY_GROUPS)
    if not isinstance(roe["deny_groups"], list) or not all(isinstance(g, str) for g in roe["deny_groups"]):
        raise ValueError(f"{path}: deny_groups must be a list of API groups")
    return roe


def load_target(path):
    """Load the application's profile and reject anything a run could not use."""
    target = load_yaml(path)
    entrypoint = target.get("entrypoint") or {}
    if not isinstance(entrypoint.get("service"), str) or not positive_int(entrypoint.get("port")):
        raise ValueError(f"{path}: entrypoint needs a service name and a port")
    journeys = target.get("journeys")
    if not isinstance(journeys, list) or not journeys:
        raise ValueError(f"{path}: journeys must list at least one journey")
    names = set()
    for journey in journeys:
        name = journey.get("name")
        if not isinstance(name, str) or not name or name in names:
            raise ValueError(f"{path}: every journey needs a unique name")
        names.add(name)
        if not isinstance(journey.get("writes", False), bool):
            raise ValueError(f"{path}: journey '{name}': writes must be true or false")
        steps = journey.get("steps")
        if not isinstance(steps, list) or not steps:
            raise ValueError(f"{path}: journey '{name}' has no steps")
        for step in steps:
            if step.get("method") not in METHODS or not str(step.get("path", "")).startswith("/"):
                raise ValueError(f"{path}: journey '{name}': every step needs a method and a path starting with /")
    steady = target.get("steady_state") or {}
    rate, p95 = steady.get("success_rate"), steady.get("p95_ms")
    if not isinstance(rate, (int, float)) or isinstance(rate, bool) or not 0 < rate <= 1:
        raise ValueError(f"{path}: steady_state.success_rate must be above 0 and at most 1")
    if not positive_int(p95):
        raise ValueError(f"{path}: steady_state.p95_ms must be a whole number above 0")
    return target


def denied_group(kind, deny_groups):
    """True if a group/Kind belongs to a denied API group or to one of its subgroups."""
    group = kind.partition("/")[0]
    return any(group == denied or group.endswith("." + denied) for denied in deny_groups)