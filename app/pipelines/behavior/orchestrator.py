"""Behavior pipeline: apply_rules → fail-fast → ML → ScoreResponse."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Literal, Optional, Union

import pandas as pd

from app.core.scoring import (
    combine_rules_and_ml,
    mobile_challenges_from_score,
    web_challenges_from_score,
)
from app.ml.loader import ModelBundle
from app.pipelines.behavior.rules import BehaviorContext, apply_rules
from app.schemas.common import MobileBehaviorScoreResponse, WebBehaviorScoreResponse

BehaviorScoreResponse = Union[WebBehaviorScoreResponse, MobileBehaviorScoreResponse]


@dataclass
class BehaviorRuntime:
    bundle: ModelBundle
    history_df: Optional[pd.DataFrame]
    rule_threshold: float


def score_behavior(
    event: dict,
    runtime: BehaviorRuntime,
    kind: Literal["web", "mobile"],
) -> BehaviorScoreResponse:
    started = time.perf_counter()
    ctx = _build_context(event, runtime.history_df)

    rules_outcome = apply_rules(event, ctx)

    ml_prob: Optional[float] = None
    if rules_outcome.total_weight < runtime.rule_threshold:
        ml_prob = runtime.bundle.predict_proba(event, runtime.history_df)

    final_score, used_model = combine_rules_and_ml(
        rules_weight=rules_outcome.total_weight,
        threshold=runtime.rule_threshold,
        ml_probability=ml_prob,
    )

    reasons = [f"rule:{r.name}" for r in rules_outcome.triggered]
    if ml_prob is not None:
        reasons.append(f"ml:p_fraud={ml_prob:.3f}")

    latency_ms = int((time.perf_counter() - started) * 1000)

    if kind == "web":
        return WebBehaviorScoreResponse(
            score=final_score,
            challenges=web_challenges_from_score(final_score),
            reasons=reasons,
            used_model=used_model,
            latency_ms=latency_ms,
        )
    return MobileBehaviorScoreResponse(
        score=final_score,
        challenges=mobile_challenges_from_score(final_score),
        reasons=reasons,
        used_model=used_model,
        latency_ms=latency_ms,
    )


def _build_context(event: dict, history_df: Optional[pd.DataFrame]) -> BehaviorContext:
    if history_df is None:
        return BehaviorContext()
    customer_id = event.get("customer_id")
    if customer_id is None:
        return BehaviorContext()
    rows = history_df[history_df["customer_id"] == customer_id]
    if rows.empty:
        return BehaviorContext()
    row = rows.iloc[0]
    median = float(row.get("amt_mean", 0.0)) if "amt_mean" in row else None
    night_share = float(row.get("night_ops_share", 0.0)) if "night_ops_share" in row else 0.0
    return BehaviorContext(
        amt_median=median if median and median > 0 else None,
        known_devices=set(),  # parquet содержит share-агрегаты, без device_id
        known_night_hour=night_share > 0.05,
    )
