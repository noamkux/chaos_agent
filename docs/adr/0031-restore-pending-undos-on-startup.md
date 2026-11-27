# ADR-0031: Pending undos are restored when the orchestrator starts

**Status:** Proposed, 2026-11-27
**Related:** ADR-0006 (Postgres), ADR-0017 (write-ahead undo), ADR-0030 (node failure)

## Context
The undo log is written before every change (ADR-0017), but nothing runs a pending undo after a crash. A crash during a patch leaves a Deployment at `replicas: 0`: bad, but local. A crash during a node failure leaves a node, or a zone, cordoned and tainted, which affects every namespace. Node actions make this a requirement, not a nice-to-have.

## Options
1. **Manual:** an operator reads `undo_actions` and runs each by hand. Nothing to build; relies on someone noticing.
2. **On startup:** before a run does anything, the orchestrator runs every pending undo from any run, marks each done or failed, and refuses to start a run if one fails.
3. **A watchdog** (a CronJob or a small controller) that restores changes past their deadline even if the orchestrator never comes back. The strongest, and a separate component to build and secure.

## Decision
Option 2 now; option 3 in the backlog. Undos are run through the same `call_tool` path, so they are recorded as steps.

## Consequences
- **Gains:** a crash and a restart always end with the cluster restored, or with the run refusing to start until someone looks.
- **Trade-offs:** if the orchestrator is never started again, nothing is restored. An undo whose target was changed by someone else meanwhile will fail on its `resourceVersion` precondition, which is correct but needs a person.

## In the code
- Not built yet. Planned in `orchestrator/agent.py` or a new `orchestrator/undo.py`, called before the first step of a run; `orchestrator/db.py` gets a query for pending undos.
