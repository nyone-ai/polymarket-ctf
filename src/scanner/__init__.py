"""Market discovery + watchlist resolution."""
from __future__ import annotations

import logging

from src.config import Settings
from src.models import Market
from src.scanner.clob import ClobClient
from src.scanner.watchlist import build_watchlist

logger = logging.getLogger(__name__)


async def discover_markets(client, settings):
    raw = await client.list_markets(limit=2000)
    markets = []
    for item in raw:
        if not item.get("active"):
            continue
        if item.get("neg_risk"):
            continue
        cond = item.get("condition_id")
        tokens = item.get("clobTokenIds")
        if not tokens:
            tokens = []
        if not cond or not tokens:
            continue
        m = Market(condition_id=str(cond), question=str(item.get("question", "")))
        m.slug = str(item.get("slug", ""))
        m.clob_token_ids = [str(x) for x in tokens][:2]
        if len(m.clob_token_ids) >= 2:
            m.yes_token_id = m.clob_token_ids[0]
            m.no_token_id = m.clob_token_ids[1]
        m.liquidity_usd = float(item.get("liquidity", 0) or 0.0)
        m.volume_24h_usd = float(item.get("volume24Hr", 0) or 0.0)
        m.active = True
        m.neg_risk = False
        m.raw = item
        markets.append(m)
    return markets


async def resolve_watchlist(client, settings):
    discovered = None
    if settings.auto_discover:
        try:
            discovered = await discover_markets(client, settings)
            logger.info("Auto-discovered %d markets", len(discovered))
        except Exception as exc:
            logger.warning("Auto-discover failed: %s", exc)
    return build_watchlist(settings, discovered)
