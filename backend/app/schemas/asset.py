"""Asset (CMDB) schemas: typed security-posture attributes plus CRUD I/O shapes."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import AssetType, Environment, LifecycleState
from app.schemas.tag import TagRead


class AssetAttributes(BaseModel):
    """Typed security-posture facts evaluated by the compliance engine.

    Every field is optional: an asset may know some facts and not others, and a
    missing fact is treated as "unknown" rather than "false" by the rule engine.
    ``extra='allow'`` keeps forward-compatibility with attributes the engine does
    not yet model so nothing is silently dropped on round-trip.
    """

    model_config = ConfigDict(extra="allow")

    disk_encryption: bool | None = None
    firewall_enabled: bool | None = None
    last_patched_at: date | None = None
    os_name: str | None = None
    os_version: str | None = None
    os_eol: bool | None = None
    backup_last_at: date | None = None
    open_ports: list[int] | None = None
    tls_cert_expires_at: date | None = None
    edr_present: bool | None = None
    antivirus_present: bool | None = None
    default_credentials: bool | None = None
    logging_enabled: bool | None = None
    encryption_in_transit: bool | None = None
    password_max_age_days: int | None = None
    log_retention_days: int | None = None


class AssetCreate(BaseModel):
    """Input for creating an asset; ``short_code`` is server-assigned."""

    name: str = Field(min_length=1, max_length=255)
    asset_type: AssetType
    environment: Environment = Environment.prod
    lifecycle_state: LifecycleState = LifecycleState.active
    location: str | None = Field(default=None, max_length=255)
    description: str | None = None
    owner_id: uuid.UUID | None = None
    attributes: AssetAttributes = Field(default_factory=AssetAttributes)
    custom_fields: dict[str, object] = Field(default_factory=dict)
    tag_ids: list[uuid.UUID] = Field(default_factory=list)


class AssetUpdate(BaseModel):
    """Partial update; only supplied fields are applied."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    asset_type: AssetType | None = None
    environment: Environment | None = None
    lifecycle_state: LifecycleState | None = None
    location: str | None = Field(default=None, max_length=255)
    description: str | None = None
    owner_id: uuid.UUID | None = None
    attributes: AssetAttributes | None = None
    custom_fields: dict[str, object] | None = None
    tag_ids: list[uuid.UUID] | None = None


class AssetStateChange(BaseModel):
    """Dedicated lifecycle-state transition input (audited as ``state_change``)."""

    lifecycle_state: LifecycleState


class AssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    short_code: str
    name: str
    asset_type: AssetType
    lifecycle_state: LifecycleState
    environment: Environment
    location: str | None
    description: str | None
    owner_id: uuid.UUID | None
    attributes: dict[str, object]
    custom_fields: dict[str, object]
    tags: list[TagRead]
    created_at: datetime
    updated_at: datetime


class AssetListItem(BaseModel):
    """Lighter projection for list endpoints (no heavy JSON blobs or tag joins)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    short_code: str
    name: str
    asset_type: AssetType
    lifecycle_state: LifecycleState
    environment: Environment
    owner_id: uuid.UUID | None
