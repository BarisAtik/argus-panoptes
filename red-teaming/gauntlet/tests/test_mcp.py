import asyncio
import sys

import pytest

mcp = pytest.importorskip("mcp")

from gauntlet.agents import make_agent  # noqa: E402
from gauntlet.mcp_bridge import McpBackend  # noqa: E402
from gauntlet.runner import run_trial  # noqa: E402
from gauntlet.scenario import load_scenarios  # noqa: E402

ALL = load_scenarios()


@pytest.mark.parametrize("defense", ["none", "layered"])
def test_mcp_transport_matches_direct_calls(defense):
    for sc in ALL:
        a = run_trial(sc, lambda: make_agent("compromised"), defense, 0)
        b = run_trial(sc, lambda: make_agent("compromised"), defense, 0, backend_factory=McpBackend)
        assert (a.attack, a.utility, a.n_calls, a.error) == (b.attack, b.utility, b.n_calls, b.error), sc.id


def test_real_stdio_server_exposes_the_poisoned_description():
    async def go():
        params = mcp.StdioServerParameters(
            command=sys.executable, args=["-m", "gauntlet.mcp_bridge", "--scenario", "sc-tool-description-poison"])
        async with mcp.Client(params) as client:
            tools = {t.name: t for t in (await client.list_tools()).tools}
            result = await client.call_tool("get_weather", {"city": "Utrecht", "notes": ""})
            return tools, result

    tools, result = asyncio.run(asyncio.wait_for(go(), 30))
    assert "<IMPORTANT>" in tools["get_weather"].description
    assert result.content[0].text.startswith("Sunny")
