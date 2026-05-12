from __future__ import annotations

from fastapi import APIRouter, Body, Depends

from app.api.score_openapi_examples import MERCHANT_OPENAPI_HIGH_PFRAUD, MERCHANT_OPENAPI_LOW_PFRAUD
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
            "merchant_low_p_fraud": {
                "summary": "Merchant — низкий p_fraud (полная карточка)",
                "description": (
                    "Полный JSON как в task.md: `site_name`/`merchant_name`, реквизиты, "
                    "отзывы. Инференс использует `site_name` для mock; лишние поля не мешают."
                ),
                "value": MERCHANT_OPENAPI_LOW_PFRAUD,
            },
            "merchant_high_p_fraud": {
                "summary": "Merchant — высокий p_fraud (полная карточка)",
                "description": (
                    "Известный фрод-домен из seed + негативные отзывы; правила и/или LLM "
                    "дают высокий скор (зависит от mock и модели)."
                ),
                "value": MERCHANT_OPENAPI_HIGH_PFRAUD,
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
