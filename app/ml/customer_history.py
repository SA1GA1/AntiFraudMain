"""In-memory lookup истории клиентов (parquet → pandas DataFrame).

Если parquet не сгенерирован, возвращает None — модели в этом случае получают
has_history=0 для всех клиентов (cold-start ветка, поддерживается обучением).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd
import pyarrow.parquet as pq


@dataclass
class CustomerHistory:
    dataframe: pd.DataFrame

    @classmethod
    def load(cls, path: Path) -> "CustomerHistory":
        df = pq.read_table(str(path)).to_pandas()
        return cls(dataframe=df)


def maybe_load(path: Path) -> Optional[CustomerHistory]:
    if not Path(path).exists():
        return None
    return CustomerHistory.load(Path(path))
