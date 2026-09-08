"""SQLite persistence for trade records and daily PnL (aiosqlite)."""
from __future__ import annotations

import asyncio
import logging
from datetime import date
from pathlib import Path
from typing import Optional

import aiosqlite

logger = logging.getLogger(__name__)


SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    mode TEXT NOT NULL,
    market_slug TEXT NOT NULL,
    condition_id TEXT,
    yes_token_id TEXT,
    no_token_id TEXT,
    yes_price REAL NOT NULL,
    no_price REAL NOT NULL,
    size REAL NOT NULL,
    fee_usd REAL NOT NULL DEFAULT 0.0,
    cost_basis REAL NOT NULL DEFAULT 0.0,
    merge_amount REAL NOT NULL DEFAULT 0.0,
    tx_hash TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_trades_ts ON trades(ts);
CREATE TABLE IF NOT EXISTS daily_pnl (
    day TEXT PRIMARY KEY,
    gross_est REAL NOT NULL DEFAULT 0.0,
    fee_total REAL NOT NULL DEFAULT 0.0,
    pnl_est REAL NOT NULL DEFAULT 0.0,
    trades_count INTEGER NOT NULL DEFAULT 0
);
"""


class TradeStore:
    """Async SQLite store for trade history and daily PnL estimates."""

    def __init__(self, db_path: str | Path = "data/bot.db"):
        self.db_path = Path(db_path)
        self._conn: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()

    async def init(self) -> None:
        """Open the database and create schema if needed."""
        if self._conn is not None:
            return
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(str(self.db_path))
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()

    async def _execute(self, sql: str, params: tuple) -> None:
        async with self._lock:
            cursor = await self._conn.execute(sql, params)
            await self._conn.commit()
            await cursor.close()

    async def record_trade(self, record: "TradeRecord") -> None:
        """Persist a trade record (settled or failed) into SQLite."""
        await self.init()
        opp = record.opportunity
        market = opp.market
        total_fee = sum(f.fee_usd for f in (record.fills or []))
        pair_cost = (record.pportunity.yes_ask + record.opportunity.no_ask) if record.opportunity else 0.0
        if record.merge is not None:
            size = record.merge.merged_amount
            tx_hash = record.merge.tx_hash
        elif record.fills:
            size = record.fills[0].size
            tx_hash = None
        else:
            size = 0.0
            tx_hash = None

        row = (
            record.ts.isoformat(),
            record.mode,
            market.slug,
            market.condition_id,
            market.yes_token_id,
            market.no_token_id,
            opp.yes_ask,
            opp.no_ask,
            size,
            total_fee,
            pair_cost * size + total_fee,
            size,
            tx_hash,
            record.status,
            record.error,
        )
        sql = """
            INSERT INTO trades (
                ts, mode, market_slug, condition_id, yes_token_id, no_token_id,
                yes_price, no_price, size, fee_usd, cost_basis, merge_amount, tx_hash, status, error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        try:
            await self._execute(sql, row)
            await self._update_daily_pnl(record.ts.date(), size, pair_cost * size + total_fee, total_fee, record.status)
        except Exception as exc:  # pragma: no cover
            logger.exception("failed to persist trade record: %s", exc)

    async def _update_daily_pnl(self, day: date, size: float, cost_basis: float, fee: float, status: str) -> None:
        """Accumulate per-day PnL estimates for settled trades."""
        if status != "settled" or size <= 0:
            return
        gain_est = size - fee
        pnl_est = size - cost_basis
        async with self._lock:
            await self._conn.execute(
                """
                INSERT INTO daily_pnl (day, gross_est, fee_total, pnl_est, trades_count)
                VALUES (?, ?, ?, ?, 1)
                ON CONFLICT(day) DO UPDATE SET
                    gross_est = gross_est + excluded.gross_est,
                    fee_total = fee_total + excluded.fee_total,
                    pnl_est = pnl_est + excluded.pnl_est,
                    trades_count = trades_count + 1
                """,
                (day.isoformat(), gain_est, fee, pnl_est),
            )
            await self._conn.commit()

    async def load_recent(self, limit: int = 50) -> list[dict]:
        """Loadthe most recent trade rows as dicts."""
        await self.init()
        cursor = await self._conn.execute(
            "SELECT * FROM trades ORDER BY id DESC LIMIT ?", (limit,)
        )
        rows = await cursor.fetchall()
        await cursor.close()
        return [dict(r) for r in rows]

    async def compute_daily_pnl(self, days: int = 7) -> list[dict]:
        """Return daily PnL summaries for the last `days` days (oldest first)."""
        await self.init()
        cursor = await self._conn.execute(
            """
            SELECT day, gross_est, fee_total, pnl_est, trades_count
            FROM daily_pnl ORDER BY day DESC LIMIT ?
            """,
            (days,),
        )
        rows = await cursor.fetchall()
        await cursor.close()
        return [dict(r) for r in reversed(rows)]

    async def close(self) -> None:
        """Close the underlying connection."""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None