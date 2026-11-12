"""HTTP gateway — the same four capabilities behind the sincor-x402
paywall, using the PUBLISHED ``sincor-x402==0.1.0`` package.

Call flow per capability route:

1. First ``FREE_CALLS_PER_DAY`` (10) calls per caller ID per UTC day
   are served free (counted by the free-tier ledger).
2. From call 11 the request enters the package's ``VerifiedEndpoint``:
   no ``X-PAYMENT`` header -> the package's own HTTP 402 challenge
   (accepts[] priced 0.01 USDC, 500 bps platform-fee split in extra).
3. With ``X-PAYMENT`` the package runs its full rail: accepts[] hedge
   -> facilitator verify -> escrow hold -> execute -> verify ->
   SEAL release / refund.

SETTLEMENT HONESTY: settlement runs through the package's labelled
LOCAL REFERENCE facilitator/escrow (``LocalFacilitator`` /
``LocalReferencePlatform``). It is NOT on-chain, uses NO mainnet, NO
real keys and NO CDP. This stays the labelled reference path until the
founder's CDP facilitator decision lands.

Caller ID: ``X-Caller-Id`` header, else the payer address inside a
presented X-PAYMENT authorization, else the client IP.

Run: ``sincor-mcp-gateway`` (binds SINCOR_GATEWAY_HOST:PORT, default
127.0.0.1:8402).
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from sincor_x402 import PaymentRequirement, VerifiedEndpoint
from sincor_x402.server import decode_payment_header

from . import capabilities, config
from .errors import CapabilityError
from .freetier import FreeTierLedger

FEE_ATOMIC = config.PRICE_ATOMIC * config.FEE_BPS // 10_000
NET_ATOMIC = config.PRICE_ATOMIC - FEE_ATOMIC

SETTLEMENT_LABEL = ("local-reference (sincor-x402==0.1.0 labelled "
                    "reference facilitator/escrow — NOT on-chain)")


def _requirement(resource: str, description: str) -> PaymentRequirement:
    return PaymentRequirement(
        scheme="exact",
        network="base",
        max_amount_required=str(config.PRICE_ATOMIC),
        asset=config.USDC_BASE,
        pay_to=config.PAY_TO,
        max_timeout_seconds=60,
        resource=resource,
        description=description,
        extra={
            "feeBps": config.FEE_BPS,
            "platformFeeAtomic": str(FEE_ATOMIC),
            "providerNetAtomic": str(NET_ATOMIC),
            "feeRecipient": config.PAY_TO,
            "settlement": "local-reference",
            "settlementNote": (
                "Settled via the sincor-x402 package's LOCAL REFERENCE "
                "facilitator/escrow. Not on-chain; no mainnet settlement "
                "until the founder's CDP facilitator decision lands."),
        },
    )


def build_endpoints() -> dict:
    """One VerifiedEndpoint per capability (shared escrow state)."""
    return {
        "price": VerifiedEndpoint(
            lambda **kw: capabilities.get_eth_usd_price(),
            requirement=_requirement(
                "/v1/price/eth-usd", "SINCOR Base ETH/USD price feed"),
            spec={"required_keys": ["key", "value", "source", "age_seconds"],
                  "predicate": "is_dict"},
            timeout_seconds=30),
        "quote": VerifiedEndpoint(
            lambda **kw: capabilities.solver_quote(**kw),
            requirement=_requirement(
                "/v1/solver/quote", "SINCOR unsigned solver quote"),
            spec={"required_keys": ["quote_id", "signed", "amount_out_net"],
                  "predicate": "is_dict"},
            timeout_seconds=120),
        "reputation": VerifiedEndpoint(
            lambda **kw: capabilities.erc8004_reputation(**kw),
            requirement=_requirement(
                "/v1/oracle/reputation", "SINCOR ERC-8004 reputation lookup"),
            spec={"required_keys": ["agent", "score", "successes",
                                    "failures", "total"],
                  "predicate": "is_dict"},
            timeout_seconds=30),
        "validation": VerifiedEndpoint(
            lambda **kw: capabilities.erc8004_validation_lookup(**kw),
            requirement=_requirement(
                "/v1/oracle/validation", "SINCOR ERC-8004 validation lookup"),
            spec={"required_keys": ["task_id", "attestation_key", "seen"],
                  "predicate": "is_dict"},
            timeout_seconds=30),
    }


def _prepare_quote(kw: dict) -> dict:
    out = {}
    for key in ("token_in", "token_out", "amount_in_atomic"):
        if key in kw:
            out[key] = kw[key]
    for key in ("deadline_seconds", "slippage_bps"):
        if key in kw:
            try:
                out[key] = int(kw[key])
            except (TypeError, ValueError):
                raise CapabilityError("bad_request", f"{key} must be an integer")
    return out


# route -> (capability key, capability fn, kwargs preparer)
ROUTES = {
    ("GET", "/v1/price/eth-usd"): (
        "price", capabilities.get_eth_usd_price, lambda kw: {}),
    ("POST", "/v1/solver/quote"): (
        "quote", capabilities.solver_quote, _prepare_quote),
    ("GET", "/v1/oracle/reputation"): (
        "reputation", capabilities.erc8004_reputation,
        lambda kw: {"agent_address": kw.get("agent", "")}),
    ("GET", "/v1/oracle/validation"): (
        "validation", capabilities.erc8004_validation_lookup,
        lambda kw: {"task_id": kw.get("task_id", ""),
                    "sigil_commitment": kw.get("sigil_commitment", "")}),
}


class _Handler(BaseHTTPRequestHandler):
    server_version = "sincor-mcp-gateway/0.1"
    endpoints: dict = {}
    ledger: FreeTierLedger = None  # set by make_server

    # -- plumbing ------------------------------------------------------
    def log_message(self, *args):  # keep stdout clean
        pass

    def _send(self, status: int, body: dict, headers: dict | None = None):
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(raw)

    def _caller_id(self) -> str:
        caller = self.headers.get("X-Caller-Id")
        if caller:
            return caller.strip()
        raw = self.headers.get("X-PAYMENT")
        if raw:
            try:
                payload = decode_payment_header(raw)
                payer = (payload.get("payload") or {}).get(
                    "authorization", {}).get("from")
                if payer:
                    return f"payer:{payer}"
            except Exception:
                pass
        return f"ip:{self.client_address[0]}"

    def _has_payment(self) -> bool:
        return bool(self.headers.get("X-PAYMENT")
                    or self.headers.get("Payment-Signature"))

    # -- request handling ------------------------------------------------
    def _handle(self, method: str):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        if method == "GET" and path == "/health":
            return self._send(200, {
                "ok": True, "service": "sincor-mcp-gateway",
                "settlement": SETTLEMENT_LABEL,
                "free_calls_per_day": config.FREE_CALLS_PER_DAY,
                "price_atomic": config.PRICE_ATOMIC, "fee_bps": config.FEE_BPS})
        if method == "GET" and path == "/":
            return self._send(200, {
                "service": "sincor-mcp-gateway",
                "routes": sorted(f"{m} {p}" for (m, p) in ROUTES),
                "paywall": "first 10 calls/day per caller free, then "
                           "x402 402 challenge at 0.01 USDC (500 bps fee)",
                "settlement": SETTLEMENT_LABEL})

        route = ROUTES.get((method, path))
        if route is None:
            return self._send(404, {"ok": False, "error": "not_found",
                                    "path": path})
        cap_key, free_fn, prepare = route

        # raw kwargs: JSON body (POST) or query params (GET)
        if method == "POST":
            try:
                length = int(self.headers.get("Content-Length") or 0)
                raw_kwargs = json.loads(self.rfile.read(length) or b"{}")
                if not isinstance(raw_kwargs, dict):
                    raise ValueError("body must be a JSON object")
            except (ValueError, json.JSONDecodeError) as exc:
                return self._send(400, {"ok": False, "error": "bad_request",
                                        "detail": str(exc)})
        else:
            raw_kwargs = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        try:
            kwargs = prepare(raw_kwargs)
        except CapabilityError as exc:
            return self._send(exc.http_status,
                              {"ok": False, "error": exc.code,
                               "detail": exc.message})

        caller = self._caller_id()

        # Free path — only when the caller is not presenting payment.
        if not self._has_payment() and self.ledger.consume(caller):
            try:
                result = free_fn(**kwargs)
            except CapabilityError as exc:
                return self._send(exc.http_status,
                                  {"ok": False, "error": exc.code,
                                   "detail": exc.message})
            return self._send(200, {"ok": True, "result": result}, {
                "X-Sincor-Free-Tier": "true",
                "X-Sincor-Free-Remaining": str(self.ledger.remaining(caller)),
            })

        # Paywall path — the published package runs the whole rail.
        endpoint = self.endpoints[cap_key]
        resp = endpoint.handle(
            headers={k: v for k, v in self.headers.items()}, kwargs=kwargs)
        body = dict(resp.body)
        if resp.status == 200:
            body["fee_split"] = {
                "fee_bps": config.FEE_BPS,
                "gross_atomic": config.PRICE_ATOMIC,
                "platform_fee_atomic": FEE_ATOMIC,
                "provider_net_atomic": NET_ATOMIC,
                "fee_recipient": config.PAY_TO,
            }
            body["settlement_rail"] = SETTLEMENT_LABEL
        headers = dict(resp.headers)
        headers["X-Sincor-Free-Tier"] = "false"
        return self._send(resp.status, body, headers)

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")


def make_server(host: str, port: int, ledger: FreeTierLedger | None = None,
                endpoints: dict | None = None) -> ThreadingHTTPServer:
    handler = type("BoundHandler", (_Handler,), {
        "endpoints": endpoints if endpoints is not None else build_endpoints(),
        "ledger": ledger if ledger is not None else FreeTierLedger(),
    })
    return ThreadingHTTPServer((host, port), handler)


def main() -> None:
    server = make_server(config.GATEWAY_HOST, config.GATEWAY_PORT)
    host, port = server.server_address[:2]
    print(f"sincor-mcp-gateway on http://{host}:{port} — "
          f"10 free calls/day/caller, then 0.01 USDC x402 "
          f"(fee {config.FEE_BPS} bps); settlement: {SETTLEMENT_LABEL}")
    server.serve_forever()


if __name__ == "__main__":
    main()
