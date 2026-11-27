# ADR-0007: The agent loop is written on the Claude API, without an agent framework

**Status:** Accepted, 2026-11-25
**Related:** ADR-0010 (orchestrator calls every tool), ADR-0006 (steps)

## Context
The agent needs a loop: send the conversation to the model, run the tool calls it asks for, send the results back, until it stops. The question: write the loop, or use a framework?

## Options
1. **An agent framework** (LangChain, LangGraph, CrewAI and the like). Ready-made loops, memory and tool wiring. But the parts that matter most here (checking every call against the Rules of Engagement, recording every step before it runs, refusing tools the model invents) would be hooks inside someone else's loop, and the framework's abstractions change often.
2. **The Claude API's native tool calling, with our own loop.** About 50 lines. Every decision in the loop is ours and visible.

## Decision
Option 2. `run_agent` calls `messages.create`, records the response and its token usage as a step, runs each `tool_use` block, and returns the results, until the model stops calling tools or `MAX_ITERATIONS` (20) is reached.
- **`MAX_TOKENS` (16384) cut-off fails the run:** a truncated response may hold a truncated tool call, which cannot be run safely.
- **Automatic prompt caching:** the breakpoint moves to the last block as the conversation grows, so each call pays full price only for what is new. In the run of 2026-11-27, 245K of 270K input tokens came from the cache.
- **Tool output is data, never instructions:** stated in the system prompt, as a first defense against prompt injection from the system under test.

## Consequences
- **Gains:** full control over safety and audit; nothing between the loop and the API to debug; small enough to read in one sitting.
- **Trade-offs:** features a framework gives for free (retries, streaming, conversation summarization when the context grows) must be written by us when needed. A long run grows the context with every experiment result; there is no summarization yet.

## In the code
- `orchestrator/agent.py`: `run_agent`, `MAX_ITERATIONS`, `MAX_TOKENS`, the `cache_control` argument, the `stop_reason` checks.
- `orchestrator/db.py`: `record_llm_step`.
