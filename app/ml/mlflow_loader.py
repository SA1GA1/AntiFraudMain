"""MlflowLoader — fetches FraudMLP checkpoints from an MLFlow Registry.

todo.md #3: production-loader for the daily-retrain cycle. Replaces
LocalFileLoader when `FRAUD_MODEL_BACKEND=mlflow`.

Strategy
--------
We do **not** use `mlflow.pyfunc.load_model` — that would force us through the
FraudPyfunc DataFrame in/out API and lose the `ModelBundle.predict_proba`
contract that the rest of the backend relies on.

Instead we:
1. resolve the desired ModelVersion (`Production` stage by default, or explicit
   `version=N` for rollback);
2. download the run's `model/` artifact tree to a temp dir;
3. locate the `checkpoint` artifact (raw .pt blob) and feed it to the
   existing `_load_bundle(path, pkg)` — reusing the `_pkg_*` trainer-alias
   trick already in `app.ml.loader`;
4. locate the `customer_features` artifact (per-version parquet) and return it
   alongside, so `/admin/reload-model` can swap `app.state.history_*` atomically.

The artifact layout produced by `trainer/train.py:_Tracker.log_pyfunc` puts the
two artifacts under `<model_dir>/artifacts/<key>`. We probe several plausible
locations to stay robust across MLFlow versions.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Optional

import pandas as pd

from app.core.logging import get_logger
from app.ml.loader import Kind, ModelBundle, ReloadResult, _load_bundle

_LOGGER = get_logger("mlflow_loader")

_MODEL_NAMES: dict[Kind, str] = {
    "web": "fraud_mlp_web",
    "mobile": "fraud_mlp_mobile",
}


def _model_name(kind: Kind) -> str:
    return _MODEL_NAMES[kind]


def _find_artifact(root: Path, key: str) -> Optional[Path]:
    """Locate an MLFlow artifact file by key, tolerating layout variations."""
    candidates = [
        root / "artifacts" / key,
        root / key,
        root / "model" / "artifacts" / key,
    ]
    for c in candidates:
        if c.is_file():
            return c
    matches = [p for p in root.rglob(key) if p.is_file()]
    return matches[0] if matches else None


class MlflowLoader:
    def __init__(
        self,
        tracking_uri: str,
        web_model_name: str = "fraud_mlp_web",
        mobile_model_name: str = "fraud_mlp_mobile",
        client=None,
    ) -> None:
        import mlflow
        from mlflow.tracking import MlflowClient

        mlflow.set_tracking_uri(tracking_uri)
        self._mlflow = mlflow
        self.tracking_uri = tracking_uri
        self.client = client or MlflowClient(tracking_uri=tracking_uri)
        self._names: dict[Kind, str] = {"web": web_model_name, "mobile": mobile_model_name}
        self._cache: dict[Kind, Optional[ModelBundle]] = {"web": None, "mobile": None}
        self._versions: dict[Kind, Optional[int]] = {"web": None, "mobile": None}

    # ----------------------------------------------------------------- protocol
    def load_web(self) -> ModelBundle:
        if self._cache["web"] is None:
            self.reload("web")
        bundle = self._cache["web"]
        assert bundle is not None
        return bundle

    def load_mobile(self) -> ModelBundle:
        if self._cache["mobile"] is None:
            self.reload("mobile")
        bundle = self._cache["mobile"]
        assert bundle is not None
        return bundle

    def reload(self, kind: Kind, version: Optional[int] = None) -> ReloadResult:
        name = self._names[kind]
        mv = self._resolve_version(name, version)
        bundle, history_df = self._download_and_load(kind, mv)
        previous = self._versions[kind]
        self._cache[kind] = bundle
        self._versions[kind] = int(mv.version)
        _LOGGER.info(
            "mlflow_reload",
            kind=kind,
            model_name=name,
            version=int(mv.version),
            previous=previous,
            has_history=history_df is not None,
        )
        return ReloadResult(
            kind=kind,
            bundle=bundle,
            version=int(mv.version),
            previous_version=previous,
            history_df=history_df,
        )

    # ----------------------------------------------------------------- helpers
    def _resolve_version(self, name: str, version: Optional[int]):
        if version is not None:
            return self.client.get_model_version(name, str(version))
        versions = self.client.get_latest_versions(name, stages=["Production"])
        if not versions:
            raise RuntimeError(
                f"No 'Production' version found for {name!r} in MLFlow registry"
            )
        return versions[0]

    def _download_and_load(self, kind: Kind, mv) -> tuple[ModelBundle, Optional[pd.DataFrame]]:
        from app.ml import _pkg_mobile, _pkg_web

        pkg = _pkg_web if kind == "web" else _pkg_mobile
        with tempfile.TemporaryDirectory(prefix="mlflow_fraud_") as tmp:
            local = self._mlflow.artifacts.download_artifacts(
                run_id=mv.run_id,
                artifact_path="model",
                dst_path=tmp,
            )
            local_path = Path(local)
            ckpt = _find_artifact(local_path, "checkpoint")
            if ckpt is None:
                raise RuntimeError(
                    f"checkpoint artifact not found under {local_path}"
                )
            bundle = _load_bundle(ckpt, pkg)
            cf = _find_artifact(local_path, "customer_features")
            history_df = pd.read_parquet(cf) if cf is not None else None
        return bundle, history_df
