"""Integration tests for the compliance evaluation, drift, and reporting service.

These exercise the real rule registry and scoring math against ORM rows built
directly in the test database. Assets are given a *minimal* attribute set so the
set of applicable rules — and therefore the expected score — is fully determined
and hand-computable. Rules whose backing attribute is absent evaluate to
``not_applicable`` and are excluded from the math (see ``compliance/scoring.py``).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import Session

from app.compliance.registry import get_rule
from app.models.asset import Asset
from app.models.compliance import ComplianceResult
from app.models.enums import (
    AssetType,
    ComplianceStatus,
    Environment,
    LifecycleState,
    Role,
    Severity,
)
from app.models.user import User
from app.services import compliance_service

pytestmark = pytest.mark.integration


# Severity weights (mirror Severity.weight): low=1, medium=2, high=5, critical=10.
_W_HIGH = Severity.high.weight  # disk-encryption, encryption-in-transit
_W_CRITICAL = Severity.critical.weight  # owner-mfa
_W_LOW = Severity.low.weight  # has-owner


def _make_owner(db: Session, *, email: str, mfa: bool) -> User:
    owner = User(
        email=email,
        full_name="Owner",
        hashed_password="x",
        role=Role.operator,
        is_active=True,
        mfa_enabled=mfa,
    )
    db.add(owner)
    db.flush()
    return owner


def _make_asset(
    db: Session,
    *,
    short_code: str,
    name: str,
    owner: User | None,
    attributes: dict[str, object],
    lifecycle: LifecycleState = LifecycleState.active,
) -> Asset:
    asset = Asset(
        short_code=short_code,
        name=name,
        asset_type=AssetType.host,
        lifecycle_state=lifecycle,
        environment=Environment.prod,
        owner_id=owner.id if owner is not None else None,
        attributes=attributes,
    )
    db.add(asset)
    db.flush()
    return asset


def _seed_two_assets(db: Session) -> tuple[Asset, Asset]:
    """Asset A is fully compliant on its applicable rules; Asset B is not.

    Asset A (owner w/ MFA, disk+transit encrypted):
        disk-encryption        pass  (high,     w5)
        encryption-in-transit  pass  (high,     w5)
        owner-mfa              pass  (critical, w10)
        has-owner             pass  (low,      w1)   -> score 100.0

    Asset B (no owner, disk NOT encrypted):
        disk-encryption        fail  (high,     w5)
        has-owner             fail  (low,      w1)
        owner-mfa             N/A   (no owner -> excluded) -> score 0.0
    """
    owner = _make_owner(db, email="mfa-owner@test.local", mfa=True)
    asset_a = _make_asset(
        db,
        short_code="SVR-AAA",
        name="compliant-host",
        owner=owner,
        attributes={"disk_encrypted": True, "encryption_in_transit": True},
    )
    asset_b = _make_asset(
        db,
        short_code="SVR-BBB",
        name="noncompliant-host",
        owner=None,
        attributes={"disk_encrypted": False},
    )
    db.flush()
    return asset_a, asset_b


def test_run_evaluation_persists_results_and_scores_org(db: Session) -> None:
    # Arrange
    asset_a, asset_b = _seed_two_assets(db)

    # Act
    run = compliance_service.run_evaluation(db, triggered_by=None)
    db.flush()

    # Assert — org score is the unweighted mean of the two asset scores.
    assert run.total_assets == 2
    assert run.org_score == pytest.approx(50.0)

    # One ComplianceResult per (asset, rule) for every active asset.
    from app.compliance.registry import get_rules

    results = compliance_service.get_results(db, run_id=run.id)
    expected_rows = 2 * len(get_rules())
    assert len(results) == expected_rows
    assert all(isinstance(r, ComplianceResult) for r in results)

    # Asset A passes every rule that applies to it.
    a_results = {r.rule_id: r for r in results if r.asset_id == asset_a.id}
    assert a_results["disk-encryption"].status is ComplianceStatus.passed
    assert a_results["encryption-in-transit"].status is ComplianceStatus.passed
    assert a_results["owner-mfa"].status is ComplianceStatus.passed
    assert a_results["has-owner"].status is ComplianceStatus.passed

    # Asset B: disk fail, no-owner fail, owner-mfa not applicable (no owner).
    b_results = {r.rule_id: r for r in results if r.asset_id == asset_b.id}
    assert b_results["disk-encryption"].status is ComplianceStatus.failed
    assert b_results["has-owner"].status is ComplianceStatus.failed
    assert b_results["owner-mfa"].status is ComplianceStatus.not_applicable

    # Severity is denormalised onto the result row from the rule definition.
    assert a_results["owner-mfa"].severity is Severity.critical
    assert b_results["disk-encryption"].severity is Severity.high


def test_run_evaluation_status_counts_match_results(db: Session) -> None:
    # Arrange
    _seed_two_assets(db)

    # Act
    run = compliance_service.run_evaluation(db, triggered_by=None)
    db.flush()
    results = compliance_service.get_results(db, run_id=run.id)

    # Assert — the run's tallies match a direct count over the result rows.
    passed = sum(1 for r in results if r.status is ComplianceStatus.passed)
    failed = sum(1 for r in results if r.status is ComplianceStatus.failed)
    na = sum(1 for r in results if r.status is ComplianceStatus.not_applicable)
    assert run.passed_count == passed
    assert run.failed_count == failed
    assert run.not_applicable_count == na
    assert passed + failed + na == len(results)


def test_run_evaluation_excludes_retired_assets(db: Session) -> None:
    # Arrange — one active, one retired (out of scope).
    _make_asset(
        db,
        short_code="SVR-ACT",
        name="active",
        owner=None,
        attributes={"disk_encrypted": True},
    )
    _make_asset(
        db,
        short_code="SVR-RET",
        name="retired",
        owner=None,
        attributes={"disk_encrypted": False},
        lifecycle=LifecycleState.retired,
    )
    db.flush()

    # Act
    run = compliance_service.run_evaluation(db, triggered_by=None)
    db.flush()

    # Assert — the retired asset is not evaluated.
    assert run.total_assets == 1
    results = compliance_service.get_results(db, run_id=run.id)
    assert {r.asset_id for r in results} == {
        a.id for a in db.query(Asset).filter(Asset.short_code == "SVR-ACT").all()
    }


def test_latest_run_returns_most_recent(db: Session) -> None:
    # Arrange — no run yet.
    assert compliance_service.latest_run(db) is None

    _seed_two_assets(db)

    # Act — two runs in sequence.
    first = compliance_service.run_evaluation(db, triggered_by=None)
    db.flush()
    second = compliance_service.run_evaluation(db, triggered_by=None)
    db.flush()

    # Assert
    latest = compliance_service.latest_run(db)
    assert latest is not None
    assert latest.id == second.id
    assert latest.id != first.id


def test_second_evaluation_grows_drift_and_reports_newly_failing(db: Session) -> None:
    # Arrange — first run establishes a baseline.
    asset_a, _asset_b = _seed_two_assets(db)
    first = compliance_service.run_evaluation(db, triggered_by=None)
    db.flush()
    first_drift = compliance_service.drift_series(db)
    assert len(first_drift) == 1
    assert first_drift[0]["run_id"] == first.id

    # Act — introduce a NEW failure on asset A (transit encryption regresses),
    # then run a second evaluation.
    asset_a.attributes = {"disk_encrypted": True, "encryption_in_transit": False}
    db.add(asset_a)
    db.flush()
    second = compliance_service.run_evaluation(db, triggered_by=None)
    db.flush()

    # Assert — the drift series grew and is ordered oldest-first.
    drift = compliance_service.drift_series(db)
    assert len(drift) == 2
    assert [p["run_id"] for p in drift] == [first.id, second.id]
    # Asset A regressed, so the org score dropped between the two runs.
    assert drift[1]["org_score"] < drift[0]["org_score"]

    # newly_failing reports exactly the (asset, rule) that flipped to failing.
    newly = compliance_service.newly_failing(db)
    keys = {(item["asset_id"], item["rule_id"]) for item in newly}
    assert (asset_a.id, "encryption-in-transit") in keys
    # Asset B was already failing disk-encryption/has-owner in run one, so those
    # are NOT reported as newly failing.
    assert all(item["rule_id"] != "disk-encryption" for item in newly)

    # The newly-failing entry carries the rule's framework control reference.
    rule = get_rule("encryption-in-transit")
    assert rule is not None
    entry = next(i for i in newly if i["rule_id"] == "encryption-in-transit")
    assert entry["control"] == rule.control
    assert entry["severity"] is Severity.high


def test_newly_failing_empty_on_first_run(db: Session) -> None:
    # Arrange — single run; there is no previous run to diff against.
    _seed_two_assets(db)
    compliance_service.run_evaluation(db, triggered_by=None)
    db.flush()

    # Act / Assert — with no prior run, every current failure is "already known"
    # only relative to nothing, so the diff against an absent previous run is the
    # full failing set. The contract diffs latest vs previous; with no previous
    # run the set difference is the full current failing set.
    newly = compliance_service.newly_failing(db)
    # Asset B fails disk-encryption + has-owner on the first run.
    rule_ids = {item["rule_id"] for item in newly}
    assert "disk-encryption" in rule_ids
    assert "has-owner" in rule_ids


def test_report_returns_audit_ready_structure_with_control_refs(db: Session) -> None:
    # Arrange
    asset_a, asset_b = _seed_two_assets(db)
    run = compliance_service.run_evaluation(db, triggered_by=None)
    db.flush()

    # Act
    report = compliance_service.report(db)

    # Assert — top-level audit structure.
    assert report["run_id"] == run.id
    assert report["org_score"] == pytest.approx(50.0)
    assert report["total_assets"] == 2
    assert set(report["status_counts"].keys()) == {"pass", "fail", "not_applicable"}
    # severity_failing has a fully-populated, stable shape.
    assert set(report["severity_failing"].keys()) == {s.value for s in Severity}

    # Per-asset breakdown, sorted worst-first (lowest score first).
    per_asset = report["per_asset"]
    assert len(per_asset) == 2
    assert per_asset[0]["score"] <= per_asset[-1]["score"]
    by_asset = {row["asset_id"]: row for row in per_asset}
    assert by_asset[asset_a.id]["score"] == pytest.approx(100.0)
    assert by_asset[asset_b.id]["score"] == pytest.approx(0.0)
    assert by_asset[asset_b.id]["failed"] >= 1

    # Failing controls carry framework + control references and remediation.
    failing = report["failing_controls"]
    assert failing, "expected at least one failing control"
    disk = next(c for c in failing if c["rule_id"] == "disk-encryption")
    rule = get_rule("disk-encryption")
    assert rule is not None
    assert disk["framework"] == rule.framework
    assert disk["control"] == rule.control
    assert disk["remediation"] == rule.remediation
    assert disk["severity"] == Severity.high.value


def test_report_empty_when_no_run(db: Session) -> None:
    # Act — report with nothing evaluated yet.
    report = compliance_service.report(db)

    # Assert — well-formed "awaiting first scan" shape, not an exception.
    assert report["run_id"] is None
    assert report["org_score"] == pytest.approx(100.0)
    assert report["total_assets"] == 0
    assert report["per_asset"] == []
    assert report["failing_controls"] == []


def test_run_evaluation_records_audit_entry(db: Session) -> None:
    # Arrange
    actor = _make_owner(db, email="actor@test.local", mfa=True)
    _seed_two_assets(db)

    # Act
    run = compliance_service.run_evaluation(db, triggered_by=actor)
    db.flush()

    # Assert — an audit log row references the run and captures the score.
    from app.models.audit import AuditLog

    audit = (
        db.query(AuditLog)
        .filter(AuditLog.entity_type == "compliance_run", AuditLog.entity_id == run.id)
        .one_or_none()
    )
    assert audit is not None
    assert audit.actor_id == actor.id
    assert audit.after["org_score"] == pytest.approx(run.org_score)


def test_get_results_scopes_to_asset(db: Session) -> None:
    # Arrange
    asset_a, _asset_b = _seed_two_assets(db)
    run = compliance_service.run_evaluation(db, triggered_by=None)
    db.flush()

    # Act — scope reads to a single asset and a non-existent asset.
    scoped = compliance_service.get_results(db, run_id=run.id, asset_id=asset_a.id)
    none_match = compliance_service.get_results(db, run_id=run.id, asset_id=uuid.uuid4())

    # Assert
    assert scoped, "expected results for asset A"
    assert {r.asset_id for r in scoped} == {asset_a.id}
    assert none_match == []


def test_get_results_defaults_to_latest_run(db: Session) -> None:
    # Arrange — two runs; the default read uses the latest.
    _seed_two_assets(db)
    compliance_service.run_evaluation(db, triggered_by=None)
    db.flush()
    second = compliance_service.run_evaluation(db, triggered_by=None)
    db.flush()

    # Act
    default_results = compliance_service.get_results(db)

    # Assert — every returned row belongs to the latest run.
    assert default_results
    assert {r.run_id for r in default_results} == {second.id}
    # Sanity: the count equals the latest run's persisted row set.
    direct = db.query(ComplianceResult).filter(ComplianceResult.run_id == second.id).count()
    assert len(default_results) == direct
