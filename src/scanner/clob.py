"""Thin async client for Polymarket CLOB public endpoints."""
from __future__ import annotations

import logging
import time
from typing import Optional

import httpx

from src.models import Market, Orderbook, Quote, Side
from src.utils.retry import retry_async

logger = logging.getLogger(__name__)

CLOB_BASE = "https://clob.polymarket.com"


class ClobClient:
    def __init__(self, base_url=CLOB_BASE, timeout=10.0):
        self.base_url = base_url
        self.timeout = timeout
        self._client = None

    async def _get(self, path, params=None):
        if self._client is None:
            self._client = httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout)
        resp = await self._client.get(path, params=params)
        resp.raise_for_status()
        return resp.json()

    async def list_markets(self, limit=500) -> list[dict]:
        data = await retry_async(lambda: self._get("/markets", {"limit": str(limit)}))
        return data.get("data", []) or []

    async def get_orderbook(self, token_id, depth=20) -> Orderbook:
        data = await self._get("/book", {"token_id": token_id, "depth": str(depth)})
        book = self._parse_book(token_id, data)
        return book

    def _parse_book(self, token_id, data) -> Orderbook:
        market = Market(condition_id=token_id, question=token_id)
        ob = Orderbook(market=market)
        for level in data.get("bids", []):
            pq = level.get("price")
            sz = level.get("size")
            if pq is None or sz is None:
                continue
            ob.bids_yes.append(Quote(token_id=token_id, side=Side.BUY, price=float(pq), size=float(sz)))
        for level in data.get("asks", []):
            pq = level.get("price")
            sz = level.get("size")
            if pq is None or sz is None:
                continue
            ob.asks_yes.append(Quote(token_id=token_id, side=Side.ASK, price=float(pq), size=float(sz)))
        return ob

    async def close(self):
        if self._client is not None:
            await self._client.aclose()
            self._client = None
