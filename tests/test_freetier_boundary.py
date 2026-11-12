"""Free-tier boundary: call 10 is free, call 11 returns HTTP 402."""
import requests

from sincor_mcp.freetier import FreeTierLedger
from conftest import exhaust_caller


def test_ledger_boundary_unit(tmp_path):
    ledger = FreeTierLedger(path=tmp_path / "ft.json", limit=10)
    assert ledger.remaining("alice") == 10
    for i in range(10):
        assert ledger.consume("alice") is True, f"call {i + 1} should be free"
    assert ledger.remaining("alice") == 0
    assert ledger.consume("alice") is False, "call 11 must not be free"
    # per-caller isolation
    assert ledger.consume("bob") is True
    assert ledger.remaining("bob") == 9


def test_ledger_persists_across_instances(tmp_path):
    path = tmp_path / "ft.json"
    FreeTierLedger(path=path, limit=10).consume("alice")
    assert FreeTierLedger(path=path, limit=10).remaining("alice") == 9


def test_gateway_call_10_free_call_11_is_402(gateway):
    caller = "boundary-caller"
    for i in range(10):
        resp = requests.get(f"{gateway}/v1/price/eth-usd",
                            headers={"X-Caller-Id": caller}, timeout=30)
        assert resp.status_code == 200, f"call {i + 1}: {resp.text}"
        assert resp.headers.get("X-Sincor-Free-Tier") == "true"
        assert resp.json()["ok"] is True
    resp = requests.get(f"{gateway}/v1/price/eth-usd",
                        headers={"X-Caller-Id": caller}, timeout=30)
    assert resp.status_code == 402, resp.text
    # a different caller still has a full free quota
    resp = requests.get(f"{gateway}/v1/price/eth-usd",
                        headers={"X-Caller-Id": "someone-else"}, timeout=30)
    assert resp.status_code == 200
    assert resp.headers.get("X-Sincor-Free-Remaining") == "9"


def test_free_quota_shared_across_routes(gateway):
    caller = "cross-route-caller"
    exhaust_caller(gateway, caller)
    resp = requests.get(
        f"{gateway}/v1/oracle/reputation",
        params={"agent": "0x1111111111111111111111111111111111111111"},
        headers={"X-Caller-Id": caller}, timeout=30)
    assert resp.status_code == 402, resp.text
