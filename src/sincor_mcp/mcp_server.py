"""SINCOR MCP server (stdio transport, MCP spec via the official SDK).

Tools (all read-only, all honest about their limits):

- ``get_eth_usd_price``        live Base ETH/USD monitor feed
- ``solver_quote``             UNSIGNED solver quote (signed: false)
- ``erc8004_reputation``       ERC-8004 reputation lookup (interface level)
- ``erc8004_validation_lookup`` ERC-8004 validation/attestation lookup

Run: ``sincor-mcp-server`` or ``python -m sincor_mcp``.
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from . import capabilities

mcp = FastMCP(
    "sincor-mcp-server",
    instructions=(
        "SINCOR data/execution feeds. Price feed is live monitor data. "
        "Solver quotes are UNSIGNED paper quotes (measurements, not "
        "orders). The ERC-8004 oracle is interface-level: the contract "
        "is not deployed on Base mainnet; reads run against a labelled "
        "local-reference deployment of the real compiled contract."),
)


@mcp.tool()
def get_eth_usd_price() -> dict:
    """Latest Base ETH/USD price from SINCOR's monitor feed.

    Returns the freshest observation across sources (Uniswap V3 pool
    state via two public RPCs + Chainlink cross-check) with its source
    and age in seconds, plus a per-source breakdown."""
    return capabilities.get_eth_usd_price()


@mcp.tool()
def solver_quote(token_in: str, token_out: str, amount_in_atomic: str,
                 deadline_seconds: int = 120,
                 slippage_bps: int = 50) -> dict:
    """Unsigned solver quote for a token swap intent on Base.

    token_in/token_out: symbol (WETH, USDC, AXM, SINC) or 0x address.
    amount_in_atomic: input amount in the token's atomic units, as a
    string (e.g. "100000000" = 100 USDC). The quote is UNSIGNED
    (signed: false, signature: null) — a measurement from public pool
    state, never a submittable order. Includes route, gross/net output
    and the 500 bps platform-fee breakdown."""
    return capabilities.solver_quote(
        token_in, token_out, amount_in_atomic,
        deadline_seconds=deadline_seconds, slippage_bps=slippage_bps)


@mcp.tool()
def erc8004_reputation(agent_address: str) -> dict:
    """ERC-8004 reputation lookup for an agent address.

    Returns score / successes / failures / total from the
    SincorValidationReputationOracle. Interface level: the oracle is
    NOT deployed on Base mainnet; the default backend is a labelled
    local-reference deployment of the real compiled contract."""
    return capabilities.erc8004_reputation(agent_address)


@mcp.tool()
def erc8004_validation_lookup(task_id: str, sigil_commitment: str) -> dict:
    """ERC-8004 validation lookup: has the (taskId, SIGIL commitment)
    attestation been recorded on the oracle? Both inputs are bytes32
    hex strings (0x-prefixed or bare)."""
    return capabilities.erc8004_validation_lookup(task_id, sigil_commitment)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
