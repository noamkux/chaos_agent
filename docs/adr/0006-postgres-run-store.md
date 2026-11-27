# ADR-0006: Postgres holds runs, every step, and the undo log

**Status:** Accepted, 2026-11-24
**Related:** ADR-0017 (write-ahead undo), ADR-0031 (restore on startup)

## Context
A run makes dozens of LLM calls and tool calls, some of which change the cluster. We need to know afterwards exactly what happened (audit), to be able to continue or clean up after a crash (checkpoint and undo), to prevent two runs from breaking the same namespace at once, and to feed the eval. The question: where is that state kept?

## Options
1. **Log files.** Simple. But not queryable, and nothing enforces "one run per namespace".
2. **SQLite on the orchestrator's disk.** No server. But the orchestrator will run as a Job in the cluster, whose disk does not survive it.
3. **Postgres, bundled in the chart.** A real database with constraints and JSON columns, that survives the orchestrator.

## Decision
Option 3. A StatefulSet with a PVC in the chart, its password from an `existingSecret` or generated once and kept across upgrades. Three tables:
- **`runs`:** one row per run, with its RoE and target profile; also the queue and the lock.
- **`steps`:** every LLM call and every tool call, numbered within the run, with input, output, whether it was allowed, and token counts. A call is recorded before it runs and completed after, so a crash leaves a step with input and no output. Denied calls are recorded too.
- **`undo_actions`:** what must be restored, written before the change it undoes (ADR-0017).

**One running run per namespace** is a partial unique index (`one_running_run_per_namespace`), enforced by Postgres, not by code.

## Consequences
- **Gains:** a complete, queryable audit; step numbers the model and the summary can cite as evidence; a lock that holds even with two orchestrators; the undo log survives a crash.
- **Trade-offs:** one more stateful component to run and back up. The schema is applied on every start with `CREATE ... IF NOT EXISTS`, which adds but never changes or removes: the lab database still has the old `findings` table. There are no migrations yet.
- **Not solved:** cost tracking (`spent_usd`, `budget_usd`) exists in the schema but is not enforced yet (backlog).

## In the code
- `orchestrator/schema.sql`: the three tables and the partial unique index.
- `orchestrator/db.py`: `create_run`, `claim_run` (catches the unique violation), `start_step`, `finish_step`, `record_llm_step`, `add_undo`, `finish_undo`.
- `charts/chaos-agent/templates/postgresql-*.yaml`: the StatefulSet, Service and Secret.
- `lab/watch-run.sh`: follows a run live from the database.
