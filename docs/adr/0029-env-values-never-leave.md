# ADR-0029: Env values and Secrets never leave the MCP servers

**Status:** Accepted, 2026-11-26
**Related:** ADR-0012 (discovery), ADR-0017 (snapshots), ADR-0004 (W4)

## Context
Workloads often carry secrets in their env, as literals or from Secrets. Anything a tool returns ends up in the prompt, in the model provider's logs, in the `steps` table, and in the report. The question: what about env values?

## Options
1. **Return env as it is, and trust the prompt not to repeat it.** The value is already in the database and sent to the model.
2. **Redact values that look secret.** Heuristic: misses some, and still sends the rest.
3. **Never return values at all:** only the name of each variable and where its value comes from.

## Decision
Option 3.
- **Workload facts** show each env variable's name and its source (`literal`, `secretKeyRef`, `configMapKeyRef`, `fieldRef`, `resourceFieldRef`), `envFrom` by name, volumes by name and type. Never a value, never a Secret.
- **The inventory never lists Secrets.**
- **Snapshots** (which hold full objects, values included) stay as Secrets in `chaos-system` (ADR-0017).
- **API errors** are reduced to status and reason, since an error body can contain parts of the object.
- **A canary:** the lab plants `lab-fake-7f3c9a2e5b8d41f6` as a literal env value in checkoutservice (W4). It must never appear in a tool output, the database, the audit or a report; the manual client test checks tool output for it.

## Consequences
- **Gains:** the agent can still reason about secrets ("this Secret is a literal in env") without ever seeing one.
- **Trade-offs:** some legitimate reasoning needs a value (a hostname in an env variable that points at a dependency); the agent gets only the name, which often says enough.
- **Not solved:** the canary is checked in tool output by a manual test, not yet across the database and reports in CI (ADR-0034).

## In the code
- `servers/mcp/k8s.py`: `CONTAINER_FIELDS` (env left out on purpose), `env_facts`, `SKIPPED_KINDS` (Secrets).
- `servers/mcp/disrupt.py`: `api_error`, the snapshot comment.
- `servers/mcp/tests/try_client.py`: `CANARY` and the leak check.
- `lab/apps/boutique/patches/checkoutservice-secret-in-env.yaml`: the canary.
