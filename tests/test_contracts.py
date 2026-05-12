from __future__ import annotations

import pandas as pd
import pytest

from contracts import (
    EVENT_FIELDS_MOBILE,
    EVENT_FIELDS_WEB,
    EVENT_SCHEMA_MOBILE,
    EVENT_SCHEMA_WEB,
    LABEL_SOURCES,
    LABELS_SCHEMA,
)


def test_web_schema_validates_minimal_payload():
    df = pd.DataFrame(
        [{"customer_id": 1, "event_id": 2, "operaton_amt": 100.0, "is_vpn_detected": 0}]
    )
    out = EVENT_SCHEMA_WEB.validate(df)
    assert len(out) == 1


def test_web_schema_allows_extra_columns():
    df = pd.DataFrame(
        [{"customer_id": 1, "event_id": 2, "unknown_field": "anything"}]
    )
    out = EVENT_SCHEMA_WEB.validate(df)
    assert "unknown_field" in out.columns


def test_web_schema_rejects_missing_identity():
    df = pd.DataFrame([{"operaton_amt": 100.0}])
    with pytest.raises(Exception):
        EVENT_SCHEMA_WEB.validate(df)


def test_mobile_schema_validates_minimal_payload():
    df = pd.DataFrame(
        [
            {
                "customer_id": "1",
                "event_id": "2",
                "operaton_amt": 50.0,
                "is_rooted_jailbroken": 0,
            }
        ]
    )
    out = EVENT_SCHEMA_MOBILE.validate(df)
    assert len(out) == 1


def test_event_field_lists_nonempty_and_distinct():
    assert len(EVENT_FIELDS_WEB) > 50
    assert len(EVENT_FIELDS_MOBILE) > 50
    assert len(set(EVENT_FIELDS_WEB)) == len(EVENT_FIELDS_WEB)
    assert len(set(EVENT_FIELDS_MOBILE)) == len(EVENT_FIELDS_MOBILE)


def test_labels_schema_valid_row():
    df = pd.DataFrame(
        [
            {
                "customer_id": 1,
                "event_id": 2,
                "target": 1,
                "label_dttm": "2026-05-12T10:00:00Z",
                "source": "manual",
            }
        ]
    )
    out = LABELS_SCHEMA.validate(df)
    assert len(out) == 1


def test_labels_schema_rejects_bad_target():
    df = pd.DataFrame(
        [
            {
                "customer_id": 1,
                "event_id": 2,
                "target": 5,  # out of {0,1}
                "label_dttm": "2026-05-12T10:00:00Z",
                "source": "manual",
            }
        ]
    )
    with pytest.raises(Exception):
        LABELS_SCHEMA.validate(df)


def test_labels_schema_rejects_unknown_source():
    df = pd.DataFrame(
        [
            {
                "customer_id": 1,
                "event_id": 2,
                "target": 0,
                "label_dttm": "2026-05-12T10:00:00Z",
                "source": "telepathy",  # not in LABEL_SOURCES
            }
        ]
    )
    with pytest.raises(Exception):
        LABELS_SCHEMA.validate(df)


def test_label_sources_contains_expected():
    assert set(LABEL_SOURCES) >= {"manual", "chargeback", "fraud_team", "complaint"}
