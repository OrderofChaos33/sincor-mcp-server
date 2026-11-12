"""The four capabilities, shared verbatim by the MCP server and the
HTTP gateway so both surfaces return identical payloads."""
from __future__ import annotations

from . import feed_adapter, oracle_adapter, solver_adapter
from .errors import CapabilityError


def get_eth_usd_price() -> dict:
    """Latest Base ETH/USD from the price-monitor feed (with source+age)."""
    return feed_adapter.latest_eth_usd()


def solver_quote(token_in: str, token_out: str, amount_in_atomic: str,
                 deadline_seconds: int = 120,
                 slippage_bps: int = 50) -> dict:
    """Unsigned solver quote (signed:false — a measurement, not an order)."""
    return solver_adapter.quote(token_in, token_out, amount_in_atomic,
                                deadline_seconds=deadline_seconds,
                                slippage_bps=slippage_bps)


def _parse_address(agent: str) -> str:
    try:
        from web3 import Web3
    except ImportError as exc:
        raise CapabilityError("unavailable", f"web3 not installed: {exc}")
    if not Web3.is_address(agent):
        raise CapabilityError("bad_request", f"invalid address: {agent!r}")
    return Web3.to_checksum_address(agent)


def _parse_bytes32(value: str, field: str) -> bytes:
    raw = value[2:] if value.startswith(("0x", "0X")) else value
    try:
        data = bytes.fromhex(raw)
    except ValueError:
        raise CapabilityError("bad_request", f"{field} must be hex bytes32")
    if len(data) != 32:
        raise CapabilityError(
            "bad_request", f"{field} must be exactly 32 bytes, got {len(data)}")
    return data


def erc8004_reputation(agent_address: str) -> dict:
    """ERC-8004 reputation lookup for one agent address."""
    return oracle_adapter.reputation(_parse_address(agent_address))


def erc8004_validation_lookup(task_id: str, sigil_commitment: str) -> dict:
    """ERC-8004 validation lookup: has this (taskId, SIGIL commitment)
    attestation been recorded on the oracle?"""
    return oracle_adapter.validation_lookup(
        _parse_bytes32(task_id, "task_id"),
        _parse_bytes32(sigil_commitment, "sigil_commitment"))
