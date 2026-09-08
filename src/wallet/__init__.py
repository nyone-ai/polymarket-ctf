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
        """Normalize py-clob-client responses into a list of fill dicts.

        Handles both the raw POST responses (per-order dicts/arrays) and
        the ``get_order_amounts`` style completed-order payloads.
        """
        if not responses:
            return []
        if isinstance(responses, str):
            responses = [{"status": responses}]
        if not isinstance(responses, list):
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
            if matched:
                fills.append(self._normalize_fill(item, status))
        return fills

    @staticmethod
    def _normalize_fill(item: dict, status: str) -> dict:
        """Extract a single completed-fill record from a live CLOB response."""
        txs = item.get("transactionsHashes") or item.get("transaction_hash") or item.get("transactions") or []
        if isinstance(txs, str):
            tx = txs
        elif isinstance(txs, list) and txs:
            tx = txs[0] if not isinstance(txs[0], dict) else (txs[0].get("tx_hash") or txs[0].get("transactionHash") or None)
        else:
            tx = None
        token_id = item.get("token_id") or item.get("asset_id") or item.get("tokenId") or item.get("assetId")
        if token_id is None:
            asset = item.get("asset") or {}
            if isinstance(asset, dict):
                token_id = asset.get("token_id") or asset.get("tokenId") or asset.get("asset_id")
        price_raw = item.get("price")
        price = float(price_raw) if price_raw is not None else 0.0
        size_raw = item.get("size")
        size = float(size_raw) if size_raw is not None else 0.0
        fee_raw = item.get("fee")
        fee = float(fee_raw) if fee_raw is not None else 0.0
        return {
            "token_id": token_id,
            "price": price,
            "size": size,
            "fee": fee,
            "status": status,
            "tx_hash": tx,
            "order_id": item.get("orderID") or item.get("order_id") or item.get("orderId"),
            "trade_ids": item.get("tradeIDs") or item.get("trade_ids") or [],
        }

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
                    # POLY_PROXY signature: funder must be the EOA owning the proxy.

                    kwargs["funder"] = self.address
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
            tif = "FAK" if order_type == "IOC" else "FOK"   # v2 CLOB: "IOC" is no longer a valid time-in-force
            response = await asyncio.to_thread(
                client.post_order, signed, tif
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
