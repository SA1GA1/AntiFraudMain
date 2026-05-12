from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Body, Depends, HTTPException

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
from app.schemas.behavior import MobileBehaviorEvent, WebBehaviorEvent
from app.schemas.common import ScoreResponse

router = APIRouter(prefix="/score", tags=["behavior"])
_LOGGER = get_logger("api.behavior")

# Полный веб-контракт task.md + поля для rules + числовые/категориальные колонки web FraudMLP
# (_pkg_web/preprocess). Лишние ключи безопасны (препроцессор заполняет пропуски).
_WEB_CLEAN_OPENAPI_EXAMPLE: dict[str, object] = {
    "customer_id": 7777,
    "event_id": 7777001001,
    "session_id": 7777002001,
    "device_id": "dev_browser_stable_01",
    "event_dttm": "2026-05-12T14:30:00+03:00",
    "hour_of_day": 14,
    "day_of_week": 1,
    "browser_fingerprint": "fp_sha256_a1b2c3d4e5f67890",
    "user_agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "browser_name": "Chrome",
    "browser_version": "124.0.0.0",
    "os_type": "Windows",
    "os_version": "10.0",
    "operaton_amt": 4200.0,
    "currency_iso_cd": "RUB",
    "mcc_code": "5411",
    "merchant_name": "SUPERMARKET_OK",
    "pos_cd": "ECOM",
    "transaction_type": "payment",
    "is_developer_tools": 0,
    "developer_tools_enabled": 0,
    "is_headless_browser": 0,
    "screen_resolution": "1920x1080",
    "screen_color_depth": 24,
    "timezone_offset": 180,
    "timezone_offset_minutes": 180,
    "system_language": "ru-RU",
    "browser_language": "ru-RU",
    "accept_language": "ru-RU,ru;q=0.9,en;q=0.8",
    "is_incognito": 0,
    "installed_fonts_count": 312,
    "ip_address_hash": "sha256_ip_anon_prefixed_01",
    "is_vpn_detected": 0,
    "is_proxy_detected": 0,
    "is_tor_detected": 0,
    "connection_type": "wifi",
    "network_rtt_avg_ms": 38.5,
    "asn": 8359,
    "isp_name": "Residential ISP Mock",
    "mouse_velocity_avg": 0.42,
    "mouse_acceleration_avg": 0.08,
    "mouse_jitter_score": 0.12,
    "mouse_linearity_score": 0.88,
    "click_duration_avg_ms": 95.0,
    "right_click_count": 2,
    "scroll_velocity_avg": 1.1,
    "keyboard_typing_speed_median_ms": 118.0,
    "keyboard_typing_speed_std_dev": 22.0,
    "keyboard_typing_rhythm_cv": 0.19,
    "backspace_ratio": 0.04,
    "clipboard_paste_ratio": 0.01,
    "copy_events_count": 1,
    "paste_events_count": 1,
    "tab_switch_count": 3,
    "focus_blur_count": 4,
    "form_fill_duration_sec": 45.0,
    "idle_time_before_submit_sec": 8.0,
    "error_correction_ratio": 0.02,
    "hover_time_avg_ms": 420.0,
    "double_click_count": 0,
    "drag_drop_events": 0,
    "resize_events_count": 0,
    "zoom_level": 100,
    "webgl_vendor": "Google Inc. (NVIDIA)",
    "canvas_fingerprint": "canvas_hash_demo_01",
    "audio_fingerprint": "audio_hash_demo_01",
    "session_duration_sec": 420.0,
    "pages_visited_count": 6,
    "login_method": "password",
    "failed_login_attempts": 0,
    "time_since_last_login_sec": 3600.0,
    "is_new_device": 0,
    "is_new_browser": 0,
    "device_trust_score": 0.82,
    "transfers_count_last_10min": 0,
    "geo_speed_km_h": 5.0,
    "is_rooted_jailbroken": 0,
    "is_emulator": 0,
    "is_debugger_attached": 0,
    "biometric_entry_used": 0,
    "accuracy_meters": 25.0,
    "latitude": 55.751244,
    "longitude": 37.618423,
    "touch_typing_rhythm_median_ms": 0.0,
    "touch_typing_rhythm_std_dev": 0.0,
    "touch_typing_rhythm_cv": 0.0,
    "tap_velocity_avg": 0.0,
    "tap_pressure_avg": 0.0,
    "touch_jitter_score": 0.0,
    "swipe_angle_deviation": 0.0,
    "app_background_events": 0,
    "screen_orientation_changes": 0,
    "accelerometer_variance_x": 0.0,
    "accelerometer_variance_y": 0.0,
    "gyroscope_variance": 0.0,
    "battery_level": 0.0,
    "storage_free_percent": 0.0,
    "carrier_mcc": 250,
    "carrier_mnc": 99,
    "attestation_status": "not_applicable_web",
    "app_version": "web",
    "device_model": "Desktop",
    "app_install_source": "n_a",
    "integrity_token": "n_a",
    "carrier_name": "n_a",
    "sim_country_code": "RU",
    "sim_carrier_name": "n_a",
    "location_provider": "n_a",
    "battery_charging_state": "unknown",
}

# Web: дневная оплата, длинная сессия, без VPN/Tor — подобрано под низкий p_fraud
# после переобучения web FraudMLP (rules не триггерятся → used_model=true).
_WEB_ML_BENIGN_OPENAPI_EXAMPLE: dict[str, object] = {
    "customer_id": 77001,
    "event_id": 7700100001,
    "session_id": 7700100002,
    "user_agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "browser_fingerprint": "fp_web_benign_stable",
    "browser_name": "Chrome",
    "browser_version": "124.0.0.0",
    "os_type": "Windows",
    "os_version": "10.0",
    "event_dttm": "2025-08-09T14:30:00+03:00",
    "hour_of_day": 16,
    "day_of_week": 3,
    "operaton_amt": 800.0,
    "currency_iso_cd": "RUB",
    "mcc_code": "5411",
    "merchant_name": "Pyaterochka",
    "pos_cd": "ECOM",
    "transaction_type": "payment",
    "connection_type": "wifi",
    "timezone_offset_minutes": 180,
    "ip_address_hash": "sha256_web_benign_demo",
    "is_vpn_detected": 0,
    "is_proxy_detected": 0,
    "is_tor_detected": 0,
    "is_new_device": 0,
    "is_new_browser": 0,
    "session_duration_sec": 860.0,
    "transfers_count_last_10min": 0,
    "geo_speed_km_h": 13.86,
    "network_rtt_avg_ms": 48.25,
    "clipboard_paste_ratio": 0.145,
    "backspace_ratio": 0.349,
    "form_fill_duration_sec": 103.2,
    "is_rooted_jailbroken": 0,
    "is_emulator": 0,
    "is_debugger_attached": 0,
    "developer_tools_enabled": 0,
    "biometric_entry_used": 0,
    "accuracy_meters": 12.0,
    "latitude": 55.751244,
    "longitude": 37.618423,
    "attestation_status": "not_applicable_web",
    "app_version": "web",
    "device_model": "Desktop",
    "app_install_source": "n_a",
    "integrity_token": "n_a",
    "carrier_name": "n_a",
    "sim_country_code": "RU",
    "sim_carrier_name": "n_a",
    "location_provider": "gps",
    "battery_charging_state": "unknown",
    "carrier_mcc": 250,
    "carrier_mnc": 1,
}

# «Нормальное событие» из tests/fixtures/behavior_mobile_safe.json + поля для behavior-rules.
# С поставляемым mobile_best.pt даёт ml:p_fraud≈0, decision safe, used_model=true.
_MOBILE_ML_BENIGN_OPENAPI_EXAMPLE: dict[str, object] = {
    "customer_id": 123123123123129,
    "event_id": 999999999999002,
    "session_id": 125000000000001,
    "device_id": 5827153760409737833,
    "installation_id": 4229187280601133165,
    "app_version": "9.1.0",
    "os_type": "iOS",
    "os_version": "iOS 17",
    "device_model": "iPhone 14",
    "event_dttm": "2025-08-09 14:30:00",
    "operaton_amt": 1500.0,
    "currency_iso_cd": 643,
    "mcc_code": "5411",
    "merchant_name": "Pyaterochka",
    "pos_cd": 0,
    "transaction_type": "payment",
    "attestation_status": "passed",
    "is_rooted_jailbroken": 0,
    "is_emulator": 0,
    "is_debugger_attached": 0,
    "developer_tools_enabled": 0,
    "app_install_source": "official",
    "integrity_token": "pass",
    "connection_type": "wifi",
    "carrier_name": "MTS",
    "carrier_mcc": 250,
    "carrier_mnc": 1,
    "ip_address_hash": "9af34c01ab",
    "is_vpn_detected": 0,
    "is_proxy_detected": 0,
    "network_rtt_avg_ms": 22.0,
    "sim_country_code": "RU",
    "sim_carrier_name": "MTS",
    "latitude": 55.751244,
    "longitude": 37.618423,
    "accuracy_meters": 8.0,
    "location_provider": "gps",
    "timezone_offset_minutes": 180,
    "geo_speed_km_h": 4.0,
    "touch_typing_rhythm_median_ms": 220.0,
    "touch_typing_rhythm_std_dev": 65.0,
    "touch_typing_rhythm_cv": 0.295,
    "tap_velocity_avg": 480.0,
    "tap_pressure_avg": 0.55,
    "touch_jitter_score": 0.62,
    "swipe_angle_deviation": 18.0,
    "clipboard_paste_ratio": 0.04,
    "backspace_ratio": 0.21,
    "form_fill_duration_sec": 78.0,
    "app_background_events": 0,
    "screen_orientation_changes": 1,
    "accelerometer_variance_x": 1.4,
    "accelerometer_variance_y": 1.2,
    "gyroscope_variance": 0.31,
    "biometric_entry_used": 1,
    "battery_level": 68.0,
    "battery_charging_state": "discharging",
    "storage_free_percent": 72.0,
    "event_type_nm": 1,
    "event_desc": 42,
    "channel_indicator_type": 2,
    "channel_indicator_sub_type": 1,
    "accept_language": "ru-RU",
    "browser_language": "ru-RU",
    "operating_system_type": 1,
    "compromised": "0",
    "developer_tools": "0",
    "web_rdp_connection": 0,
    "phone_voip_call_state": 0,
    "session_duration_sec": 120.0,
    "transfers_count_last_10min": 0,
    "is_new_device": 0,
}


_MOBILE_CLEAN_OPENAPI_EXAMPLE: dict[str, object] = {
    "customer_id": 8888,
    "event_id": 2,
    "session_id": 8888000001,
    "operaton_amt": 1500,
    "geo_speed_km_h": 30,
    "hour_of_day": 14,
    "is_vpn_detected": 0,
    "is_proxy_detected": 0,
    "session_duration_sec": 60,
    "os_type": "Android",
    "device_id": "dev_abc",
    "is_new_device": 0,
}

_MOBILE_OBVIOUS_FRAUD_OPENAPI_EXAMPLE: dict[str, object] = {
    "customer_id": 9999,
    "event_id": 1,
    "session_id": 9999000001,
    "operaton_amt": 250000,
    "geo_speed_km_h": 1500,
    "is_vpn_detected": 1,
    "session_duration_sec": 60,
    "os_type": "Android",
}


def _run_pipeline(
    *,
    payload: dict,
    kind: Literal["web", "mobile"],
    settings: Settings,
    loader,
    history,
    event_sink,
) -> ScoreResponse:
    """Общая обвязка: проверка loader, выбор bundle/history, score, event_sink."""
    if loader is None:
        raise HTTPException(status_code=503, detail="ML loader not initialized")

    bundle = loader.load_web() if kind == "web" else loader.load_mobile()
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


@router.post(
    "/behavior/web",
    response_model=ScoreResponse,
    summary="Score web behavioural event",
    description=(
        "Pipeline: rules → fail-fast → PyTorch FraudMLP (web). Тело запроса — "
        "строгая Pydantic-схема `WebBehaviorEvent` с явными типами и полным "
        "перечнем полей web-препроцессора и поведенческих правил. "
        "`extra=forbid`: лишние ключи отклоняются с 422. "
        "503 означает, что ML-loader не поднят (см. lifespan / пути к .pt), "
        "а не ошибку тела запроса."
    ),
)
async def score_behavior_web_endpoint(
    payload: WebBehaviorEvent = Body(
        ...,
        openapi_examples={
            "web_clean": {
                "summary": "Web, чистый кейс (полный контракт task.md + ML/rules)",
                "description": (
                    "Все поля из раздела «веб» task.md, признаки behavior-rules и "
                    "колонки web-препроцессора."
                ),
                "value": _WEB_CLEAN_OPENAPI_EXAMPLE,
            },
            "web_ml_benign": {
                "summary": "Web, низкий p_fraud (ML: не фрод)",
                "description": (
                    "Типичная дневная оплата из браузера после длинной сессии; правила "
                    "не срабатывают, ответ идёт от web FraudMLP."
                ),
                "value": _WEB_ML_BENIGN_OPENAPI_EXAMPLE,
            },
        },
    ),
    settings: Settings = Depends(get_settings),
    loader=Depends(get_loader),
    history_web=Depends(get_history_web),
    event_sink=Depends(get_event_sink),
) -> ScoreResponse:
    return _run_pipeline(
        payload=payload.model_dump(),
        kind="web",
        settings=settings,
        loader=loader,
        history=history_web,
        event_sink=event_sink,
    )


@router.post(
    "/behavior/mobile",
    response_model=ScoreResponse,
    summary="Score mobile behavioural event",
    description=(
        "Pipeline: rules → fail-fast → PyTorch FraudMLP (mobile). Тело запроса — "
        "строгая Pydantic-схема `MobileBehaviorEvent` с явными типами и полным "
        "перечнем полей mobile-препроцессора и поведенческих правил. "
        "`extra=forbid`: лишние ключи отклоняются с 422."
    ),
)
async def score_behavior_mobile_endpoint(
    payload: MobileBehaviorEvent = Body(
        ...,
        openapi_examples={
            "mobile_clean": {
                "summary": "Mobile, чистый кейс (доходит до ML)",
                "value": _MOBILE_CLEAN_OPENAPI_EXAMPLE,
            },
            "mobile_obvious_fraud": {
                "summary": "Mobile, fail-fast по правилам (VPN+гео-телепорт+сумма)",
                "value": _MOBILE_OBVIOUS_FRAUD_OPENAPI_EXAMPLE,
            },
            "mobile_ml_benign": {
                "summary": "Mobile, нейросеть: не фрод (низкий скор)",
                "description": (
                    "Кейс «нормальное событие» из tests/fixtures/behavior_mobile_safe.json "
                    "с полями для behavior-rules. С поставляемым mobile_best.pt обычно "
                    "used_model=true и decision safe (низкая p_fraud)."
                ),
                "value": _MOBILE_ML_BENIGN_OPENAPI_EXAMPLE,
            },
        },
    ),
    settings: Settings = Depends(get_settings),
    loader=Depends(get_loader),
    history_mobile=Depends(get_history_mobile),
    event_sink=Depends(get_event_sink),
) -> ScoreResponse:
    return _run_pipeline(
        payload=payload.model_dump(),
        kind="mobile",
        settings=settings,
        loader=loader,
        history=history_mobile,
        event_sink=event_sink,
    )
