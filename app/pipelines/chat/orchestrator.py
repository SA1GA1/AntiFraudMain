"""Chat pipeline: regex → fail-fast → LLM → ScoreResponse."""

from __future__ import annotations

import time
from typing import Optional

from app.core.scoring import combine_rules_and_ml, decision_from_score
from app.pipelines.chat.filter import score_thread
from app.pipelines.chat.llm import LLMClient, score_chat_with_llm
from app.schemas.common import ScoreResponse


async def score_chat(
    payload: dict,
    threshold: float,
    llm: Optional[LLMClient],
) -> ScoreResponse:
    started = time.perf_counter()
    rules = score_thread(payload)

    llm_prob: Optional[float] = None
    llm_reason = ""
    if rules.total_weight >= threshold and llm is not None:
        try:
            llm_score, llm_reason = await score_chat_with_llm(payload, llm)
            llm_prob = llm_score / 10.0
        except Exception:
            llm_prob = None

    final_score, used_model = combine_rules_and_ml(
        rules_weight=rules.total_weight,
        threshold=10_000.0,  # для chat не делаем early-exit без LLM, т.к. сами правила
                              # дают грубый сигнал; LLM уточняет
        ml_probability=llm_prob,
    )

    reasons = [f"rule:{t.name}" for t in rules.triggered]
    if llm_reason:
        reasons.append(f"llm:{llm_reason}")

    return ScoreResponse(
        score=final_score,
        decision=decision_from_score(final_score),
        reasons=reasons,
        used_model=used_model,
        latency_ms=int((time.perf_counter() - started) * 1000),
    )
