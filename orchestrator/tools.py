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
SERVERS = {
    "observe": "http://127.0.0.1:8081/mcp",
}


async def load_tools(max_level):
    """Return the tools the agent may see in this run, in the Claude API format.

    Args:
        max_level: the run's level; ALLOWED_LEVELS maps it to the servers this run may use.

    Returns:
        Tool definitions named <level>__<tool>, ready for the tools parameter of the API.
    """
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
    """Prefer structured output; fall back to the text blocks (used for errors).

    Args:
        result: the CallToolResult returned by the MCP client.

    Returns:
        The structured content (a list tool's output is under "result"), or the error text.
    """
    if result.structured_content is not None:
        return result.structured_content
    return "\n".join(b.text for b in result.content if isinstance(b, TextContent))


async def call_tool(conn, run_id, allowed_tools, scope, name, args):
    """Check a call against the run's rules, execute it, record it.

    Args:
        conn: open connection from connect().
        run_id: the run's id, from create_run.
        allowed_tools: names returned by load_tools for this run; any other name is denied.
        scope: the run's namespaces, from roe["scope"]["namespaces"].
        name: <level>__<tool>, from the model's tool_use block or from discovery.
        args: the tool's arguments; from the model, so untrusted.

    Returns:
        JSON text {"step", "is_error", "content"} for the agent, where step is the step number
        the agent cites as evidence; or "DENIED: <reason>".
    """
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