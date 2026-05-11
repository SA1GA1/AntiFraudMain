"""LLM-обёртка для chat: формирует prompt, парсит JSON-ответ Ollama."""

from __future__ import annotations

import json
from typing import Protocol

from app.llm.parser import parse_llm_score
from app.llm.prompts import CHAT_SYSTEM


class LLMClient(Protocol):
    async def chat_json(self, system: str, user: str) -> dict: ...


async def score_chat_with_llm(payload: dict, client: LLMClient) -> tuple[float, str]:
    user = json.dumps(payload, ensure_ascii=False)
    raw = await client.chat_json(system=CHAT_SYSTEM, user=user)
    return parse_llm_score(raw)
