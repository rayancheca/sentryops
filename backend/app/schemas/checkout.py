"""Asset check-in/out schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CheckoutCreate(BaseModel):
    """Input for checking an asset out to a holder."""

    holder_id: uuid.UUID
    notes: str | None = None


class CheckoutRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    asset_id: uuid.UUID
    holder_id: uuid.UUID | None
    checked_out_by_id: uuid.UUID | None
    checked_out_at: datetime
    checked_in_at: datetime | None
    notes: str | None
