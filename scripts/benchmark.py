"""Замеряет p50/p95/p99 latency для трёх endpoint'ов против ЗАПУЩЕННОГО backend.

Использование:
    python scripts/benchmark.py --base http://localhost:8000 --n 200
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from statistics import median, quantiles
from typing import Any

import httpx

DEFAULT_BASE = "http://localhost:8000"

BEHAVIOR_PAYLOAD = {
    "customer_id": 4242,
    "event_id": 1,
    "event_dttm": "2025-08-09 14:00:00",
    "operaton_amt": 1500,
    "geo_speed_km_h": 30,
    "session_duration_sec": 60,
    "os_type": "Android",
}

CHAT_PAYLOAD = {
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
            "message_text": "Это служба безопасности. Срочно переведите средства.",
            "timestamp": "2024-05-20T14:30:00Z",
        }
    ],
}

MERCHANT_PAYLOAD = {"site_name": "fast-pay-service.ru"}


async def _bench_one(client: httpx.AsyncClient, url: str, payload: dict) -> float:
    t0 = time.perf_counter()
    resp = await client.post(url, json=payload)
    resp.raise_for_status()
    return (time.perf_counter() - t0) * 1000.0


async def _bench(base: str, path: str, payload: dict, n: int) -> list[float]:
    async with httpx.AsyncClient(timeout=5.0) as client:
        # warm-up
        await _bench_one(client, f"{base}{path}", payload)
        return [await _bench_one(client, f"{base}{path}", payload) for _ in range(n)]


def _percentile(values: list[float], p: float) -> float:
    if len(values) < 2:
        return values[0] if values else 0.0
    qs = quantiles(values, n=100)
    return qs[int(p) - 1]


def _print(name: str, values: list[float]) -> None:
    print(
        f"{name:>10}: "
        f"p50={median(values):6.1f}ms  "
        f"p95={_percentile(values, 95):6.1f}ms  "
        f"p99={_percentile(values, 99):6.1f}ms  "
        f"max={max(values):6.1f}ms  n={len(values)}"
    )


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=DEFAULT_BASE)
    parser.add_argument("--n", type=int, default=200)
    args = parser.parse_args()

    cases = [
        ("behavior", "/score/behavior", BEHAVIOR_PAYLOAD),
        ("chat", "/score/chat", CHAT_PAYLOAD),
        ("merchant", "/score/merchant", MERCHANT_PAYLOAD),
    ]
    for name, path, payload in cases:
        values = await _bench(args.base, path, payload, args.n)
        _print(name, values)


if __name__ == "__main__":
    asyncio.run(main())
