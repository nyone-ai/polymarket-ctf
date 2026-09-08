"""Wallet module: EOA wallet with py-clob-client v2 order placement."""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from src.config import Settings

logger = logging.getLogger(__name__)


class EoWallet:
    """EOA wallet for signing and submitting CLOB orders."""

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

    def _build_sdk_client(self):
        """Build a py-clob-client v2 client with Level-2 credentials."""
        from py_clob_client.client import ClobClient
        from py_clob_client.clob_types import ApiCreds

        kwargs = {}
        if self.settings.clob_signature_type == 1:
            if not self.settings.polymarket_proxy_address:
                raise RuntimeError(
                    "polymarket_proxy_address required when clob_signature_type=1 (POLY_PROXY)"
                )
            kwargs["funder"] = self.settings.polymarket_proxy_address
        client = ClobClient(
            self.settings.clob_host,
            chain_id=self.settings.chain_id,
            key=self.settings.private_key,
            signature_type=self.settings.clob_signature_type,
            **kwargs,
        )
        if self.settings.clob_api_secret and self.settings.clob_api_passphrase:
            client.set_api_creds(
                ApiCreds(
                    api_key=self.settings.clob_api_key,
                    api_secret=self.settings.clob_api_secret,
                    api_passphrase=self.settings.clob_api_passphrase,
                )
            )
        elif self.settings.clob_api_key:
            client.set_api_creds(client.create_or_derive_api_creds())
            logger.info("Derived CLOB API credentials from API key")
        else:
            raise RuntimeError("clob_api_key required for live CLOB orders")
        self._sdk = client
        return client

    def parse_fills(self, responses) -> list:
        """Normalize py-clob-client responses into a list of fill dicts."""
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
            status = str(item.get("status") or "").upper()
            data = item.get("data") or []
            if isinstance(data, list)and data:
                fills.extend(self.parse_fills(data))
                continue
            if status and status not in {"MATCHED", "FILLED", "FILL", "SUCCESS"}:
                continue
            side = str(item.get("side") or "BUY").upper()
            size = self._parse_fill_size(item, side)
            if size <=  0.0:
                continue
            fills.append(self._normalize_fill(item, status, size, side))
        return fills

    @staticmethod
    def _to_float(value) -> float:
        if value is None:
            return 0.0
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _parse_fill_size(item: dict, side: str) -> float:
        """Extract the filled size from a CLOB order response.

        ``makerAmount``/``takingAmount`` mirror the signed order side: for BUY
        orders the maker provides collateral and the taker provides outcome tokens; for
        SELL orders the roles flip. ``place_orders`` only posts BUY, so responses
        without an explicit ``side`` are treated as BUY.

        The direct size fields (``size``/``sizeMatched``) win when present; otherwise
        the matched share count is derived from the amount pair.
        """

        for key in ("size", "sizeMatched", "matchedSize", "originalSize"):
            val = item.get(key)
            if val is not None:
                return EoWallet._to_float(val)
        making = EoWallet._to_float(item.get("makingAmount") or item.get("makerAmount"))
        taking = EoWallet._to_float(item.get("takingAmount") or item.get("takerAmount"))
        price = EoWallet._to_float(item.get("price"))
        if side == "SELL":
            if making >  0.0:
                return making / 1e6
            if taking >  0.0 and price >  0.0:
                return taking / price / 1e6
        if taking >  0.0:
            return taking / 1e6
        if making >  0.0 and price >  0.0:
            return making / price / 1e6
        return 0.0

    @staticmethod
    def _normalize_fill(item: dict, status: str, size: float, side: str) -> dict:
        """Extract a single completed-fill record from a live CLOB response."""
        txs = item.get("transactionsHashes") or item.get("transaction_hash") or item.get("transactions") or item.get("txHash") or []
        if isinstance(txs, str):
            tx = txs
        elif isinstance(txs, list)and txs:
            tx = txs[0] if not isinstance(txs[0], dict) else (txs[0].get("tx_hash") or txs[0].get("transactionHash") or None)
        else:
            tx = None
        token_id = item.get("tokenID") or item.get("token_id") or item.get("assetID") or item.get("asset_id") or item.get("tokenId")
        if token_id is None:
            asset = item.get("asset") or {}
            if isinstance(asset, dict):
                token_id = asset.get("token_id") or asset.get("tokenId") or asset.get("asset_id")
        price = EoWallet._to_float(item.get("price"))
        if price ==  0.0:
            making = EoWallet._to_float(item.get("makingAmount") or item.get("makerAmount"))
            taking = EoWallet._to_float(item.get("takingAmount") or item.get("takerAmount"))
            if making >  0.0 and taking >  0.0:
                price = (taking / making) if side == "SELL" else (making / taking)
        fee = EoWallet._to_float(
            item.get("fee") or item.get("taker_fee") or item.get("maker_fee") or item.get("fee_amount")
        )
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
        """Place CLOB orders via the py-clob-client v2 SDK."""
        if not orders:
            return []
        logger.info("Placing %d CLOB orders (type=%s)", len(orders), order_type)
        from py_clob_client.clob_types import OrderArgs
        from py_clob_client.order_builder.constants import BUY

        if client is None:
            if self._sdk is None:
                self._build_sdk_client()
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
            tif = "FAK" if order_type == "IOC" else "FOK"
            response = await asyncio.to_thread(
                client.post_order, signed, tif
            )
            responses.append(response)
        return responses

    async def sign_order(self, token_id: str, price: float, size: float, side: str = "BUY") -> dict:
        raise NotImplementedError("manual REST signing is not used; use place_orders instead")

    async def submit_and_wait(self, order: dict, order_type: str = "FOK") -> dict:
        raise NotImplementedError("refusing to fabricate an order fill; live orders go via place_orders")

    async def wait_for_fills(self, tx_hash: str) -> list:
        raise NotImplementedError("polling fills is replaced by parsing place_orders responses directly")

    async def execute_orders(self, orders: list, order_type: str = "FOK") -> str:
        raise NotImplementedError("use place_orders + parse_fills instead")
