# ADR-0018: API groups whose controllers act outside the namespace are denied by default

**Status:** Accepted, 2026-11-26
**Related:** ADR-0016 (denylist), ADR-0017 (snapshots), ADR-0020 (owners)

## Context
With every kind open to patching (ADR-0016), some custom resources are dangerous in a way a snapshot cannot fix: their controllers act outside the namespace or outside the cluster. Restoring the YAML restores the object, not what the controller did because of it:
- an Argo CD Application with `prune: true` whose path is patched deletes every resource of the application, PVCs included; restoring the Application recreates the Deployments, not the data;
- a Crossplane or ACK (`services.k8s.aws`) database whose instance class is patched is a real cloud change, with a reboot and a cost, and minutes of modification that no 30 s recovery window can judge;
- a CloudNativePG Cluster scaled down fails over and deletes a replica with its PVC;
- a Velero Schedule or Restore stops backups or overwrites resources.

The question: how do we keep the agent away from these, on every cluster, when the list differs per customer?

## Options
1. **Hard-code them in the server's denylist.** Always on, but the list is customer-specific, and a customer who understands the risk cannot opt in.
2. **Deny them in the RoE, with a default list,** enforced by the orchestrator before any call; a group also matches its subgroups.
3. **Nothing; trust the restore.** Wrong for the reasons above.

## Decision
Option 2. `deny_groups` in the RoE; when it is left out, `DEFAULT_DENY_GROUPS` applies: `argoproj.io`, `fluxcd.io`, `services.k8s.aws`, `crossplane.io`, `upbound.io`, `cnrm.cloud.google.com`, `azure.com`, `velero.io`, `cnpg.io`. Setting the key replaces the list. A group matches itself and every subgroup (`argoproj.io` also matches `workflows.argoproj.io`, and not `notargoproj.io`).

Chaos on the GitOps tool itself stays possible the right way: scaling `argocd-application-controller` to 0 is an `apps/Deployment` change.

## Consequences
- **Gains:** the snapshot guarantee ("restore puts things back") holds for everything the agent may touch.
- **Trade-offs:** enforced by the orchestrator only, not by the admission policy, so a direct call to the disrupt server bypasses it. A new operator with the same risk is open until someone adds its group.

## In the code
- `orchestrator/run_config.py`: `DEFAULT_DENY_GROUPS`, the `deny_groups` check in `load_roe`, `denied_group`.
- `orchestrator/runner.py`: `check` (`run_config.denied_group`).
- `lab/apps/boutique/roe.yaml`: `deny_groups`, with the reasons.
