"""Design-constraint regressions (DEVWATCH-426/429/431/433/441/442/445).

- DC-6 (DEVWATCH-442): tool input schemas stay flat/minimal; malformed
  params fail with a structured, correctable error and the server stays
  usable afterwards.
- DC-7 (DEVWATCH-445): the solver snapshot cache holds public pool state
  only — no per-user/per-caller data can leak across callers.
- DC-5 (DEVWATCH-441): requirements.lock pins every direct dependency
  to its installed version.
"""
import asyncio
import json
from importlib import metadata
from pathlib import Path

import pytest

from sincor_mcp import solver_adapter
from sincor_mcp.mcp_server import mcp

ROOT = Path(__file__).resolve().parents[1]

# Flat JSON-schema primitives an LLM caller can satisfy without $defs,
# unions, or nested objects (DEVWATCH-442).
_FLAT_TYPES = {"string", "integer", "number", "boolean"}
_FORBIDDEN_SCHEMA_KEYS = {"$defs", "$ref", "anyOf", "oneOf", "allOf", "not",
                          "if", "then", "else"}


def _walk_schema(node, path="root"):
    """Yield (path, node) for every dict in a JSON schema."""
    if isinstance(node, dict):
        yield path, node
        for key, val in node.items():
            yield from _walk_schema(val, f"{path}.{key}")
    elif isinstance(node, list):
        for i, val in enumerate(node):
            yield from _walk_schema(val, f"{path}[{i}]")


def test_tool_input_schemas_are_flat():
    """DC-6: every registered tool schema is a flat top-level object of
    primitive properties — no $defs, unions, refs, or nested objects."""
    tools = asyncio.run(mcp.list_tools())
    assert {t.name for t in tools} == {
        "get_eth_usd_price", "solver_quote",
        "erc8004_reputation", "erc8004_validation_lookup",
    }
    for tool in tools:
        schema = tool.inputSchema
        assert schema.get("type") == "object", tool.name
        for path, node in _walk_schema(schema):
            assert not (_FORBIDDEN_SCHEMA_KEYS & set(node)), \
                f"{tool.name}: forbidden schema key at {path}: {node}"
            assert "$ref" not in json.dumps(node), \
                f"{tool.name}: $ref at {path}"
        for prop, subschema in schema.get("properties", {}).items():
            assert subschema.get("type") in _FLAT_TYPES, \
                f"{tool.name}.{prop}: non-flat type {subschema!r}"
            assert "properties" not in subschema, \
                f"{tool.name}.{prop}: nested object properties"


def test_malformed_params_fail_correctably():
    """DC-6: wrong-type / missing-arg calls raise a structured validation
    error (ToolError), not a crash — and the server stays usable after."""
    async def _run():
        errors = []
        for name, args in [
            ("solver_quote", {"token_in": "USDC", "token_out": "WETH",
                              "amount_in_atomic": "100000000",
                              "deadline_seconds": "not-an-int"}),
            ("solver_quote", {"token_in": "USDC", "token_out": "WETH"}),
            ("erc8004_reputation", {"agent_address": 12345}),
        ]:
            try:
                await mcp.call_tool(name, args)
            except Exception as exc:  # noqa: BLE001 — asserting on shape
                errors.append(exc)
            else:
                raise AssertionError(f"{name} {args} unexpectedly succeeded")
        return errors

    errors = asyncio.run(_run())
    assert len(errors) == 3
    for exc in errors:
        assert type(exc).__name__ == "ToolError", type(exc).__name__
        assert "validation error" in str(exc).lower(), str(exc)[:200]

    # Server still usable afterwards (same process, same server object).
    result = asyncio.run(mcp.call_tool("get_eth_usd_price", {}))
    assert result, "expected a price result after the malformed calls"
    assert "base:eth_usd" in result[0].text


def _all_dict_keys(node):
    if isinstance(node, dict):
        for key, val in node.items():
            yield key
            yield from _all_dict_keys(val)
    elif isinstance(node, list):
        for val in node:
            yield from _all_dict_keys(val)


def test_snapshot_cache_is_caller_independent(monkeypatch):
    """DC-7: the solver snapshot cache is one shared public-pool-state
    snapshot. A second quote (different token pair, standing in for a
    second caller) reuses the cached snapshot — the reader runs once —
    and no caller/user/session key appears in any result."""
    pools, quote_engine, _ = solver_adapter._import_solver()
    snapshot = solver_adapter.build_fixture_snapshot()
    calls = []

    class _CountingReader:
        def snapshot(self):
            calls.append(1)
            return snapshot

    monkeypatch.setattr(solver_adapter, "_provider", None)
    monkeypatch.setattr(solver_adapter, "_cache",
                        {"snapshot": None, "at": 0.0, "mode": None})
    monkeypatch.setattr(solver_adapter, "_import_solver",
                        lambda: (pools, quote_engine, _CountingReader))
    monkeypatch.setattr(solver_adapter.config, "SOLVER_SNAPSHOT_MODE", "live")
    monkeypatch.setattr(solver_adapter.config, "SNAPSHOT_CACHE_SECONDS", 3600)

    q1 = solver_adapter.quote("USDC", "WETH", "100000000")
    q2 = solver_adapter.quote("USDC", "WETH", "100000000")
    # Second caller, different pair — still the same cached snapshot.
    q_other = solver_adapter.quote("AXM", "USDC", str(1_000 * 10**18))

    assert len(calls) == 1, "snapshot reader must run once; cache must serve"
    # quote_id is a fresh random UUID per quote — compare everything else.
    q1_body = {k: v for k, v in q1.items() if k != "quote_id"}
    q2_body = {k: v for k, v in q2.items() if k != "quote_id"}
    assert q1_body == q2_body
    assert q1["snapshot_mode"] == "live"
    assert q_other["snapshot_mode"] == "live"
    assert set(solver_adapter._cache) == {"snapshot", "at", "mode"}
    for result in (q1, q2, q_other):
        keys = {k.lower() for k in _all_dict_keys(result)}
        assert not (keys & {"caller", "caller_id", "user", "user_id",
                            "session", "session_id"}), keys


def test_lockfile_pins_match_installed():
    """DC-5: requirements.lock pins every direct dependency to exactly
    the version installed in this environment (transitive deps pinned
    alongside)."""
    lockfile = ROOT / "requirements.lock"
    assert lockfile.is_file(), "requirements.lock missing (DEVWATCH-441)"
    pinned = {}
    for line in lockfile.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "==" not in line:
            continue
        name, version = line.split("==", 1)
        pinned[name.strip().lower().replace("_", "-")] = version.strip()
    assert len(pinned) > 50, f"lockfile looks unpinned/sparse: {len(pinned)}"
    for dist in ("mcp", "web3", "requests", "eth-abi", "sincor-x402",
                 "pytest", "eth-tester", "py-evm"):
        key = dist.lower().replace("_", "-")
        assert key in pinned, f"{dist} not pinned in requirements.lock"
        assert pinned[key] == metadata.version(dist), \
            f"{dist}: lockfile {pinned[key]} != installed " \
            f"{metadata.version(dist)}"
