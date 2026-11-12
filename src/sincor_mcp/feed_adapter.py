"""Price-feed adapter — wraps the price-monitors read-only Feed API.

The Feed opens the monitors' SQLite store with ``mode=ro``; this adapter
never writes to that DB (a fresh Feed per call also means callers always
see the freshest observation the monitor runner has written).
"""
from __future__ import annotations

import sys

from . import config
from .errors import CapabilityError


def _load_feed_class():
    path = str(config.PRICE_MONITORS_PATH)
    if path not in sys.path:
        sys.path.insert(0, path)
    try:
        from price_monitors.feed import Feed
    except ImportError as exc:
        raise CapabilityError(
            "unavailable",
            f"price_monitors package not importable from {path}: {exc}")
    return Feed


def latest_eth_usd() -> dict:
    """Freshest Base ETH/USD observation across all monitor sources."""
    Feed = _load_feed_class()
    feed = Feed(config.PRICE_MONITORS_DB)
    try:
        if not feed.available:
            raise CapabilityError(
                "unavailable",
                f"price monitor store not found at {config.PRICE_MONITORS_DB}")
        latest = feed.latest(config.ETH_USD_KEY)
        if latest is None:
            raise CapabilityError(
                "not_found",
                f"no observations recorded for {config.ETH_USD_KEY} yet")
        per_source = feed.latest_per_source(config.ETH_USD_KEY)
        return {
            "key": latest["key"],
            "value": latest["value"],
            "source": latest["source"],
            "kind": latest["kind"],
            "ts": latest["ts"],
            "age_seconds": latest["age_seconds"],
            "per_source": {
                src: {"value": obs["value"], "age_seconds": obs["age_seconds"],
                      "ts": obs["ts"]}
                for src, obs in per_source.items() if obs
            },
            "feed": "sincor price-monitors (Uniswap V3 pool state x2 RPC + "
                    "Chainlink cross-check), read-only",
        }
    finally:
        feed.close()
