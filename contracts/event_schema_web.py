"""Pandera schema for web behavioural events.

Field list mirrors AntiFraudMLWeb/trainer/preprocess.py NUMERIC_COLS +
CATEGORICAL_COLS, plus identity fields (customer_id, event_id, event_dttm).

best-effort path (todo.md #6): all columns are optional + nullable, strict=False
so unknown columns pass through. Validation never fails on a real payload;
it's used for coverage measurement and as a single source of truth for the
field set.
"""

from __future__ import annotations

import pandera.pandas as pa
from pandera.pandas import Check, Column, DataFrameSchema

_IDENTITY: list[str] = ["customer_id", "event_id", "event_dttm"]

_NUMERIC: list[str] = [
    "operaton_amt",
    "is_developer_tools", "is_headless_browser", "is_incognito",
    "is_vpn_detected", "is_proxy_detected", "is_tor_detected",
    "is_new_device", "is_new_browser", "biometric_login",
    "network_rtt_avg_ms", "screen_color_depth", "installed_fonts_count",
    "timezone_offset",
    "mouse_velocity_avg", "mouse_acceleration_avg",
    "mouse_jitter_score", "mouse_linearity_score",
    "click_duration_avg_ms", "right_click_count", "scroll_velocity_avg",
    "keyboard_typing_speed_median_ms", "keyboard_typing_speed_std_dev",
    "keyboard_typing_rhythm_cv",
    "backspace_ratio", "clipboard_paste_ratio",
    "copy_events_count", "paste_events_count",
    "tab_switch_count", "focus_blur_count",
    "form_fill_duration_sec", "idle_time_before_submit_sec",
    "error_correction_ratio", "hover_time_avg_ms",
    "double_click_count", "drag_drop_events",
    "resize_events_count", "zoom_level",
    "session_duration_sec", "pages_visited_count",
    "failed_login_attempts", "time_since_last_login_sec",
    "device_trust_score",
    "asn",
]

_CATEGORICAL: list[str] = [
    "currency_iso_cd", "mcc_code", "pos_cd",
    "browser_name", "browser_version", "os_type", "os_version",
    "screen_resolution", "system_language",
    "browser_language", "accept_language",
    "merchant_name", "transaction_type",
    "connection_type", "isp_name",
    "webgl_vendor",
    "login_method",
    "hour_of_day", "day_of_week",
]

EVENT_FIELDS_WEB: list[str] = _IDENTITY + _NUMERIC + _CATEGORICAL


def _build_schema() -> DataFrameSchema:
    cols: dict[str, Column] = {
        "customer_id": Column(object, nullable=False, required=True, coerce=True),
        "event_id": Column(object, nullable=False, required=True, coerce=True),
        "event_dttm": Column(str, nullable=True, required=False, coerce=True),
        "operaton_amt": Column(float, Check.ge(0), nullable=True, required=False, coerce=True),
    }
    for col in _NUMERIC:
        if col == "operaton_amt":
            continue
        cols[col] = Column(float, nullable=True, required=False, coerce=True)
    for col in _CATEGORICAL:
        cols[col] = Column(str, nullable=True, required=False, coerce=True)
    return DataFrameSchema(cols, strict=False, coerce=True)


EVENT_SCHEMA_WEB: DataFrameSchema = _build_schema()
