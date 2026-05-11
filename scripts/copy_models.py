"""Копирует обученные ML-модели и (если есть) parquet с историей в models/.

Источники по умолчанию:
  ../AntiFraudMLMobile/trainer/checkpoints/best.pt → models/mobile_best.pt
  ../AntiFraudMLWeb/trainer/checkpoints/best.pt    → models/web_best.pt
  ../AntiFraudMLMobile/data_augmented/customer_features.parquet → models/customer_features.parquet
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "models"
TARGET.mkdir(exist_ok=True)

PAIRS = [
    (
        Path("../AntiFraudMLMobile/trainer/checkpoints/best.pt"),
        TARGET / "mobile_best.pt",
    ),
    (
        Path("../AntiFraudMLWeb/trainer/checkpoints/best.pt"),
        TARGET / "web_best.pt",
    ),
    (
        Path("../AntiFraudMLMobile/data_augmented/customer_features.parquet"),
        TARGET / "customer_features.parquet",
    ),
]


def main() -> int:
    missing = []
    copied = []
    for src, dst in PAIRS:
        src_abs = (ROOT / src).resolve()
        if not src_abs.exists():
            missing.append(src_abs)
            continue
        shutil.copy2(src_abs, dst)
        copied.append((src_abs, dst))
        print(f"  ✓ {src_abs} → {dst}")

    if missing:
        print("\nNot found (these are optional):")
        for p in missing:
            print(f"  • {p}")

    if not copied:
        print("\nNothing was copied.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
