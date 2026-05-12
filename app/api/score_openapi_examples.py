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

# ── Merchant: полная карточка как в task.md (лишние поля в теле допустимы). ──

MERCHANT_OPENAPI_LOW_PFRAUD: dict[str, object] = {
    "site_name": "ozon.ru",
    "merchant_name": "ozon.ru",
    "registration_date": "2000-04-23",
    "domain_age_days": 9100,
    "owner_name": "ООО Интернет Решения",
    "admin_contact": "support@ozon.ru",
    "inn": "7704217370",
    "server_ip": "176.99.10.10",
    "reviews": [
        {"rating": 5, "text": "Привезли вовремя, упаковка целая."},
        {"rating": 4, "text": "Нормальный маркетплейс, пользуюсь годами."},
        {"rating": 5, "text": "Возврат без проблем, поддержка ответила быстро."},
        {"rating": 5, "text": "Широкий выбор, акции адекватные."},
    ],
}

MERCHANT_OPENAPI_HIGH_PFRAUD: dict[str, object] = {
    "site_name": "fast-pay-service.ru",
    "merchant_name": "fast-pay-service.ru",
    "registration_date": "2024-01-10",
    "domain_age_days": 120,
    "owner_name": "ИП Петров А.А.",
    "admin_contact": "info@fast-pay-service.ru",
    "inn": "771234567890",
    "server_ip": "45.132.67.89",
    "reviews": [
        {"rating": 5, "text": "хорошо"},
        {"rating": 5, "text": "норм"},
        {"rating": 1, "text": "Мошенники, не пришел товар, деньги не вернули!"},
        {"rating": 1, "text": "Обман, фишинговый сайт, украли данные карты."},
    ],
}
