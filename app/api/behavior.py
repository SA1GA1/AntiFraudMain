from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from app.config import Settings
from app.deps import get_history, get_loader, get_settings
from app.pipelines.behavior.orchestrator import BehaviorRuntime, score_behavior
from app.schemas.behavior import is_web_payload
from app.schemas.common import ScoreResponse

router = APIRouter(prefix="/score", tags=["behavior"])


@router.post("/behavior", response_model=ScoreResponse)
async def score_behavior_endpoint(
    request: Request,
    payload: dict = Body(...),
    settings: Settings = Depends(get_settings),
    loader=Depends(get_loader),
    history=Depends(get_history),
) -> ScoreResponse:
    if loader is None:
        raise HTTPException(status_code=503, detail="ML loader not initialized")

    bundle = loader.load_web() if is_web_payload(payload) else loader.load_mobile()
    history_df = history.dataframe if history is not None else None

    runtime = BehaviorRuntime(
        bundle=bundle,
        history_df=history_df,
        rule_threshold=settings.rule_threshold_behavior,
    )
    return score_behavior(payload, runtime)
