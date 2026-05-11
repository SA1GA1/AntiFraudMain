from __future__ import annotations

from pathlib import Path

import pytest

from app.config import Settings


def _models_available(settings: Settings) -> bool:
    return settings.mobile_model_path.exists() and settings.web_model_path.exists()


@pytest.fixture(scope="module")
def settings() -> Settings:
    return Settings()


@pytest.fixture(scope="module")
def loader(settings: Settings):
    if not _models_available(settings):
        pytest.skip(
            "ML checkpoints not present in ./models — run `python scripts/copy_models.py` first."
        )
    from app.ml.loader import LocalFileLoader

    return LocalFileLoader(
        mobile_path=settings.mobile_model_path,
        web_path=settings.web_model_path,
    )


def test_loader_loads_mobile_model(loader):
    bundle = loader.load_mobile()
    assert bundle.model is not None
    assert bundle.preprocessor is not None
    assert hasattr(bundle.model, "forward")
    assert bundle.cat_vocab_sizes
    assert bundle.n_numeric > 0


def test_loader_loads_web_model(loader):
    bundle = loader.load_web()
    assert bundle.model is not None
    assert bundle.preprocessor is not None
    assert hasattr(bundle.model, "forward")
    assert bundle.cat_vocab_sizes
    assert bundle.n_numeric > 0


def test_loader_caches_models(loader):
    a = loader.load_mobile()
    b = loader.load_mobile()
    assert a is b


def test_inference_returns_probability(loader):
    import json

    sample_path = Path("/Users/aleksandr/Documents/AntiFraud/AntiFraudMLMobile/test1.json")
    if not sample_path.exists():
        pytest.skip("Mobile sample test1.json not found")
    payload = json.loads(sample_path.read_text(encoding="utf-8"))
    event = payload["events"][0]
    event = {k: v for k, v in event.items() if not k.startswith("_")}

    bundle = loader.load_mobile()
    prob = bundle.predict_proba(event)
    assert 0.0 <= prob <= 1.0


def test_customer_history_lookup(settings: Settings):
    if not settings.customer_history_path.exists():
        pytest.skip("customer_features.parquet not present")
    from app.ml.customer_history import CustomerHistory

    hist = CustomerHistory.load(settings.customer_history_path)
    df = hist.dataframe
    assert "customer_id" in df.columns
    assert len(df) > 0
