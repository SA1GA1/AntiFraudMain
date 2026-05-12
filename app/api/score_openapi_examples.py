"""Тела запросов для OpenAPI: полные JSON + пары «низкий / высокий p_fraud» для /score/*."""

from __future__ import annotations

# ── Chat: все поля, которые читает pipeline (counterparty_metadata + messages). ──

CHAT_OPENAPI_LOW_PFRAUD: dict[str, object] = {
    "counterparty_metadata": {
        "user_id": "usr_friend_stable",
        "verification_status": "verified",
        "account_age_days": 1825,
        "geo_location": "RU-MOW",
        "geo_mismatch": False,
        "kyc_level": "full",
    },
    "messages": [
        {
            "sender_id": "usr_friend_stable",
            "receiver_id": "usr_self_001",
            "message_text": (
                "Привет! Напомни, во сколько сегодня встреча у метро? "
                "Погода отличная, можно пройтись пешком."
            ),
            "timestamp": "2026-05-12T10:15:00Z",
        },
        {
            "sender_id": "usr_self_001",
            "receiver_id": "usr_friend_stable",
            "message_text": "В 18:30 у входа в парк, жду у фонтана.",
            "timestamp": "2026-05-12T10:16:22Z",
        },
    ],
}

CHAT_OPENAPI_HIGH_PFRAUD: dict[str, object] = {
    "counterparty_metadata": {
        "user_id": "usr_phish_urgent",
        "verification_status": "unverified",
        "account_age_days": 2,
        "geo_location": "XX-UNK",
        "geo_mismatch": True,
        "kyc_level": "none",
    },
    "messages": [
        {
            "sender_id": "usr_phish_urgent",
            "receiver_id": "usr_victim_104",
            "message_text": (
                "СРОЧНО! Служба безопасности банка. Ваш счёт заблокирован из-за "
                "подозрительной активности. Переведите средства на резервный счёт "
                "для разблокировки: https://fake-bank-secure-login.ru/pay?token=abc"
            ),
            "timestamp": "2026-05-12T03:40:00Z",
        },
        {
            "sender_id": "usr_victim_104",
            "receiver_id": "usr_phish_urgent",
            "message_text": "Как мне убедиться, что это официальный канал?",
            "timestamp": "2026-05-12T03:41:10Z",
        },
    ],
}

# ── Merchant: только идентификатор магазина; карточка и отзывы — из merchant_mock. ──

MERCHANT_OPENAPI_LOW_PFRAUD: dict[str, object] = {
    "site_name": "ozon.ru",
    "merchant_name": "ozon.ru",
}

MERCHANT_OPENAPI_HIGH_PFRAUD: dict[str, object] = {
    "site_name": "fast-pay-service.ru",
    "merchant_name": "fast-pay-service.ru",
}
