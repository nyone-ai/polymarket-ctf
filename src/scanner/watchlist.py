"""Watchlist loading + market filtering (explicit / auto / hybrid)."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from src.config import Settings
from src.models import Market, WatchlistMode

logger = logging.getLogger(__name__)


def _is_zero_id(token_id):
    return not token_id or token_id.strip() == "" or token_id.strip() == "0x0000000000000000000000000000000000000000"


def load_explicit(path=None, condition_ids=None):
    if path is None:
        path = "config/markets.watchlist.json"
    p = Path(path)
    if not p.exists():
        logger.warning("Watchlist file %s not found", p)
        return []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Failed to parse watchlist %s: %s", p, exc)
        return []
    markets = []
    for entry in raw.get("markets", []):
        cid = entry.get("condition_id", "")
        if not cid or _is_zero_id(str(cid)) or "Replace" in str(entry.get("question", "")):
            continue
        if "condition_id" not in entry:
            logger.warning("Watchlist entry missing condition_id: %s", entry)
            continue
        yes_id = entry.get("yes_token_id")
        no_id = entry.get("no_token_id")
        if _is_zero_id(yes_id):
            yes_id = None
        if _is_zero_id(no_id):
            no_id = None
        if yes_id is None:
            for x in entry.get("clob_token_ids", []):
                if x:
                    yes_id = str(x)
                    break
        if no_id is None:
            seen_second = False
            for x in entry.get("clob_token_ids", []):
                if not x:
                    continue
                if seen_second:
                    no_id = str(x)
                    break
                seen_second = True
        m = Market(condition_id=str(entry["condition_id"]),question=str(entry.get("question", "")))
        m.slug = str(entry.get("slug", ""))
        m.yes_token_id = str(yes_id) if yes_id else None
        m.no_token_id = str(no_id) if no_id else None
        m.liquidity_usd = float(entry.get("liquidity_usd", 0.0))
        m.volume_24h_usd = float(entry.get("volume_24h_usd", 0.0))
        m.active = bool(entry.get("active", True))
        m.neg_risk = bool(entry.get("neg_risk", False))
        m.clob_token_ids = []
        for x in entry.get("clob_token_ids", []):
            if x:
                m.clob_token_ids.append(str(x))
        m.raw = entry
        markets.append(m)
    existing = {m.condition_id for m in markets}
    for cid in condition_ids or []:
        if str(cid) not in existing:
            mm = Market(condition_id=str(cid), question="")
            markets.append(mm)
            existing.add(mm.condition_id)
    return markets


def filter_auto(markets, settings):
    out = []
    for m in markets:
        if settings.auto_discover_active_only and not m.active:
            continue
        # /markets (V2) no longer exposes liquidity/volume; only filter when reported.
        if m.liquidity_usd > 0.0 and m.liquidity_usd < settings.auto_discover_min_liquidity:
            continue
        if m.volume_24h_usd > 0.0 and m.volume_24h_usd < settings.auto_discover_min_volume_24h:
            continue
        if m.neg_risk:
            continue
        if not m.yes_token_id or not m.no_token_id:
            continue
        out.append(m)
    return out


def build_watchlist(settings, discovered=None):
    mode = WatchlistMode(settings.watchlist_mode)
    explicit = load_explicit(settings.watchlist_path, getattr(settings, "watchlist_condition_ids", None))
    by_cond = {}
    for m in discovered or []:
        by_cond[m.condition_id] = m
    for m in explicit:
        if not m.yes_token_id and m.condition_id in by_cond:
            src = by_cond[m.condition_id]
            m.yes_token_id = src.yes_token_id
            m.no_token_id = src.no_token_id
            m.slug = src.slug
            m.question = src.question
            m.clob_token_ids = list(src.clob_token_ids)
            m.liquidity_usd = src.liquidity_usd
            m.volume_24h_usd = src.volume_24h_usd
    if mode is WatchlistMode.EXPLICIT:
        return explicit if explicit else filter_auto(discovered, settings)
    if mode is WatchlistMode.AUTO:
        return filter_auto(discovered, settings)
    seen = set()
    for m in explicit:
        seen.add(m.condition_id)
    extra = []
    for m in filter_auto(discovered, settings):
        if m.condition_id not in seen:
            extra.append(m)
    return explicit + extra

