import os
import sys
import threading

# Deterministic solver snapshot for the whole suite (fixture pools).
os.environ.setdefault("SINCOR_SOLVER_SNAPSHOT", "fixture")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest  # noqa: E402


@pytest.fixture(scope="session")
def gateway(tmp_path_factory):
    """The real gateway on an ephemeral port, default free-tier limit."""
    from sincor_mcp.freetier import FreeTierLedger
    from sincor_mcp.gateway import make_server

    state = tmp_path_factory.mktemp("gw-state") / "free_tier.json"
    server = make_server("127.0.0.1", 0, ledger=FreeTierLedger(path=state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    yield f"http://{host}:{port}"
    server.shutdown()


def exhaust_caller(base_url: str, caller: str, limit: int = 10):
    """Burn a caller's free quota with cheap price calls."""
    import requests
    for _ in range(limit):
        resp = requests.get(f"{base_url}/v1/price/eth-usd",
                            headers={"X-Caller-Id": caller}, timeout=30)
        assert resp.status_code == 200, resp.text
