"""Start `nightwatch mcp` as a real subprocess and hunt over stdio.

python evals/mcp_smoke.py [--index NAME --url URL]
"""

from __future__ import annotations

import asyncio
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main() -> None:
    extra = sys.argv[1:]
    url = extra[extra.index("--url") : extra.index("--url") + 2] if "--url" in extra else []
    index = extra[extra.index("--index") : extra.index("--index") + 2] if "--index" in extra else []
    server = StdioServerParameters(
        command=sys.executable, args=["-m", "nightwatch.cli", *url, "mcp", *index]
    )
    async with stdio_client(server) as (read, write), ClientSession(read, write) as session:
        await session.initialize()

        async def call(name: str, **arguments):
            reply = await session.call_tool(name, arguments)
            content = reply.structured_content
            return content["result"] if "result" in content else content

        print("tools:", [tool.name for tool in (await session.list_tools()).tools])
        print("coverage:", (await call("coverage"))["by_status"])
        rules = await call("find_rules", words="lsass", technique="T1003", limit=3)
        print("rules:", [rule["title"] for rule in rules])
        for rule in rules:
            ran = await call("run_rule", rule_id=rule["id"], limit=1)
            print(" ", rule["title"][:50], "->", ran.get("alerts"), ran.get("readiness"))
        found = await call("search_logs", field="CommandLine", contains="mimikatz", limit=2)
        labelled = all("untrusted_log_text" in event for event in found)
        print("search_logs:", len(found), "events, labelled:", labelled)


if __name__ == "__main__":
    asyncio.run(main())
