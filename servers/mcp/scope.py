"""Namespace scope shared by all tools of this server."""

""" a global check to see if the namespace in the chart values 
is the same name space the agent want to work on"""

import os

from mcp.server.mcpserver.exceptions import ToolError

ALLOWED_NAMESPACES = set(os.environ["ALLOWED_NAMESPACES"].split(","))


def check_scope(namespace):
    """Reject any namespace this server was not deployed to touch."""
    if namespace not in ALLOWED_NAMESPACES:
        raise ToolError(f"namespace '{namespace}' is out of scope")