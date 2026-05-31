"""Pure compliance scoring math.

These functions are deliberately free of any database, ORM, or framework
dependency so they can be unit-tested in isolation and reused by the service
layer, the reporting layer, and tests alike.

Scoring model
-------------
Each rule has a :class:`~app.models.enums.Severity` whose ``weight`` reflects
how much a failure matters (low=1, medium=2, high=5, critical=10). A rule
applied to an asset yields one of three statuses:

* ``pass``            — the control holds; the rule's weight counts toward both
                        the earned and the applicable totals.
* ``fail``            — the control is violated; the weight counts toward the
                        applicable total only.
* ``not_applicable``  — the rule cannot be assessed for this asset (e.g. a
                        required attribute is missing). It is EXCLUDED from the
                        math entirely; it neither helps nor hurts the score.

Asset score (0..100):

    asset_score = 100 * (sum of weights of PASSED applicable rules)
                       / (sum of weights of PASSED+FAILED applicable rules)

When no rule is applicable to an asset, the score is defined as ``100.0`` — we
have no evidence of a violation, so the asset is treated as compliant rather
than penalised for missing data.

Organisation rollup is the unweighted mean of per-asset scores (each asset
counts equally regardless of how many rules applied to it), and ``100.0`` when
there are no assets.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from app.models.enums import ComplianceStatus, Severity

# A score of 100 represents perfect / not-assessable-but-clean compliance.
PERFECT_SCORE = 100.0


def _is_applicable(status: ComplianceStatus) -> bool:
    """True when a result counts toward the applicable-weight denominator."""
    return status in (ComplianceStatus.passed, ComplianceStatus.failed)


def asset_score(evals: Iterable[tuple[Severity, ComplianceStatus]]) -> float:
    """Weighted compliance score for a single asset, on a 0..100 scale.

    ``evals`` is an iterable of ``(severity, status)`` pairs — one per rule
    evaluated against the asset. ``not_applicable`` results are excluded from
    both numerator and denominator. Returns :data:`PERFECT_SCORE` when no rule
    is applicable (no evidence of a violation).

    Formula::

        100 * Σ weight(passed applicable) / Σ weight(passed+failed applicable)
    """
    earned = 0
    applicable = 0
    for severity, status in evals:
        if not _is_applicable(status):
            continue
        weight = severity.weight
        applicable += weight
        if status is ComplianceStatus.passed:
            earned += weight
    if applicable == 0:
        return PERFECT_SCORE
    return 100.0 * earned / applicable


def org_rollup(asset_scores: list[float]) -> float:
    """Organisation-wide score: the unweighted mean of per-asset scores.

    Every asset contributes equally so a single noisy host cannot dominate a
    fleet. Returns :data:`PERFECT_SCORE` for an empty fleet.
    """
    if not asset_scores:
        return PERFECT_SCORE
    return sum(asset_scores) / len(asset_scores)


def severity_failing_counts(
    evals_by_severity: Iterable[tuple[Severity, ComplianceStatus]],
) -> dict[str, int]:
    """Count FAILING evaluations grouped by severity.

    Returns a dict keyed by severity value (``"low"``..``"critical"``) with a
    stable, fully-populated shape — every severity is present, defaulting to 0 —
    so downstream consumers (drift series, dashboards) never have to guess at
    missing keys. Only ``fail`` results are counted; ``pass`` and
    ``not_applicable`` are ignored.
    """
    counts: dict[str, int] = {severity.value: 0 for severity in Severity}
    for severity, status in evals_by_severity:
        if status is ComplianceStatus.failed:
            counts[severity.value] += 1
    return counts


def aggregate_status_counts(
    statuses: Iterable[ComplianceStatus],
) -> Mapping[str, int]:
    """Tally pass/fail/not_applicable across a flat stream of statuses."""
    counts = {
        ComplianceStatus.passed.value: 0,
        ComplianceStatus.failed.value: 0,
        ComplianceStatus.not_applicable.value: 0,
    }
    for status in statuses:
        counts[status.value] += 1
    return counts
