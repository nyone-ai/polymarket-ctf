"""CTF merge/redeem adapter (Polymarket CTF Exchange on Polygon)."""
from __future__ import annotations

import logging
from typing import Optional

from src.config import Settings

logger = logging.getLogger(__name__)


NEG_RISK_MERGE_SIG = "mergePositions(bytes32,bytes32,bytes32,uint256)"
CTF_MERGE_SIG = "mergePositions(bytes32,bytes32,uint256)"


class CtfAdapter:
    def __init__(self, settings):
        self.settings = settings
        self._w3 = None
        self._exchange = None
        self._neg_risk = None

    def _web3(self):
        if self._w3 is None:
            from web3 import Web3
            url = self.settings.rpc_url
            self._w3 = Web3(Web3.HTTPProvider(url))
        return self._w3

    def _get_contracts(self):
        w3 = self._web3()
        if self._exchange is None:
            addr = self.settings.ctf_exchange_address
            if not addr:
                raise RuntimeError("ctf_exchange_address not configured")
            self._exchange = w3.eth.contract(address=addr)
        return self._exchange

    def merge(self, condition_id, amount, yes_token_id=None, no_token_id=None) -> str:
        raise NotImplementedError("merge wiring requires ABI + gas logic; see PLAN.md")

    def redeem(self, condition_id, amount) -> str:
        raise NotImplementedError("redeem wiring requires resolved market; handled post-resolution")
