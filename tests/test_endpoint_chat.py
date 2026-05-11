from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.deps import get_llm
from app.main import create_app


class _StubLLM:
    """Возвращает заранее заготовленный JSON, имитируя Ollama."""

    def __init__(self, score: float = 8.0, reason: str = "социнженерия") -> None:
        self.score = score
        self.reason = reason
        self.calls = 0

    async def chat_json(self, system: str, user: str) -> dict:
        self.calls += 1
        return {"score": self.score, "reason": self.reason}


@pytest.fixture
def stub_llm() -> _StubLLM:
    return _StubLLM(score=8.5, reason="фишинговая ссылка и запрос кода из СМС")


@pytest.fixture
def client(stub_llm: _StubLLM) -> TestClient:
    app = create_app(load_models=False)
    app.state.llm = stub_llm
    app.dependency_overrides[get_llm] = lambda: stub_llm
    with TestClient(app) as c:
        yield c


_PHISHING_PAYLOAD = {
    "counterparty_metadata": {
        "user_id": "usr_8492",
        "verification_status": "unverified",
        "account_age_days": 3,
        "geo_location": "KZ-ALA",
        "geo_mismatch": True,
        "kyc_level": "none",
    },
    "messages": [
        {
            "sender_id": "usr_8492",
            "receiver_id": "usr_1057",
            "message_text": (
                "Здравствуйте! Это служба безопасности банка. Ваш счёт под угрозой. "
                "Срочно переведите средства на безопасный кошелёк: "
                "https://sber-bank-secure.ru/verify"
            ),
            "timestamp": "2024-05-20T14:30:00Z",
        }
    ],
}

_CLEAN_PAYLOAD = {
    "counterparty_metadata": {
        "user_id": "usr_friend",
        "verification_status": "verified",
        "account_age_days": 1500,
        "geo_mismatch": False,
        "kyc_level": "full",
    },
    "messages": [
        {
            "sender_id": "usr_friend",
            "receiver_id": "usr_1057",
            "message_text": "Привет! Когда увидимся?",
            "timestamp": "2024-05-20T14:30:00Z",
        }
    ],
}


def test_chat_phishing_triggers_llm(client, stub_llm):
    response = client.post("/score/chat", json=_PHISHING_PAYLOAD)
    assert response.status_code == 200
    body = response.json()
    assert body["score"] >= 6.0
    assert body["decision"] in {"sms", "biometry"}
    assert body["used_model"] is True
    assert stub_llm.calls == 1


def test_chat_clean_does_not_trigger_llm(client, stub_llm):
    response = client.post("/score/chat", json=_CLEAN_PAYLOAD)
    assert response.status_code == 200
    body = response.json()
    assert body["score"] <= 3.0
    assert body["decision"] == "safe"
    assert body["used_model"] is False
    assert stub_llm.calls == 0


def test_chat_handles_llm_failure_gracefully(stub_llm):
    class _BrokenLLM:
        async def chat_json(self, system: str, user: str) -> dict:
            raise RuntimeError("ollama down")

    app = create_app(load_models=False)
    broken = _BrokenLLM()
    app.dependency_overrides[get_llm] = lambda: broken
    with TestClient(app) as c:
        response = c.post("/score/chat", json=_PHISHING_PAYLOAD)
    assert response.status_code == 200
    body = response.json()
    # rules alone уже дают score >= 6; LLM крашнулся → used_model=False
    assert body["score"] >= 6.0
    assert body["used_model"] is False
