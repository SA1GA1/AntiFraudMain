from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def test_health_endpoint_returns_ok():
    app = create_app(load_models=False)
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "version" in body
