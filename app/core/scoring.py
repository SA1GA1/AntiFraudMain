"""Маппинг весов правил и вероятности ML в финальный скор 0..10 + challenges/decision."""

from __future__ import annotations

from typing import Literal, Optional

SimpleDecision = Literal["safe", "unsafe"]
WebChallenge = Literal["safe", "captcha", "email", "sms", "second_device"]
MobileChallenge = Literal["safe", "gyroscope", "touch_id", "face_id", "sms", "email"]

WEIGHT_TO_SCORE = 2.0  # rule weight 2.0 → score 4.0


def score_from_weights(total_weight: float) -> float:
    return round(min(10.0, max(0.0, total_weight * WEIGHT_TO_SCORE)), 1)


def score_from_probability(probability: float) -> float:
    return round(min(10.0, max(0.0, probability * 10.0)), 1)


def web_challenges_from_score(score: float) -> list[WebChallenge]:
    if score < 3.0:
        return ["safe"]
    if score < 5.0:
        return ["captcha"]
    if score < 8.5:
        return ["captcha", "email", "sms"]
    return ["captcha", "email", "sms", "second_device"]


def mobile_challenges_from_score(score: float) -> list[MobileChallenge]:
    if score < 3.0:
        return ["safe"]
    if score < 5.0:
        return ["gyroscope"]
    if score < 8.5:
        return ["gyroscope", "face_id", "sms"]
    return ["gyroscope", "touch_id", "face_id", "sms", "email"]


def decision_from_score(score: float) -> SimpleDecision:
    return "safe" if score < 5.0 else "unsafe"


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
