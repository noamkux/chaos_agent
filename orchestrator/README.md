## Layout

- `main.py`: the entry point of the chart's Job, one run from the environment.
- `config.py`: loads and checks the RoE and `target.yaml`.
- `agent/`: `loop.py`, the loop with the model and its prompt; `knowledge.py`, what the agent remembers.
- `experiments/`: `runner.py` runs one experiment; `judge.py` decides its verdict; `node_failure.py`; `undo.py`.
- `storage/`: `db.py` and `schema.sql`.
- `mcp_client.py`: the bridge to the MCP servers, with the allowlist, the scope and the audit of every call.
- `tests/unit/`: the unit tests; `tests/try_*.py`: manual runs against the lab.

## Why a database

The agent is not a script that runs and exits. It is a process that runs for tens of minutes, changes real systems, and can fail at any moment. The database solves five problems that have no good alternative solution.

### 1. Recovery after a crash (the most important)

Scenario: the agent scales `cartservice` to 0 to test something, and at that exact moment the orchestrator crashes (OOM, the laptop shuts down, a bug). Everything in memory is lost, including the fact that `cartservice` must be restored to 2 replicas. The site stays down and nobody knows why.

In `dependency-check.sh` this information lived in a variable, and `trap` covered a crash of the script itself. But `trap` does not help if the machine goes down. Only what was written to disk before the disruption survives, and the orchestrator restores from it when it starts again.

### 2. Audit: what the agent did, and why

An LLM is not deterministic. The same run twice can choose different experiments. When something goes wrong, or when someone asks "who took checkout down at 14:32?", there has to be a record of every action, in order, with its input and output.

The eval reads the same record to count Rules of Engagement violations and to search for the canary. Without an audit there is no way to test the agent, and no reason to trust it.

### 3. A budget that spans more than one run

A per-run budget can live in memory. A monthly budget (alert at 80%, block at 100%) has to sum every run in the month, from CI, from a CronJob and from the CLI, each of them a separate process. They need a shared place to write to.

### 4. Coordination between concurrent runs

A CI job and a CronJob can start in the same second on the same namespace. Two disruption experiments running at once on the same system ruin each other's measurements, and possibly the system itself. One point has to decide that only one runs.

Postgres does this atomically: when two processes try to take the lock at the same moment, only one succeeds.

### 5. History

Results of previous runs: whether a weakness was fixed, whether it came back, and how runs compare across models.

## Database schema

Postgres holds the state of the system itself: what is running, what was done, what must be restored and what was found. Metrics stay in Prometheus, knowledge in git and chromadb.

### runs

One row per agent run on one namespace. Every other table belongs to a run. It also acts as the queue and the per-namespace lock.

- **id**: run identifier, referenced by every other table and shown in reports ("Run #42").
- **namespace**: the namespace under test; the scope of the run and the key of the lock.
- **status**: `queued`, `running`, `completed`, `aborted` or `failed`. `aborted` means a safety mechanism stopped the run (watchdog, budget) and a partial report exists; `failed` means the system itself broke.
- **model**: exact model ID used, so evals can compare models and costs.
- **max_level**: highest action level allowed (`observe`, `probe`, `disrupt`). Checked on every tool call.
- **roe, profile, focus**: copies of the run's inputs as they were at start, so the audit shows which rules applied even if the files change later.
- **budget_usd, spent_usd**: the run's budget and how much is used. Enforced in code before every LLM call. `numeric`, because money is not stored as float.
- **created_at, started_at, finished_at**: queue time, start and end. Separates "the queue is busy" from "the agent is slow".
- **error**: why a run ended as `failed` or `aborted`.

**one_running_run_per_namespace**: a partial unique index on `namespace` where `status = 'running'`. Postgres rejects a second running run on the same namespace, atomically. The lock is released automatically when the status changes.

### steps

One row per LLM call or tool call, in order. It is both the audit log and the checkpoint: after a crash the orchestrator rebuilds the agent's conversation from it.

- **id**: step identifier, referenced by `undo_actions`.
- **run_id**: the run this step belongs to. A foreign key, so no orphan steps.
- **step**: order within the run, unique per run. Order cannot come from timestamps, because read tools run in parallel.
- **kind**: `llm` or `tool`.
- **name**: the tool with its server (`chaos.scale_deployment`) or the model name.
- **input, output**: what was sent and what came back. Output is stored after secret redaction; the eval searches it for the canary.
- **allowed**: whether the orchestrator approved the call. Denied calls are recorded too, so the eval counts attempted violations, not only successful ones.
- **tokens_in, tokens_out, cost_usd**: usage and cost of LLM steps. The sum is the run's `spent_usd`.
- **started_at, finished_at**: tool latency, and a step with no `finished_at` after a crash is a step whose outcome is unknown.

### undo_actions

The inverse of every disruptive action, written before the action runs. `steps` records what the agent did; `undo_actions` records what must still be restored.

- **id**: undo identifier.
- **run_id**: the run that caused the disruption.
- **step_id**: the step that caused it, linking each restore to its action.
- **action**: the inverse operation as JSON, with the exact prior state (for example: scale `cartservice` back to 2 replicas).
- **status**: `pending` until the restore is verified, then `done`; `failed` if the restore did not work. On startup, every `pending` row is restored before anything else.
- **created_at, done_at**: when the undo was registered and when it was completed; the gap is how long the system was disrupted.
