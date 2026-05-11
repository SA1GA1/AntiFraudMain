"""Async-клиент к merchant_mock сервису."""

from __future__ import annotations

from typing import Any, Optional

import httpx


class MerchantClient:
    def __init__(self, base_url: str, timeout_ms: int = 500) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_ms / 1000.0
        self._client = httpx.AsyncClient(timeout=self.timeout_s)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def fetch(self, site_name: str) -> Optional[dict[str, Any]]:
        try:
            resp = await self._client.get(f"{self.base_url}/merchant/{site_name}")
        except httpx.HTTPError:
            return None
        if resp.status_code != 200:
            return None
        return resp.json()
