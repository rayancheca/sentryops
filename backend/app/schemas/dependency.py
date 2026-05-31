"""Dependency-graph schemas: edge I/O. Tree/graph results are plain dicts."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field


class DependencyCreate(BaseModel):
    """Create a directed edge: ``source`` depends on ``target``."""

    source_asset_id: uuid.UUID
    target_asset_id: uuid.UUID
    kind: str | None = Field(default=None, max_length=50)


class DependencyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_asset_id: uuid.UUID
    target_asset_id: uuid.UUID
    kind: str | None
