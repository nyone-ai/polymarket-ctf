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


def ask_depth(book, side, max_price):
    """Total size of ask levels fillable in one FOK (at or below best ask)."""
    levels = book.asks_yes if side is Side.YES else book.asks_no
    return sum(q.size for q in levels if q.price <= max_price + 1e-9)


def find_opportunity(market, book, settings) -> Optional[Opportunity]:
    # Guard against zero-size ask levels (they cannot be filled)..
    y = best_ask(book, Side.YES)
    n = best_ask(book, Side.NO)
    if y is None or n is None or y.size <= 0 or n.size <= 0:
        return None
    total = y.price + n.price
    profit = 1.0 - total
    margin_bps = profit * 10000
    if total >= settings.threshold:
        return None
    if margin_bps < settings.min_profit_margin_bps:
        return None
    size = min(ask_depth(book, Side.YES, y.price), ask_depth(book, Side.NO, n.price))
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
        self._day_start = self._current_day()
        self._day_pnl = 0.0
        self._trading_halted = False
        self._trade_timestamps = deque(maxlen=settings.max_trades_per_minute)

    @staticmethod
    def _current_day():
        return datetime.datetime.now(datetime.timezone.utc).date()

    def can_trade(self):
        if self._trading_halted:
            return False
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
        today = self._current_day()
        if today != self._day_start:
            logger.info("New trading day, resetting daily loss halt")
            self._day_start = today
            self._day_pnl = 0.0
            self._trading_halted = False
        self._day_pnl += day_pnl
        if self._day_pnl <= -self.settings.max_daily_loss:
            logger.error("Daily loss limit hit %s", self._day_pnl)
            self._trading_halted = True
            return False
        return True

    def size_for_trade(self, opp):
        return min(opp.max_size, self.settings.max_size_per_trade)
