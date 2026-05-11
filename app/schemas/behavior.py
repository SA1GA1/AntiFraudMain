"""Pydantic-схемы поведенческих событий из task.md.

Минимальная валидация (только критичные для rules/ML поля), остальные принимаем
через extra="allow" — payload переходит в модель как dict.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class _BaseEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    customer_id: int | str
    event_id: int | str
    event_dttm: str | None = None
    operaton_amt: float = Field(0.0, ge=0)
    hour_of_day: Optional[int] = Field(None, ge=0, le=23)
    day_of_week: Optional[int] = Field(None, ge=0, le=6)

    is_vpn_detected: int = 0
    is_proxy_detected: int = 0
    geo_speed_km_h: float = 0.0
    session_duration_sec: float = 0.0
    transfers_count_last_10min: int = 0


class MobileBehaviorEvent(_BaseEvent):
    os_type: str = "Android"
    device_id: Optional[str] = None
    is_new_device: int = 0


class WebBehaviorEvent(_BaseEvent):
    browser_fingerprint: Optional[str] = None
    user_agent: Optional[str] = None
    is_tor_detected: int = 0
    is_new_browser: int = 0
    is_new_device: int = 0


def is_web_payload(payload: dict) -> bool:
    """Грубая эвристика для дискриминатора web/mobile."""
    if "browser_fingerprint" in payload or "user_agent" in payload:
        return True
    if "browser_name" in payload:
        return True
    os_type = (payload.get("os_type") or "").lower()
    if os_type in {"ios", "android"}:
        return False
    return False
