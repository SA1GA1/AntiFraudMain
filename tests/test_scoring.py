from __future__ import annotations

import pytest

from app.core.scoring import combine_rules_and_ml, decision_from_score, score_from_weights


def test_score_from_weights_clamps_to_ten():
    assert score_from_weights(20.0) == 10.0


def test_score_from_weights_zero_for_no_triggers():
    assert score_from_weights(0.0) == 0.0


def test_score_from_weights_doubles_weight_to_score():
    # rule weights sum 2.0 → score 4.0 (so single critical rule pushes user to "review/sms")
    assert score_from_weights(2.0) == 4.0


def test_decision_safe_for_low_score():
    assert decision_from_score(2.0) == "safe"


def test_decision_review_for_mid_score():
    assert decision_from_score(4.5) == "review"


def test_decision_sms_for_high_score():
    assert decision_from_score(6.5) == "sms"


def test_decision_biometry_for_critical_score():
    assert decision_from_score(9.0) == "biometry"


def test_combine_rules_only_when_threshold_exceeded():
    # rules trigger above threshold → ML is skipped
    score, used = combine_rules_and_ml(
        rules_weight=3.0, threshold=2.0, ml_probability=None
    )
    assert score == pytest.approx(6.0)
    assert used is False


def test_combine_uses_ml_when_rules_clean():
    score, used = combine_rules_and_ml(
        rules_weight=0.5, threshold=2.0, ml_probability=0.7
    )
    assert score == pytest.approx(7.0)
    assert used is True


def test_combine_takes_max_when_both_present_below_threshold():
    score, used = combine_rules_and_ml(
        rules_weight=1.0, threshold=2.0, ml_probability=0.3
    )
    # rules→2.0, ml→3.0; final = max
    assert score == pytest.approx(3.0)
    assert used is True
