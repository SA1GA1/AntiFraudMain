from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from app.config import Settings
from app.core.logging import get_logger
from app.deps import (
    get_event_sink,
    get_history_mobile,
    get_history_web,
    get_loader,
    get_settings,
)
from app.pipelines.behavior.orchestrator import BehaviorRuntime, score_behavior
from app.schemas.behavior import is_web_payload
from app.schemas.common import ScoreResponse

router = APIRouter(prefix="/score", tags=["behavior"])
_LOGGER = get_logger("api.behavior")


@router.post("/behavior", response_model=ScoreResponse)
async def score_behavior_endpoint(
    request: Request,
    payload: dict = Body(...),
    settings: Settings = Depends(get_settings),
    loader=Depends(get_loader),
    history_web=Depends(get_history_web),
    history_mobile=Depends(get_history_mobile),
    event_sink=Depends(get_event_sink),
) -> ScoreResponse:
    if loader is None:
        raise HTTPException(status_code=503, detail="ML loader not initialized")

    is_web = is_web_payload(payload)
    kind = "web" if is_web else "mobile"
    bundle = loader.load_web() if is_web else loader.load_mobile()
    history = history_web if is_web else history_mobile
    history_df = history.dataframe if history is not None else None

    runtime = BehaviorRuntime(
        bundle=bundle,
        history_df=history_df,
        rule_threshold=settings.rule_threshold_behavior,
    )
    response = score_behavior(payload, runtime)

    if event_sink is not None:
        try:
            event_sink.enqueue(payload, kind)
        except Exception as exc:
            _LOGGER.warning("event_sink_enqueue_failed", error=str(exc))

    return response
