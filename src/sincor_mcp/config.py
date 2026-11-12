"""Environment-driven configuration. Every path has a default pointing
at the component's real location on this machine; every value can be
overridden by env var (the registry listings use these same vars)."""
from __future__ import annotations

import os
from pathlib import Path

HOME = Path.home()


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


# --- capability 1: price monitors -------------------------------------
PRICE_MONITORS_PATH = Path(_env(
    "SINCOR_PRICE_MONITORS_PATH", str(HOME / "workspace" / "price-monitors")))
PRICE_MONITORS_DB = Path(_env(
    "SINCOR_PRICE_MONITORS_DB", str(PRICE_MONITORS_PATH / "state" / "price_monitors.db")))
ETH_USD_KEY = "base:eth_usd"

# --- capability 2: solver quoting engine -------------------------------
SOLVER_SRC = Path(_env(
    "SINCOR_SOLVER_SRC", str(HOME / "workspace" / "sincor2-solver-wt" / "src")))
# "live" (default: read Base mainnet pool state via public RPC),
# "fixture" (deterministic local fixture snapshot — tests/demos only).
SOLVER_SNAPSHOT_MODE = _env("SINCOR_SOLVER_SNAPSHOT", "live").strip().lower()
SNAPSHOT_CACHE_SECONDS = int(_env("SINCOR_SNAPSHOT_CACHE_SECONDS", "30"))

# --- capability 3: ERC-8004 oracle --------------------------------------
ORACLE_ARTIFACT = Path(_env(
    "SINCOR_ORACLE_ARTIFACT",
    str(HOME / "workspace" / "sincor2-erc8004" / "out"
        / "SincorValidationReputationOracle.sol"
        / "SincorValidationReputationOracle.json")))
# Optional configured mode: if BOTH are set, reputation/validation reads
# go to this deployed instance instead of the local-reference deployment.
ORACLE_RPC_URL = _env("SINCOR_ORACLE_RPC_URL", "")
ORACLE_ADDRESS = _env("SINCOR_ORACLE_ADDRESS", "")

# --- paywall -------------------------------------------------------------
# SINCOR Treasury (receives the platform-fee split; also the payTo).
PAY_TO = _env("SINCOR_PAY_TO", "0x09E2891432827D8835d2E9b83B25e2a5ba9612Ac")
PRICE_ATOMIC = int(_env("SINCOR_PRICE_ATOMIC", "10000"))        # 0.01 USDC (6 dp)
FEE_BPS = int(_env("SINCOR_FEE_BPS", "500"))                    # 5% platform fee (canon)
FREE_CALLS_PER_DAY = int(_env("SINCOR_FREE_CALLS_PER_DAY", "10"))
USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"

STATE_DIR = Path(_env(
    "SINCOR_MCP_STATE_DIR",
    str(Path(__file__).resolve().parents[2] / "state")))

GATEWAY_HOST = _env("SINCOR_GATEWAY_HOST", "127.0.0.1")
GATEWAY_PORT = int(_env("SINCOR_GATEWAY_PORT", "8402"))
