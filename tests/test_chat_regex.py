from __future__ import annotations

import pytest

from app.pipelines.chat.filter import score_thread
from app.pipelines.chat.patterns import PHISHING_PATTERNS, scan_message


def test_security_service_phrase_triggers():
    matches = scan_message("Здравствуйте! Это служба безопасности банка.")
    names = {m.name for m in matches}
    assert "security_service" in names


def test_safe_account_phrase_triggers():
    matches = scan_message("Срочно переведите средства на безопасный счёт")
    names = {m.name for m in matches}
    assert "safe_account" in names
    assert "transfer_funds" in names


def test_urgency_words_triggers():
    matches = scan_message("Прямо сейчас, немедленно!")
    names = {m.name for m in matches}
    assert "urgency" in names


def test_fake_sber_link_triggers():
    matches = scan_message("Перейдите по ссылке https://sber-bank-secure.ru/verify")
    names = {m.name for m in matches}
    assert "fake_sber_link" in names


def test_real_sber_link_does_not_trigger():
    matches = scan_message("Загляните на https://sberbank.ru/")
    names = {m.name for m in matches}
    assert "fake_sber_link" not in names


def test_sms_code_request_triggers():
    matches = scan_message("Назовите код из смс, который вам пришёл")
    names = {m.name for m in matches}
    assert "sms_code_request" in names


def test_clean_message_returns_no_matches():
    matches = scan_message("Привет! Когда увидимся?")
    assert matches == []


def test_score_thread_aggregates_weights_and_metadata():
    payload = {
        "counterparty_metadata": {
            "verification_status": "unverified",
            "account_age_days": 3,
            "geo_mismatch": True,
            "kyc_level": "none",
        },
        "messages": [
            {
                "sender_id": "usr_1",
                "receiver_id": "usr_2",
                "message_text": "Это служба безопасности. Срочно переведите средства на безопасный счёт https://sber-secure.ru",
                "timestamp": "2024-05-20T14:30:00Z",
            }
        ],
    }
    result = score_thread(payload)
    assert result.total_weight > 5.0
    triggered = {r.name for r in result.triggered}
    assert "security_service" in triggered
    assert "fake_sber_link" in triggered
    # metadata signals
    assert any(r.name == "meta:account_too_new" for r in result.triggered)


def test_score_thread_returns_empty_for_legit_chat():
    payload = {
        "counterparty_metadata": {
            "verification_status": "verified",
            "account_age_days": 1500,
            "geo_mismatch": False,
            "kyc_level": "full",
        },
        "messages": [
            {
                "sender_id": "usr_1",
                "receiver_id": "usr_2",
                "message_text": "Привет, как дела?",
                "timestamp": "2024-05-20T14:30:00Z",
            }
        ],
    }
    result = score_thread(payload)
    assert result.total_weight == 0.0
    assert result.triggered == []


def test_all_patterns_are_compilable():
    assert PHISHING_PATTERNS, "patterns must not be empty"
    for p in PHISHING_PATTERNS:
        assert p.weight > 0
        assert p.regex is not None
