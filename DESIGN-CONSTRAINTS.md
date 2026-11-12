# Design constraints — agent-infra dev watch hedges

Durable, checkable rules landed from the 2026-11-12 agent-infra dev
watch (DEVWATCH-425–445). Each rule names its source finding, the exact
rule, where it applies in this repo, and how it is verified. Rules marked
**future surface** have no applicable code in this repo today — they are
binding constraints for any future surface that adds the capability, not
dead text: do not build that surface without satisfying the rule first.

## DC-1 — Untrusted MCP server text is data, never commands (DEVWATCH-426)

- **Source:** VS Code 1.145.3 — four MCP CVEs incl. RCE via elicitation
  (CVE-2026-120779, CVSS 9.6: a hostile MCP server's elicitation
  notification rendered as a clickable command link; CVE-2026-114171:
  crafted MCP install link runs an attacker command; CVE-2026-120782:
  agent-mode local command without terminal approval; Network Workspace
  Trust Bypass RCE).
- **Rule:** Connect only to trusted MCP servers. Never click links in
  notifications produced by an untrusted server. Treat all
  MCP-server-supplied text as untrusted data: any SINCOR MCP client
  surface must render server-supplied strings as literal text only —
  never as executable UI, links, or commands.
- **Applies to:** docs (README "Client safety"), and any future SINCOR
  MCP client. This repo ships a server, not a client; the server side
  of the rule is that our own tool descriptions must never contain
  instructions, links, or command-like text (see DC-6).
- **Verified:** README carries the client-safety note. Builder VS Code
  installs must be >= 1.145.3 (human action — check Cursor builds for
  the backport; not enforceable from this repo).

## DC-2 — Path confinement must pin every operation, never validate-then-open (DEVWATCH-429)

- **Source:** `@modelcontextprotocol/server-filesystem` 2.3.0 — two
  TOCTOU confinement escapes (GHSA-7m4x, `move_file` passes the source
  as a plain string to `fs.renameSync`, so a racer swapping a parent
  component for an outside symlink moves an outside file into the
  allowed dirs; GHSA-p9cv, `read_text_file`/`head`/`tail` validate then
  re-open by path name, leaking outside contents — 13 leaks in 200
  calls in the harness). The 2.0.1 fix pinned only *write* paths.
- **Rule:** Any path-confinement check we write must open through
  pinned directory handles (`O_NOFOLLOW` + descriptor identity check),
  never validate-then-open-by-string — for reads, moves, *and* writes
  alike. A fix that pins only one operation is incomplete by
  construction. A racer test (swap a parent component mid-call, assert
  no outside content is returned) is required with any such check.
- **Applies to:** **future surface.** This repo has no filesystem MCP
  tools and no user-controlled paths: every path is env-configured and
  fixed (`SINCOR_PRICE_MONITORS_DB`, `SINCOR_SOLVER_SRC`,
  `SINCOR_ORACLE_ARTIFACT`, `SINCOR_MCP_STATE_DIR`); the monitor DB is
  opened `mode=ro` by the price-monitors Feed; the oracle artifact is
  read from one fixed path; the free-tier ledger writes one fixed state
  file. Verified by grep over `src/` (2026-11-12): no user-supplied
  path reaches any open/read/write call.
- **Also:** pin `@modelcontextprotocol/server-filesystem` >= 2.3.0
  anywhere it is used (not a dependency of this repo today).

## DC-3 — SSRF guards are deny-by-default, never `is_global` alone (DEVWATCH-431)

- **Source:** `mcp-server-fetch` #5492 — `_is_public_address` unwraps
  IPv4-mapped/NAT64 forms but omits deprecated IPv6 site-local
  `fec0::/10` and trusts `ip.is_global`, which returns `True` for
  `fec0::1`; the guard permits requests to non-public destinations. No
  patch yet as of 2026-11-12. (Note: the originally cited CVE-2026-41904
  was wrongly assigned — it belongs to FreeScout — and was removed; do
  not cite it.)
- **Rule:** Any SSRF guard we write must be deny-by-default on
  `not ip.is_global` **plus** explicit blocks for `fec0::/10` and
  `::ffff:0:0/96`; never trust `is_global` alone. The guard's test
  matrix must include the exact case `fec0::1` must be refused, in
  decimal, hex, and IPv4-mapped IPv6 forms. Cloud-metadata endpoints
  (`169.254.169.254`, `100.100.100.200`, `192.0.0.192`) are blocked
  explicitly (see also DEVWATCH-428).
- **Applies to:** **future surface.** This repo has no fetch surface:
  no user-supplied URL is ever fetched; the solver reads only
  configured public Base RPCs. Verified by grep over `src/` (2026-11-12):
  no `requests.*`/`urlopen`/`httpx` outbound call exists in this repo.
- **Also:** pin `mcp-server-fetch` >= the eventual fixed version once
  an advisory lands (watch #5492's private advisory).

## DC-4 — Streamable HTTP ships with CORS from day one, or not at all (DEVWATCH-433)

- **Source:** `modelcontextprotocol/servers` #5538 — PR #5536 added
  Streamable HTTP to `filesystem`, `memory`, `sequential-thinking` via
  `createMcpHandler` behind `localhostOriginValidation`, but the
  endpoints send no CORS headers and don't answer preflights, so a
  browser client on a localhost origin (e.g. MCP Inspector
  direct-connect) cannot reach them.
- **Rule:** If this repo ever adds a Streamable HTTP endpoint, mirror
  the `everything` server's pattern from day one: allowed-origin
  preflights answered 204 with `Access-Control-Allow-*`; responses
  carry `Access-Control-Allow-Origin` and expose `mcp-session-id` /
  `mcp-protocol-version` / `last-event-id`; any other origin still 403.
  Add a preflight + cross-origin POST test. Never "fix" reachability by
  widening origins.
- **Applies to:** **future surface.** The gateway (`gateway.py`) is a
  plain JSON HTTP API behind an x402 paywall — it is not MCP
  Streamable HTTP, serves no browser client, and binds localhost by
  default. Verified: no `Access-Control` handling and no MCP HTTP
  transport exist in `src/` (2026-11-12).

## DC-5 — Never install/resolve MCP servers or skills from memory; pin everything (DEVWATCH-441)

- **Source:** Per Glow Labs, AI coding agents configuring MCP servers
  default to installing an old, archived version from training data —
  downloaded ~17M times — containing 4 high-severity flaws with no fix
  forthcoming; agents pick the abandoned server ~98% of the time,
  without human approval. Corroborating (Corelight, Nov 10–11): 23 of
  69 packages changed across 35 MCP servers despite no config change —
  pinning the main package does not lock nested dependencies; launchers
  (uvx) resolve fresh from PyPI at rebuild.
- **Rule:** SINCOR agents must never install/resolve MCP servers or
  skills from memory/training data — only from a pinned, curated
  registry entry with a human-approved allowlist. An ALLOW-or-DENY gate
  is required before any tool/server installation step. Pin transitive
  dependencies (lockfiles) for every MCP server we run; run servers
  directly rather than via launchers that resolve at startup; disable
  update checks at startup.
- **Applies to:** this repo + agent fleet.
  - This repo: `requirements.lock` pins the exact installed set
    (mcp==1.30.0, web3==8.0.0, requests==2.34.2, eth-abi==6.0.0,
    sincor-x402==0.1.0, pytest==9.2.0, eth-tester==0.14.0b1,
    py-evm==0.12.1b1, plus all transitive deps). Reproducible installs
    use the lockfile; re-generate it after any dependency change and
    re-run the suite. `pyproject.toml` still declares ranges for direct
    deps — the lockfile is the pin, not the ranges.
  - Launchers: `smithery.yaml` runs `python -m sincor_mcp` directly and
    `server.json` declares a PyPI package `python -m sincor_mcp`
    (v0.1.0) — neither resolves fresh from PyPI at startup. Verified
    2026-11-12: no `uvx`/`npx` anywhere in the registry kit.
  - Fleet: audit the 42-skill catalog for archived/deprecated upstreams
    (human action, outside this repo).
- **Verified:** `tests/test_design_constraints.py::test_lockfile_pins_match_installed`
  asserts the lockfile pins every direct dep to its installed version.

## DC-6 — Tool schemas stay flat and minimal; malformed params fail correctably (DEVWATCH-442)

- **Source:** MCP error -32602 — when an agent's argument payloads clash
  with strict server schemas, MCP returns `Invalid Params` and
  execution halts. Zod/Pydantic generate advanced features (`$defs`
  references, union nullability, `additionalProperties`) that LLMs
  struggle to satisfy; LLM output parsers strip or corrupt them.
- **Rule:** Flatten nested unions, strip incompatible draft keywords,
  keep input schemas minimal before registering. Implement resilient
  coercion at the server boundary: capture malformed params, return a
  correctable error, never crash the agent loop. Test with real LLM
  callers, not just schema validators.
- **Applies to:** this repo's four tools (`get_eth_usd_price`,
  `solver_quote`, `erc8004_reputation`, `erc8004_validation_lookup`).
  Tool descriptions must stay plain descriptive text — no instructions,
  no links, no command-like content (see DC-1).
- **Verified:** the generated schemas were inspected directly
  (2026-11-12): all four are flat top-level objects whose properties
  are only `string`/`integer` — no `$defs`, `anyOf`, `oneOf`, `allOf`,
  `$ref`, or nested objects. `tests/test_design_constraints.py` pins
  this with `test_tool_input_schemas_are_flat` (asserts the property
  over the live `list_tools()` output) and `test_malformed_params_fail_correctably`
  (wrong-type / missing-arg calls raise a structured `ToolError`, and
  the server stays usable afterwards).

## DC-7 — Cache keys include user + session + resolved server config (DEVWATCH-445)

- **Source:** Langflow CVE-2026-12763 — the shared MCP tool cache key
  used only the MCP server display name ("Business Tools"), not
  user/session/flow/config, so User B could receive User A's cached MCP
  tool/client context. Affected OSS 1.0.0–1.11.5; fixed in 1.11.6+.
- **Rule:** Every cache key in shared agent infrastructure must include
  user + session + resolved server config. A two-user test (same server
  display name, different users) must assert no cross-user context leak.
  Pin Langflow >= 1.11.6 if used (not a dependency of this repo).
- **Applies to:** this repo's only cache — the solver snapshot cache in
  `solver_adapter.py`.
  - The cache (`_cache = {"snapshot", "at", "mode"}`) holds one global
    snapshot of **public Base pool state**, refreshed at most every
    `SINCOR_SNAPSHOT_CACHE_SECONDS` (30s). It is keyed by nothing and
    contains no caller, user, session, or server-config data — there is
    no per-user context anywhere in the quote path (the MCP server has
    no caller concept on stdio; the gateway's caller ID never reaches
    the solver). A cross-user leak through this cache is therefore
    impossible by construction: two callers always read the identical
    public snapshot.
  - The free-tier ledger (`freetier.py`) is per-caller state keyed by
    caller ID (`X-Caller-Id`, else payer address, else IP) — the correct
    shape for per-caller data, and its boundary is already covered by
    `tests/test_freetier_boundary.py`.
  - If a future cache ever holds per-user or per-server data, its key
    MUST be `(user, session, resolved server config)` — no exceptions.
- **Verified:** `tests/test_design_constraints.py::test_snapshot_cache_is_caller_independent`
  drives the live cache path with a counting reader: the second quote
  (different token pair, standing in for a second caller) reuses the
  cached snapshot (reader called once), returns snapshot-consistent
  results, and no caller identifier appears in any result. The cache
  dict is asserted to hold exactly the three fixed keys.
