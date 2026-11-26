"""Findings: the report_finding tool, its validation, and writing results to the findings table."""

REPORT_FINDING_NAME = "report_finding"
OTHER = "other"

STATUSES = ["confirmed", "survived", "not_proven", "inconclusive"]
SEVERITIES = ["high", "medium", "low"]
CATEGORIES = ["single-point-of-failure", "excessive-load", "excessive-latency",
              "misconfiguration", "shared-fate"]
LEVELS = ["observe", "probe", "disrupt"]

# Above this many object names, components and dependency are sent without an enum: a very
# large enum makes the strict schema too complex for the API, and the run would fail on its
# first call. validate() checks every name against the full inventory either way.
MAX_ENUM_NAMES = 300

def report_finding_tool(selected, components):
    """The report_finding tool for one run, with the run's checks and components as enums."""
    names = sorted(components)
    name_field = {"type": "string", "enum": names} if len(names) <= MAX_ENUM_NAMES else {"type": "string"}
    return {
        "name": REPORT_FINDING_NAME,
        "description": (
            "Record the result of one check for every component that has the same result and "
            "evidence, in one call; call again for components with a different result. Call it "
            "for every check you test, whatever the result: confirmed, survived, not_proven or "
            "inconclusive. A later call with the same check_name, component and dependency "
            "replaces the earlier one. Use check_name 'other' for a weakness outside the catalog."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "check_name": {"type": "string", "enum": sorted(selected) + [OTHER]},
                "components": {"type": "array", "items": name_field,
                               "description": "Object names from the inventory, at least one."},
                "dependency": {**name_field,
                               "description": "For a check about a pair: the component it depends on."},
                "status": {"type": "string", "enum": STATUSES},
                "evidence_steps": {"type": "array", "items": {"type": "integer"},
                                   "description": "The step numbers of the tool results that show the evidence."},
                "evidence_summary": {"type": "string",
                                     "description": "What those tool results show, in one or two sentences."},
                "title": {"type": "string", "description": "One line for the report."},
                "severity": {"type": "string", "enum": SEVERITIES,
                             "description": ("Required for check_name 'other'. For a catalog check, "
                                             "only to change its default severity.")},
                "severity_reason": {"type": "string",
                                    "description": "Required when severity is set."},
                "category": {"type": "string", "enum": CATEGORIES,
                             "description": "Required for check_name 'other'."},
            },
            "required": ["check_name", "components", "status", "evidence_steps",
                         "evidence_summary", "title"],
        },
    }

def validate(args, selected, components, run_level, valid_steps):
    """Check a report_finding call against the run's rules and build one row per component for the findings table."""
    # Kubernetes names are lowercase, and the LLM can change the string and add Up case letters.
    name = str(args.get("check_name", "")).lower()
    # dict.fromkeys drops a name the model repeated and keeps the order.
    reported = list(dict.fromkeys(str(c).lower() for c in args.get("components") or []))
    dependency = args.get("dependency")
    dependency = dependency.lower() if dependency else None
    status = str(args.get("status", "")).lower()
    cited = set(args.get("evidence_steps") or [])
    summary = (args.get("evidence_summary") or "").strip()
    title = (args.get("title") or "").strip()

    # What the model reported: a real check, a real component, a real status.
    if name != OTHER and name not in selected:
        return None, f"unknown check_name '{name}'. Use a name from the catalog list, or 'other'."
    if not reported:
        return None, "components must list at least one name from the inventory."
    unknown = [c for c in reported if c not in components]
    if unknown:
        return None, f"unknown components {unknown}. Use names from the inventory."
    if dependency is not None and (dependency not in components or dependency in reported):
        return None, f"dependency '{dependency}' must be a name from the inventory that is not in components."
    if status not in STATUSES:
        return None, f"status must be one of {STATUSES}."
    if not title or not summary:
        return None, "title and evidence_summary must not be empty."

    # The status must match what this run's level can prove.
    check = selected.get(name)
    # none measn other
    if check is not None:
        above_run = LEVELS.index(check["max_level"]) > LEVELS.index(run_level)
        if above_run and status in ("confirmed", "survived"):
            return None, (f"{name} needs {check['max_level']} to be proven and this run is "
                          f"{run_level}: report not_proven or inconclusive.")
        if not above_run and status == "not_proven":
            return None, (f"{name} can be proven at this run's level ({run_level}): report "
                          "confirmed, survived or inconclusive.")

    # Evidence: only real tool results from this run.
    rejected = cited - valid_steps
    if rejected:
        return None, (f"steps {sorted(rejected)} are not successful tool results from this run. "
                      "Cite the step numbers shown in tool results.")
    if not cited and status != "inconclusive":
        return None, "evidence_steps must cite at least one tool result."

    # Severity and category: from the catalog, or stated by the model for 'other'.
    default = check["default_severity"] if check else None
    severity = str(args.get("severity") or default or "").lower()
    reason = (args.get("severity_reason") or "").strip() or None
    if severity not in SEVERITIES:
        return None, "severity is required for check_name 'other', one of high, medium, low."
    if check and severity != default and not reason:
        return None, f"severity_reason is required to change the default severity ({default})."
    category = check["category"] if check else str(args.get("category", "")).lower()
    if category not in CATEGORIES:
        return None, f"category is required for check_name 'other', one of {CATEGORIES}."

    return [{
        "check_name": name,
        "component": component,
        "dependency": dependency,
        "status": status,
        "category": category,
        "severity": severity,
        "severity_reason": reason,
        "title": title,
        "evidence": {"steps": sorted(cited), "summary": summary},
        "recommendation": check["remediation"].strip() if check else None,
    } for component in reported], None