from __future__ import annotations

from fastapi import APIRouter, Body, Depends

from app.config import Settings
from app.deps import get_llm, get_settings
from app.pipelines.chat.orchestrator import score_chat
from app.schemas.common import ScoreResponse

router = APIRouter(prefix="/score", tags=["chat"])


@router.post(
    "/chat",
    response_model=ScoreResponse,
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
            "phishing": {
                "summary": "Фишинг — социнженерия + подозрительная ссылка",
                "value": {
                    "counterparty_metadata": {
                        "user_id": "usr_8492",
                        "verification_status": "unverified",
                        "account_age_days": 3,
                        "geo_location": "KZ-ALA",
                        "geo_mismatch": True,
                        "kyc_level": "none",
                    },
                    "messages": [
                        {
                            "sender_id": "usr_8492",
                            "receiver_id": "usr_1057",
                            "message_text": (
                                "Здравствуйте! Это служба безопасности банка. "
                                "Ваш счёт под угрозой. Срочно переведите средства "
                                "на безопасный кошелёк: "
                                "https://sber-bank-secure.ru/verify"
                            ),
                            "timestamp": "2024-05-20T14:30:00Z",
                        }
                    ],
                },
            },
            "clean": {
                "summary": "Безобидная переписка",
                "value": {
                    "counterparty_metadata": {
                        "user_id": "usr_friend",
                        "verification_status": "verified",
                        "account_age_days": 1500,
                        "geo_mismatch": False,
                        "kyc_level": "full",
                    },
                    "messages": [
                        {
                            "sender_id": "usr_friend",
                            "receiver_id": "usr_1057",
                            "message_text": "Привет! Когда увидимся?",
                            "timestamp": "2024-05-20T14:30:00Z",
                        }
                    ],
                },
            },
        },
    ),
    settings: Settings = Depends(get_settings),
    llm=Depends(get_llm),
) -> ScoreResponse:
    return await score_chat(
        payload=payload,
        threshold=settings.rule_threshold_chat,
        llm=llm,
    )
