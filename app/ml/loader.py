"""ModelLoader: загружает FraudMLP-чекпоинты Mobile/Web с pickle-совместимостью.

Pickle хранит ссылки на классы как `trainer.preprocess.Preprocessor` (так пакет
назывался при обучении). Чтобы распаковать, перед `torch.load` мы регистрируем
наш локальный пакет (`app.ml._pkg_mobile` или `app.ml._pkg_web`) под именем
`trainer` в `sys.modules`. Уже распакованный объект сохраняет ссылку на класс
конкретного пакета — последующая смена alias на другой вариант не ломает его.

Интерфейс `ModelLoader` оставлен Protocol-ом, чтобы позже подключить
`MlflowLoader` без правок прикладного кода.
"""

from __future__ import annotations

import pickle
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Protocol

import numpy as np
import pandas as pd
import torch

_LOAD_LOCK = threading.Lock()


@dataclass
class ModelBundle:
    """Готовая к инференсу модель + препроцессор + меты."""

    model: torch.nn.Module
    preprocessor: Any  # Preprocessor (mobile или web; тип определяется пакетом)
    cat_vocab_sizes: list[int]
    n_numeric: int
    n_aggregate: int

    def predict_proba(
        self,
        event: dict,
        agg_df: Optional[pd.DataFrame] = None,
    ) -> float:
        """Прогноз на одно событие, возвращает P(fraud) ∈ [0, 1]."""
        df = pd.DataFrame([event])
        num, cat = self.preprocessor.transform_events(df)
        agg, has_hist = self.preprocessor.transform_aggregates(
            df["customer_id"].to_numpy(), agg_df
        )
        with torch.no_grad():
            logit = self.model(
                torch.from_numpy(num),
                torch.from_numpy(cat),
                torch.from_numpy(agg),
                torch.from_numpy(has_hist),
            )
        prob = torch.sigmoid(logit).item()
        return float(prob)


class ModelLoader(Protocol):
    def load_mobile(self) -> ModelBundle: ...
    def load_web(self) -> ModelBundle: ...


def _alias_trainer(pkg) -> None:
    """Регистрирует pkg и его подмодули под именем `trainer` в sys.modules."""
    sys.modules["trainer"] = pkg
    sys.modules["trainer.preprocess"] = pkg.preprocess
    sys.modules["trainer.aggregate"] = pkg.aggregate
    sys.modules["trainer.model"] = pkg.model


def _load_bundle(checkpoint_path: Path, pkg) -> ModelBundle:
    with _LOAD_LOCK:
        _alias_trainer(pkg)
        ck = torch.load(str(checkpoint_path), map_location="cpu", weights_only=False)
    preprocessor = pickle.loads(ck["preprocessor"])
    model = pkg.model.FraudMLP(
        cat_vocab_sizes=ck["cat_vocab_sizes"],
        n_numeric=ck["n_numeric"],
        n_aggregate=ck["n_aggregate"],
    )
    model.load_state_dict(ck["model_state"])
    model.eval()
    return ModelBundle(
        model=model,
        preprocessor=preprocessor,
        cat_vocab_sizes=list(ck["cat_vocab_sizes"]),
        n_numeric=int(ck["n_numeric"]),
        n_aggregate=int(ck["n_aggregate"]),
    )


class LocalFileLoader:
    """Грузит FraudMLP-чекпоинты с диска и кэширует в памяти."""

    def __init__(self, mobile_path: Path, web_path: Path) -> None:
        self.mobile_path = Path(mobile_path)
        self.web_path = Path(web_path)
        self._mobile: Optional[ModelBundle] = None
        self._web: Optional[ModelBundle] = None

    def load_mobile(self) -> ModelBundle:
        if self._mobile is None:
            from app.ml import _pkg_mobile

            self._mobile = _load_bundle(self.mobile_path, _pkg_mobile)
        return self._mobile

    def load_web(self) -> ModelBundle:
        if self._web is None:
            from app.ml import _pkg_web

            self._web = _load_bundle(self.web_path, _pkg_web)
        return self._web
