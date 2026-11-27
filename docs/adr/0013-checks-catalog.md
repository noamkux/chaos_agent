# ADR-0013: A checks catalog the agent works through

**Status:** Superseded by ADR-0014, 2026-11-26 (accepted 2026-11-25)
**Related:** ADR-0002 (chaos), ADR-0014 (no catalog)

## Context
To make the agent's work broad and repeatable, we needed a list of what to look for. The question: where does that list live?

## Options
1. **In the prompt.** Simple, but grows without structure, and cannot be validated.
2. **A catalog of checks as files,** each with what it applies to (`applies_to` in `group/Kind`), how to prove it and at which level, loaded by the orchestrator and shown to the model as an index. Findings reported through a strict `report_finding` tool, validated against the catalog, the inventory and the run level, and stored in a `findings` table. Scored by `evaluate.py` against `ground_truth.yaml`.

## Decision (at the time)
Option 2: `catalog/`, a loader, `get_check`, `report_finding` and the `findings` table.

## Why it was superseded
A catalog is a menu. The agent ran checks we wrote, so it could only find weaknesses we already knew about, and the project read as an SRE report generator (ADR-0002). The point of chaos engineering is discovering weaknesses nobody knew about. The catalog, `report_finding`, the findings table and `evaluate.py` were removed in commit `393037e`.

## What stayed
- `group/Kind` naming and dynamic discovery (ADR-0012), first built for `applies_to`.
- Evidence by step number, first required by `report_finding`.

## In the code
- Removed. History: commits `cbefb46`, `8e16b5e`, `282220b`, `f41f4f3` (added) and `393037e` (removed).
