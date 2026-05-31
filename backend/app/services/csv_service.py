"""CSV import/export for assets using only the stdlib ``csv`` module.

Export is a flat projection (the typed ``attributes``/``custom_fields`` JSON blobs
are not flattened — round-tripping those belongs to the JSON API). Import validates
each row through ``AssetCreate`` and audits every successful create; bad rows are
collected and reported rather than aborting the whole batch.
"""

from __future__ import annotations

import csv
import io
import uuid

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.enums import AssetType, Environment, LifecycleState
from app.schemas.asset import AssetCreate
from app.services.asset_service import create_asset

# Columns emitted on export and accepted on import (order is the export header).
_EXPORT_FIELDS = [
    "short_code",
    "name",
    "asset_type",
    "environment",
    "lifecycle_state",
    "location",
    "description",
]
# Columns a user may supply to create an asset (short_code is server-assigned).
_IMPORT_FIELDS = [
    "name",
    "asset_type",
    "environment",
    "lifecycle_state",
    "location",
    "description",
]


def export_assets_csv(db: Session) -> str:
    """Serialise every asset to a CSV document string."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=_EXPORT_FIELDS, extrasaction="ignore")
    writer.writeheader()
    for asset in db.execute(select(Asset).order_by(Asset.created_at)).scalars():
        writer.writerow(
            {
                "short_code": asset.short_code,
                "name": asset.name,
                "asset_type": asset.asset_type.value,
                "environment": asset.environment.value,
                "lifecycle_state": asset.lifecycle_state.value,
                "location": asset.location or "",
                "description": asset.description or "",
            }
        )
    return buffer.getvalue()


def _build_create(row: dict[str, str]) -> AssetCreate:
    """Map a CSV row to an ``AssetCreate``; raises ``ValueError``/``ValidationError``."""
    name = (row.get("name") or "").strip()
    raw_type = (row.get("asset_type") or "").strip()
    if not raw_type:
        raise ValueError("asset_type is required")

    payload: dict[str, object] = {
        "name": name,
        "asset_type": AssetType(raw_type),
    }
    if env := (row.get("environment") or "").strip():
        payload["environment"] = Environment(env)
    if state := (row.get("lifecycle_state") or "").strip():
        payload["lifecycle_state"] = LifecycleState(state)
    if location := (row.get("location") or "").strip():
        payload["location"] = location
    if description := (row.get("description") or "").strip():
        payload["description"] = description
    return AssetCreate.model_validate(payload)


def import_assets_csv(
    db: Session,
    text: str,
    actor_id: uuid.UUID | None = None,
    *,
    source_ip: str | None = None,
) -> dict[str, object]:
    """Create assets from CSV text. Returns ``{created, errors}``.

    ``errors`` is a list of ``{row, error}`` so partial success is observable. The
    caller commits once after a successful batch.
    """
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        return {"created": 0, "errors": [{"row": 0, "error": "Empty or headerless CSV."}]}

    created = 0
    errors: list[dict[str, object]] = []
    # Row 1 is the header, so data rows start at line 2.
    for line_no, row in enumerate(reader, start=2):
        try:
            payload = _build_create(row)
        except (ValueError, ValidationError) as exc:
            errors.append({"row": line_no, "error": str(exc)})
            continue
        create_asset(db, payload, actor_id=actor_id, source_ip=source_ip)
        created += 1

    return {"created": created, "errors": errors}
