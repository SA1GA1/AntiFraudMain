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


@router.post(
    "/behavior",
    response_model=ScoreResponse,
    summary="Score behavioural event (mobile/web)",
    description=(
        "Pipeline: rules → fail-fast → PyTorch FraudMLP. "
        "Discriminator mobile/web — по наличию `browser_fingerprint`/`user_agent` "
        "или `os_type ∈ {ios, android}`. Любые поля из task.md принимаются "
        "(`extra=allow`), обязательны только `customer_id` и `event_id`."
    ),
)
async def score_behavior_endpoint(
    request: Request,
    payload: dict = Body(
        ...,
        openapi_examples={
            "mobile_clean": {
                "summary": "Mobile, чистый кейс (доходит до ML)",
                "value": {
                    "customer_id": 8888,
                    "event_id": 2,
                    "operaton_amt": 1500,
                    "geo_speed_km_h": 30,
                    "hour_of_day": 14,
                    "is_vpn_detected": 0,
                    "is_proxy_detected": 0,
                    "session_duration_sec": 60,
                    "os_type": "Android",
                    "device_id": "dev_abc",
                    "is_new_device": 0,
                },
            },
            "mobile_obvious_fraud": {
                "summary": "Mobile, fail-fast по правилам (VPN+гео-телепорт+сумма)",
                "value": {
                    "customer_id": 9999,
                    "event_id": 1,
                    "operaton_amt": 250000,
                    "geo_speed_km_h": 1500,
                    "is_vpn_detected": 1,
                    "session_duration_sec": 60,
                    "os_type": "Android",
                },
            },
            "web_clean": {
                "summary": "Web, чистый кейс",
                "value": {
                    "customer_id": 7777,
                    "event_id": "evt_w_001",
                    "operaton_amt": 4200,
                    "hour_of_day": 11,
                    "browser_fingerprint": "fp_a1b2c3",
                    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                    "is_tor_detected": 0,
                    "is_new_browser": 0,
                    "is_new_device": 0,
                },
            },
        },
    ),
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
