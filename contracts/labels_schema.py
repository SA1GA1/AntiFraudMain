"""Pandera schema for label parquets written to ~/fraud/labels{,_mobile}/.

Strict contract — used to reject malformed POST /admin/labels-batch payloads
(todo.md #4d). Same schema is consumed by trainer/extract.py on the ML side.

Columns:
- customer_id, event_id — join keys against events
- target — 0 (legit) or 1 (fraud)
- label_dttm — ISO timestamp when label was assigned
- source — origin tag, see LABEL_SOURCES
"""

from __future__ import annotations

import pandera.pandas as pa
from pandera.pandas import Check, Column, DataFrameSchema

LABEL_SOURCES: tuple[str, ...] = ("manual", "chargeback", "fraud_team", "complaint")


LABELS_SCHEMA: DataFrameSchema = DataFrameSchema(
    {
        "customer_id": Column(object, nullable=False, required=True, coerce=True),
        "event_id": Column(object, nullable=False, required=True, coerce=True),
        "target": Column(int, Check.isin([0, 1]), nullable=False, required=True, coerce=True),
        "label_dttm": Column(str, nullable=False, required=True, coerce=True),
        "source": Column(str, Check.isin(list(LABEL_SOURCES)), nullable=False, required=True, coerce=True),
    },
    strict=True,
    coerce=True,
)
