from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Force config defaults that don't depend on real .pt files for unit tests
os.environ.setdefault("MOBILE_MODEL_PATH", str(ROOT / "models" / "mobile_best.pt"))
os.environ.setdefault("WEB_MODEL_PATH", str(ROOT / "models" / "web_best.pt"))
os.environ.setdefault("CUSTOMER_HISTORY_PATH", str(ROOT / "models" / "customer_features.parquet"))


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
