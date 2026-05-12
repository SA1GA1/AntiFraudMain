from __future__ import annotations

from fastapi import APIRouter, Body, Depends

from app.config import Settings
from app.deps import get_llm, get_merchant, get_settings
from app.pipelines.merchant.orchestrator import score_merchant
from app.schemas.common import ScoreResponse

router = APIRouter(prefix="/score", tags=["merchant"])


@router.post(
    "/merchant",
    response_model=ScoreResponse,
    summary="Score merchant / online store by name or domain",
    description=(
        "Pipeline: GET в merchant_mock → правила → если сработали ИЛИ домен молодой, "
        "зовётся LLM с карточкой магазина и отзывами. Принимает `site_name` или "
        "`merchant_name` (любое из двух)."
    ),
)
async def score_merchant_endpoint(
    payload: dict = Body(
        ...,
        openapi_examples={
            "known_legit": {
                "summary": "Известный легитимный магазин (правила чистые, LLM не вызывается)",
                "value": {"site_name": "ozon.ru"},
            },
            "young_suspicious_tld": {
                "summary": "Молодой домен на подозрительном TLD",
                "value": {"site_name": "shop-cards-deal.cc"},
            },
            "known_fraud": {
                "summary": "Заранее известный фрод-сайт (триггерит LLM)",
                "value": {"site_name": "fast-pay-service.ru"},
            },
            "unknown": {
                "summary": "Незнакомый магазин",
                "value": {"site_name": "totally-unknown.xyz"},
            },
        },
    ),
    settings: Settings = Depends(get_settings),
    merchant=Depends(get_merchant),
    llm=Depends(get_llm),
) -> ScoreResponse:
    site_name = payload.get("site_name") or payload.get("merchant_name") or ""
    return await score_merchant(
        site_name=str(site_name),
        threshold=settings.rule_threshold_merchant,
        merchant_client=merchant,
        llm=llm,
    )
