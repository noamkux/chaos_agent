# ADR-0017: Snapshots are Secrets in chaos-system, restored by replace, with a write-ahead undo log

**Status:** Accepted, 2026-11-26
**Related:** ADR-0006 (Postgres), ADR-0029 (env values never leave), ADR-0031 (restore on startup)

## Context
Every patch must be undone after the experiment, even if the orchestrator crashes in between. Three questions: where is the state before the change kept, how is it restored, and how does a crash not lose it?

## Options
**Where the snapshot lives:**
1. **In Postgres.** Already there. But a full object holds env values, including literal secrets (the lab's W4 plants exactly that); they would end up in the database and in every backup of it.
2. **In the orchestrator's memory.** Lost on a crash.
3. **As a Secret in the server's own namespace,** labeled as a snapshot, readable only by the disrupt server.

**How to restore:**
1. **A reverse patch.** Cannot remove fields the patch added.
2. **Replace with the snapshot,** using the current `resourceVersion`: puts the whole object back exactly, including removing what the patch added.

**When the undo is recorded:**
1. **After the change.** A crash between the change and the record leaves a change nobody knows to undo.
2. **Before the change (write-ahead).** A crash leaves a pending undo that can be run later.

## Decision
- **Snapshots as Secrets** in `chaos-system` (`POD_NAMESPACE` from the Downward API), with a random name and the label `chaos-agent.io/snapshot`. `restore_snapshot` refuses any Secret without the label, so the tool cannot be used to read other Secrets in `chaos-system`, such as the Postgres password. The object is cleaned of `status` and server-managed metadata before it is stored.
- **Restore by replace,** then delete the snapshot only after the replace succeeded, so a failed restore can be retried.
- **Write-ahead undo:** the runner writes the undo (`restore_snapshot` with the snapshot id) to `undo_actions` as pending before the patch, and marks it done after the restore. A failed restore marks it failed and stops the run.

## Consequences
- **Gains:** env values never reach the database or the model; every patch can be undone exactly; a crash leaves a record of what is still changed.
- **Trade-offs:** the disrupt ServiceAccount needs create, get and delete on Secrets in its own namespace, which the admission policy allows only there. A pending undo is only useful if something runs it: today that is manual, and ADR-0031 adds it on startup.

## In the code
- `servers/mcp/disrupt.py`: `SNAPSHOT_NAMESPACE`, `SNAPSHOT_LABEL`, `clean`, `snapshot_resource`, `restore_snapshot`.
- `orchestrator/runner.py`: the patch branch of `run_experiment` (`db.add_undo` before `PATCH`, `db.finish_undo` after `RESTORE`, `RuntimeError` on a failed restore).
- `orchestrator/db.py`: `add_undo`, `finish_undo`; `orchestrator/schema.sql`: `undo_actions`.
- `charts/chaos-agent/templates/mcp-rbac.yaml`: the `-snapshots` Role.
