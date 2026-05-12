"""Pydantic-схемы поведенческих событий: строгие, без extra-полей.

`MobileBehaviorEvent` и `WebBehaviorEvent` явно перечисляют все поля, которые
понимают behavior-rules и соответствующий FraudMLP-препроцессор
(`app.ml._pkg_mobile.preprocess` / `app.ml._pkg_web.preprocess`), плюс поля
из task.md и Swagger-примеров. Лишние ключи отклоняются (`extra="forbid"`).
Дискриминатор web/mobile теперь определяется выбранным эндпоинтом
(`/score/behavior/web` vs `/score/behavior/mobile`), эвристика по полям
больше не нужна.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

# Identity-поля могут приходить и числом, и строкой (в фикстурах встречаются
# 19-значные device_id как int, и тестовые "dev_abc" как str).
IdField = int | str


class _StrictModel(BaseModel):
    """Базовый класс: запрещаем неизвестные ключи, валидируем при присваивании."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


# ---------------------------------------------------------------------------
# Mobile
# ---------------------------------------------------------------------------


class MobileBehaviorEvent(_StrictModel):
    """Полный контракт мобильного поведенческого события."""

    # ── Identity ───────────────────────────────────────────────────────────
    customer_id: IdField = Field(..., description="ID клиента (int или str)")
    event_id: IdField = Field(..., description="ID события (int или str)")
    session_id: Optional[IdField] = None
    device_id: Optional[IdField] = None
    installation_id: Optional[IdField] = None
    event_dttm: Optional[str] = Field(
        default=None, description="ISO-8601 или 'YYYY-MM-DD HH:MM:SS'"
    )

    # ── Источник: source-категориальные ────────────────────────────────────
    event_type_nm: Optional[int | str] = None
    event_desc: Optional[int | str] = None
    channel_indicator_type: Optional[int | str] = None
    channel_indicator_sub_type: Optional[int | str] = None
    currency_iso_cd: Optional[int | str] = None
    operating_system_type: Optional[int | str] = None
    mcc_code: Optional[int | str] = None
    pos_cd: Optional[int | str] = None
    accept_language: Optional[str] = None
    browser_language: Optional[str] = None

    # ── task.md категориальные ─────────────────────────────────────────────
    attestation_status: Optional[str] = None
    transaction_type: Optional[str] = None
    app_version: Optional[str] = None
    os_type: str = "Android"
    os_version: Optional[str] = None
    device_model: Optional[str] = None
    merchant_name: Optional[str] = None
    app_install_source: Optional[str] = None
    integrity_token: Optional[str] = None
    connection_type: Optional[str] = None
    carrier_name: Optional[str] = None
    sim_country_code: Optional[str] = None
    sim_carrier_name: Optional[str] = None
    location_provider: Optional[str] = None
    battery_charging_state: Optional[str] = None

    # ── Производные временные ──────────────────────────────────────────────
    hour_of_day: Optional[int] = Field(default=None, ge=0, le=23)
    day_of_week: Optional[int] = Field(default=None, ge=0, le=6)

    # ── Финансы ────────────────────────────────────────────────────────────
    operaton_amt: float = Field(default=0.0, ge=0.0, description="Сумма операции")

    # ── Безопасность / атестация (бинарные 0/1) ────────────────────────────
    is_rooted_jailbroken: int = Field(default=0, ge=0, le=1)
    is_emulator: int = Field(default=0, ge=0, le=1)
    is_debugger_attached: int = Field(default=0, ge=0, le=1)
    developer_tools_enabled: int = Field(default=0, ge=0, le=1)
    is_vpn_detected: int = Field(default=0, ge=0, le=1)
    is_proxy_detected: int = Field(default=0, ge=0, le=1)
    is_tor_detected: int = Field(default=0, ge=0, le=1)
    biometric_entry_used: int = Field(default=0, ge=0, le=1)
    is_new_device: int = Field(default=0, ge=0, le=1)

    # ── Сеть / гео ─────────────────────────────────────────────────────────
    ip_address_hash: Optional[str] = None
    network_rtt_avg_ms: float = Field(default=0.0, ge=0.0)
    accuracy_meters: float = Field(default=0.0, ge=0.0)
    geo_speed_km_h: float = Field(default=0.0, ge=0.0)
    timezone_offset_minutes: int = Field(default=0)
    latitude: Optional[float] = Field(default=None, ge=-90.0, le=90.0)
    longitude: Optional[float] = Field(default=None, ge=-180.0, le=180.0)

    # ── Биометрия касаний ──────────────────────────────────────────────────
    touch_typing_rhythm_median_ms: float = Field(default=0.0, ge=0.0)
    touch_typing_rhythm_std_dev: float = Field(default=0.0, ge=0.0)
    touch_typing_rhythm_cv: float = Field(default=0.0, ge=0.0)
    tap_velocity_avg: float = Field(default=0.0, ge=0.0)
    tap_pressure_avg: float = Field(default=0.0, ge=0.0)
    touch_jitter_score: float = Field(default=0.0, ge=0.0)
    swipe_angle_deviation: float = Field(default=0.0, ge=0.0)

    # ── Поведение в форме / устройство ─────────────────────────────────────
    clipboard_paste_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    backspace_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    form_fill_duration_sec: float = Field(default=0.0, ge=0.0)
    app_background_events: int = Field(default=0, ge=0)
    screen_orientation_changes: int = Field(default=0, ge=0)
    accelerometer_variance_x: float = Field(default=0.0, ge=0.0)
    accelerometer_variance_y: float = Field(default=0.0, ge=0.0)
    gyroscope_variance: float = Field(default=0.0, ge=0.0)
    battery_level: float = Field(default=0.0, ge=0.0, le=100.0)
    storage_free_percent: float = Field(default=0.0, ge=0.0, le=100.0)

    # ── Carrier (MCC/MNC) ──────────────────────────────────────────────────
    carrier_mcc: Optional[int] = Field(default=None, ge=0)
    carrier_mnc: Optional[int] = Field(default=None, ge=0)

    # ── Source бинарные флаги (могут приходить строкой "0"/"1") ────────────
    compromised: int | str = Field(default=0)
    web_rdp_connection: int = Field(default=0, ge=0, le=1)
    developer_tools: int | str = Field(default=0)
    phone_voip_call_state: int = Field(default=0, ge=0, le=1)

    # ── Сессия (используется правилами) ────────────────────────────────────
    session_duration_sec: float = Field(default=0.0, ge=0.0)
    transfers_count_last_10min: int = Field(default=0, ge=0)


# ---------------------------------------------------------------------------
# Web
# ---------------------------------------------------------------------------


class WebBehaviorEvent(_StrictModel):
    """Полный контракт веб-поведенческого события."""

    # ── Identity ───────────────────────────────────────────────────────────
    customer_id: IdField = Field(..., description="ID клиента (int или str)")
    event_id: IdField = Field(..., description="ID события (int или str)")
    session_id: Optional[IdField] = None
    device_id: Optional[IdField] = None
    event_dttm: Optional[str] = None

    # ── Браузер / ОС ───────────────────────────────────────────────────────
    browser_fingerprint: Optional[str] = None
    user_agent: Optional[str] = None
    browser_name: Optional[str] = None
    browser_version: Optional[str] = None
    os_type: Optional[str] = None
    os_version: Optional[str] = None
    device_model: Optional[str] = None
    app_version: Optional[str] = None

    # ── Финансы / транзакция ───────────────────────────────────────────────
    operaton_amt: float = Field(default=0.0, ge=0.0)
    currency_iso_cd: Optional[int | str] = None
    mcc_code: Optional[int | str] = None
    merchant_name: Optional[str] = None
    pos_cd: Optional[int | str] = None
    transaction_type: Optional[str] = None

    # ── Производные временные ──────────────────────────────────────────────
    hour_of_day: Optional[int] = Field(default=None, ge=0, le=23)
    day_of_week: Optional[int] = Field(default=None, ge=0, le=6)

    # ── DevTools / окружение ───────────────────────────────────────────────
    is_developer_tools: int = Field(default=0, ge=0, le=1)
    developer_tools_enabled: int = Field(default=0, ge=0, le=1)
    is_headless_browser: int = Field(default=0, ge=0, le=1)
    is_incognito: int = Field(default=0, ge=0, le=1)
    screen_resolution: Optional[str] = None
    screen_color_depth: Optional[int] = Field(default=None, ge=0)
    timezone_offset: Optional[int] = None
    timezone_offset_minutes: Optional[int] = None
    system_language: Optional[str] = None
    browser_language: Optional[str] = None
    accept_language: Optional[str] = None
    installed_fonts_count: Optional[int] = Field(default=None, ge=0)

    # ── Сеть ───────────────────────────────────────────────────────────────
    ip_address_hash: Optional[str] = None
    is_vpn_detected: int = Field(default=0, ge=0, le=1)
    is_proxy_detected: int = Field(default=0, ge=0, le=1)
    is_tor_detected: int = Field(default=0, ge=0, le=1)
    connection_type: Optional[str] = None
    network_rtt_avg_ms: Optional[float] = Field(default=None, ge=0.0)
    asn: Optional[int] = Field(default=None, ge=0)
    isp_name: Optional[str] = None

    # ── Мышь / клавиатура / форма ──────────────────────────────────────────
    mouse_velocity_avg: Optional[float] = Field(default=None, ge=0.0)
    mouse_acceleration_avg: Optional[float] = None
    mouse_jitter_score: Optional[float] = None
    mouse_linearity_score: Optional[float] = None
    click_duration_avg_ms: Optional[float] = Field(default=None, ge=0.0)
    right_click_count: Optional[int] = Field(default=None, ge=0)
    scroll_velocity_avg: Optional[float] = None
    keyboard_typing_speed_median_ms: Optional[float] = Field(default=None, ge=0.0)
    keyboard_typing_speed_std_dev: Optional[float] = Field(default=None, ge=0.0)
    keyboard_typing_rhythm_cv: Optional[float] = None
    backspace_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    clipboard_paste_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    copy_events_count: Optional[int] = Field(default=None, ge=0)
    paste_events_count: Optional[int] = Field(default=None, ge=0)
    tab_switch_count: Optional[int] = Field(default=None, ge=0)
    focus_blur_count: Optional[int] = Field(default=None, ge=0)
    form_fill_duration_sec: float = Field(default=0.0, ge=0.0)
    idle_time_before_submit_sec: Optional[float] = Field(default=None, ge=0.0)
    error_correction_ratio: Optional[float] = Field(default=None, ge=0.0)
    hover_time_avg_ms: Optional[float] = Field(default=None, ge=0.0)
    double_click_count: Optional[int] = Field(default=None, ge=0)
    drag_drop_events: Optional[int] = Field(default=None, ge=0)
    resize_events_count: Optional[int] = Field(default=None, ge=0)
    zoom_level: Optional[int] = Field(default=None, ge=0)

    # ── Фингерпринты ───────────────────────────────────────────────────────
    webgl_vendor: Optional[str] = None
    canvas_fingerprint: Optional[str] = None
    audio_fingerprint: Optional[str] = None

    # ── Сессия / поведение клиента ─────────────────────────────────────────
    session_duration_sec: float = Field(default=0.0, ge=0.0)
    pages_visited_count: Optional[int] = Field(default=None, ge=0)
    login_method: Optional[str] = None
    failed_login_attempts: Optional[int] = Field(default=None, ge=0)
    time_since_last_login_sec: Optional[float] = Field(default=None, ge=0.0)
    is_new_device: int = Field(default=0, ge=0, le=1)
    is_new_browser: int = Field(default=0, ge=0, le=1)
    device_trust_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)

    # ── Гео ────────────────────────────────────────────────────────────────
    geo_speed_km_h: float = Field(default=0.0, ge=0.0)
    latitude: Optional[float] = Field(default=None, ge=-90.0, le=90.0)
    longitude: Optional[float] = Field(default=None, ge=-180.0, le=180.0)
    accuracy_meters: Optional[float] = Field(default=None, ge=0.0)
    location_provider: Optional[str] = None

    # ── Mobile-совместимые поля (web FraudMLP подаёт нули, но контракт принимает) ─
    is_rooted_jailbroken: int = Field(default=0, ge=0, le=1)
    is_emulator: int = Field(default=0, ge=0, le=1)
    is_debugger_attached: int = Field(default=0, ge=0, le=1)
    biometric_entry_used: int = Field(default=0, ge=0, le=1)
    biometric_login: Optional[int] = Field(default=None, ge=0, le=1)
    attestation_status: Optional[str] = None
    app_install_source: Optional[str] = None
    integrity_token: Optional[str] = None
    carrier_name: Optional[str] = None
    carrier_mcc: Optional[int] = Field(default=None, ge=0)
    carrier_mnc: Optional[int] = Field(default=None, ge=0)
    sim_country_code: Optional[str] = None
    sim_carrier_name: Optional[str] = None
    battery_charging_state: Optional[str] = None
    touch_typing_rhythm_median_ms: float = Field(default=0.0, ge=0.0)
    touch_typing_rhythm_std_dev: float = Field(default=0.0, ge=0.0)
    touch_typing_rhythm_cv: float = Field(default=0.0, ge=0.0)
    tap_velocity_avg: float = Field(default=0.0, ge=0.0)
    tap_pressure_avg: float = Field(default=0.0, ge=0.0)
    touch_jitter_score: float = Field(default=0.0, ge=0.0)
    swipe_angle_deviation: float = Field(default=0.0, ge=0.0)
    app_background_events: int = Field(default=0, ge=0)
    screen_orientation_changes: int = Field(default=0, ge=0)
    accelerometer_variance_x: float = Field(default=0.0, ge=0.0)
    accelerometer_variance_y: float = Field(default=0.0, ge=0.0)
    gyroscope_variance: float = Field(default=0.0, ge=0.0)
    battery_level: float = Field(default=0.0, ge=0.0, le=100.0)
    storage_free_percent: float = Field(default=0.0, ge=0.0, le=100.0)

    # ── Сессия behaviour rules ─────────────────────────────────────────────
    transfers_count_last_10min: int = Field(default=0, ge=0)
