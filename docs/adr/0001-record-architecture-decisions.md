# ADR-0001: Record architecture decisions

**Status:** Accepted, 2026-11-27

## Context
The project changed direction several times in a few days: a checks catalog was built and removed, the agent's tools moved to the orchestrator, the permissions model went from an allowlist to a denylist. The reasons lived in chat conversations and in commit messages. Without them, a reviewer (or the next version of us) sees the code but not why it is shaped that way, and is likely to reopen questions that were already settled.

## Options
1. **Keep the reasons in commit messages.** Already done, and tied to the exact change. But a decision often spans many commits, and commit messages do not show the options that were rejected.
2. **One design document, updated in place.** Easy to read top to bottom. But updating in place erases the history: once the catalog section is gone, so is the reason it was removed.
3. **Architecture Decision Records** (Michael Nygard's format, 2011, here in the MADR style): one short file per decision, never deleted; a changed decision gets a new record, and the old one is marked superseded.

## Decision
Option 3. Every record in `docs/adr/` has the same sections:
- **Status:** Accepted, Proposed (decided but not built yet), or Superseded by another record.
- **Context:** the question we faced and why it came up.
- **Options:** what was considered, with its pros and cons.
- **Decision:** what was chosen.
- **Consequences:** what it gives us, its trade-offs, and what it does not solve.
- **In the code:** the files and functions where the decision lives.
- **Related:** other records.

Records are numbered in the order the decisions were made, not by topic. `README.md` in this folder is the index.

## Consequences
- **Gains:** the reasons and the rejected options stay next to the code, and are reviewed with it.
- **Trade-offs:** records must be written when the decision is made, or they drift into being written from memory. A record points at code that keeps changing, so its "In the code" section must be updated when the code moves.

## In the code
- `docs/adr/README.md`: the index.
