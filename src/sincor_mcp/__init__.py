"""sincor_mcp — SINCOR pay-per-call MCP server + x402 HTTP gateway.

Exposes three already-built SINCOR capabilities behind one MCP server
(stdio) and one HTTP gateway fronted by the published ``sincor-x402``
package's paywall:

1. Base ETH/USD price feed   (price-monitors, read-only Feed API)
2. Solver quotes             (solver quoting engine, UNSIGNED quotes)
3. ERC-8004 validation/reputation oracle (interface-level; the oracle
   contract is NOT deployed on Base mainnet — the default backend is a
   labelled in-process local-reference deployment)

Settlement honesty: the gateway settles through sincor-x402's labelled
LOCAL REFERENCE facilitator/escrow. No mainnet, no real keys, no CDP.
That changes only when the founder's CDP facilitator decision lands.
"""

__version__ = "0.1.0"
