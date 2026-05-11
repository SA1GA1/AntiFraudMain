"""Быстрые сигналы по карточке магазина (без LLM)."""

from __future__ import annotations

from dataclasses import dataclass, field

YOUNG_DOMAIN_DAYS = 60
MID_DOMAIN_DAYS = 180
NEGATIVE_RATING_THRESHOLD = 1
MIN_REVIEWS_FOR_TRUST = 5
SUSPICIOUS_TLDS = (".cc", ".tk", ".click", ".top")


@dataclass
class MerchantTrigger:
    name: str
    weight: float
    detail: str = ""


@dataclass
class MerchantRulesResult:
    triggered: list[MerchantTrigger] = field(default_factory=list)
    total_weight: float = 0.0
    needs_llm: bool = False


def evaluate_merchant(record: dict) -> MerchantRulesResult:
    res = MerchantRulesResult()
    site = (record.get("site_name") or "").lower()
    domain_age = int(record.get("domain_age_days") or 9999)
    reviews = record.get("reviews") or []

    if domain_age < YOUNG_DOMAIN_DAYS:
        res.triggered.append(
            MerchantTrigger("young_domain", 2.0, f"{domain_age}d < {YOUNG_DOMAIN_DAYS}")
        )
        res.total_weight += 2.0

    if any(site.endswith(tld) for tld in SUSPICIOUS_TLDS):
        res.triggered.append(MerchantTrigger("suspicious_tld", 1.0, site))
        res.total_weight += 1.0

    if reviews:
        bad = sum(1 for r in reviews if int(r.get("rating", 5)) <= NEGATIVE_RATING_THRESHOLD)
        share = bad / len(reviews)
        if share >= 0.3:
            res.triggered.append(
                MerchantTrigger("negative_reviews", 2.5, f"{bad}/{len(reviews)} 1★")
            )
            res.total_weight += 2.5
    if len(reviews) < MIN_REVIEWS_FOR_TRUST and domain_age < MID_DOMAIN_DAYS:
        res.triggered.append(
            MerchantTrigger("few_reviews_young_domain", 1.0, f"{len(reviews)} reviews")
        )
        res.total_weight += 1.0

    inn = str(record.get("inn") or "").strip()
    if inn in {"", "0000000000"} or len(inn.replace("0", "")) == 0:
        res.triggered.append(MerchantTrigger("invalid_inn", 1.5, inn or "<empty>"))
        res.total_weight += 1.5

    res.needs_llm = res.total_weight > 0 or domain_age < MID_DOMAIN_DAYS
    return res
