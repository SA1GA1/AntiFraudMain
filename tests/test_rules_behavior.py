from __future__ import annotations

import pytest

from app.pipelines.behavior.rules import (
    BehaviorContext,
    apply_rules,
    rule_amount_outlier,
    rule_geo_teleport,
    rule_micro_session,
    rule_new_device,
    rule_night_anomaly,
    rule_transfer_spike,
    rule_vpn_proxy,
)


@pytest.fixture
def cold_context() -> BehaviorContext:
    return BehaviorContext(amt_median=None, known_devices=set(), known_night_hour=False)


@pytest.fixture
def warm_context() -> BehaviorContext:
    return BehaviorContext(
        amt_median=2_000.0,
        known_devices={"dev_known"},
        known_night_hour=False,
    )


# --- 1. amount outlier ---

def test_amount_outlier_triggers_for_huge_amount_in_cold_start(cold_context):
    event = {"operaton_amt": 250_000}
    r = rule_amount_outlier(event, cold_context)
    assert r.triggered
    assert r.weight == 2.0


def test_amount_outlier_does_not_trigger_for_small_amount_in_cold_start(cold_context):
    event = {"operaton_amt": 1_500}
    r = rule_amount_outlier(event, cold_context)
    assert not r.triggered


def test_amount_outlier_triggers_when_5x_median(warm_context):
    event = {"operaton_amt": 12_000}
    r = rule_amount_outlier(event, warm_context)
    assert r.triggered


def test_amount_outlier_does_not_trigger_within_normal_range(warm_context):
    event = {"operaton_amt": 3_000}
    r = rule_amount_outlier(event, warm_context)
    assert not r.triggered


# --- 2. geo teleport ---

def test_geo_teleport_triggers_for_high_speed():
    event = {"geo_speed_km_h": 1200}
    r = rule_geo_teleport(event, BehaviorContext())
    assert r.triggered
    assert r.weight == 2.5


def test_geo_teleport_does_not_trigger_for_normal_speed():
    event = {"geo_speed_km_h": 50}
    r = rule_geo_teleport(event, BehaviorContext())
    assert not r.triggered


def test_geo_teleport_handles_missing_field():
    r = rule_geo_teleport({}, BehaviorContext())
    assert not r.triggered


# --- 3. night anomaly ---

def test_night_anomaly_triggers_at_3am_for_unusual_user(cold_context):
    event = {"hour_of_day": 3}
    r = rule_night_anomaly(event, cold_context)
    assert r.triggered


def test_night_anomaly_does_not_trigger_when_user_known_for_night_ops():
    ctx = BehaviorContext(known_night_hour=True)
    event = {"hour_of_day": 3}
    r = rule_night_anomaly(event, ctx)
    assert not r.triggered


def test_night_anomaly_does_not_trigger_during_day(cold_context):
    event = {"hour_of_day": 14}
    r = rule_night_anomaly(event, cold_context)
    assert not r.triggered


# --- 4. new device ---

def test_new_device_triggers_when_flag_set():
    event = {"is_new_device": 1}
    r = rule_new_device(event, BehaviorContext())
    assert r.triggered


def test_new_device_triggers_when_device_id_unknown():
    event = {"device_id": "dev_xxx"}
    ctx = BehaviorContext(known_devices={"dev_a", "dev_b"})
    r = rule_new_device(event, ctx)
    assert r.triggered


def test_new_device_does_not_trigger_for_known_device():
    event = {"device_id": "dev_a"}
    ctx = BehaviorContext(known_devices={"dev_a", "dev_b"})
    r = rule_new_device(event, ctx)
    assert not r.triggered


# --- 5. vpn / proxy / tor ---

@pytest.mark.parametrize("flag_field", ["is_vpn_detected", "is_proxy_detected", "is_tor_detected"])
def test_vpn_proxy_triggers_for_any_flag(flag_field):
    event = {flag_field: 1}
    r = rule_vpn_proxy(event, BehaviorContext())
    assert r.triggered


def test_vpn_proxy_does_not_trigger_when_all_clear():
    event = {"is_vpn_detected": 0, "is_proxy_detected": 0}
    r = rule_vpn_proxy(event, BehaviorContext())
    assert not r.triggered


# --- 6. transfer spike ---

def test_transfer_spike_triggers_above_threshold():
    event = {"transfers_count_last_10min": 6}
    r = rule_transfer_spike(event, BehaviorContext())
    assert r.triggered


def test_transfer_spike_does_not_trigger_for_normal_rate():
    event = {"transfers_count_last_10min": 1}
    r = rule_transfer_spike(event, BehaviorContext())
    assert not r.triggered


# --- 7. micro session ---

def test_micro_session_triggers_for_under_3_seconds():
    event = {"session_duration_sec": 2}
    r = rule_micro_session(event, BehaviorContext())
    assert r.triggered


def test_micro_session_does_not_trigger_for_normal_session():
    event = {"session_duration_sec": 60}
    r = rule_micro_session(event, BehaviorContext())
    assert not r.triggered


# --- aggregator ---

def test_apply_rules_sums_weights_of_triggered():
    event = {
        "operaton_amt": 200_000,         # cold-start outlier (+2.0)
        "geo_speed_km_h": 1500,          # teleport (+2.5)
        "is_vpn_detected": 1,            # vpn (+1.5)
        "session_duration_sec": 30,
    }
    result = apply_rules(event, BehaviorContext())
    triggered_names = {r.name for r in result.triggered}
    assert triggered_names == {"amount_outlier", "geo_teleport", "vpn_proxy"}
    assert result.total_weight == pytest.approx(2.0 + 2.5 + 1.5)


def test_apply_rules_with_clean_event_returns_zero():
    event = {
        "operaton_amt": 1_000,
        "geo_speed_km_h": 30,
        "hour_of_day": 14,
        "is_vpn_detected": 0,
        "is_proxy_detected": 0,
        "session_duration_sec": 60,
        "transfers_count_last_10min": 1,
    }
    result = apply_rules(event, BehaviorContext(amt_median=2_000.0, known_devices=set()))
    assert result.total_weight == 0.0
    assert result.triggered == []
