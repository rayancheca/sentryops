"""Pure-logic unit tests for compliance scoring math.

These tests never touch the database; they feed ``(Severity, ComplianceStatus)``
pairs and plain float lists straight into the scoring functions and assert on the
exact numbers the documented formula produces.

Scoring contract (from ``app/compliance/scoring.py``)::

    asset_score = 100 * Σ weight(passed applicable) / Σ weight(passed+failed applicable)

``not_applicable`` results are excluded from BOTH numerator and denominator, and
an asset with no applicable rules scores ``100.0``. The org rollup is the
unweighted mean of per-asset scores (``100.0`` when empty). Severity weights are
low=1, medium=2, high=5, critical=10.
"""

from __future__ import annotations

import pytest

from app.compliance.scoring import (
    PERFECT_SCORE,
    asset_score,
    org_rollup,
    severity_failing_counts,
)
from app.models.enums import ComplianceStatus, Severity

PASS = ComplianceStatus.passed
FAIL = ComplianceStatus.failed
NA = ComplianceStatus.not_applicable


# ---------------------------------------------------------------------------
# asset_score
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_asset_score_all_pass_is_100() -> None:
    # Arrange — every applicable rule, across severities, holds.
    evals = [
        (Severity.low, PASS),
        (Severity.medium, PASS),
        (Severity.high, PASS),
        (Severity.critical, PASS),
    ]

    # Act
    score = asset_score(evals)

    # Assert
    assert score == 100.0


@pytest.mark.unit
def test_asset_score_all_fail_is_0() -> None:
    # Arrange
    evals = [
        (Severity.low, FAIL),
        (Severity.high, FAIL),
        (Severity.critical, FAIL),
    ]

    # Act
    score = asset_score(evals)

    # Assert
    assert score == 0.0


@pytest.mark.unit
def test_asset_score_no_applicable_rules_is_perfect_score() -> None:
    # Arrange — only not_applicable results means no evidence of a violation.
    evals = [
        (Severity.critical, NA),
        (Severity.high, NA),
    ]

    # Act
    score = asset_score(evals)

    # Assert
    assert score == PERFECT_SCORE
    assert score == 100.0


@pytest.mark.unit
def test_asset_score_empty_iterable_is_perfect_score() -> None:
    # Arrange / Act
    score = asset_score([])

    # Assert
    assert score == PERFECT_SCORE


@pytest.mark.unit
def test_asset_score_not_applicable_excluded_from_numerator_and_denominator() -> None:
    # Arrange — a critical NA must NOT drag the score down; with one passing
    # low rule applicable, the score is a perfect 100 despite the failed-looking
    # critical being marked not_applicable.
    with_na = [
        (Severity.low, PASS),
        (Severity.critical, NA),
    ]
    without_na = [
        (Severity.low, PASS),
    ]

    # Act
    score_with_na = asset_score(with_na)
    score_without_na = asset_score(without_na)

    # Assert — the NA result is invisible to the math.
    assert score_with_na == score_without_na == 100.0


@pytest.mark.unit
def test_asset_score_mixed_worked_example_hand_computed() -> None:
    # Arrange — weights: low=1, medium=2, high=5, critical=10.
    #   PASS:  low(1) + high(5)            -> earned = 6
    #   FAIL:  medium(2) + critical(10)    -> not earned
    #   NA:    critical(10)                -> excluded entirely
    # applicable = 1 + 5 + 2 + 10 = 18; earned = 6
    # expected = 100 * 6 / 18 = 33.3333...
    evals = [
        (Severity.low, PASS),
        (Severity.high, PASS),
        (Severity.medium, FAIL),
        (Severity.critical, FAIL),
        (Severity.critical, NA),
    ]
    expected = 100.0 * 6 / 18

    # Act
    score = asset_score(evals)

    # Assert
    assert score == pytest.approx(expected)
    assert score == pytest.approx(33.33333, rel=1e-4)


@pytest.mark.unit
def test_asset_score_weighting_favours_high_severity_passes() -> None:
    # Arrange — passing the critical rule but failing a low one should score
    # far above 50 because the critical weight (10) dominates the low (1).
    evals = [
        (Severity.critical, PASS),
        (Severity.low, FAIL),
    ]
    # earned = 10, applicable = 11 -> 100 * 10/11 ~= 90.9
    expected = 100.0 * 10 / 11

    # Act
    score = asset_score(evals)

    # Assert
    assert score == pytest.approx(expected)
    assert score > 90.0


@pytest.mark.unit
def test_asset_score_accepts_generator_input() -> None:
    # Arrange — the iterable contract should not require a materialised list.
    evals = ((sev, PASS) for sev in (Severity.low, Severity.high))

    # Act
    score = asset_score(evals)

    # Assert
    assert score == 100.0


# ---------------------------------------------------------------------------
# org_rollup
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_org_rollup_empty_fleet_is_perfect_score() -> None:
    # Arrange / Act
    rollup = org_rollup([])

    # Assert
    assert rollup == PERFECT_SCORE
    assert rollup == 100.0


@pytest.mark.unit
def test_org_rollup_is_unweighted_mean() -> None:
    # Arrange
    scores = [100.0, 50.0, 0.0]
    expected = (100.0 + 50.0 + 0.0) / 3

    # Act
    rollup = org_rollup(scores)

    # Assert
    assert rollup == pytest.approx(expected)
    assert rollup == pytest.approx(50.0)


@pytest.mark.unit
def test_org_rollup_each_asset_counts_equally() -> None:
    # Arrange — a single noisy host (0) cannot dominate a large clean fleet
    # any more than one asset's worth of weight.
    scores = [100.0] * 9 + [0.0]
    expected = 900.0 / 10

    # Act
    rollup = org_rollup(scores)

    # Assert
    assert rollup == pytest.approx(expected)
    assert rollup == pytest.approx(90.0)


@pytest.mark.unit
def test_org_rollup_single_asset_returns_that_score() -> None:
    # Arrange / Act
    rollup = org_rollup([42.5])

    # Assert
    assert rollup == pytest.approx(42.5)


# ---------------------------------------------------------------------------
# severity_failing_counts
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_severity_failing_counts_shape_is_fully_populated() -> None:
    # Arrange / Act — even with no input, every severity key is present at 0.
    counts = severity_failing_counts([])

    # Assert
    assert counts == {"low": 0, "medium": 0, "high": 0, "critical": 0}
    assert set(counts) == {member.value for member in Severity}


@pytest.mark.unit
def test_severity_failing_counts_tallies_only_failures() -> None:
    # Arrange — pass and not_applicable must be ignored; only fails counted.
    evals = [
        (Severity.low, FAIL),
        (Severity.low, FAIL),
        (Severity.high, FAIL),
        (Severity.high, PASS),  # ignored
        (Severity.critical, NA),  # ignored
        (Severity.medium, PASS),  # ignored
    ]

    # Act
    counts = severity_failing_counts(evals)

    # Assert
    assert counts == {"low": 2, "medium": 0, "high": 1, "critical": 0}


@pytest.mark.unit
def test_severity_failing_counts_counts_every_severity() -> None:
    # Arrange — one failure per severity.
    evals = [
        (Severity.low, FAIL),
        (Severity.medium, FAIL),
        (Severity.high, FAIL),
        (Severity.critical, FAIL),
    ]

    # Act
    counts = severity_failing_counts(evals)

    # Assert
    assert counts == {"low": 1, "medium": 1, "high": 1, "critical": 1}


@pytest.mark.unit
def test_severity_failing_counts_ignores_passes_and_na_entirely() -> None:
    # Arrange — no failures at all should yield an all-zero, full-shaped map.
    evals = [
        (Severity.critical, PASS),
        (Severity.critical, NA),
        (Severity.low, PASS),
    ]

    # Act
    counts = severity_failing_counts(evals)

    # Assert
    assert counts == {"low": 0, "medium": 0, "high": 0, "critical": 0}
