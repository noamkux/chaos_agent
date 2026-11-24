"""Manual check of the cluster server."""
import asyncio

from mcp import Client


async def main():
    async with Client("http://127.0.0.1:8080/mcp") as client:
        tools = await client.list_tools()
        print("tools:", [t.name for t in tools.tools])

        result = await client.call_tool("get_workloads", {"namespace": "boutique"})
        for w in result.structured_content["result"]:
            print(w["name"], w["replicas"], w["limits"].get("cpu"), w["empty_dir_volumes"])

        denied = await client.call_tool("get_workloads", {"namespace": "kube-system"})
        print("kube-system is_error:", denied.is_error)


asyncio.run(main())