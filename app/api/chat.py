from __future__ import annotations

from fastapi import APIRouter, Body, Depends

from app.config import Settings
from app.deps import get_llm, get_settings
from app.pipelines.chat.orchestrator import score_chat
from app.schemas.common import ScoreResponse

router = APIRouter(prefix="/score", tags=["chat"])


@router.post("/chat", response_model=ScoreResponse)
async def score_chat_endpoint(
    payload: dict = Body(...),
    settings: Settings = Depends(get_settings),
    llm=Depends(get_llm),
) -> ScoreResponse:
    return await score_chat(
        payload=payload,
        threshold=settings.rule_threshold_chat,
        llm=llm,
    )
