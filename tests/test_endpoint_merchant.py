from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.deps import get_llm, get_merchant
from app.main import create_app

SEED = json.loads(
    (Path(__file__).resolve().parents[1] / "merchant_mock" / "seed.json").read_text(
        encoding="utf-8"
    )
)


class _StubMerchant:
    async def fetch(self, site_name: str) -> dict | None:
        return SEED.get(site_name)


class _StubLLM:
    def __init__(self, score: float, reason: str = "") -> None:
        self.score = score
        self.reason = reason
        self.calls = 0

    async def chat_json(self, system: str, user: str) -> dict:
        self.calls += 1
        return {"score": self.score, "reason": self.reason}


@pytest.fixture
def make_client():
    def _build(llm_score: float = 8.0):
        app = create_app(load_models=False)
        merchant = _StubMerchant()
        llm = _StubLLM(score=llm_score, reason=f"stub-llm({llm_score})")
        app.dependency_overrides[get_merchant] = lambda: merchant
        app.dependency_overrides[get_llm] = lambda: llm
        return TestClient(app), llm

    return _build


def test_merchant_known_fraud_site(make_client):
    client, llm = make_client(llm_score=9.0)
    with client:
        response = client.post(
            "/score/merchant", json={"site_name": "fast-pay-service.ru"}
        )
    assert response.status_code == 200
    body = response.json()
    assert body["score"] >= 6.0
    assert body["used_model"] is True
    assert llm.calls == 1


def test_merchant_legit_old_site_skips_llm(make_client):
    client, llm = make_client(llm_score=0.0)
    with client:
        response = client.post("/score/merchant", json={"site_name": "ozon.ru"})
    assert response.status_code == 200
    body = response.json()
    assert body["score"] <= 3.0
    assert body["decision"] == "safe"
    assert body["used_model"] is False
    assert llm.calls == 0


def test_merchant_young_suspicious_tld(make_client):
    client, llm = make_client(llm_score=8.0)
    with client:
        response = client.post(
            "/score/merchant", json={"site_name": "shop-cards-deal.cc"}
        )
    assert response.status_code == 200
    body = response.json()
    assert body["score"] >= 7.0
    triggered = {r.split(":")[1] for r in body["reasons"] if r.startswith("rule:")}
    assert "young_domain" in triggered
    assert "suspicious_tld" in triggered


def test_merchant_unknown_site_returns_medium(make_client):
    client, _ = make_client(llm_score=0.0)
    with client:
        response = client.post(
            "/score/merchant", json={"site_name": "totally-unknown.xyz"}
        )
    assert response.status_code == 200
    body = response.json()
    assert 4.0 <= body["score"] <= 6.0
    assert any("merchant:unknown" in r for r in body["reasons"])
