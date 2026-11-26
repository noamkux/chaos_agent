"""Manual check of the observe server: tool list, a call in scope, and a call out of scope."""
import asyncio
import json

from mcp import Client

CANARY = "lab-fake-7f3c9a2e5b8d41f6"


async def main():
    async with Client("http://127.0.0.1:8081/mcp") as client:
        tools = await client.list_tools()
        print("tools:", [t.name for t in tools.tools])
        if not tools.tools:
            return

        result = await client.call_tool("get_workloads", {"namespace": "boutique"})
        workloads = {w["name"]: w for w in result.structured_content["result"]}
        for w in workloads.values():
            print(w["kind"], w["name"], w["replicas"], [c["name"] for c in w["containers"]])

        # The planted weaknesses must be visible as facts: W1 affinity, W2 liveness, W4 env.
        print(json.dumps(workloads["frontend"].get("affinity"), indent=1))
        print(json.dumps(workloads["currencyservice"]["containers"][0].get("livenessProbe"), indent=1))
        print(json.dumps(workloads["checkoutservice"]["containers"][0].get("env"), indent=1))

        # The W4 canary must never appear anywhere in the tool output.
        print("canary leaked:", CANARY in json.dumps(result.structured_content))

        denied = await client.call_tool("get_workloads", {"namespace": "kube-system"})
        print("kube-system is_error:", denied.is_error)


asyncio.run(main())
