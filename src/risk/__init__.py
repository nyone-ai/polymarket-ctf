"""Risk management: opportunity detection, sizing, limits."""
from __future__ import annotations

import datetime
import logging
import time
from collections import deque
from typing import Optional

from src.config import Settings
from src.models import Opportunity, Orderbook, Side

logger = logging.getLogger(__name__)


def best_ask(book, side):
    if side is Side.YES:
        levels = book.asks_yes
    else:
        levels = book.asks_no
    if not levels:
        return None
    levels = sorted(levels, key=lambda q: q.price)
    return levels[0]


def find_opportunity(market, book, settings) -> Optional[Opportunity]:
    y = best_ask(book, Side.YES)
    n = best_ask(book, Side.NO)
    if y is None or n is None:
        return None
    total = y.price + n.price
    profit = 1.0 - total
    margin_bps = profit * 10000
    if total >= settings.threshold:
        return None
    if profit < settings.min_profit_usd and settings.min_profit_usd > 0:
        return None
    if margin_bps < settings.min_profit_margin_bps:
        return None
    size = min(y.size, n.size)
    max_cost = settings.max_size_per_trade
    if size * total > max_cost:
        size = max_cost / total
    return Opportunity(
        market=market,
        yes_ask=y.price,
        no_ask=n.price,
        combined_cost=total,
        profit_per_pair=profit,
        profit_margin_bps=margin_bps,
        max_size=size,
        quote_ts=datetime.datetime.now(datetime.timezone.utc),
    )


class RiskManager:
    def __init__(self, settings):
        self.settings = settings
        self.trades = []
        self._opened_at = 0.0
        self._day_start = 0.0
        self._day_pnl = 0.0
        self._trade_timestamps = deque(maxlen=settings.max_trades_per_minute)

    def can_trade(self):
        now = time.monotonic()
        if now - self._opened_at < self.settings.cooldown_seconds:
            return False
        # Rate limit: max_trades_per_minute
        cutoff = now - 60
        while self._trade_timestamps and self._trade_timestamps[0] < cutoff:
            self._trade_timestamps.popleft()
        if len(self._trade_timestamps) >= self.settings.max_trades_per_minute:
            return False
        return True

    def mark_open(self):
        self._opened_at = time.monotonic()
        self._trade_timestamps.append(self._opened_at)

    def check_daily_loss(self, day_pnl):
        self._day_pnl += day_pnl
        if self._day_pnl <= -self.settings.max_daily_loss:
            logger.error("Daily loss limit hit %s", self._day_pnl)
            return False
        return True

    def size_for_trade(self, opp):
        return min(opp.max_size, self.settings.max_size_per_trade)
