"""LLM-обёртка для merchant: prompt + JSON-парсинг."""

from __future__ import annotations

import json
from typing import Protocol

from app.llm.parser import parse_llm_score
from app.llm.prompts import MERCHANT_SYSTEM


class LLMClient(Protocol):
    async def chat_json(self, system: str, user: str) -> dict: ...


async def score_merchant_with_llm(record: dict, client: LLMClient) -> tuple[float, str]:
    user = json.dumps(record, ensure_ascii=False)
    raw = await client.chat_json(system=MERCHANT_SYSTEM, user=user)
    return parse_llm_score(raw)
