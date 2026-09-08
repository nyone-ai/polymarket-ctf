"""Wallet module: EOA wallet with py-clob-client v2 order placement."""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from src.config import Settings

logger = logging.getLogger(__name__)


class EoWallet:
    """EOA wallet for signing and submitting CLOB orders (py-clob-client v2)."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._w3 = None
        self._account = None
        self._sdk = None

    def _web3(self):
        if self._w3 is None:
            from web3 import Web3
            self._w3 = Web3(Web3.HTTPProvider(self.settings.rpc_url))
        return self._w3

    def _account_obj(self):
        if self._account is None:
            from eth_account import Account
            self._account = Account.from_key(self._normalize_key(self.settings.private_key))
        return self._account

    @staticmethod
    def _normalize_key(key: str) -> str:
        """Strip the 0x prefix if present."""
        return key.strip().removeprefix("0x")

    @property
    def address(self) -> str:
        """Derived wallet address from the private key."""
        return self._account_obj().address

    def parse_fills(self, responses) -> list:
        """Normalize py-clob-client responses into a list of fill dicts."""

        if not responses:
            return []
        if isinstance(responses, dict):
            responses = [responses]
        fills = []
        for item in responses:
            if not isinstance(item, dict):
                continue
            status = str(item.get("status") or "" ).upper()
            data = item.get("data") or []
            if isinstance(data, list) and data:
                fills.extend(self.parse_fills(data))
                continue
            matched = status == "MATCHED" or status in {"FILLED", "FILL", "SUCCESS"}
            if not matched:
                continue
            txs = item.get("transactionsHashes") or item.get("transaction_hash") or []
            fills.append({
                "token_id": item.get("token_id") or item.get("asset_id") or item.get("tokenId"),
                "price": float(item.get("price") or 0.0),
                "size": float(item.get("size") or 0.0),
                "fee": float(item.get("fee") or 0.0),
                "status": status,
                "tx_hash": txs[0] if isinstance(txs, list) and txs else (txs if isinstance(txs, str) else None),
                "order_id": item.get("orderID") or item.get("order_id"),
                "trade_ids": item.get("tradeIDs") or item.get("trade_ids") or [],
            })
        return fills

    async def place_orders(self, orders: list, order_type: str = "FOK", client=None) -> list:
        """Place CLOB orders via the py-clob-client v2 SDK.




        Each item in ``orders`` is a dict with token_id/price/size.
        Returns the raw responses list (feeds into ``parse_fills``).
        """
        if not orders:
            return []
        logger.info("Placing %d CLOB orders (type=%s)", len(orders), order_type)
        from py_clob_client.clob_types import OrderArgs
        from py_clob_client.order_builder.constants import BUY

        if client is None:
            if self._sdk is None:
                from py_clob_client.client import ClobClient
                kwargs = {}
                if self.settings.clob_signature_type == 1:
                    kwargs["funder"] = self.settings.wallet_address
                self._sdk = ClobClient(
                    self.settings.clob_host,
                    key=self.settings.private_key,
                    chain_id=self.settings.chain_id,
                    signature_type=self.settings.clob_signature_type,
                    **kwargs,
                )
            client = self._sdk

        responses = []
        for order in orders:
            args = OrderArgs(
                price=float(order["price"]),
                size=float(order["size"]),
                side=BUY,
                token_id=str(order["token_id"]),
            )
            signed = client.create_order(args)
            response = await asyncio.to_thread(
                client.post_order, signed, "IOC" if order_type == "IOC" else "FOK"
            )
            responses.append(response)
        return responses

    async def sign_order(self, token_id: str, price: float, size: float, side: str = "BUY") -> dict:
        """Placeholder for manual EIP-712 signing; not used in the live v2 flow."""
        raise NotImplementedError("manual REST signing is not used; use place_orders instead")

    async def submit_and_wait(self, order: dict, order_type: str = "FOK") -> dict:
        """Placeholder for the removed REST fallback; refuse to fabricate fills."""
        raise NotImplementedError("refusing to fabricate an order fill; live orders go via place_orders")

    async def wait_for_fills(self, tx_hash: str) -> list:
        """Placeholder for the removed polling flow."""
        raise NotImplementedError("polling fills is replaced by parsing place_orders responses directly")

    async def execute_orders(self, orders: list, order_type: str = "FOK") -> str:
        """Placeholder retained for compatibility."""
        raise NotImplementedError("use place_orders + parse_fills instead")
