# ADR-0010: The orchestrator calls every MCP tool; the model's only tool is run_experiment

**Status:** Accepted, 2026-11-26
**Related:** ADR-0011 (deterministic or agent), ADR-0015 (generic disrupt tools), ADR-0007 (the loop)

## Context
At first the model called MCP tools directly: `get_workloads`, then `snapshot_resource`, `patch_resource`, `restore_snapshot`. That leaves the order of a safe experiment to the model: it could patch without a snapshot, forget to restore, or measure after the change instead of before. The question: who calls the tools?

## Options
1. **The model calls every tool, the orchestrator checks each call.** Most freedom for the model. But a check per call cannot enforce a sequence (snapshot, then patch, then restore), and every safety rule is one more instruction the model may not follow.
2. **The model calls some tools (observation), the orchestrator wraps the dangerous ones.** A middle ground, but two paths to the same servers, and observation results the model asked for are not citable as one consistent inventory.
3. **The orchestrator calls every MCP tool. The model gets one internal tool, `run_experiment`, which takes a plan** (hypothesis, action, journeys, how long the change stays) **and returns a measured, judged result.**

## Decision
Option 3.
- The model's tools are only what `run_agent` builds in `available`: `run_experiment`, when every experiment tool is loaded.
- Any other tool name the model sends goes to `call_tool` with an empty allowed set, so it is denied and recorded with `allowed = false`.
- The runner runs every experiment in a fixed order nobody can skip: check, steady check, background measurement, snapshot, write-ahead undo, change, wait, restore, judge.
- Observation (inventory, workload facts) is collected by the orchestrator before the first LLM call and put in the prompt with its step numbers (ADR-0012).

## Consequences
- **Gains:** the order of a safe experiment is code, not a prompt; every server call is made by code we wrote and recorded under the experiment's step; the model's tool schema is small, so its prompt is cheaper.
- **Trade-offs:** the model cannot ask for a fact that discovery did not collect, or run an action the runner does not know. Every new kind of action (a node failure, a Chaos Mesh fault) needs runner code, not only a new server tool.

## In the code
- `orchestrator/agent.py`: `run_agent`, `internal`, `available`, and the `tools.call_tool(conn, run_id, set(), ...)` branch for any other name.
- `orchestrator/runner.py`: `run_experiment_tool` (the schema the model sees), `run_experiment`, `EXPERIMENT_TOOLS`.
- `orchestrator/tools.py`: `call_tool`, the allowed-set check.
