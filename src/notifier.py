"""Optional Telegram alerts via Bot API."""
from __future__ import annotations

import logging

import httpx

from src.config import Settings

logger = logging.getLogger(__name__)


class Notifier:
    def __init__(self, settings):
        self.settings = settings
        self.enabled = bool(settings.telegram_bot_token and settings.telegram_chat_id)
        self._client = None

    async def _get_client(self):
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=10.0)
        return self._client

    async def send(self, text):
        if not self.enabled:
            return
        client = await self._get_client()
        url = "https://api.telegram.org/bot" + settings.telegram_bot_token + "/sendMessage"
        payload = {"chat_id": str(settings.telegram_chat_id), "text": text}
        try:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
        except Exception as exc:
            logger.warning("Telegram send failed: %s", exc)

    async def close(self):
        if self._client is not None:
            await self._client.aclose()
            self._client = None
