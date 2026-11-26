"""Bridge between the agent and the MCP servers: filters tools by level and records every call."""
import json

from mcp import Client
from mcp.types import TextContent

import db

# For each run level, the server levels it may use. Each level includes the ones below it.
ALLOWED_LEVELS = {
    "observe": ["observe"],
    "probe": ["observe", "probe"],
    "disrupt": ["observe", "probe", "disrupt"],
}

# One MCP server pod per level; the server name is its level.
# Local port-forwards until the orchestrator runs as a Job in the cluster (then from env, see the chart task).
SERVERS = {
    "observe": "http://127.0.0.1:8081/mcp",
    "probe": "http://127.0.0.1:8082/mcp",
    "disrupt": "http://127.0.0.1:8083/mcp",
}


async def load_tools(max_level):
    """Return the tools the agent may see in this run, in the Claude API format."""
    allowed_levels = ALLOWED_LEVELS[max_level]
    tools = []
    for server, url in SERVERS.items():
        if server not in allowed_levels:
            continue
        async with Client(url) as client:
            result = await client.list_tools()
        for tool in result.tools:
            tools.append({
                "name": f"{server}__{tool.name}",
                "description": tool.description,
                "input_schema": tool.input_schema,
            })
    return tools


def result_content(result):
    """Prefer structured output; fall back to the text blocks (used for errors)."""
    if result.structured_content is not None:
        return result.structured_content
    return "\n".join(b.text for b in result.content if isinstance(b, TextContent))


async def call_tool(conn, run_id, allowed_tools, scope, name, args):
    """Check a call against the run's rules, execute it, record it."""
    denied = None
    if name not in allowed_tools:
        denied = f"tool '{name}' is not allowed in this run"
    elif "namespace" in args and args["namespace"] not in scope:
        denied = f"namespace '{args['namespace']}' is out of scope"

    step_id, step = db.start_step(conn, run_id, name, args, allowed=denied is None)

    if denied:
        db.finish_step(conn, step_id, {"denied": denied})
        return f"DENIED: {denied}"

    server, _, tool = name.partition("__")
    async with Client(SERVERS[server]) as client:
        result = await client.call_tool(tool, args)

    output = {"is_error": result.is_error, "content": result_content(result)}
    db.finish_step(conn, step_id, output)
    return json.dumps({"step": step, **output})