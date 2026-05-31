"""Tag schemas: creation input and read projection."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field


class TagCreate(BaseModel):
    """Input for creating a tag. Colour defaults to the slate accent used by the model."""

    name: str = Field(min_length=1, max_length=64)
    color: str = Field(default="#64748b", max_length=20)


class TagRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    color: str
