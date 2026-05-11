"""Прогон regex по списку сообщений + сигналы из counterparty_metadata."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.pipelines.chat.patterns import Match, scan_message


@dataclass
class ChatTrigger:
    name: str
    weight: float
    snippet: str = ""


@dataclass
class ChatScanResult:
    triggered: list[ChatTrigger] = field(default_factory=list)
    total_weight: float = 0.0


_META_RULES = (
    ("meta:account_too_new", 1.0, lambda m: int(m.get("account_age_days") or 9999) < 7),
    ("meta:unverified", 0.5, lambda m: m.get("verification_status") == "unverified"),
    ("meta:geo_mismatch", 0.5, lambda m: bool(m.get("geo_mismatch"))),
    ("meta:no_kyc", 0.5, lambda m: m.get("kyc_level") == "none"),
)


def score_thread(payload: dict) -> ChatScanResult:
    res = ChatScanResult()
    for msg in payload.get("messages", []):
        text = msg.get("message_text", "") or ""
        for m in scan_message(text):
            res.triggered.append(ChatTrigger(name=m.name, weight=m.weight, snippet=m.snippet))
            res.total_weight += m.weight
    meta = payload.get("counterparty_metadata") or {}
    for name, weight, predicate in _META_RULES:
        try:
            if predicate(meta):
                res.triggered.append(ChatTrigger(name=name, weight=weight))
                res.total_weight += weight
        except (TypeError, ValueError):
            continue
    return res
