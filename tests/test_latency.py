"""Latency SLA: p95 для всех трёх endpoint-ов должен быть < 900 мс.

LLM-зависимости моканы (моментальные ответы), как при идеально быстрой Ollama;
реальный SLA проверяется через scripts/benchmark.py против поднятого стека.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from statistics import quantiles

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.deps import get_llm, get_merchant
from app.main import create_app

SLA_MS = 900
RUNS = 30

SEED = json.loads(
    (Path(__file__).resolve().parents[1] / "merchant_mock" / "seed.json").read_text(
        encoding="utf-8"
    )
)


class _FastLLM:
    async def chat_json(self, system: str, user: str) -> dict:
        return {"score": 7, "reason": "stub"}


class _FastMerchant:
    async def fetch(self, site_name: str) -> dict | None:
        return SEED.get(site_name)


def _has_models() -> bool:
    s = Settings()
    return s.mobile_model_path.exists() and s.web_model_path.exists()


def _percentile(values: list[float], p: float) -> float:
    if len(values) < 2:
        return values[0] if values else 0.0
    qs = quantiles(values, n=100)
    return qs[int(p) - 1]


@pytest.fixture(scope="module")
def client() -> TestClient:
    if not _has_models():
        pytest.skip("ML checkpoints absent")
    app = create_app(load_models=True)
    app.dependency_overrides[get_llm] = lambda: _FastLLM()
    app.dependency_overrides[get_merchant] = lambda: _FastMerchant()
    with TestClient(app) as c:
        yield c


_BEHAVIOR_PAYLOAD = {
    "customer_id": 4242,
    "event_id": 1,
    "event_dttm": "2025-08-09 14:00:00",
    "operaton_amt": 1500,
    "geo_speed_km_h": 30,
    "is_vpn_detected": 0,
    "is_proxy_detected": 0,
    "session_duration_sec": 60,
    "os_type": "Android",
}

_CHAT_PAYLOAD = {
    "counterparty_metadata": {
        "verification_status": "unverified",
        "account_age_days": 3,
        "geo_mismatch": True,
        "kyc_level": "none",
    },
    "messages": [
        {
            "sender_id": "u1",
            "receiver_id": "u2",
            "message_text": "Это служба безопасности банка. Срочно переведите средства на безопасный счёт.",
            "timestamp": "2024-05-20T14:30:00Z",
        }
    ],
}


def _measure(client: TestClient, path: str, payload: dict) -> list[float]:
    durations = []
    for _ in range(RUNS):
        t0 = time.perf_counter()
        resp = client.post(path, json=payload)
        durations.append((time.perf_counter() - t0) * 1000.0)
        assert resp.status_code == 200
    return durations


def test_behavior_p95_under_sla(client):
    durations = _measure(client, "/score/behavior/mobile", _BEHAVIOR_PAYLOAD)
    p95 = _percentile(durations, 95)
    assert p95 < SLA_MS, f"behavior p95={p95:.1f}ms exceeds SLA {SLA_MS}ms"


def test_chat_p95_under_sla(client):
    durations = _measure(client, "/score/chat", _CHAT_PAYLOAD)
    p95 = _percentile(durations, 95)
    assert p95 < SLA_MS, f"chat p95={p95:.1f}ms exceeds SLA {SLA_MS}ms"


def test_merchant_p95_under_sla(client):
    durations = _measure(client, "/score/merchant", {"site_name": "fast-pay-service.ru"})
    p95 = _percentile(durations, 95)
    assert p95 < SLA_MS, f"merchant p95={p95:.1f}ms exceeds SLA {SLA_MS}ms"
