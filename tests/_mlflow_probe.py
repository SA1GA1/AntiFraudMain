"""One-shot diagnostic for MlflowLoader 'checkpoint artifact not found'.

Run inside api container:
    docker compose exec api python /app/tests/_mlflow_probe.py
"""
from __future__ import annotations

import os
import tempfile

import mlflow
from mlflow.tracking import MlflowClient

URI = os.environ.get("MLFLOW_TRACKING_URI", "http://mlflow:5000")
MODEL = os.environ.get("PROBE_MODEL", "fraud_mlp_mobile")

mlflow.set_tracking_uri(URI)
client = MlflowClient(URI)

versions = client.search_model_versions(f"name='{MODEL}'")
if not versions:
    raise SystemExit(f"no versions for {MODEL}")

mv = max(versions, key=lambda v: int(v.version))
print(f"version={mv.version}  stage={mv.current_stage}  run_id={mv.run_id}")
print(f"source={mv.source}")
print(f"aliases={getattr(mv, 'aliases', None)}")


def walk_registry(path: str, depth: int = 0) -> None:
    for art in client.list_artifacts(mv.run_id, path):
        print("  " * (depth + 1) + f"{art.path}  is_dir={art.is_dir}  size={art.file_size}")
        if art.is_dir:
            walk_registry(art.path, depth + 1)


print("\n--- list_artifacts(run_id, 'model') ---")
walk_registry("model")

print("\n--- list_artifacts(run_id, '') [root] ---")
walk_registry("")


def dump_tree(p: str) -> None:
    for root, _, files in os.walk(p):
        for f in files:
            print(" ", os.path.join(root, f).removeprefix(p))


with tempfile.TemporaryDirectory() as td:
    p = mlflow.artifacts.download_artifacts(run_id=mv.run_id, artifact_path="model", dst_path=td)
    print(f"\n--- download_artifacts(run_id, 'model') -> {p} ---")
    dump_tree(p)

with tempfile.TemporaryDirectory() as td:
    p = mlflow.artifacts.download_artifacts(mv.source, dst_path=td)
    print(f"\n--- download_artifacts(mv.source={mv.source!r}) -> {p} ---")
    dump_tree(p)

with tempfile.TemporaryDirectory() as td:
    uri = f"models:/{MODEL}/{mv.version}"
    p = mlflow.artifacts.download_artifacts(uri, dst_path=td)
    print(f"\n--- download_artifacts({uri!r}) -> {p} ---")
    dump_tree(p)
