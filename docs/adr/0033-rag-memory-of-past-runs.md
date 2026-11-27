# ADR-0033: Retrieval over past experiments, so a run builds on the ones before it

**Status:** Proposed, 2026-11-26 (the store is still to be decided)
**Related:** ADR-0006 (Postgres), ADR-0027 (prompt)

## Context
Every run starts from nothing: it repeats the experiments of the last run, and spends its budget rediscovering known results instead of going deeper. A course requirement is a RAG component. The question: what is retrieved, and from where?

## Options
**What is retrieved:**
1. **Documentation** (Kubernetes docs, chaos engineering guides). Generic; the model already knows most of it.
2. **Past experiments and their results** on the same application: hypothesis, action, verdict, timeline summary, and the agent's conclusion. Specific to this system, and exactly what a new run needs to avoid repeating itself.

**The store:**
1. **ChromaDB,** a dedicated vector store. The plan in the handoff of 2026-11-26. One more component in the chart.
2. **pgvector in the Postgres we already run.** No new component, and experiments are already rows in `steps`. Needs the extension in the Postgres image.

## Decision
Past experiments (option 1 of the first question). The store is to be decided before it is built: ChromaDB as planned, or pgvector to avoid a new component. Retrieval happens in the orchestrator, before the first LLM call, like discovery, and the retrieved experiments go into the prompt with their run and step ids.

## Consequences
- **Gains:** a second run can confirm what the first left unconfirmed and test what it suggested next.
- **Trade-offs:** results from an older version of the application may mislead; each retrieved experiment must carry its date and run.

## In the code
- Not built yet.
