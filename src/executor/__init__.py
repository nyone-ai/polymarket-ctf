"""Execution: paper simulator + live CLOB/CTF execution."""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from src.config import Settings
from src.models import (
    MergeResult,
    Opportunity,
    OrderFill,
    OrderRequest,
    OrderType,
    Side,
    TradeMode,
    TradeRecord,
)

from src.collateral import Collateral
from src.ctf import CtfAdapter
from src.utils.number import round_size

logger = logging.getLogger(__name__)


class Executor:
    def __init__(self, settings: Settings, clob=None, wallet=None, store=None):
        self.settings = settings
        self.clob = clob
        self.wallet = wallet
        self.store = store
        self.last_executed_at = 0.0
        self._preflight_live()

    def _preflight_live(self):
        if self.settings.mode != TradeMode.LIVE:
            return
        missing = []
        for key in ('private_key', 'wallet_address', 'rpc_url', 'clob_api_key'):
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
        if self.settings.mode == TradeMode.PAPER:
            return await self._execute_paper(opp, size)
        return await self._execute_live(opp, size)

    async def _execute_paper(self, opp, size) -> TradeRecord:
        fee = size * 0.0
        yes_fill = OrderFill(
            token_id=opp.market.yes_token_id,
            side=Side.YES,
            price=opp.yes_ask,
            size=size,
            fee_usd=fee / 2.0,
        )
        no_fill = OrderFill(
            token_id=opp.market.no_token_id,
            side=Side.NO,
            price=opp.no_ask,
            size=size,
            fee_usd=fee / 2.0,
        )
        total_cost = size * (opp.yes_ask + opp.no_ask) + fee
        logger.info("PAPER buy YES+NO size=%s cost=%s", size, total_cost)
        await asyncio.sleep(0.01)
        merged = MergeResult(
            market=opp.market,
            yes_fill=yes_fill,
            no_fill=no_fill,
            merged_amount=size,
        )
        record = TradeRecord(
            opportunity=opp,
            fills=[yes_fill, no_fill],
            merge=merged,
            status="settled",
        )
        if self.store is not None:
            await self.store.record_trade(record)
        return record

    async def _execute_live(self, opp, size) -> TradeRecord:
        """
        Live execution: buy YES+NO via CLOB + merge into pUSD via CTF.
        
        Steps:
        1. Place CLOB orders for YES and NO (FOK or IOC)
        2. Wait for both orders to fill
        3. Execute CTF mergePositions to convert YES+NO -> pUSD
        4. Handle partial fills, excess tokens, gas, timeout
        """
        if self.settings.clob_api_key is None:
            raise RuntimeError("CLOB_API_KEY required for live mode")
        if self.settings.private_key is None:
            raise RuntimeError("PRIVATE_KEY required for live mode")
        if self.settings.wallet_address is None:
            raise RuntimeError("WALLET_ADDRESS required for live mode")

        logger.info("Starting LIVE execution: market=%s size=%s", opp.market.slug, size)

        # 1. Place CLOB orders for YES and NO
        yes_fill, no_fill = await self._place_clob_orders(opp, size)

        # 2. Determine merge amount (handle partial fills)
        merge_amount = min(yes_fill.size, no_fill.size)
        excess_yes = yes_fill.size - merge_amount
        excess_no = no_fill.size - merge_amount

        if merge_amount <= 0:
            # One side did not fill at all: keep the filled side as a position
            # rather than dumping it at a loss; the error explains the state.
            msg = "No tokens filled; cannot execute merge"
            logger.error(msg)
            record = TradeRecord(
                opportunity=opp,
                fills=[yes_fill, no_fill],
                status="failed",
                error=msg,
                mode="live",
            )
            if self.store is not None:
                await self.store.record_trade(record)
            return record

        logger.info(
            "Both sides filled; merge_amount=%s (YES=%s, NO=%s, excess_yes=%s, excess_no=%s)",
            merge_amount, yes_fill.size, no_fill.size, excess_yes, excess_no,
        )

        # 3. Execute CTF merge to convert YES+NO -> pUSD
        merge_tx = await self._execute_ctf_merge(
            opp, merge_amount, excess_yes, excess_no
        )

        # 4. Handle any excess tokens that weren't part of the merge
        if excess_yes > 0 or excess_no > 0:
            logger.info(
                "Keeping excess tokens as position: YES=%s NO=%s",
                excess_yes, excess_no,
            )

        # 5. Build trade record
        merged = MergeResult(
            market=opp.market,
            yes_fill=yes_fill,
            no_fill=no_fill,
            merged_amount=merge_amount,
            tx_hash=merge_tx,
        )
        record = TradeRecord(
            opportunity=opp,
            fills=[yes_fill, no_fill],
            merge=merged,
            status="settled",
            mode="live",
        )
        if self.store is not None:
            await self.store.record_trade(record)
        return record

    async def _place_clob_orders(self, opp: Opportunity, size: float):
        """
        Place YES and NO orders via CLOB.
        For FOK: if full fill not available, the order is killed.
        For IOC: partial fills are accepted; remaining is cancelled.
        
        Uses py-clob-client SDK if available, otherwise falls back to REST + EIP-712 signing.
        """
        order_type = self.settings.order_type
        logger.info("Placing CLOB orders: YES @ %s, NO @ %s, size=%s, type=%s",
                     opp.yes_ask, opp.no_ask, size, order_type)

        yes_req = OrderRequest(
            token_id=opp.market.yes_token_id,
            side=Side.YES,
            price=opp.yes_ask,
            size=size,
            order_type=OrderType.FOK if order_type == "FOK" else (OrderType.IOC if order_type == "IOC" else OrderType.FOK),
        )
        no_req = OrderRequest(
            token_id=opp.market.no_token_id,
            side=Side.NO,
            price=opp.no_ask,
            size=size,
            order_type=yes_req.order_type,
        )

        if self.wallet is None:
            from src.wallet import EoWallet
            self.wallet = EoWallet(self.settings)
        yes_fill, no_fill = await asyncio.gather(
            self._place_order_via_sdk(yes_req),
            self._place_order_via_sdk(no_req),
        )

        logger.info("Order fills - YES: %s @ %s, NO: %s @ %s",
                     yes_fill.size, yes_fill.price, no_fill.size, no_fill.price)
        
        return yes_fill, no_fill

    async def _place_order_via_sdk(self, req: OrderRequest) -> OrderFill:
        """Place order via the official py-clob-client-v2 SDK."""
        from src.wallet import EoWallet

        if self.wallet is None:
            self.wallet = EoWallet(self.settings)

        order_params = {
            "token_id": req.token_id,
            "price": req.price,
            "size": req.size,
        }

        responses = await self.wallet.place_orders(
            [order_params], order_type=req.order_type.value
        )
        fills = self.wallet.parse_fills(responses)

        if not fills:
            logger.warning(
                "No fills received for token %s. Aborting merge for this trade.",
                req.token_id,
            )
            return OrderFill(
                token_id=req.token_id,
                side=req.side,
                price=req.price,
                size=0,
                fee_usd=0,
                tx_hash=None,
            )

        total_size = sum(float(f.get("size") or 0.0) for f in fills)
        total_fee = sum(float(f.get("fee") or 0.0) for f in fills)
        tx_hash = next((f.get("tx_hash") for f in fills if f.get("tx_hash")), None)
        fill_price = next((f.get("price") for f in fills if (f.get("price") or 0.0) > 0.0), req.price)

        return OrderFill(
            token_id=req.token_id,
            side=req.side,
            price=fill_price,
            size=total_size,
            fee_usd=total_fee,
            tx_hash=tx_hash,
        )

    async def _place_order_via_rest(self, req: OrderRequest) -> OrderFill:
        """Reject the obsolete placeholder REST fallback.

        A locally fabricated signature or fill is unsafe in live trading.  Live
        execution must use the SDK path until a fully tested REST signer exists.
        """
        raise RuntimeError("CLOB REST fallback is not implemented safely; use the SDK integration")

    async def _execute_ctf_merge(
        self,
        opp: Opportunity,
        merge_amount: float,
        excess_yes: float,
        excess_no: float,
    ) -> str:
        """
        Execute CTF mergePositions to convert YES+NO -> pUSD.
        Returns transaction hash.
        """
        from src.wallet import EoWallet
        
        # Estimate gas before sending
        tx_timeout = self.settings.tx_timeout_seconds
        
        # Create CTF adapter
        ctf = CtfAdapter(self.settings)
        
        # Submit merge transaction with timeout
        loop = asyncio.get_event_loop()
        
        try:
            tx_hash = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: ctf.merge(
                        condition_id=opp.market.condition_id,
                        amount=merge_amount,
                        yes_token_id=opp.market.yes_token_id,
                        no_token_id=opp.market.no_token_id,
                    ),
                ),
                timeout=tx_timeout,
            )
            logger.info("CTF merge transaction submitted: %s", tx_hash)
            return tx_hash
        except asyncio.TimeoutError:
            logger.error("CTF merge transaction timed out after %ss", tx_timeout)
            raise RuntimeError(f"CTF merge timed out after {tx_timeout}s")

    async def _handle_excess(
        self, opp: Opportunity, excess_yes: float, excess_no: float
    ):
        """Handle leftover tokens after partial fills."""
        if self.settings.excess_mode == "cancel":
            # Leave excess on-chain; they remain as positions
            logger.info("Excess tokens left in position (cancel mode): YES=%.6f, NO=%.6f", excess_yes, excess_no)
        elif self.settings.excess_mode == "sell":
            raise RuntimeError(
                "excess_mode=sell is disabled until the order model supports an explicit SELL direction"
            )
        else:
            logger.warning("Unknown excess_mode: %s; leaving tokens in position", self.settings.excess_mode)

    async def _stub_delay(self):
        await asyncio.sleep(0.0)

