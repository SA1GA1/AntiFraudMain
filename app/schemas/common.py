from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

Decision = Literal["safe", "review", "sms", "biometry"]


class ScoreResponse(BaseModel):
    score: float = Field(..., ge=0.0, le=10.0, description="Fraud score: 0 — clean, 10 — definitely fraud")
    decision: Decision = Field(..., description="Recommended action for the bank")
    reasons: list[str] = Field(default_factory=list, description="Human-readable signals that influenced the score")
    used_model: bool = Field(..., description="Whether ML/LLM model was invoked (false = pure rule-based shortcut)")
    latency_ms: int = Field(..., ge=0)


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
