"""402 challenge shape + full paid settle through the PUBLISHED
sincor-x402 package's local-reference rail."""
import base64
import json

import requests

from conftest import exhaust_caller

TREASURY = "0x09E2891432827D8835d2E9b83B25e2a5ba9612Ac"
USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
PAYER = "0x2222222222222222222222222222222222222222"


def _challenge(gateway, caller):
    resp = requests.get(f"{gateway}/v1/price/eth-usd",
                        headers={"X-Caller-Id": caller}, timeout=30)
    assert resp.status_code == 402, resp.text
    return resp.json()


def _payment_header(accepted, *, signature="0x" + "ab" * 65, value="10000",
                    to=TREASURY):
    payload = {
        "x402Version": 1, "scheme": "exact", "network": "base",
        "payload": {
            "signature": signature,
            "authorization": {"from": PAYER, "to": to, "value": value},
        },
        "accepted": accepted,
    }
    return base64.b64encode(json.dumps(payload).encode()).decode()


def test_challenge_shape(gateway):
    caller = "shape-caller"
    exhaust_caller(gateway, caller)
    body = _challenge(gateway, caller)
    assert body["x402Version"] == 1
    assert body["error"] == "payment_required"
    accepts = body["accepts"]
    assert len(accepts) == 1
    a = accepts[0]
    assert a["scheme"] == "exact"
    assert a["network"] == "base"
    assert a["maxAmountRequired"] == "10000"          # 0.01 USDC
    assert a["asset"] == USDC
    assert a["payTo"] == TREASURY
    assert a["extra"]["feeBps"] == 500                # 500 bps split
    assert a["extra"]["platformFeeAtomic"] == "500"
    assert a["extra"]["providerNetAtomic"] == "9500"
    assert a["extra"]["settlement"] == "local-reference"
    assert "escrow" in body and body["escrow"]["specHash"]
    assert body["escrow"]["scheme"] == "sincor-escrow-v1"


def test_paid_call_settles_via_reference_rail(gateway):
    caller = "paying-caller"
    exhaust_caller(gateway, caller)
    accepted = _challenge(gateway, caller)["accepts"][0]
    resp = requests.get(
        f"{gateway}/v1/price/eth-usd",
        headers={"X-Caller-Id": caller,
                 "X-PAYMENT": _payment_header(accepted)}, timeout=30)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["result"]["key"] == "base:eth_usd"
    assert body["verification"]["passed"] is True
    assert body["settlement"]["status"] == "released"
    assert "local-reference" in body["settlement"]["rail"]
    assert body["fee_split"]["platform_fee_atomic"] == 500
    assert body["fee_split"]["provider_net_atomic"] == 9500
    assert resp.headers.get("X-PAYMENT-RESPONSE")


def test_paid_quote_call(gateway):
    caller = "paying-quote-caller"
    exhaust_caller(gateway, caller)
    resp = requests.post(
        f"{gateway}/v1/solver/quote",
        json={"token_in": "USDC", "token_out": "WETH",
              "amount_in_atomic": "100000000"},
        headers={"X-Caller-Id": caller}, timeout=30)
    assert resp.status_code == 402
    accepted = resp.json()["accepts"][0]
    resp = requests.post(
        f"{gateway}/v1/solver/quote",
        json={"token_in": "USDC", "token_out": "WETH",
              "amount_in_atomic": "100000000"},
        headers={"X-Caller-Id": caller,
                 "X-PAYMENT": _payment_header(accepted)}, timeout=30)
    assert resp.status_code == 200, resp.text
    result = resp.json()["result"]
    assert result["signed"] is False
    assert resp.json()["settlement"]["status"] == "released"


def test_accepts_hedge_rejects_rewritten_terms(gateway):
    caller = "hedge-caller"
    exhaust_caller(gateway, caller)
    accepted = dict(_challenge(gateway, caller)["accepts"][0])
    accepted["maxAmountRequired"] = "1"  # client tries to rewrite the price
    resp = requests.get(
        f"{gateway}/v1/price/eth-usd",
        headers={"X-Caller-Id": caller,
                 "X-PAYMENT": _payment_header(accepted, value="1")},
        timeout=30)
    assert resp.status_code == 402
    assert resp.json()["error"] == "accepts_mismatch"


def test_facilitator_rejects_wrong_amount(gateway):
    caller = "wrong-amount-caller"
    exhaust_caller(gateway, caller)
    accepted = _challenge(gateway, caller)["accepts"][0]
    resp = requests.get(
        f"{gateway}/v1/price/eth-usd",
        headers={"X-Caller-Id": caller,
                 "X-PAYMENT": _payment_header(accepted, value="9999")},
        timeout=30)
    assert resp.status_code == 402
    assert resp.json()["error"] == "payment_verification_failed"


def test_gateway_health_and_index(gateway):
    resp = requests.get(f"{gateway}/health", timeout=10)
    assert resp.status_code == 200
    assert resp.json()["free_calls_per_day"] == 10
    assert "local-reference" in resp.json()["settlement"]
