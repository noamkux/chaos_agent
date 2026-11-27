# ADR-0016: A denylist, not an allowlist, enforced in the server and in the API server

**Status:** Accepted, 2026-11-26
**Related:** ADR-0015 (generic tools), ADR-0018 (deny groups), ADR-0030 (node failure)

## Context
The first version of `disrupt.py` had an allowlist of eight patchable kinds (Deployments, Services, ConfigMaps, HPAs, PDBs, NetworkPolicies...). That is a menu again, one level down: applications with CRDs (Argo Rollouts, Istio VirtualServices, KEDA ScaledObjects) hide their most interesting weaknesses exactly there. Two questions:
1. Allowlist or denylist?
2. Kubernetes RBAC has no exclusions ("everything except Secrets" cannot be written as a Role). How do we grant "almost everything" without trusting only our own code?

## Options
**What may be changed:**
1. **An allowlist of kinds.** Tight, but a menu.
2. **A denylist of kinds and of fields.** Deny only what cannot be restored or is about permissions; everything else, custom resources included, is open.

**How it is enforced:**
1. **RBAC with an explicit list of kinds.** Tight RBAC, but it is the allowlist again, and a new CRD is out of reach.
2. **RBAC `*` in the tested namespaces, with the denylist only in code.** Matches the denylist, but then Secrets are writable at the RBAC level, and our code is the only guard.
3. **RBAC `*` in the tested namespaces, plus a ValidatingAdmissionPolicy (GA since Kubernetes 1.30) that denies the denylist for the disrupt ServiceAccount in the API server itself.**

How other tools handle it: Litmus gives each experiment its own minimal ServiceAccount (an allowlist that works because its experiments are known in advance); Harness binds one Role per application namespace instead of a ClusterRole; Chaos Mesh adds a second fence with `enableFilterNamespace`. Our experiments are not known in advance, so the allowlist pattern does not fit.

## Decision
- **Denied kinds:** Secrets, PersistentVolumeClaims, ServiceAccounts, Roles and RoleBindings. PVCs are data a snapshot cannot restore; the rest are credentials and permissions.
- **Denied fields, at any depth of a patch:** `image`, `command`, `args`, `securityContext`, `serviceAccountName`, `serviceAccount`, `automountServiceAccountToken`, `hostNetwork`, `hostPID`, `hostIPC`, `volumes`. These do not break anything; they run other code or gain privileges, which is exploitation, not chaos. Resources, probes, env and everything else in a pod template stay open.
- **RBAC:** `patch` and `update` on `*/*`, and `delete` on pods, only in the allowed namespaces. Reads through the built-in `view` ClusterRole, which excludes Secrets.
- **Enforced twice:** `disrupt.py` refuses denied kinds and fields; the `mcp-disrupt-guard` ValidatingAdmissionPolicy denies the same, plus any CREATE or DELETE other than deleting pods and managing its own snapshot Secrets, for the disrupt ServiceAccount only, with `failurePolicy: Fail`. Tested: a replicas patch passes; image and hostNetwork changes are denied by the API server.

## Consequences
- **Gains:** the agent can change any kind, CRDs included; a bug in our code, or a call that bypasses the orchestrator, still cannot touch Secrets or change an image.
- **Trade-offs:** RBAC alone looks broad (`*`), which can alarm a security review; the admission policy must be read alongside it. A CRD without the `view` aggregation label is not readable, so it cannot be snapshotted, so it cannot be changed; a customer can grant it in values. Requires Kubernetes 1.30 or later.

## In the code
- `servers/mcp/disrupt.py`: `DENIED_KINDS`, `FORBIDDEN_FIELDS`, `resource_for`, `forbidden_fields`.
- `charts/chaos-agent/templates/_helpers.tpl`: the disrupt rules in `chaos-agent.mcp.rules`, and `chaos-agent.mcp.podGuard`.
- `charts/chaos-agent/templates/mcp-rbac.yaml`: the `view` RoleBinding.
- `charts/chaos-agent/templates/mcp-admission-policy.yaml`: the policy and its binding.
