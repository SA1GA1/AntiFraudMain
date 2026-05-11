"""Merchant pipeline: GET merchant_mock → правила → (опц.) LLM → ScoreResponse."""

from __future__ import annotations

import time
from typing import Optional

from app.core.scoring import combine_rules_and_ml, decision_from_score
from app.pipelines.merchant.enrich import MerchantClient
from app.pipelines.merchant.llm import LLMClient, score_merchant_with_llm
from app.pipelines.merchant.rules import evaluate_merchant
from app.schemas.common import ScoreResponse


async def score_merchant(
    site_name: str,
    threshold: float,
    merchant_client: MerchantClient,
    llm: Optional[LLMClient],
) -> ScoreResponse:
    started = time.perf_counter()
    record = await merchant_client.fetch(site_name)
    if record is None:
        # Магазин неизвестен — это уже подозрительно (нет вообще данных).
        return ScoreResponse(
            score=5.0,
            decision=decision_from_score(5.0),
            reasons=[f"merchant:unknown:{site_name}"],
            used_model=False,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    rules = evaluate_merchant(record)

    llm_prob: Optional[float] = None
    llm_reason = ""
    if rules.needs_llm and llm is not None:
        try:
            llm_score, llm_reason = await score_merchant_with_llm(record, llm)
            llm_prob = llm_score / 10.0
        except Exception:
            llm_prob = None

    final_score, used_model = combine_rules_and_ml(
        rules_weight=rules.total_weight,
        threshold=threshold if not rules.needs_llm else 10_000.0,
        ml_probability=llm_prob,
    )

    reasons = [f"rule:{t.name}:{t.detail}" for t in rules.triggered]
    if llm_reason:
        reasons.append(f"llm:{llm_reason}")
    reasons.append(f"merchant:domain_age={record.get('domain_age_days')}")

    return ScoreResponse(
        score=final_score,
        decision=decision_from_score(final_score),
        reasons=reasons,
        used_model=used_model,
        latency_ms=int((time.perf_counter() - started) * 1000),
    )
