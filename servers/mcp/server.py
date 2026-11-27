"""Chaos agent MCP server. One codebase, deployed once per level; each pod exposes only its level's tools."""
import os
import disrupt
import probe

from mcp.server import MCPServer

import k8s

LEVEL = os.environ["LEVEL"]

# The only place in this server that decides which tool belongs to which level.
TOOLS_BY_LEVEL = {
    "observe": [k8s.get_workloads, k8s.get_inventory, k8s.get_placement],
    "probe": [probe.measure_journeys],
    "disrupt": [disrupt.snapshot_resource, disrupt.patch_resource, disrupt.restore_snapshot,
                disrupt.delete_pod, disrupt.cordon_node, disrupt.taint_node_lost, disrupt.evict_pods,
                disrupt.restore_node],
    
}

mcp = MCPServer(f"chaos-agent-{LEVEL}")

# like @mcp.tool() but in a loop
for tool in TOOLS_BY_LEVEL[LEVEL]:
    mcp.tool()(tool)


if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8081")),
    )
