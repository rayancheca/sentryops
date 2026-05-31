"""Behavioral tests for CSV import/export of assets (app/services/csv_service.py).

Covers the export -> import round-trip (assets recreated from their own export),
optional-field handling, and the partial-success contract: a malformed row is
reported in ``errors`` without aborting the rest of the batch.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.enums import AssetType, Environment, LifecycleState
from app.schemas.asset import AssetCreate
from app.services.asset_service import create_asset
from app.services.csv_service import export_assets_csv, import_assets_csv

pytestmark = pytest.mark.integration


def _asset_count(db: Session) -> int:
    return int(db.scalar(select(func.count()).select_from(Asset)) or 0)


def test_export_then_import_round_trip(db: Session) -> None:
    # Arrange — two assets created through the real service.
    create_asset(
        db,
        AssetCreate(
            name="web-01",
            asset_type=AssetType.host,
            environment=Environment.prod,
            lifecycle_state=LifecycleState.active,
            location="rack-7",
            description="frontend host",
        ),
    )
    create_asset(
        db,
        AssetCreate(
            name="payments-api",
            asset_type=AssetType.service,
            environment=Environment.staging,
        ),
    )
    db.flush()

    # Act — export, wipe, then re-import the same document.
    exported = export_assets_csv(db)
    db.execute(Asset.__table__.delete())
    db.flush()
    assert _asset_count(db) == 0

    result = import_assets_csv(db, exported)
    db.flush()

    # Assert — both assets recreated, no errors; fields survived the round-trip.
    assert result["created"] == 2
    assert result["errors"] == []
    assert _asset_count(db) == 2

    recreated = {a.name: a for a in db.scalars(select(Asset)).all()}
    assert recreated["web-01"].asset_type is AssetType.host
    assert recreated["web-01"].environment is Environment.prod
    assert recreated["web-01"].location == "rack-7"
    assert recreated["web-01"].description == "frontend host"
    assert recreated["payments-api"].asset_type is AssetType.service
    assert recreated["payments-api"].environment is Environment.staging


def test_import_assigns_fresh_short_codes(db: Session) -> None:
    # Arrange — a minimal valid CSV (short_code is server-assigned on import).
    csv_text = "name,asset_type,environment\ndb-primary,host,prod\n"

    # Act
    result = import_assets_csv(db, csv_text)
    db.flush()

    # Assert — created with a type-prefixed short code.
    assert result["created"] == 1
    asset = db.scalars(select(Asset).where(Asset.name == "db-primary")).one()
    assert asset.short_code.startswith("HST-")


def test_import_reports_malformed_row_without_aborting(db: Session) -> None:
    # Arrange — three rows: valid, bad enum value, valid.
    csv_text = (
        "name,asset_type,environment\n"
        "good-one,host,prod\n"
        "bad-one,not-a-real-type,prod\n"
        "good-two,service,dev\n"
    )

    # Act
    result = import_assets_csv(db, csv_text)
    db.flush()

    # Assert — the two valid rows landed; the bad row is reported by line number.
    assert result["created"] == 2
    assert len(result["errors"]) == 1
    error = result["errors"][0]
    assert error["row"] == 3  # header is line 1, so the bad data row is line 3.
    assert error["error"]
    names = {a.name for a in db.scalars(select(Asset)).all()}
    assert names == {"good-one", "good-two"}


def test_import_reports_missing_required_asset_type(db: Session) -> None:
    # Arrange — a row missing the required asset_type.
    csv_text = "name,asset_type,environment\nno-type,,prod\n"

    # Act
    result = import_assets_csv(db, csv_text)
    db.flush()

    # Assert — nothing created; the missing field is reported.
    assert result["created"] == 0
    assert len(result["errors"]) == 1
    assert "asset_type is required" in result["errors"][0]["error"]


def test_import_empty_document_reports_headerless_error(db: Session) -> None:
    # Act — an empty string has no header row.
    result = import_assets_csv(db, "")

    # Assert — a single error describing the empty/headerless document.
    assert result["created"] == 0
    assert len(result["errors"]) == 1
    assert result["errors"][0]["row"] == 0


def test_export_empty_state_emits_header_only(db: Session) -> None:
    # Act — no assets seeded.
    exported = export_assets_csv(db)

    # Assert — exactly the header line, no data rows.
    lines = exported.strip().splitlines()
    assert len(lines) == 1
    assert lines[0].startswith("short_code,name,asset_type")
