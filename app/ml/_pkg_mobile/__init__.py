"""Pickle-compat пакет: классы из ../AntiFraudMLMobile/trainer/.

Регистрируется в sys.modules под именем `trainer` через app.ml.loader перед
`torch.load`. Импортируется как relative-пакет, чтобы preprocess.py мог делать
`from .aggregate import FEATURE_COLUMNS as AGG_FEATURE_COLUMNS`.
"""

from __future__ import annotations

from . import aggregate, model, preprocess  # noqa: F401  (re-export for sys.modules alias)
