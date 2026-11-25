"""Checks catalog: loads the check files and builds the part of the system prompt that lists them."""
from pathlib import Path

import yaml

CATALOG_DIR = Path(__file__).parent.parent / "catalog"

INDEX_FIELDS = ["name", "area", "category", "summary", "applies_to", "max_level"]
DETAIL_FIELDS = ["default_severity", "signals", "proof",
                 "confirmed_when", "survived_when", "remediation"]

PROMPT_HEADER = """## Checks catalog

These are known weaknesses. When a check applies to this system, you must test it.
The catalog is a floor, not a limit: also look for weaknesses outside it, using the
failure categories below, and report those as observations.
Each check shows the highest level that may be used to prove it (max_level).
Before you test a check, call get_check(name) to read how to prove it.
Report every result, confirmed or survived, with report_finding.

Failure categories: single-point-of-failure, excessive-load, excessive-latency,
misconfiguration, shared-fate.

Checks that apply to this system (name | category | max_level | summary):
"""


def load_catalog(directory=CATALOG_DIR):
    """Read every check file. Returns a dict from check name to check."""
    checks = {}
    for path in sorted(directory.glob("*.yaml")):
        check = yaml.safe_load(path.read_text())
        missing = [field for field in INDEX_FIELDS + DETAIL_FIELDS if field not in check]
        if missing:
            raise ValueError(f"{path.name}: missing fields {missing}")
        if check["name"] != path.stem:
            raise ValueError(f"{path.name}: name '{check['name']}' does not match the file name")
        checks[check["name"]] = check
    return checks


def select_checks(checks, present_kinds, focus=None):
    """Keep the checks that apply to resources in the system and match the run's focus."""
    focus = focus or {}
    selected = {}
    for name, check in checks.items():
        if not set(check["applies_to"]) & present_kinds:
            continue
        if focus.get("checks") and name not in focus["checks"]:
            continue
        if focus.get("areas") and check["area"] not in focus["areas"]:
            continue
        selected[name] = check
    return selected


def render_index(selected):
    """Build the catalog section of the system prompt, sorted by name so it is identical across runs."""
    lines = [f"- {name} | {check['category']} | {check['max_level']} | {check['summary'].strip()}"
             for name, check in sorted(selected.items())]
    return PROMPT_HEADER + "\n".join(lines) + "\n"


GET_CHECK_TOOL = {
    "name": "get_check",
    "description": ("Return the details of one check from the catalog: how to prove it, "
                    "when it counts as confirmed or survived, and the fix."),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Check name, exactly as listed in the catalog."},
        },
        "required": ["name"],
    },
}


def get_check(selected, name):
    """Return the details of one selected check, or an error the model can act on."""
    if name not in selected:
        return {"error": f"unknown check '{name}'. Use a name from the catalog list."}
    check = selected[name]
    return {"name": name, **{field: check[field] for field in DETAIL_FIELDS}}