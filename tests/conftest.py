from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Force config defaults that don't depend on real .pt files for unit tests
os.environ.setdefault("MOBILE_MODEL_PATH", str(ROOT / "models" / "mobile_best.pt"))
os.environ.setdefault("WEB_MODEL_PATH", str(ROOT / "models" / "web_best.pt"))
os.environ.setdefault("CUSTOMER_HISTORY_PATH", str(ROOT / "models" / "customer_features.parquet"))

# Hermetic defaults: never write to the user's real ~/fraud during tests.
_FRAUD_TEST_ROOT = Path(tempfile.gettempdir()) / "antifraud-pytest-fraud-root"
_FRAUD_TEST_ROOT.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("FRAUD_ROOT", str(_FRAUD_TEST_ROOT))
# Disable async event_sink by default so unit tests don't spawn background tasks
# they aren't asserting on. Individual sink tests instantiate EventSink directly.
os.environ.setdefault("EVENT_SINK_ENABLED", "false")
os.environ.setdefault("FRAUD_BACKEND_RELOAD_TOKEN", "test-admin-token")


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
