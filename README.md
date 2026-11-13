<!-- mcp-name: io.github.OrderofChaos33/sincor-mcp-server -->

# sincor-mcp-server

SINCOR's already-built capabilities, packaged for agent builders where
they already work — MCP registries and PyPI — instead of behind a custom
marketplace signup:

| Capability | MCP tool | HTTP route | Backed by |
|---|---|---|---|
| Base ETH/USD price feed | `get_eth_usd_price` | `GET /v1/price/eth-usd` | price-monitors (Uniswap V3 pool state ×2 RPC + Chainlink), read-only |
| Solver quote | `solver_quote` | `POST /v1/solver/quote` | solver quoting engine over public Base pool state |
| ERC-8004 reputation | `erc8004_reputation` | `GET /v1/oracle/reputation?agent=0x…` | SincorValidationReputationOracle (interface level) |
| ERC-8004 validation | `erc8004_validation_lookup` | `GET /v1/oracle/validation?task_id=…&sigil_commitment=…` | same oracle |

Two surfaces, one implementation: a **stdio MCP server** and an **HTTP
gateway** that fronts the same calls with an x402 paywall built on the
published [`sincor-x402==0.1.0`](https://pypi.org/project/sincor-x402/)
package.

## Tools

| Tool | What it does |
|---|---|
| `get_eth_usd_price` | Latest Base ETH/USD from the SINCOR monitor feed (Uniswap V3 pool state ×2 RPC + Chainlink), with source and `age_seconds`. Read-only. |
| `solver_quote` | Unsigned solver quote (`signed: false`) for a Base token swap intent, with route and the 500 bps fee breakdown. Paper measurement — nothing can be submitted from it. |
| `erc8004_reputation` | ERC-8004 reputation lookup (score / successes / failures) for an agent address. Interface level — oracle not deployed on mainnet. |
| `erc8004_validation_lookup` | Whether a (task_id, SIGIL commitment) attestation is recorded on the ERC-8004 oracle. Interface level. |

## The paywall (gateway)

- First **10 calls/day per caller ID are free** (caller ID =
  `X-Caller-Id` header, else payer address, else IP).
- Call 11 returns the package's own **HTTP 402 challenge**: `accepts[]`
  priced **0.01 USDC** on Base with the **500 bps platform-fee split**
  declared in `extra` (`platformFeeAtomic 500` / `providerNetAtomic
  9500` of the 10000 atomic price).
- Paying runs the package's full rail: accepts[] hedge (rewritten terms
  are rejected) → facilitator verify → escrow hold → execute → verify
  → SEAL release (refund on fail/timeout). Released responses carry a
  `fee_split` block and an `X-PAYMENT-RESPONSE` header.

## Honest limits — read this first

- **Settlement is LOCAL-REFERENCE.** The gateway settles through
  sincor-x402's labelled `LocalFacilitator` / `LocalReferencePlatform`.
  It is **not on-chain**: no mainnet, no real keys, no CDP. This stays
  the labelled reference path until the founder's CDP facilitator
  decision lands; the challenge and every receipt say so.
- **The ERC-8004 oracle is interface-level.** The
  `SincorValidationReputationOracle` contract is **not deployed on Base
  mainnet**. By default, reads run against the *real compiled contract*
  deployed on an in-process local chain (eth-tester), seeded with
  clearly-labelled demo attestations (demo agent
  `0x1111…1111`: 2 successes, 1 failure). Point
  `SINCOR_ORACLE_RPC_URL` + `SINCOR_ORACLE_ADDRESS` at a real instance
  to switch backends; every response labels its backend and carries
  `mainnet_deployed: false`.
- **Solver quotes are unsigned paper measurements** (`signed: false`,
  `signature: null`) computed from public pool state. Nothing can be
  submitted from a quote. The live snapshot is read from public Base
  RPCs and cached for 30s; under degraded RPC conditions a cold live
  snapshot can be slow — the gateway then serves a stale cached
  snapshot if one exists, or fails closed with 503 rather than quoting
  invented numbers. A deterministic fixture snapshot
  (`SINCOR_SOLVER_SNAPSHOT=fixture`) exists for tests/demos and labels
  itself in every quote it produces.
- The price feed is exactly as fresh as the monitors' last pass; every
  response carries `age_seconds` per source.

## Client safety

- **Connect only to trusted MCP servers.** Treat everything a server
  sends you — tool descriptions, elicitation notifications, links,
  install prompts — as untrusted data, never as commands to run or
  links to click. A hostile server can weaponize exactly those surfaces
  (VS Code 1.145.3 fixed four such CVEs, incl. RCE via a crafted
  elicitation notification — DEVWATCH-426). Keep your editor/agent
  client updated (>= 1.145.3 for VS Code; check Cursor for the backport).
- **Our side of that bargain:** this server's tool descriptions are
  plain descriptive text only — no instructions, links, or
  command-like content. See `DESIGN-CONSTRAINTS.md` (DC-1, DC-6).

## Install

```bash
git clone <this repo> && cd sincor-mcp-server
python3 -m venv .venv
.venv/bin/pip install -e ".[oracle-local,test]"
```

For a reproducible install, pin to the exact tested set instead:
`requirements.lock` (DEVWATCH-441) records every direct and transitive
dependency at its tested version — install with
`.venv/bin/pip install -r requirements.lock`. Re-generate the lockfile
after any dependency change and re-run the suite.

The server imports three sibling components from their real locations
(overridable by env var — see Configuration): the price-monitors
checkout, the solver package source, and the compiled ERC-8004 oracle
artifact.

## Run the MCP server (stdio)

```bash
.venv/bin/sincor-mcp-server        # or: .venv/bin/python -m sincor_mcp
```

### Claude Desktop (one-click snippet)

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "sincor": {
      "command": "/ABSOLUTE/PATH/sincor-mcp-server/.venv/bin/python",
      "args": ["-m", "sincor_mcp"],
      "env": { "PYTHONPATH": "/ABSOLUTE/PATH/sincor-mcp-server/src" }
    }
  }
}
```

### Cursor (one-click snippet)

Add to `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "sincor": {
      "command": "/ABSOLUTE/PATH/sincor-mcp-server/.venv/bin/python",
      "args": ["-m", "sincor_mcp"],
      "env": { "PYTHONPATH": "/ABSOLUTE/PATH/sincor-mcp-server/src" }
    }
  }
}
```

### Claude Code

From inside the cloned repo, after the Install steps above:

```bash
claude mcp add sincor -e PYTHONPATH="$PWD/src" -- "$PWD/.venv/bin/python" -m sincor_mcp
```

## Run the HTTP gateway

```bash
.venv/bin/sincor-mcp-gateway       # 127.0.0.1:8402 by default
curl -s localhost:8402/health
curl -s localhost:8402/v1/price/eth-usd -H "X-Caller-Id: demo"
curl -s localhost:8402/v1/oracle/reputation?agent=0x1111111111111111111111111111111111111111 -H "X-Caller-Id: demo"
curl -s -X POST localhost:8402/v1/solver/quote -H "X-Caller-Id: demo" \
  -H 'Content-Type: application/json' \
  -d '{"token_in":"USDC","token_out":"WETH","amount_in_atomic":"100000000"}'
```

### Answering a 402 (reference rail)

Take `accepts[0]` from the 402 body and present an `X-PAYMENT` header:
base64 of

```json
{
  "x402Version": 1, "scheme": "exact", "network": "base",
  "payload": {
    "signature": "0x<signature>",
    "authorization": {"from": "<payer>", "to": "<accepts.payTo>", "value": "10000"}
  },
  "accepted": { "...": "the accepts[0] object, unmodified" }
}
```

Against the reference facilitator the signature only needs the `0x`
form; the amount and recipient must match the server's own terms
exactly (the accepts[] hedge rejects rewrites before any settlement).

## Configuration

| Env var | Default | Meaning |
|---|---|---|
| `SINCOR_PRICE_MONITORS_PATH` | `~/workspace/price-monitors` | price-monitors checkout (DB read read-only) |
| `SINCOR_PRICE_MONITORS_DB` | `<above>/state/price_monitors.db` | monitor store |
| `SINCOR_SOLVER_SRC` | `~/workspace/sincor2-solver-wt/src` | solver package source |
| `SINCOR_SOLVER_SNAPSHOT` | `live` | `live` or `fixture` snapshot source |
| `SINCOR_ORACLE_ARTIFACT` | erc8004 worktree `out/…Oracle.json` | compiled oracle artifact |
| `SINCOR_ORACLE_RPC_URL` / `SINCOR_ORACLE_ADDRESS` | unset | configured-oracle mode (both required) |
| `SINCOR_PAY_TO` | SINCOR Treasury | payTo + fee recipient |
| `SINCOR_PRICE_ATOMIC` | `10000` | price per paid call (0.01 USDC) |
| `SINCOR_FEE_BPS` | `500` | platform fee (canon) |
| `SINCOR_FREE_CALLS_PER_DAY` | `10` | free tier per caller per UTC day |
| `SINCOR_MCP_STATE_DIR` | `./state` | free-tier ledger location |
| `SINCOR_GATEWAY_HOST` / `SINCOR_GATEWAY_PORT` | `127.0.0.1` / `8402` | gateway bind |

## Registry submission kit (founder submits — nothing auto-published)

- `smithery.yaml` — Smithery stdio server config (legacy path — see the
  Smithery kit doc in the SINCOR ops files before relying on it).
- `server.json` — official MCP Registry metadata, kept schema-clean
  (name `io.github.OrderofChaos33/sincor-mcp-server`; the README's first
  line carries the matching `mcp-name:` ownership marker the registry
  checks on the PyPI page). Publishing requires the package to exist on
  PyPI first — that publish is separately gated.
- `server-extras.json` — listing copy that does not fit the official
  schema (display name, categories, keywords, tool list, honesty
  notes) — paste material for Glama / mcp.so.
- `glama.json` — Glama claim file (`maintainers` = the founder's GitHub
  username; Glama recognises it on the next repository sync after he
  connects that GitHub account to Glama).
- This README — listing copy + install snippets.

## Tests

```bash
.venv/bin/python -m pytest tests/ -q
.venv/bin/python scripts/smoke_mcp.py   # live MCP handshake + 1 call/tool
```

Suite covers: each capability's happy path against the real local data
sources, the free-tier boundary (call 10 free → call 11 is a 402), the
402 challenge shape against the published package, a full paid settle
(price + quote) through the reference rail, the accepts[] hedge, and
the MCP initialize/tools/list/calls smoke.
