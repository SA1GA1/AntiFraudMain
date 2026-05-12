"""Идемпотентный seed MLFlow Model Registry.

Кладёт стартовые чекпоинты `/models/{mobile,web}_best.pt` как первые версии
зарегистрированных моделей `fraud_mlp_{mobile,web}` в Production stage,
чтобы `MlflowLoader` мог их подтянуть при старте backend'а.

Конвенция артефактов согласована с `app/ml/mlflow_loader.py:_find_artifact`:
файл логируется под именем `checkpoint` в `artifact_path="model/artifacts"` —
после `download_artifacts(artifact_path="model")` локальный путь будет
`{tmp}/model/artifacts/checkpoint`, что попадает в первый candidate
`root / "artifacts" / "checkpoint"`.

При повторном `docker compose up` скрипт молча скипает уже засеяненные модели.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile

import mlflow
from mlflow.exceptions import RestException
from mlflow.tracking import MlflowClient

MODELS = [
    ("mobile", "fraud_mlp_mobile", "/models/mobile_best.pt"),
    ("web", "fraud_mlp_web", "/models/web_best.pt"),
]


def already_seeded(client: MlflowClient, name: str) -> bool:
    try:
        versions = client.get_latest_versions(name, stages=["Production"])
    except RestException as exc:
        if "RESOURCE_DOES_NOT_EXIST" in str(exc):
            return False
        raise
    return bool(versions)


def seed_one(kind: str, name: str, checkpoint_path: str) -> None:
    client = MlflowClient()

    if already_seeded(client, name):
        print(f"[{kind}] {name} уже имеет Production version — skip")
        return

    if not os.path.isfile(checkpoint_path):
        print(f"[{kind}] {checkpoint_path} не найден — пропускаю", file=sys.stderr)
        return

    mlflow.set_experiment(name)

    with tempfile.TemporaryDirectory() as td:
        staging = os.path.join(td, "checkpoint")
        shutil.copyfile(checkpoint_path, staging)

        with mlflow.start_run(run_name=f"seed_{kind}") as run:
            mlflow.log_artifact(staging, artifact_path="model/artifacts")
            mlflow.set_tag("seed", "true")
            mlflow.set_tag("source_path", checkpoint_path)
            run_id = run.info.run_id
            artifact_uri = run.info.artifact_uri

    try:
        client.create_registered_model(name)
    except RestException as exc:
        if "RESOURCE_ALREADY_EXISTS" not in str(exc):
            raise

    mv = client.create_model_version(
        name=name,
        source=f"{artifact_uri}/model",
        run_id=run_id,
    )
    client.transition_model_version_stage(
        name=name,
        version=mv.version,
        stage="Production",
        archive_existing_versions=False,
    )
    print(f"[{kind}] seeded {name} v{mv.version} → Production (run_id={run_id})")


def main() -> int:
    tracking_uri = os.environ.get("MLFLOW_TRACKING_URI", "http://mlflow:5000")
    mlflow.set_tracking_uri(tracking_uri)
    print(f"MLFLOW_TRACKING_URI={tracking_uri}")

    for kind, name, ckpt in MODELS:
        seed_one(kind, name, ckpt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
