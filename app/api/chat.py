from __future__ import annotations

from fastapi import APIRouter, Body, Depends

from app.api.score_openapi_examples import CHAT_OPENAPI_HIGH_PFRAUD, CHAT_OPENAPI_LOW_PFRAUD
from app.config import Settings
from app.deps import get_llm, get_settings
from app.pipelines.chat.orchestrator import score_chat
from app.schemas.common import SimpleScoreResponse

router = APIRouter(prefix="/score", tags=["chat"])


@router.post(
    "/chat",
    response_model=SimpleScoreResponse,
    summary="Score chat messages for social-engineering / phishing",
    description=(
        "Pipeline: regex + meta-сигналы → если суммарный вес правил выше порога, "
        "зовётся LLM (Ollama) для финального решения. На чистых сообщениях LLM "
        "не вызывается — отвечаем сразу по правилам."
    ),
)
async def score_chat_endpoint(
    payload: dict = Body(
        ...,
        openapi_examples={
            "chat_low_p_fraud": {
                "summary": "Chat — низкий p_fraud (все поля контракта)",
                "description": (
                    "Полный `counterparty_metadata` (включая geo) и два сообщения с "
                    "нормальным тоном; regex/meta дают малый вес, LLM часто не вызывается."
                ),
                "value": CHAT_OPENAPI_LOW_PFRAUD,
            },
            "chat_high_p_fraud": {
                "summary": "Chat — высокий p_fraud (все поля контракта)",
                "description": (
                    "Новый непроверенный контрагент + ссылки и давление в тексте; "
                    "суммарный вес правил выше порога → LLM (если доступна) с высоким скором."
                ),
                "value": CHAT_OPENAPI_HIGH_PFRAUD,
            },
        },
    ),
    settings: Settings = Depends(get_settings),
    llm=Depends(get_llm),
) -> SimpleScoreResponse:
    return await score_chat(
        payload=payload,
        threshold=settings.rule_threshold_chat,
        llm=llm,
    )
