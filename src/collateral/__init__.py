"""Collateral adapter: USDC.e deposit/withdraw via WrapperUSDC."""
from __future__ import annotations

import logging

from src.config import Settings

logger = logging.getLogger(__name__)


WRAPPER_DEPOSIT_SIG = "deposit(uint256)"
WRAPPER_WITHDRAW_SIG = "withdraw(uint256)"


class Collateral:
    def __init__(self, settings, address):
        self.settings = settings
        self.address = address
        self._w3 = None
        self._wrapper = None

    def _web3(self):
        if self._w3 is None:
            from web3 import Web3
            url = self.settings.rpc_url
            self._w3 = Web3(Web3.HTTPProvider(url))
        return self._w3

    def wrapper_balance(self) -> int:
        raise NotImplementedError("requires wrapper ABI + checksum address")

    def deposit(self, amount_wei) -> str:
        raise NotImplementedError("deposit wiring requires ABI + env creds")

    def withdraw(self, amount_wei) -> str:
        raise NotImplementedError("withdraw wiring requires ABI + env creds")
