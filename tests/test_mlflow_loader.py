from __future__ import annotations

import pickle
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock

import pandas as pd
import pytest
import torch

from app.ml.loader import Kind


# ---------------------------------------------------------------------------
# Helpers: fabricate a fake "MLFlow artifact tree" with a real checkpoint that
# `_load_bundle` can unpickle. We reuse the production .pt if it exists, and
# fall back to skip if not — keeps the suite green on dev machines without
# trained models.
# ---------------------------------------------------------------------------


def _real_checkpoint(kind: Kind) -> Optional[Path]:
    from app.config import Settings

    s = Settings()
    path = s.web_model_path if kind == "web" else s.mobile_model_path
    return path if path.exists() else None


@pytest.fixture
def fake_mlflow_artifact_tree(tmp_path: Path, request):
    """Build <tmp>/model/artifacts/{checkpoint,customer_features} layout."""
    kind: Kind = request.param
    ck = _real_checkpoint(kind)
    if ck is None:
        pytest.skip(f"no {kind} checkpoint in ./models — cannot exercise loader")

    model_dir = tmp_path / "model"
    artifacts_dir = model_dir / "artifacts"
    artifacts_dir.mkdir(parents=True)
    shutil.copy(ck, artifacts_dir / "checkpoint")

    hist = pd.DataFrame({"customer_id": [1, 2], "amt_mean": [100.0, 200.0]})
    hist.to_parquet(artifacts_dir / "customer_features")

    return kind, tmp_path, model_dir


@pytest.fixture
def mlflow3_artifact_tree(tmp_path: Path, request):
    """Mimic real MLflow 3.x pyfunc.log_model layout: original basenames are
    preserved on disk (`artifacts/best.pt`, `artifacts/customer_features.parquet`),
    and the key→path mapping lives in MLmodel YAML."""
    kind: Kind = request.param
    ck = _real_checkpoint(kind)
    if ck is None:
        pytest.skip(f"no {kind} checkpoint in ./models — cannot exercise loader")

    model_dir = tmp_path / "model"
    artifacts_dir = model_dir / "artifacts"
    artifacts_dir.mkdir(parents=True)
    shutil.copy(ck, artifacts_dir / "best.pt")

    hist = pd.DataFrame({"customer_id": [1, 2], "amt_mean": [100.0, 200.0]})
    hist.to_parquet(artifacts_dir / "customer_features.parquet")

    (model_dir / "MLmodel").write_text(
        "artifact_path: model\n"
        "flavors:\n"
        "  python_function:\n"
        "    artifacts:\n"
        "      checkpoint:\n"
        "        path: artifacts/best.pt\n"
        "        uri: runs:/abc/model/artifacts/best.pt\n"
        "      customer_features:\n"
        "        path: artifacts/customer_features.parquet\n"
        "        uri: runs:/abc/model/artifacts/customer_features.parquet\n"
    )

    return kind, tmp_path, model_dir


def _mock_mlflow_client(version: int = 1, run_id: str = "abc123"):
    mv = MagicMock()
    mv.version = str(version)
    mv.run_id = run_id
    client = MagicMock()
    client.get_latest_versions.return_value = [mv]
    client.get_model_version.return_value = mv
    return client, mv


@pytest.mark.parametrize("fake_mlflow_artifact_tree", ["web", "mobile"], indirect=True)
def test_loader_pulls_production_version(fake_mlflow_artifact_tree, monkeypatch):
    kind, root, model_dir = fake_mlflow_artifact_tree
    from app.ml import mlflow_loader as ml_mod

    client, mv = _mock_mlflow_client(version=7)

    def fake_download(run_id, artifact_path, dst_path):
        # Simulate mlflow copying the run's artifact_path tree into dst_path
        target = Path(dst_path) / artifact_path
        if not target.exists():
            shutil.copytree(model_dir, target)
        return str(target)

    monkeypatch.setattr(ml_mod, "_LOGGER", MagicMock())
    loader = ml_mod.MlflowLoader(tracking_uri="file:///tmp/mlruns", client=client)
    monkeypatch.setattr(loader._mlflow.artifacts, "download_artifacts", fake_download)

    result = loader.reload(kind)
    assert result.version == 7
    assert result.previous_version is None
    assert result.history_df is not None
    assert result.bundle.model is not None
    # Cache is populated:
    if kind == "web":
        assert loader._cache["web"] is result.bundle
    else:
        assert loader._cache["mobile"] is result.bundle
    # get_latest_versions called for Production stage
    client.get_latest_versions.assert_called_once()
    args, kwargs = client.get_latest_versions.call_args
    assert kwargs.get("stages") == ["Production"] or "Production" in (args[1] if len(args) > 1 else [])


@pytest.mark.parametrize("mlflow3_artifact_tree", ["web", "mobile"], indirect=True)
def test_loader_resolves_mlflow3_layout_via_mlmodel(mlflow3_artifact_tree, monkeypatch):
    """Regression: real MLflow 3.x layout keeps original basenames on disk;
    the checkpoint→path mapping lives in MLmodel YAML, not in the filename."""
    kind, root, model_dir = mlflow3_artifact_tree
    from app.ml import mlflow_loader as ml_mod

    client, mv = _mock_mlflow_client(version=11)

    def fake_download(run_id, artifact_path, dst_path):
        target = Path(dst_path) / artifact_path
        if not target.exists():
            shutil.copytree(model_dir, target)
        return str(target)

    monkeypatch.setattr(ml_mod, "_LOGGER", MagicMock())
    loader = ml_mod.MlflowLoader(tracking_uri="file:///tmp/mlruns", client=client)
    monkeypatch.setattr(loader._mlflow.artifacts, "download_artifacts", fake_download)

    result = loader.reload(kind)
    assert result.version == 11
    assert result.bundle.model is not None
    assert result.history_df is not None


def test_loader_raises_when_no_production_version():
    from app.ml.mlflow_loader import MlflowLoader

    client = MagicMock()
    client.get_latest_versions.return_value = []
    loader = MlflowLoader(tracking_uri="file:///tmp/mlruns", client=client)
    with pytest.raises(RuntimeError, match="No 'Production' version"):
        loader.reload("web")


@pytest.mark.parametrize("fake_mlflow_artifact_tree", ["web"], indirect=True)
def test_loader_fetches_specific_version_for_rollback(fake_mlflow_artifact_tree, monkeypatch):
    kind, root, model_dir = fake_mlflow_artifact_tree
    from app.ml import mlflow_loader as ml_mod

    client, mv = _mock_mlflow_client(version=3)

    def fake_download(run_id, artifact_path, dst_path):
        target = Path(dst_path) / artifact_path
        if not target.exists():
            shutil.copytree(model_dir, target)
        return str(target)

    loader = ml_mod.MlflowLoader(tracking_uri="file:///tmp/mlruns", client=client)
    monkeypatch.setattr(loader._mlflow.artifacts, "download_artifacts", fake_download)

    result = loader.reload(kind, version=3)
    assert result.version == 3
    client.get_model_version.assert_called_once_with("fraud_mlp_web", "3")
    # get_latest_versions should NOT have been used when version is explicit
    client.get_latest_versions.assert_not_called()


def test_local_loader_reload_invalidates_cache():
    from unittest.mock import patch

    from app.ml.loader import LocalFileLoader, ReloadResult

    loader = LocalFileLoader(mobile_path=Path("/x/m.pt"), web_path=Path("/x/w.pt"))
    sentinel = object()
    loader._web = sentinel  # type: ignore[assignment]

    def fake_load_bundle(path, pkg):
        return MagicMock()

    with patch("app.ml.loader._load_bundle", fake_load_bundle):
        result = loader.reload("web")
    assert isinstance(result, ReloadResult)
    assert loader._web is not sentinel
    assert loader._web is result.bundle


def test_deps_switcher_picks_mlflow_backend(monkeypatch):
    from app.config import Settings
    from app.deps import build_runtime

    monkeypatch.setenv("FRAUD_MODEL_BACKEND", "mlflow")
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "file:///tmp/mlruns")
    settings = Settings()
    # Stub OllamaClient and MerchantClient construction (they spin up httpx clients)
    with monkeypatch.context() as m:
        m.setattr("app.llm.client.OllamaClient", lambda **kw: MagicMock())
        m.setattr("app.pipelines.merchant.enrich.MerchantClient", lambda **kw: MagicMock())
        runtime = build_runtime(settings)
    from app.ml.mlflow_loader import MlflowLoader

    assert isinstance(runtime.models, MlflowLoader)
