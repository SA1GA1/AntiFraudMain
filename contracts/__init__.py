"""Schema contracts shared between backend and trainer repos.

These are deliberately permissive (`strict=False`, all columns nullable+optional)
to support the best-effort bootstrap path described in todo.md #6. The full
column lists are mirrored from trainer/preprocess.py in AntiFraudMLWeb / Mobile
and used by:

- `app.persistence.event_sink` — coverage logging (fraction of fields present).
- `app.api.admin` — strict validation of `/admin/labels-batch` payloads.
- `AntiFraudMLWeb` / `AntiFraudMLMobile` trainer/extract.py — copied via
  `scripts/sync_contracts.sh`.
"""

from contracts.event_schema_web import EVENT_FIELDS_WEB, EVENT_SCHEMA_WEB
from contracts.event_schema_mobile import EVENT_FIELDS_MOBILE, EVENT_SCHEMA_MOBILE
from contracts.labels_schema import LABEL_SOURCES, LABELS_SCHEMA

__all__ = [
    "EVENT_FIELDS_WEB",
    "EVENT_SCHEMA_WEB",
    "EVENT_FIELDS_MOBILE",
    "EVENT_SCHEMA_MOBILE",
    "LABEL_SOURCES",
    "LABELS_SCHEMA",
]
