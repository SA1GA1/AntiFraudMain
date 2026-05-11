"""Mock-сервис магазинов: GET /merchant/{site_name} → данные из seed.json."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException

SEED_PATH = Path(__file__).parent / "seed.json"
SEED: dict = json.loads(SEED_PATH.read_text(encoding="utf-8"))

app = FastAPI(title="merchant-mock", version="0.1.0")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "merchants_loaded": len(SEED)}


@app.get("/merchant/{site_name}")
def get_merchant(site_name: str) -> dict:
    record = SEED.get(site_name)
    if record is None:
        raise HTTPException(status_code=404, detail=f"unknown site: {site_name}")
    return record
