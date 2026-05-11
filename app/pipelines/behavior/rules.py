"""7 rule-проверок поведения пользователя из task.md.

Каждая возвращает RuleResult; agg_rules склеивает их и считает суммарный вес.
Правила, требующие истории клиента (медиана сумм, известные устройства), читают
её из BehaviorContext. Cold-start (BehaviorContext без данных) использует
консервативные пороги.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

NIGHT_HOURS = range(2, 6)  # 02:00..05:59
COLD_START_AMOUNT_THRESHOLD = 100_000.0
AMOUNT_OUTLIER_MULTIPLIER = 5.0
GEO_TELEPORT_KMH = 800.0
TRANSFER_SPIKE_THRESHOLD = 5
MICRO_SESSION_SECONDS = 3.0


@dataclass
class BehaviorContext:
    amt_median: float | None = None
    known_devices: set[str] = field(default_factory=set)
    known_night_hour: bool = False


@dataclass
class RuleResult:
    name: str
    triggered: bool
    weight: float
    reason: str


@dataclass
class RulesOutcome:
    triggered: list[RuleResult]
    total_weight: float


def _flag(event: dict, key: str) -> bool:
    return bool(event.get(key, 0))


def rule_amount_outlier(event: dict, ctx: BehaviorContext) -> RuleResult:
    amt = float(event.get("operaton_amt", 0) or 0)
    if ctx.amt_median is None:
        triggered = amt > COLD_START_AMOUNT_THRESHOLD
        reason = f"amount={amt:.0f} > cold_start_threshold={COLD_START_AMOUNT_THRESHOLD:.0f}"
    else:
        threshold = ctx.amt_median * AMOUNT_OUTLIER_MULTIPLIER
        triggered = amt > threshold
        reason = f"amount={amt:.0f} > {AMOUNT_OUTLIER_MULTIPLIER}×median={threshold:.0f}"
    return RuleResult(name="amount_outlier", triggered=triggered, weight=2.0, reason=reason)


def rule_geo_teleport(event: dict, ctx: BehaviorContext) -> RuleResult:
    speed = float(event.get("geo_speed_km_h", 0) or 0)
    triggered = speed > GEO_TELEPORT_KMH
    return RuleResult(
        name="geo_teleport",
        triggered=triggered,
        weight=2.5,
        reason=f"geo_speed_km_h={speed:.0f} > {GEO_TELEPORT_KMH:.0f}",
    )


def rule_night_anomaly(event: dict, ctx: BehaviorContext) -> RuleResult:
    hour = event.get("hour_of_day")
    if hour is None:
        return RuleResult("night_anomaly", False, 1.0, "hour_of_day missing")
    in_night = int(hour) in NIGHT_HOURS
    triggered = in_night and not ctx.known_night_hour
    return RuleResult(
        name="night_anomaly",
        triggered=triggered,
        weight=1.0,
        reason=f"hour={hour} in night_window and user not known for night ops",
    )


def rule_new_device(event: dict, ctx: BehaviorContext) -> RuleResult:
    if _flag(event, "is_new_device"):
        return RuleResult("new_device", True, 1.5, "is_new_device flag set")
    device_id = event.get("device_id")
    if device_id and ctx.known_devices and device_id not in ctx.known_devices:
        return RuleResult(
            name="new_device",
            triggered=True,
            weight=1.5,
            reason=f"device_id={device_id} not in client history",
        )
    return RuleResult("new_device", False, 1.5, "device known")


def rule_vpn_proxy(event: dict, ctx: BehaviorContext) -> RuleResult:
    flags = [
        ("is_vpn_detected", "VPN"),
        ("is_proxy_detected", "proxy"),
        ("is_tor_detected", "Tor"),
    ]
    hits = [label for key, label in flags if _flag(event, key)]
    return RuleResult(
        name="vpn_proxy",
        triggered=bool(hits),
        weight=1.5,
        reason=f"network anonymizer: {', '.join(hits)}" if hits else "no anonymizer",
    )


def rule_transfer_spike(event: dict, ctx: BehaviorContext) -> RuleResult:
    count = int(event.get("transfers_count_last_10min", 0) or 0)
    triggered = count >= TRANSFER_SPIKE_THRESHOLD
    return RuleResult(
        name="transfer_spike",
        triggered=triggered,
        weight=2.0,
        reason=f"transfers_in_10min={count} >= {TRANSFER_SPIKE_THRESHOLD}",
    )


def rule_micro_session(event: dict, ctx: BehaviorContext) -> RuleResult:
    duration = event.get("session_duration_sec")
    if duration is None:
        return RuleResult("micro_session", False, 1.0, "no session_duration_sec")
    triggered = float(duration) < MICRO_SESSION_SECONDS
    return RuleResult(
        name="micro_session",
        triggered=triggered,
        weight=1.0,
        reason=f"session_duration_sec={duration} < {MICRO_SESSION_SECONDS}",
    )


_RULES: tuple[Callable[[dict, BehaviorContext], RuleResult], ...] = (
    rule_amount_outlier,
    rule_geo_teleport,
    rule_night_anomaly,
    rule_new_device,
    rule_vpn_proxy,
    rule_transfer_spike,
    rule_micro_session,
)


def apply_rules(event: dict, ctx: BehaviorContext) -> RulesOutcome:
    triggered: list[RuleResult] = []
    total = 0.0
    for rule in _RULES:
        r = rule(event, ctx)
        if r.triggered:
            triggered.append(r)
            total += r.weight
    return RulesOutcome(triggered=triggered, total_weight=total)
