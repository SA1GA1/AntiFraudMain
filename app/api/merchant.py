from __future__ import annotations

from fastapi import APIRouter, Body, Depends

from app.config import Settings
from app.deps import get_llm, get_merchant, get_settings
from app.pipelines.merchant.orchestrator import score_merchant
from app.schemas.common import ScoreResponse

router = APIRouter(prefix="/score", tags=["merchant"])


@router.post("/merchant", response_model=ScoreResponse)
async def score_merchant_endpoint(
    payload: dict = Body(...),
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
