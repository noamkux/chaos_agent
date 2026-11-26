# Checks catalog

The catalog defines the types of weakness the agent tests for and how each one may be proven. It is a floor, not a limit: every check that applies to a system is tested in every run, and the agent also looks for weaknesses outside the catalog and reports them as observations.

The catalog does not teach the model what it already knows. It gives every run the same names, the same proof rules and the same definition of a finding, which is what makes runs comparable and lets the eval score them.

## Layout

One YAML file per check, named after the check: `catalog/<name>.yaml`. Each check is added or changed in its own PR.

## How the catalog is used

- **System prompt:** at the start of a run the orchestrator builds an index from the catalog and adds it to the system prompt. Only checks whose `applies_to` matches resources in the system, and that match the run's `focus`, are included. The index is sorted by name so the prompt is identical across runs and can be cached.
- **`get_check`:** the agent calls it to read the details of a check before testing it.
- **`report_finding`:** findings must use a `name` from the catalog; anything else is reported as an observation.
- **`focus.checks`:** must contain catalog names; the orchestrator rejects unknown names before the run starts.
- **Eval:** findings are matched to `ground_truth.yaml` by check name and component.

## Schema

Each file has two parts. The index part is short and goes into the system prompt. The details part is returned only by `get_check`.

### Index

- **`name`** (string, required): the identifier of the check, lowercase with hyphens. Must match the file name. Used as `check_name` in findings, in `ground_truth.yaml` and in `focus.checks`.
- **`area`** (required): `resilience`, `performance` or `exposure`. Used by `focus.areas` and to split the report into sections.
- **`category`** (required): the failure category, from the AWS Resilience Analysis Framework: `single-point-of-failure`, `excessive-load`, `excessive-latency`, `misconfiguration` or `shared-fate`. Used to track coverage and to guide the agent beyond the catalog.
- **`summary`** (string, required): one sentence on what the weakness is and why it hurts. It is the only description of the check the agent sees in the index.
- **`applies_to`** (list, required): the kinds the check is relevant to, as `group/Kind` without a version, for example `[apps/Deployment, apps/StatefulSet]`. The core group is written `core` (`core/Service`). Checks with no matching kind in the system are left out of the index.
- **`max_level`** (required): the highest action level that may be used to prove the check: `observe`, `probe` or `disrupt`. A safety rule, not a capability: some checks could be proven by disruption but must not be, because the proof would destroy data. It is in the index so the agent knows which checks it can prove in a run before reading their details.

### Details

- **`default_severity`** (required): `high`, `medium` or `low`. The agent may change it with a stated reason.
- **`signals`** (string, required): what in the configuration or behavior raises suspicion.
- **`proof`** (string, required): the experiment or observation that proves or refutes the check, within `max_level`.
- **`confirmed_when`** (string, required): when the weakness is proven.
- **`survived_when`** (string, required): when the system held. A survived result is reported, not dropped.
- **`remediation`** (string, required): the recommended fix.

## Rules for writing a check

- **A finding is about user impact.** A check is confirmed when a user journey fails or breaks its SLO, measured at the system boundary, not when an internal component is down. When the application has a profile, its SLOs and critical journeys set the thresholds; without one, any error in a journey counts.
- **Every check has both outcomes.** If `survived_when` cannot be written, the check is a static rule, not something the agent proves.
- **Respect the data rule.** Any check whose proof could delete or corrupt data gets `max_level: observe`.

## Example

    name: single-replica
    area: resilience
    category: single-point-of-failure
    summary: The workload runs one replica, so losing that pod makes it unavailable.
    applies_to: [apps/Deployment, apps/StatefulSet]
    max_level: disrupt

    default_severity: medium
    signals: spec.replicas is 1.
    proof: >
      Run steady k6 traffic on the user journeys. Kill the only pod and keep measuring
      until the replacement is Ready.
    confirmed_when: A user journey fails or breaks its SLO while the pod is down.
    survived_when: Every journey keeps working; no journey needs the workload, or callers degrade gracefully.
    remediation: Run at least 2 replicas with a PodDisruptionBudget (minAvailable 1), spread across zones.