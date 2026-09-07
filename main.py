"""Polymarket CTF merge-arbitrage bot entrypoint."""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from src.config import Settings
from src.executor import Executor
from src.notifier import Notifier
from src.risk import RiskManager, find_opportunity
from src.scanner import ClobClient, resolve_watchlist

logger = logging.getLogger(__name__)


def build_logging(verbose):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


async def run(settings):
    notifier = Notifier(settings)
    client = ClobClient()
    executor = Executor(settings, clob=client)
    risk = RiskManager(settings)
    logger.info("Starting bot mode=%s", settings.mode)
    while True:
        try:
            markets = await resolve_watchlist(client, settings)
            if not markets:
                logger.info("No markets; sleeping 60s")
                await asyncio.sleep(60)
                continue
            for m in markets:
                if not risk.can_trade():
                    break
                book = await client.get_orderbook(m.yes_token_id)
                opp = find_opportunity(m, book, settings)
                if opp is None:
                    continue
                size = risk.size_for_trade(opp)
                logger.info("OPP %s size=%s cost=%s", m.slug, size, opp.combined_cost)
                record = await executor.execute(opp, size)
                risk.mark_open()
                if record.status == "settled":
                    risk.check_daily_loss(size * opp.profit_per_pair)
                msg = "CTF arb: " + m.slug + " size=" + str(size) + " profit=" + str(opp.profit_per_pair)
                await notifier.send(msg)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Loop error: %s", exc)
        await asyncio.sleep(settings.poll_interval)
    await notifier.close()
    await client.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=None)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    build_logging(args.verbose)
    settings = Settings()
    try:
        asyncio.run(run(settings))
    except KeyboardInterrupt:
        logger.info("Shutting down")


