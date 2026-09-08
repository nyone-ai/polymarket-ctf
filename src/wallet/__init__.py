"""Wallet module: EOA wallet with CLOB signing and CTF transaction capabilities."""
from __future__ import annotations

import logging
import os
from typing import Optional

from src.config import Settings
from src.utils.number import to_wei

logger = logging.getLogger(__name__)


class EoWallet:
    """EOA wallet for signing CLOB orders and CTF transactions."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._w3 = None
        self._account = None

    def _web3(self):
        if self._w3 is None:
            from web3 import Web3
            self._w3 = Web3(Web3.HTTPProvider(self.settings.rpc_url))
        return self._w3

    def _account_obj(self):
        if self._account is None:
            from eth_account import Account
            self._account = Account.from_key(self.settings.private_key)
        return self._account

    @property
    def address(self) -> str:
        """Get wallet address."""
        return self._account_obj().address

    def sign_order(self, token_id: str, price: float, size: float, side: str = "BUY") -> dict:
        """
        Sign a CLOB order using EIP-712.
        
        Returns signed order dict suitable for submission.
        """
        raise NotImplementedError(
            "Manual CLOB REST signing is not implemented; use a verified py-clob-client integration"
        )

    async def submit_and_wait(self, order: dict, order_type: str = "FOK") -> dict:
        """
        Submit signed order to CLOB and wait for fill.
        
        Returns fill info dict.
        """
        raise NotImplementedError(
            "Manual CLOB REST submission is not implemented; refusing to fabricate an order fill"
        )

    async def execute_orders(self, orders: list, order_type: str = "FOK") -> str:
        """Execute multiple orders and return transaction hash."""
        logger.info("execute_orders: %d orders, type=%s", len(orders), order_type)
        raise RuntimeError("execute_orders: py-clob-client SDK integration not implemented")

    async def wait_for_fills(self, tx_hash: str) -> list:
        """Wait for order fills and return fill info list."""
        logger.info("wait_for_fills: tx=%s", tx_hash)
        raise RuntimeError("wait_for_fills: py-clob-client SDK integration not implemented")


def get_wallet(settings: Settings) -> Optional[EoWallet]:
    """Get wallet instance if credentials are available."""
    if not settings.private_key or not settings.wallet_address:
        return None
    return EoWallet(settings)


def get_account(settings: Settings):
    """Get web3 Account from settings."""
    if not settings.private_key:
        return None
    from eth_account import Account
    return Account.from_key(settings.private_key)
