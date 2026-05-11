"""Preprocessor: словари + z-score, без sklearn-зависимостей. Picklable."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

import numpy as np
import pandas as pd

from .aggregate import FEATURE_COLUMNS as AGG_FEATURE_COLUMNS

# ---------------------------------------------------------------------------
# Схема: после task.md-перехода numeric и categorical обновлены.
# ---------------------------------------------------------------------------

NUMERIC_COLS: List[str] = [
    # Source numerics
    "operaton_amt",                  # log1p-transformed
    # Task.md флаги (0/1) и числовые
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
    # Source существующие риск-флаги (как доп. сигналы):
    "compromised",
    "web_rdp_connection",
    "developer_tools",
    "phone_voip_call_state",
]

CATEGORICAL_COLS: List[str] = [
    # Source категориальные
    "event_type_nm", "event_desc",
    "channel_indicator_type", "channel_indicator_sub_type",
    "currency_iso_cd", "operating_system_type",
    "mcc_code", "pos_cd",
    "accept_language", "browser_language",
    # Task.md категориальные
    "attestation_status", "transaction_type",
    "app_version", "os_type", "os_version", "device_model",
    "merchant_name", "app_install_source", "integrity_token",
    "connection_type", "carrier_name", "sim_country_code",
    "sim_carrier_name", "location_provider", "battery_charging_state",
    # Производные временные
    "hour_of_day", "day_of_week",
]

MAX_VOCAB: int = 1024
_UNK_TOKEN: str = "__UNK__"
_NAN_TOKEN: str = "__NAN__"


def _to_numeric_binary(series: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(series):
        return series.fillna(0).astype(np.float32).clip(0.0, 1.0)
    s = series.fillna("0").astype(str).str.strip().str.lower()
    return s.isin({"1", "true", "yes", "t", "y"}).astype(np.float32)


def _temporal_categoricals(dttm: pd.Series) -> pd.DataFrame:
    dt = pd.to_datetime(dttm, errors="coerce", utc=False)
    hour = dt.dt.hour.fillna(12).astype(np.int16).astype(str)
    dow = dt.dt.dayofweek.fillna(0).astype(np.int16).astype(str)
    return pd.DataFrame({"hour_of_day": hour, "day_of_week": dow})


def _prepare_event_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    # log1p amount
    out["operaton_amt"] = np.log1p(pd.to_numeric(out["operaton_amt"], errors="coerce").fillna(0).clip(lower=0))
    # Бинарные source флаги → 0/1 float
    for c in ("compromised", "web_rdp_connection", "developer_tools",
              "phone_voip_call_state"):
        out[c] = _to_numeric_binary(out[c]) if c in out.columns else np.float32(0.0)
    # Task.md is_* флаги — приходят уже int, на всякий случай нормализуем
    for c in ("is_rooted_jailbroken", "is_emulator", "is_debugger_attached",
              "developer_tools_enabled", "is_vpn_detected", "is_proxy_detected",
              "biometric_entry_used"):
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0).astype(np.float32).clip(0, 1)
        else:
            out[c] = np.float32(0.0)
    # Числовые task.md и source
    numeric_to_float = [
        "network_rtt_avg_ms", "accuracy_meters", "geo_speed_km_h",
        "timezone_offset_minutes", "latitude", "longitude",
        "touch_typing_rhythm_median_ms", "touch_typing_rhythm_std_dev",
        "touch_typing_rhythm_cv", "tap_velocity_avg", "tap_pressure_avg",
        "touch_jitter_score", "swipe_angle_deviation", "clipboard_paste_ratio",
        "backspace_ratio", "form_fill_duration_sec", "app_background_events",
        "screen_orientation_changes", "accelerometer_variance_x",
        "accelerometer_variance_y", "gyroscope_variance", "battery_level",
        "storage_free_percent", "carrier_mcc", "carrier_mnc",
    ]
    for c in numeric_to_float:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce").astype(np.float32)
        else:
            out[c] = np.float32(0.0)
    # Временные категориальные
    if "event_dttm" in out.columns:
        out = pd.concat([out, _temporal_categoricals(out["event_dttm"])], axis=1)
    else:
        out["hour_of_day"] = "12"
        out["day_of_week"] = "0"
    # Все категориальные приводим к строкам
    for c in CATEGORICAL_COLS:
        if c in out.columns:
            out[c] = out[c].astype("string").fillna(_NAN_TOKEN)
        else:
            out[c] = _NAN_TOKEN
    return out


@dataclass
class Preprocessor:
    num_mean: Dict[str, float] = field(default_factory=dict)
    num_std: Dict[str, float] = field(default_factory=dict)
    vocab: Dict[str, Dict[str, int]] = field(default_factory=dict)
    agg_mean: Dict[str, float] = field(default_factory=dict)
    agg_std: Dict[str, float] = field(default_factory=dict)
    n_numeric: int = 0
    n_categorical: int = 0
    n_aggregate: int = 0
    cat_vocab_sizes: List[int] = field(default_factory=list)

    def fit(self, events_df: pd.DataFrame, agg_df: pd.DataFrame | None = None) -> "Preprocessor":
        ev = _prepare_event_columns(events_df)

        for col in NUMERIC_COLS:
            v = pd.to_numeric(ev[col], errors="coerce")
            self.num_mean[col] = float(v.mean())
            std = float(v.std(ddof=0))
            self.num_std[col] = std if std > 1e-6 else 1.0

        for col in CATEGORICAL_COLS:
            counts = ev[col].astype(str).value_counts()
            top = counts.iloc[: MAX_VOCAB - 1].index.tolist()
            self.vocab[col] = {_UNK_TOKEN: 0, **{v: i + 1 for i, v in enumerate(top)}}

        if agg_df is not None:
            for col in AGG_FEATURE_COLUMNS:
                v = pd.to_numeric(agg_df[col], errors="coerce")
                self.agg_mean[col] = float(v.mean())
                std = float(v.std(ddof=0))
                self.agg_std[col] = std if std > 1e-6 else 1.0

        self.n_numeric = len(NUMERIC_COLS)
        self.n_categorical = len(CATEGORICAL_COLS)
        self.n_aggregate = len(AGG_FEATURE_COLUMNS)
        self.cat_vocab_sizes = [len(self.vocab[c]) for c in CATEGORICAL_COLS]
        return self

    def transform_events(self, events_df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        ev = _prepare_event_columns(events_df)
        n = len(ev)

        num = np.empty((n, len(NUMERIC_COLS)), dtype=np.float32)
        for i, col in enumerate(NUMERIC_COLS):
            v = pd.to_numeric(ev[col], errors="coerce").astype(np.float64).to_numpy()
            v = (v - self.num_mean[col]) / self.num_std[col]
            v = np.nan_to_num(v, nan=0.0, posinf=0.0, neginf=0.0)
            num[:, i] = v.astype(np.float32)

        cat = np.empty((n, len(CATEGORICAL_COLS)), dtype=np.int64)
        for i, col in enumerate(CATEGORICAL_COLS):
            mapping = self.vocab[col]
            vals = ev[col].astype(str).to_numpy()
            cat[:, i] = np.array([mapping.get(v, 0) for v in vals], dtype=np.int64)
        return num, cat

    def transform_aggregates(self, customer_ids: np.ndarray, agg_df: pd.DataFrame | None) -> tuple[np.ndarray, np.ndarray]:
        n = len(customer_ids)
        agg_arr = np.zeros((n, len(AGG_FEATURE_COLUMNS)), dtype=np.float32)
        has_hist = np.zeros((n, 1), dtype=np.float32)
        if agg_df is None or not self.agg_mean:
            return agg_arr, has_hist
        agg_indexed = agg_df.set_index("customer_id")
        joined = agg_indexed.reindex(customer_ids)
        mask_present = joined[AGG_FEATURE_COLUMNS[0]].notna().to_numpy()
        has_hist[:, 0] = mask_present.astype(np.float32)
        for j, col in enumerate(AGG_FEATURE_COLUMNS):
            v = pd.to_numeric(joined[col], errors="coerce").astype(np.float64).to_numpy()
            v = (v - self.agg_mean[col]) / self.agg_std[col]
            v = np.nan_to_num(v, nan=0.0, posinf=0.0, neginf=0.0)
            agg_arr[:, j] = v.astype(np.float32)
        agg_arr[~mask_present] = 0.0
        return agg_arr, has_hist
