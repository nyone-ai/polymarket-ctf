"""Execution: paper simulator + live CLOB/CTF execution."""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from src.config import Settings
from src.models import MergeResult, Opportunity, OrderFill, OrderRequest, Side, TradeMode, TradeRecord

from src.utils.number import round_price, round_size

logger = logging.getLogger(__name__)


class Executor:
    def __init__(self, settings, clob=None, wallet=None):
        self.settings = settings
        self.clob = clob
        self.wallet = wallet
        self.last_executed_at = 0.0
        self._preflight_live()

    def _preflight_live(self):
        if self.settings.mode != TradeMode.LIVE:
            return
        missing = []
        for key in ('private_key','wallet_address','rpc_url','clob_api_key'):
            if not getattr(self.settings, key, None):
                missing.append(key)
        if missing:
            raise RuntimeError('live mode missing settings: ' + '+'.join(missing))

    async def execute(self, opp, size=None) -> TradeRecord:
        if size is None:
            size = opp.max_size
        size = round_size(size)
        if size <= 0:
            raise ValueError("size must be positive")
        if self.settings.mode is TradeMode.PAPER:
            return await self._execute_paper(opp, size)
        return await self._execute_live(opp, size)

    async def _execute_paper(self, opp, size) -> TradeRecord:
        fee = size * 0.0
        yes_fill = OrderFill(token_id=opp.market.yes_token_id, side=Side.YES, price=opp.yes_ask, size=size, fee_usd=fee / 2.0)
        no_fill = OrderFill(token_id=opp.market.no_token_id, side=Side.NO, price=opp.no_ask, size=size, fee_usd=fee / 2.0)
        total_cost = size * (opp.yes_ask + opp.no_ask) + fee
        logger.info("PAPER buy YES+NO size=%s cost=%s", size, total_cost)
        await self._stub_delay()
        merged = MergeResult(market=opp.market, yes_fill=yes_fill, no_fill=no_fill, merged_amount=size)

        record = TradeRecord(opportunity=opp, fills=[yes_fill, no_fill], merge=merged, status="settled")
        return record

    async def _execute_live(self, opp, size) -> TradeRecord:
        if self.settings.clob_api_key is None:
            raise RuntimeError("CLOB_API_KEY required for live mode")
        if self.settings.private_key is None:
            raise RuntimeError("PRIVATE_KEY required for live mode")
        yes_req = OrderRequest(token_id=opp.market.yes_token_id, side=Side.YES, price=opp.yes_ask, size=size)
        no_req = OrderRequest(token_id=opp.market.no_token_id, side=Side.NO, price=opp.no_ask, size=size)
        logger.warning("LIVE mode requires CLOB signing + CTF merge wiring; not yet chain-wired")
        raise NotImplementedError("live CLOB/CTF execution wiring pending")

    async def _stub_delay(self):
        await asyncio.sleep(0.0)
