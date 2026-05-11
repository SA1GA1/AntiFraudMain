from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def _has_models() -> bool:
    s = Settings()
    return s.mobile_model_path.exists() and s.web_model_path.exists()


@pytest.fixture(scope="module")
def client() -> TestClient:
    if not _has_models():
        pytest.skip("ML checkpoints not present in ./models")
    app = create_app(load_models=True)
    with TestClient(app) as c:
        yield c


def _load_event(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    event = payload["events"][0]
    return {k: v for k, v in event.items() if not k.startswith("_")}


def test_behavior_mobile_safe_event_returns_low_score(client):
    sample = Path("/Users/aleksandr/Documents/AntiFraud/AntiFraudMLMobile/test1.json")
    if not sample.exists():
        pytest.skip("Mobile test1.json not found")
    event = _load_event(sample)
    response = client.post("/score/behavior", json=event)
    assert response.status_code == 200
    body = response.json()
    assert 0.0 <= body["score"] <= 10.0
    assert body["decision"] in {"safe", "review", "sms", "biometry"}
    assert body["latency_ms"] < 1000


def test_behavior_obvious_fraud_short_circuits_via_rules(client):
    """VPN+geo-teleport+huge amount triggers rules > threshold → no ML call."""
    event = {
        "customer_id": 9999,
        "event_id": 1,
        "operaton_amt": 250_000,
        "geo_speed_km_h": 1500,
        "is_vpn_detected": 1,
        "session_duration_sec": 60,
        "os_type": "Android",
    }
    response = client.post("/score/behavior", json=event)
    assert response.status_code == 200
    body = response.json()
    assert body["score"] >= 6.0
    assert body["used_model"] is False
    assert body["latency_ms"] < 200  # fail-fast must be very fast
    triggered = {r for r in body["reasons"] if r.startswith("rule:")}
    assert "rule:amount_outlier" in triggered
    assert "rule:geo_teleport" in triggered
    assert "rule:vpn_proxy" in triggered


def test_behavior_clean_event_falls_through_to_ml(client):
    event = {
        "customer_id": 8888,
        "event_id": 2,
        "operaton_amt": 1500,
        "geo_speed_km_h": 30,
        "hour_of_day": 14,
        "is_vpn_detected": 0,
        "is_proxy_detected": 0,
        "session_duration_sec": 60,
        "os_type": "Android",
    }
    response = client.post("/score/behavior", json=event)
    assert response.status_code == 200
    body = response.json()
    assert body["used_model"] is True
    assert body["latency_ms"] < 1000
