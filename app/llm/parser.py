"""Безопасный парсинг ответа LLM с clamp 0..10."""

from __future__ import annotations


def parse_llm_score(payload: dict) -> tuple[float, str]:
    raw = payload.get("score", 0)
    try:
        score = float(raw)
    except (TypeError, ValueError):
        score = 0.0
    score = max(0.0, min(10.0, score))
    reason = str(payload.get("reason", "") or "").strip()[:300]
    return score, reason
