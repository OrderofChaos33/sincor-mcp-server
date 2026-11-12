"""Solver adapter — wraps the SINCOR solver quoting engine.

Quotes are UNSIGNED measurements from the paper/shadow solver
(``signed: False``, ``signature: None`` — always). Snapshot sources:

- ``live``    (default) Base mainnet pool state read via public RPC by
              the engine's own BasePoolReader, cached briefly.
- ``fixture`` deterministic local fixture snapshot (tests/demos only,
              labelled as such in every quote it produces).
- an injected provider (unit tests).
"""
from __future__ import annotations

import re
import sys
import threading
import time

from . import config
from .errors import CapabilityError

_lock = threading.Lock()
_cache: dict = {"snapshot": None, "at": 0.0, "mode": None}
_provider = None  # test injection: callable() -> PoolSnapshot


def set_snapshot_provider(fn) -> None:
    global _provider
    _provider = fn


def _import_solver():
    path = str(config.SOLVER_SRC)
    if path not in sys.path:
        sys.path.insert(0, path)
    try:
        from sincor2.solver import pools, quote_engine
        from sincor2.solver.pool_reader import BasePoolReader
    except ImportError as exc:
        raise CapabilityError(
            "unavailable", f"solver package not importable from {path}: {exc}")
    return pools, quote_engine, BasePoolReader


def build_fixture_snapshot():
    """Deterministic fixture snapshot built from the engine's own pool
    dataclasses (mirrors the solver suite's fixture approach). NOT live
    chain state — used for tests and offline demos only."""
    pools, _, _ = _import_solver()
    return pools.PoolSnapshot(
        block_number=0,
        gas_price_wei=6_000_000,  # 0.006 gwei, sampled Base gas 2026-11-11
        pools=(
            pools.V2PoolState(
                venue=pools.VENUE_UNISWAP_V2,
                address="0x000000000000000000000000000000000000F001",
                token0=pools.WETH, token1=pools.USDC,
                reserve0=500 * 10**18, reserve1=1_022_500 * 10**6,
                fee_bps=30),
            pools.V2PoolState(
                venue=pools.VENUE_AERODROME,
                address="0x000000000000000000000000000000000000F002",
                token0=pools.AXM, token1=pools.WETH,
                reserve0=2_000_000 * 10**18, reserve1=250 * 10**18,
                fee_bps=30),
        ),
    )


def _get_snapshot():
    """Return (snapshot, mode_label)."""
    if _provider is not None:
        return _provider(), "injected"
    if config.SOLVER_SNAPSHOT_MODE == "fixture":
        return build_fixture_snapshot(), "fixture"
    now = time.time()
    with _lock:
        if (_cache["snapshot"] is not None
                and now - _cache["at"] < config.SNAPSHOT_CACHE_SECONDS):
            return _cache["snapshot"], "live"
    _, _, BasePoolReader = _import_solver()
    try:
        snap = BasePoolReader().snapshot()
    except Exception as exc:
        with _lock:
            if _cache["snapshot"] is not None:
                return _cache["snapshot"], "live-stale-cache"
        raise CapabilityError(
            "unavailable", f"live Base pool snapshot failed: {exc}")
    with _lock:
        _cache.update(snapshot=snap, at=now, mode="live")
    return snap, "live"


def _resolve_token(pools, token: str) -> str:
    symbol_to_addr = {sym: addr for addr, sym in pools.TOKEN_SYMBOLS.items()}
    if token.upper() in symbol_to_addr:
        return symbol_to_addr[token.upper()]
    if not re.fullmatch(r"0x[0-9a-fA-F]{40}", token.strip()):
        raise CapabilityError(
            "bad_request",
            f"unknown token {token!r}: use a symbol "
            f"({', '.join(sorted(symbol_to_addr))}) or a 0x address")
    return pools.checksum(token)


def quote(token_in: str, token_out: str, amount_in_atomic,
          deadline_seconds: int = 120, slippage_bps: int = 50) -> dict:
    pools, quote_engine, _ = _import_solver()
    tin = _resolve_token(pools, token_in)
    tout = _resolve_token(pools, token_out)
    try:
        amount = int(amount_in_atomic)
    except (TypeError, ValueError):
        raise CapabilityError("bad_request",
                              "amount_in_atomic must be an integer string")
    if amount <= 0:
        raise CapabilityError("bad_request", "amount_in_atomic must be > 0")
    snap, mode = _get_snapshot()
    quoter = quote_engine.SolverQuoter(snap)
    now = int(time.time())
    try:
        result = quoter.quote(
            tin, tout, amount, deadline=now + int(deadline_seconds),
            slippage_bps=int(slippage_bps), now=now)
    except quote_engine.NoRouteError as exc:
        raise CapabilityError("not_found", str(exc))
    except quote_engine.IntentExpiredError as exc:
        raise CapabilityError("bad_request", str(exc))
    result["snapshot_mode"] = mode
    result["honesty"] = ("UNSIGNED paper quote from public pool state. "
                         "signed is always false; nothing can be submitted "
                         "from a quote.")
    return result
