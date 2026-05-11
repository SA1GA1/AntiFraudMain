"""Маппинг весов правил и вероятности ML в финальный скор 0..10 + decision."""

from __future__ import annotations

from typing import Literal, Optional

Decision = Literal["safe", "review", "sms", "biometry"]

WEIGHT_TO_SCORE = 2.0  # rule weight 2.0 → score 4.0 (одно критичное правило → review/sms)


def score_from_weights(total_weight: float) -> float:
    return round(min(10.0, max(0.0, total_weight * WEIGHT_TO_SCORE)), 1)


def score_from_probability(probability: float) -> float:
    return round(min(10.0, max(0.0, probability * 10.0)), 1)


def decision_from_score(score: float) -> Decision:
    if score < 3.0:
        return "safe"
    if score < 6.0:
        return "review"
    if score < 8.0:
        return "sms"
    return "biometry"


def combine_rules_and_ml(
    rules_weight: float,
    threshold: float,
    ml_probability: Optional[float],
) -> tuple[float, bool]:
    """Возвращает (final_score, used_model).

    Fail-fast: если rules_weight >= threshold → возвращаем чисто rule-скор,
    ML НЕ нужен. Иначе — комбинируем как max(rule_score, ml_score).
    """
    rule_score = score_from_weights(rules_weight)
    if rules_weight >= threshold:
        return rule_score, False
    if ml_probability is None:
        return rule_score, False
    ml_score = score_from_probability(ml_probability)
    return max(rule_score, ml_score), True
