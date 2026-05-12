from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.ml.loader import Kind, ModelBundle, ReloadResult


@dataclass
class _StubBundle:
    """Duck-typed ModelBundle stand-in (we only need attribute identity)."""

    name: str = "stub"


class _StubLoader:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[Kind, Optional[int]]] = []
        self.version_counter = {"web": 0, "mobile": 0}
        self._bundles: dict[Kind, ModelBundle] = {}

    def load_web(self) -> ModelBundle:  # pragma: no cover (not exercised here)
        return self._bundles.setdefault("web", _StubBundle("web"))  # type: ignore[return-value]

    def load_mobile(self) -> ModelBundle:  # pragma: no cover
        return self._bundles.setdefault("mobile", _StubBundle("mobile"))  # type: ignore[return-value]

    def reload(self, kind: Kind, version: Optional[int] = None) -> ReloadResult:
        self.calls.append((kind, version))
        if self.fail:
            raise RuntimeError("mlflow unreachable")
        prev = self.version_counter[kind] or None
        new_version = version if version is not None else self.version_counter[kind] + 1
        self.version_counter[kind] = new_version
        bundle = _StubBundle(f"{kind}-v{new_version}")
        self._bundles[kind] = bundle  # type: ignore[assignment]
        history = pd.DataFrame({"customer_id": [1, 2], "event_count": [3, 5]})
        return ReloadResult(
            kind=kind,
            bundle=bundle,  # type: ignore[arg-type]
            version=new_version,
            previous_version=prev,
            history_df=history,
        )


@pytest.fixture
def client_with_stub_loader():
    app = create_app(load_models=False)
    loader = _StubLoader()
    with TestClient(app) as c:
        # lifespan resets state — install stub loader after enter
        app.state.models = loader
        yield c, loader


def test_reload_requires_bearer_header(client_with_stub_loader):
    client, _ = client_with_stub_loader
    response = client.post(
        "/admin/reload-model",
        json={"model_name": "fraud_mlp_web"},
    )
    assert response.status_code == 401


def test_reload_rejects_wrong_token(client_with_stub_loader):
    client, _ = client_with_stub_loader
    response = client.post(
        "/admin/reload-model",
        json={"model_name": "fraud_mlp_web"},
        headers={"Authorization": "Bearer wrong"},
    )
    assert response.status_code == 403


def test_reload_web_swaps_bundle_and_history(client_with_stub_loader):
    client, loader = client_with_stub_loader
    response = client.post(
        "/admin/reload-model",
        json={"model_name": "fraud_mlp_web"},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body == {
        "reloaded": True,
        "model_name": "fraud_mlp_web",
        "version": 1,
        "previous_version": None,
    }
    assert loader.calls == [("web", None)]
    assert client.app.state.history_web is not None
    # mobile history untouched
    assert client.app.state.history_mobile is None or client.app.state.history_mobile is client.app.state.history


def test_reload_rollback_to_specific_version(client_with_stub_loader):
    client, loader = client_with_stub_loader
    client.post(
        "/admin/reload-model",
        json={"model_name": "fraud_mlp_web"},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    response = client.post(
        "/admin/reload-model",
        json={"model_name": "fraud_mlp_web", "version": 5},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["version"] == 5
    assert body["previous_version"] == 1
    assert loader.calls == [("web", None), ("web", 5)]


def test_reload_handles_mlflow_failure_with_503():
    app = create_app(load_models=False)
    with TestClient(app) as c:
        app.state.models = _StubLoader(fail=True)
        response = c.post(
            "/admin/reload-model",
            json={"model_name": "fraud_mlp_mobile"},
            headers={"Authorization": "Bearer test-admin-token"},
        )
    assert response.status_code == 503
    assert "mlflow" in response.text.lower()


def test_reload_rejects_unknown_model_name(client_with_stub_loader):
    client, _ = client_with_stub_loader
    response = client.post(
        "/admin/reload-model",
        json={"model_name": "fraud_mlp_unknown"},
        headers={"Authorization": "Bearer test-admin-token"},
    )
    assert response.status_code == 422  # pydantic Literal mismatch
