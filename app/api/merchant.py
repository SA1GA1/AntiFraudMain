from __future__ import annotations

from fastapi import APIRouter, Body, Depends

from app.api.score_openapi_examples import MERCHANT_OPENAPI_HIGH_PFRAUD, MERCHANT_OPENAPI_LOW_PFRAUD
from app.config import Settings
from app.deps import get_llm, get_merchant, get_settings
from app.pipelines.merchant.orchestrator import score_merchant
from app.schemas.common import MerchantScoreRequest, SimpleScoreResponse

router = APIRouter(prefix="/score", tags=["merchant"])


@router.post(
    "/merchant",
    response_model=SimpleScoreResponse,
    summary="Score merchant / online store by name or domain",
    description=(
        "Pipeline: GET в merchant_mock → правила → если сработали ИЛИ домен молодой, "
        "зовётся LLM с карточкой магазина и отзывами. Принимает только `site_name` или "
        "`merchant_name`; отзывы и прочие реквизиты НЕ принимаются — они берутся из "
        "merchant_mock по `site_name`."
    ),
)
async def score_merchant_endpoint(
    payload: MerchantScoreRequest = Body(
        ...,
        openapi_examples={
            "merchant_low_p_fraud": {
                "summary": "Merchant — низкий p_fraud",
                "description": (
                    "Запрос содержит только идентификатор магазина; карточка и "
                    "отзывы будут получены из merchant_mock."
                ),
                "value": MERCHANT_OPENAPI_LOW_PFRAUD,
            },
            "merchant_high_p_fraud": {
                "summary": "Merchant — высокий p_fraud",
                "description": (
                    "Известный фрод-домен из seed; правила и/или LLM дают высокий "
                    "скор по карточке из merchant_mock."
                ),
                "value": MERCHANT_OPENAPI_HIGH_PFRAUD,
            },
        },
    ),
    settings: Settings = Depends(get_settings),
    merchant=Depends(get_merchant),
    llm=Depends(get_llm),
) -> SimpleScoreResponse:
    site_name = payload.site_name or payload.merchant_name or ""
    return await score_merchant(
        site_name=str(site_name),
        threshold=settings.rule_threshold_merchant,
        merchant_client=merchant,
        llm=llm,
    )
