from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.core.scoring import MobileChallenge, SimpleDecision, WebChallenge


class MerchantScoreRequest(BaseModel):
    """Тело запроса `/score/merchant`.

    Отзывы (`reviews`) и прочая enrichment-карточка магазина (домен, ИНН,
    регистрация, IP) НЕ принимаются от клиента — они подтягиваются
    бэкендом из `merchant_mock` по `site_name`/`merchant_name`.
    """

    model_config = ConfigDict(extra="forbid")

    site_name: Optional[str] = Field(
        default=None,
        description="Доменное имя магазина, по которому идёт lookup в merchant_mock.",
    )
    merchant_name: Optional[str] = Field(
        default=None,
        description="Альтернативное имя получателя платежа (используется, если site_name пуст).",
    )


class _BaseScoreResponse(BaseModel):
    score: float = Field(..., ge=0.0, le=10.0, description="Fraud score: 0 — clean, 10 — definitely fraud")
    reasons: list[str] = Field(default_factory=list, description="Human-readable signals that influenced the score")
    used_model: bool = Field(..., description="Whether ML/LLM model was invoked (false = pure rule-based shortcut)")
    latency_ms: int = Field(..., ge=0)


class WebBehaviorScoreResponse(_BaseScoreResponse):
    challenges: list[WebChallenge] = Field(
        ...,
        min_length=1,
        description="Список челленджей для web-клиента (от лёгкого к тяжёлому). \"safe\" — никаких проверок не нужно.",
    )


class MobileBehaviorScoreResponse(_BaseScoreResponse):
    challenges: list[MobileChallenge] = Field(
        ...,
        min_length=1,
        description="Список челленджей для mobile-клиента (от лёгкого к тяжёлому). \"safe\" — никаких проверок не нужно.",
    )


class SimpleScoreResponse(_BaseScoreResponse):
    decision: SimpleDecision = Field(
        ...,
        description="Бинарное решение: safe — транзакция/контакт чистые, unsafe — есть фрод-сигнал.",
    )


class ReloadModelRequest(BaseModel):
    model_name: Literal["fraud_mlp_web", "fraud_mlp_mobile"]
    version: Optional[int] = None


class ReloadModelResponse(BaseModel):
    reloaded: bool = True
    model_name: str
    version: int
    previous_version: Optional[int] = None


LabelSource = Literal["manual", "chargeback", "fraud_team", "complaint"]


class LabelRow(BaseModel):
    customer_id: int | str
    event_id: int | str
    target: Literal[0, 1]
    kind: Literal["web", "mobile"]


class LabelsBatchResponse(BaseModel):
    written: int
    paths: list[str]
