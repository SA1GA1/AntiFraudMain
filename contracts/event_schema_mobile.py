"""Pandera schema for mobile behavioural events.

Mirror of AntiFraudMLMobile/trainer/preprocess.py NUMERIC_COLS + CATEGORICAL_COLS
+ identity fields. See contracts/event_schema_web.py for the design rationale
(best-effort, todo.md #6).
"""

from __future__ import annotations

import pandera.pandas as pa
from pandera.pandas import Check, Column, DataFrameSchema

_IDENTITY: list[str] = ["customer_id", "event_id", "event_dttm"]

_NUMERIC: list[str] = [
    "operaton_amt",
    "is_rooted_jailbroken",
    "is_emulator",
    "is_debugger_attached",
    "developer_tools_enabled",
    "is_vpn_detected",
    "is_proxy_detected",
    "biometric_entry_used",
    "network_rtt_avg_ms",
    "accuracy_meters",
    "geo_speed_km_h",
    "timezone_offset_minutes",
    "latitude",
    "longitude",
    "touch_typing_rhythm_median_ms",
    "touch_typing_rhythm_std_dev",
    "touch_typing_rhythm_cv",
    "tap_velocity_avg",
    "tap_pressure_avg",
    "touch_jitter_score",
    "swipe_angle_deviation",
    "clipboard_paste_ratio",
    "backspace_ratio",
    "form_fill_duration_sec",
    "app_background_events",
    "screen_orientation_changes",
    "accelerometer_variance_x",
    "accelerometer_variance_y",
    "gyroscope_variance",
    "battery_level",
    "storage_free_percent",
    "carrier_mcc",
    "carrier_mnc",
    "compromised",
    "web_rdp_connection",
    "developer_tools",
    "phone_voip_call_state",
]

_CATEGORICAL: list[str] = [
    "event_type_nm", "event_desc",
    "channel_indicator_type", "channel_indicator_sub_type",
    "currency_iso_cd", "operating_system_type",
    "mcc_code", "pos_cd",
    "accept_language", "browser_language",
    "attestation_status", "transaction_type",
    "app_version", "os_type", "os_version", "device_model",
    "merchant_name", "app_install_source", "integrity_token",
    "connection_type", "carrier_name", "sim_country_code",
    "sim_carrier_name", "location_provider", "battery_charging_state",
    "hour_of_day", "day_of_week",
]

EVENT_FIELDS_MOBILE: list[str] = _IDENTITY + _NUMERIC + _CATEGORICAL


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


EVENT_SCHEMA_MOBILE: DataFrameSchema = _build_schema()
