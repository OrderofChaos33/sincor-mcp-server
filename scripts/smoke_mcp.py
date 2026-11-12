"""End-to-end MCP smoke: spawn the real server over stdio, run the MCP
initialize handshake, list tools, and call every tool once.

Usage: python scripts/smoke_mcp.py
Exits non-zero on any failure. Uses the solver FIXTURE snapshot so the
run is deterministic and offline-safe; price + oracle tools hit their
real local data sources (the live monitors DB, the local-reference
oracle deployment)."""
import asyncio
import json
import os
import sys

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


async def main() -> int:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.path.join(ROOT, "src")
    env["SINCOR_SOLVER_SNAPSHOT"] = "fixture"
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "sincor_mcp"], env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            print(f"initialize OK — server: {init.serverInfo.name} "
                  f"{init.serverInfo.version}")
            tools = await session.list_tools()
            names = [t.name for t in tools.tools]
            print(f"tools/list OK — {names}")
            expected = {"get_eth_usd_price", "solver_quote",
                        "erc8004_reputation", "erc8004_validation_lookup"}
            assert expected <= set(names), f"missing tools: {expected - set(names)}"

            async def call(name, args):
                res = await session.call_tool(name, args)
                assert not res.isError, f"{name} errored: {res.content}"
                text = res.content[0].text
                print(f"call {name} OK — {text[:160]}...")
                return json.loads(text)

            price = await call("get_eth_usd_price", {})
            assert price["key"] == "base:eth_usd" and price["value"] > 0

            quote = await call("solver_quote", {
                "token_in": "USDC", "token_out": "WETH",
                "amount_in_atomic": "100000000"})
            assert quote["signed"] is False and quote["signature"] is None

            rep = await call("erc8004_reputation", {
                "agent_address": "0x1111111111111111111111111111111111111111"})
            assert rep["total"] == 3 and rep["oracle"]["mainnet_deployed"] is False

            val = await call("erc8004_validation_lookup", {
                "task_id": "0x" + "00" * 32, "sigil_commitment": "0x" + "11" * 32})
            assert val["seen"] is False
    print("SMOKE PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
