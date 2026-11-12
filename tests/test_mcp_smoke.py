"""MCP handshake smoke: run the packaged smoke script, which spawns the
real stdio server and drives it with the official MCP client
(initialize + tools/list + one call per tool)."""
import subprocess
import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_mcp_smoke_script():
    proc = subprocess.run(
        [sys.executable, os.path.join(ROOT, "scripts", "smoke_mcp.py")],
        capture_output=True, text=True, timeout=300, cwd=ROOT)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "initialize OK" in proc.stdout
    assert "tools/list OK" in proc.stdout
    assert "SMOKE PASSED" in proc.stdout
    for tool in ("get_eth_usd_price", "solver_quote", "erc8004_reputation",
                 "erc8004_validation_lookup"):
        assert f"call {tool} OK" in proc.stdout
