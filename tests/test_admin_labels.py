from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FRAUD_ROOT", str(tmp_path))
    # Settings is a class-cached object; force fresh read by clearing get_settings lru caches.
    # We construct the app after setenv so lifespan picks up the new value.
    app = create_app(load_models=False)
    app.state.settings = Settings()
    with TestClient(app) as c:
        yield c, tmp_path


def _auth() -> dict[str, str]:
    return {"Authorization": "Bearer test-admin-token"}


def test_labels_batch_writes_parquet_per_kind(client):
    c, root = client
    payload = [
        {"customer_id": 1, "event_id": 11, "target": 1, "kind": "web"},
        {"customer_id": 2, "event_id": 22, "target": 0, "kind": "mobile"},
        {"customer_id": 3, "event_id": 33, "target": 1, "kind": "web"},
    ]
    response = c.post("/admin/labels-batch", json=payload, headers=_auth())
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["written"] == 3
    assert len(body["paths"]) == 2

    web_files = list((root / "labels").rglob("*.parquet"))
    mobile_files = list((root / "labels_mobile").rglob("*.parquet"))
    assert len(web_files) == 1
    assert len(mobile_files) == 1
    web_df = pd.read_parquet(web_files[0])
    assert len(web_df) == 2
    assert set(web_df["event_id"]) == {11, 33}
    assert (web_df["source"] == "manual").all()
    assert "label_dttm" in web_df.columns


def test_labels_batch_requires_auth(client):
    c, _ = client
    response = c.post(
        "/admin/labels-batch",
        json=[{"customer_id": 1, "event_id": 1, "target": 1, "kind": "web"}],
    )
    assert response.status_code == 401


def test_labels_batch_rejects_empty(client):
    c, _ = client
    response = c.post("/admin/labels-batch", json=[], headers=_auth())
    assert response.status_code == 400


def test_labels_batch_rejects_bad_target(client):
    c, _ = client
    # pydantic catches target literal first (422)
    response = c.post(
        "/admin/labels-batch",
        json=[{"customer_id": 1, "event_id": 1, "target": 99, "kind": "web"}],
        headers=_auth(),
    )
    assert response.status_code == 422
