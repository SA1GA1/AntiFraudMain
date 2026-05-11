"""Regex-паттерны фишинга/социнженерии в русскоязычной банковской переписке."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Pattern:
    name: str
    regex: re.Pattern
    weight: float
    description: str


@dataclass
class Match:
    name: str
    weight: float
    snippet: str


PHISHING_PATTERNS: tuple[Pattern, ...] = (
    Pattern(
        name="security_service",
        regex=re.compile(r"служб[аеуыо]\s+безопасност", re.IGNORECASE),
        weight=2.0,
        description="Представление 'службой безопасности банка'",
    ),
    Pattern(
        name="safe_account",
        regex=re.compile(r"безопасн\w*\s+(счет|счёт|кошел[её]к|счета)", re.IGNORECASE),
        weight=2.5,
        description="Просьба перевести на 'безопасный' счёт",
    ),
    Pattern(
        name="urgency",
        regex=re.compile(r"\b(срочн|немедленн|прямо\s+сейчас|немедля)\w*\b", re.IGNORECASE),
        weight=1.0,
        description="Urgency-маркеры",
    ),
    Pattern(
        name="fake_sber_link",
        regex=re.compile(
            r"https?://(?!sberbank\.ru|www\.sberbank\.ru)[\w.-]*sber[\w.-]+",
            re.IGNORECASE,
        ),
        weight=2.0,
        description="Подменный домен с 'sber' в имени",
    ),
    Pattern(
        name="sms_code_request",
        regex=re.compile(r"(назовите|сообщите|пришлите|введите)\s+код\s+из\s+(смс|sms)", re.IGNORECASE),
        weight=2.5,
        description="Запрос кода из СМС",
    ),
    Pattern(
        name="transfer_funds",
        regex=re.compile(r"перевед[иите]\w*\s+(средств|деньги|сумм)", re.IGNORECASE),
        weight=1.5,
        description="Прямой призыв к переводу средств",
    ),
    Pattern(
        name="card_data_request",
        regex=re.compile(
            r"(номер\s+карт|cvc|cvv|срок\s+действия\s+карт|пин-код|пинкод)",
            re.IGNORECASE,
        ),
        weight=2.5,
        description="Запрос реквизитов карты",
    ),
    Pattern(
        name="threat_block",
        regex=re.compile(r"(счет|счёт|карта|аккаунт)\w*\s+(заблокирован|под\s+угрозой|взломан)", re.IGNORECASE),
        weight=1.5,
        description="Угроза блокировкой счёта",
    ),
)


def scan_message(text: str) -> list[Match]:
    matches: list[Match] = []
    for p in PHISHING_PATTERNS:
        m = p.regex.search(text)
        if m:
            matches.append(Match(name=p.name, weight=p.weight, snippet=m.group(0)))
    return matches
