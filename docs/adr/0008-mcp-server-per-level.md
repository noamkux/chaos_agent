# ADR-0008: One MCP server codebase, deployed once per level, each with its own ServiceAccount

**Status:** Accepted, 2026-11-25
**Related:** ADR-0009 (levels are permission boundaries), ADR-0010 (orchestrator calls every tool)

## Context
Everything that touches the cluster goes through MCP servers: reading objects, sending traffic, changing things. Their permissions differ wildly: reading is harmless, changing is not. The question: how are the tools grouped into servers, and how does each get its permissions?

## Options
1. **One server with every tool.** One Deployment. But its ServiceAccount must hold the union of all permissions, so a bug in a read-only tool runs with write access.
2. **A server per function** (cluster, metrics, load, chaos, exposure...). Six Deployments, six Dockerfiles, six templates. And some functions belong to two levels: k6 at a low rate is a measurement, at a high rate it is a load experiment.
3. **A server per level** (observe, probe, disrupt), from one codebase and one image. Each Deployment gets `LEVEL` and its own ServiceAccount, and registers only its level's tools at startup.

Least privilege for MCP servers is a published recommendation (OWASP's MCP security cheat sheet, and vendor guides that separate read and write tools). MongoDB's MCP server does the same thing with one codebase and a `--readOnly` mode.

## Decision
Option 3.
- `server.py` reads `LEVEL` (no default: a server that does not know its level does not start) and registers the functions listed under it in `TOOLS_BY_LEVEL`, the only place that decides which tool belongs to which level.
- Each level gets a Deployment, a Service and a ServiceAccount from the same template, and a Role per allowed namespace with only its level's rules.
- Tool names carry the level (`observe__get_workloads`, `disrupt__patch_resource`), so the audit shows what was dangerous at a glance.
- A level holds only its own tools: a probe run connects to both the observe and the probe servers.

## Consequences
- **Gains:** a read-only pod never holds write permissions; one image to build and scan; adding a tool is one line in `TOOLS_BY_LEVEL`.
- **Trade-offs:** three pods instead of one, and the orchestrator talks to several servers in one run. A tool that needs two levels' permissions must be split.

## In the code
- `servers/mcp/server.py`: `LEVEL`, `TOOLS_BY_LEVEL`, the registration loop.
- `charts/chaos-agent/templates/mcp.yaml`: one ServiceAccount, Deployment and Service per enabled level.
- `charts/chaos-agent/templates/mcp-rbac.yaml` and `_helpers.tpl` (`chaos-agent.mcp.rules`): the Role per level per namespace.
- `orchestrator/tools.py`: `SERVERS`, one address per level.
