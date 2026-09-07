"""Async retry helper with exponential backoff + jitter."""
from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


async def retry_async(
    coro: Callable[[], Awaitable[T]],
    retries: int =  5,
    base_delay: float = 0.5,
    max_delay: float =  10.0,
    backoff: float = 2.0,
    retry_exc: type[Exception] = Exception,
) -> T:
    """Retry a coroutine factory until success or retries exhausted."""
    delay = base_delay
    for attempt in range(1, retries + 1):
        try:
            return await asyncio.wait_for(coro(), timeout=max(30.0, max_delay))
        except retry_exc as exc:
            if attempt >= retries:
                raise
            jitter = random.uniform(0.0, delay * 0.3)
            logger.warning("Retry %d/%d after %s: %s", attempt, retries, delay, exc)
            await asyncio.sleep(delay + jitter)
            delay = min(delay * backoff, max_delay)
    raise RuntimeError("unreachable")