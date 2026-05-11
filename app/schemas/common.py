from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Decision = Literal["safe", "review", "sms", "biometry"]


class ScoreResponse(BaseModel):
    score: float = Field(..., ge=0.0, le=10.0, description="Fraud score: 0 — clean, 10 — definitely fraud")
    decision: Decision = Field(..., description="Recommended action for the bank")
    reasons: list[str] = Field(default_factory=list, description="Human-readable signals that influenced the score")
    used_model: bool = Field(..., description="Whether ML/LLM model was invoked (false = pure rule-based shortcut)")
    latency_ms: int = Field(..., ge=0)
