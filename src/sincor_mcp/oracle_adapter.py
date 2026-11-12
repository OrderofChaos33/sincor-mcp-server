"""ERC-8004 oracle adapter — read-only validation/reputation queries.

HONESTY CONTRACT: the SincorValidationReputationOracle contract is NOT
deployed on Base mainnet. Two read backends exist:

- ``local-reference`` (default): the real compiled oracle bytecode from
  the ERC-8004 worktree's Foundry artifacts, deployed on an in-process
  eth-tester chain and seeded with clearly-labelled DEMO attestations.
  Real contract logic, local chain, zero mainnet presence.
- ``configured-rpc``: only when the operator sets SINCOR_ORACLE_RPC_URL
  + SINCOR_ORACLE_ADDRESS — read-only eth_calls against that instance.

Every response carries the backend label and ``mainnet_deployed``.
"""
from __future__ import annotations

import json
import threading

from . import config
from .errors import CapabilityError

ZERO_ADDRESS = "0x" + "0" * 40
DEMO_AGENT = "0x1111111111111111111111111111111111111111"

_lock = threading.Lock()
_oracle = None


def _load_artifact() -> dict:
    try:
        with open(config.ORACLE_ARTIFACT) as fh:
            return json.load(fh)
    except OSError as exc:
        raise CapabilityError(
            "unavailable",
            f"oracle artifact not readable at {config.ORACLE_ARTIFACT}: {exc}")


class _LocalReferenceOracle:
    mode = "local-reference"

    def __init__(self):
        try:
            from web3 import Web3
            from web3.providers.eth_tester import EthereumTesterProvider
        except ImportError as exc:
            raise CapabilityError(
                "unavailable",
                f"eth-tester not installed (pip install eth-tester): {exc}")
        artifact = _load_artifact()
        self.w3 = Web3(EthereumTesterProvider())
        self.owner = self.w3.eth.accounts[0]
        factory = self.w3.eth.contract(
            abi=artifact["abi"], bytecode=artifact["bytecode"]["object"])
        tx = factory.constructor(ZERO_ADDRESS).transact({"from": self.owner})
        receipt = self.w3.eth.wait_for_transaction_receipt(tx)
        self.address = receipt.contractAddress
        self.contract = self.w3.eth.contract(
            address=self.address, abi=artifact["abi"])
        self._seed()

    def _seed(self):
        """Seed DEMO attestations so reputation reads are meaningful.
        Labelled demo data on a local chain — never mainnet history."""
        from web3 import Web3
        outcomes = [0, 0, 1]  # Outcome.Success, Success, Failure
        for i, outcome in enumerate(outcomes):
            task_id = Web3.keccak(text=f"sincor-mcp-demo-task-{i + 1}")
            sigil = Web3.keccak(text=f"sincor-mcp-demo-sigil-{i + 1}")
            tx = self.contract.functions.recordValidation(
                DEMO_AGENT, task_id, sigil, outcome).transact(
                {"from": self.owner})
            self.w3.eth.wait_for_transaction_receipt(tx)

    def reputation(self, agent: str) -> tuple:
        return self.contract.functions.reputationOf(agent).call()

    def attestation_count(self) -> int:
        return self.contract.functions.attestationCount().call()

    def validation_seen(self, task_id: bytes, sigil: bytes) -> tuple:
        key = self.contract.functions.attestationKey(task_id, sigil).call()
        seen = self.contract.functions.attestationSeen(key).call()
        return key, seen


class _ConfiguredOracle:
    mode = "configured-rpc"

    def __init__(self):
        from web3 import Web3
        artifact = _load_artifact()
        self.w3 = Web3(Web3.HTTPProvider(config.ORACLE_RPC_URL))
        self.address = config.ORACLE_ADDRESS
        self.contract = self.w3.eth.contract(
            address=self.address, abi=artifact["abi"])

    def reputation(self, agent: str) -> tuple:
        return self.contract.functions.reputationOf(agent).call()

    def attestation_count(self) -> int:
        return self.contract.functions.attestationCount().call()

    def validation_seen(self, task_id: bytes, sigil: bytes) -> tuple:
        key = self.contract.functions.attestationKey(task_id, sigil).call()
        seen = self.contract.functions.attestationSeen(key).call()
        return key, seen


def get_oracle():
    global _oracle
    if _oracle is None:
        with _lock:
            if _oracle is None:
                if config.ORACLE_RPC_URL and config.ORACLE_ADDRESS:
                    _oracle = _ConfiguredOracle()
                else:
                    _oracle = _LocalReferenceOracle()
    return _oracle


def oracle_info(oracle) -> dict:
    return {
        "contract": "SincorValidationReputationOracle",
        "backend": oracle.mode,
        "instance": oracle.address,
        "mainnet_deployed": False,
        "note": ("ERC-8004-style Validation+Reputation oracle, interface "
                 "level. NOT deployed on Base mainnet. The default "
                 "backend is the real compiled contract running on an "
                 "in-process local chain, seeded with labelled demo "
                 "attestations."),
    }


def reputation(agent: str) -> dict:
    oracle = get_oracle()
    score, successes, failures, total = oracle.reputation(agent)
    return {
        "agent": agent,
        "score": int(score),
        "successes": int(successes),
        "failures": int(failures),
        "total": int(total),
        "attestation_count": int(oracle.attestation_count()),
        "oracle": oracle_info(oracle),
    }


def validation_lookup(task_id: bytes, sigil: bytes) -> dict:
    oracle = get_oracle()
    key, seen = oracle.validation_seen(task_id, sigil)
    return {
        "task_id": "0x" + task_id.hex(),
        "sigil_commitment": "0x" + sigil.hex(),
        "attestation_key": "0x" + bytes(key).hex(),
        "seen": bool(seen),
        "oracle": oracle_info(oracle),
    }
