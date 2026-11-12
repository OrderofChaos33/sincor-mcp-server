"""Happy paths: every capability against its real local data source.

- price feed  -> the real price_monitors.db the monitor runner writes
- solver      -> the real solver engine (deterministic fixture snapshot)
- oracle      -> the real compiled oracle on the local-reference chain
"""
import pytest
from web3 import Web3

from sincor_mcp import capabilities
from sincor_mcp.errors import CapabilityError

DEMO_AGENT = "0x1111111111111111111111111111111111111111"


def test_price_feed_real_db():
    out = capabilities.get_eth_usd_price()
    assert out["key"] == "base:eth_usd"
    assert out["value"] > 0
    assert out["source"] in {"chainlink_base", "base_rpc_primary",
                             "base_rpc_fallback"}
    assert out["age_seconds"] >= 0
    assert out["per_source"], "expected at least one per-source observation"


def test_solver_quote_unsigned_with_fee_breakdown():
    q = capabilities.solver_quote("USDC", "WETH", "100000000")
    assert q["signed"] is False and q["signature"] is None
    assert q["mode"] == "PAPER"
    assert len(q["route"]) == 1
    fee = q["fees"]["platform_fee_amount"]
    assert q["fees"]["platform_fee_bps"] == 500
    assert fee == q["amount_out_gross"] * 500 // 10_000
    assert q["amount_out_net"] == q["amount_out_gross"] - fee
    assert q["snapshot_mode"] == "fixture"


def test_solver_quote_two_hop():
    q = capabilities.solver_quote("AXM", "USDC", str(1_000 * 10**18))
    assert len(q["route"]) == 2
    assert q["route"][0]["amount_out"] == q["route"][1]["amount_in"]


def test_solver_quote_by_address():
    q = capabilities.solver_quote(
        "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
        "0x4200000000000000000000000000000000000006", "50000000")
    assert q["amount_out_net"] > 0


def test_solver_bad_inputs():
    with pytest.raises(CapabilityError) as exc:
        capabilities.solver_quote("DOGE", "WETH", "1000")
    assert exc.value.code == "bad_request"
    with pytest.raises(CapabilityError) as exc:
        capabilities.solver_quote("USDC", "WETH", "not-a-number")
    assert exc.value.code == "bad_request"
    with pytest.raises(CapabilityError) as exc:
        capabilities.solver_quote("USDC", "SINC", "1000")  # no fixture route
    assert exc.value.code == "not_found"


def test_oracle_reputation_demo_agent():
    r = capabilities.erc8004_reputation(DEMO_AGENT)
    assert (r["successes"], r["failures"], r["total"]) == (2, 1, 3)
    assert r["score"] == 10  # +10 +10 -10 per the contract's deltas
    assert r["attestation_count"] == 3
    assert r["oracle"]["backend"] == "local-reference"
    assert r["oracle"]["mainnet_deployed"] is False


def test_oracle_reputation_unknown_agent_is_zero():
    r = capabilities.erc8004_reputation(
        "0x2222222222222222222222222222222222222222")
    assert (r["score"], r["successes"], r["failures"], r["total"]) == (0, 0, 0, 0)


def test_oracle_validation_lookup():
    task_id = "0x" + Web3.keccak(text="sincor-mcp-demo-task-1").hex()
    sigil = "0x" + Web3.keccak(text="sincor-mcp-demo-sigil-1").hex()
    seen = capabilities.erc8004_validation_lookup(task_id, sigil)
    assert seen["seen"] is True
    unseen = capabilities.erc8004_validation_lookup("0x" + "00" * 32,
                                                    "0x" + "11" * 32)
    assert unseen["seen"] is False


def test_oracle_bad_inputs():
    with pytest.raises(CapabilityError) as exc:
        capabilities.erc8004_reputation("not-an-address")
    assert exc.value.code == "bad_request"
    with pytest.raises(CapabilityError) as exc:
        capabilities.erc8004_validation_lookup("0x1234", "0x" + "11" * 32)
    assert exc.value.code == "bad_request"
