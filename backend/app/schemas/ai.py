"""Read schemas for AI incident-triage results and token/cost aggregates."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.enums import Severity, TriageStatus


class TriageResultRead(BaseModel):
    """A single persisted triage result, as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    incident_id: uuid.UUID
    status: TriageStatus
    model: str | None = None
    root_cause_hypothesis: str | None = None
    confidence: float | None = None
    severity_assessment: Severity | None = None
    remediation_steps: list[dict[str, Any]] | None = None
    stakeholder_comms_draft: str | None = None
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    is_seeded: bool
    created_at: datetime


class TokenCostRead(BaseModel):
    """Aggregate token usage and estimated cost across an incident's triage calls."""

    incident_id: uuid.UUID
    total_input_tokens: int
    total_output_tokens: int
    total_cost_usd: float
    calls: int
