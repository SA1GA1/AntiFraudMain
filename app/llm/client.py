"""Async-клиент к Ollama (/api/chat) с JSON-mode."""

from __future__ import annotations

import json
from typing import Any

import httpx


class OllamaClient:
    def __init__(self, base_url: str, model: str, timeout_ms: int = 800) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_s = timeout_ms / 1000.0
        self._client = httpx.AsyncClient(timeout=self.timeout_s)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def chat_json(self, system: str, user: str) -> dict[str, Any]:
        """Запрос к /api/chat с format=json. Возвращает распарсенный JSON."""
        payload = {
            "model": self.model,
            "stream": False,
            "format": "json",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        resp = await self._client.post(f"{self.base_url}/api/chat", json=payload)
        resp.raise_for_status()
        body = resp.json()
        content = body.get("message", {}).get("content", "{}")
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return {}
