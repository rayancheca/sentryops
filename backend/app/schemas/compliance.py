"""Pydantic v2 schemas for the compliance API surface.

Read schemas use ``from_attributes`` so they validate directly off ORM rows.
Deeply nested report payloads are typed at the top level and carry plain
``dict``/``list`` bodies where enumerating every nested field would add noise
without adding safety.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ComplianceStatus, Severity


class RuleRead(BaseModel):
    """A registered rule, as exposed by GET /compliance/rules."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    framework: str
    control: str
    severity: Severity
    description: str
    remediation: str


class ResultRead(BaseModel):
    """One per-asset, per-rule evaluation result row."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_id: uuid.UUID
    asset_id: uuid.UUID
    rule_id: str
    status: ComplianceStatus
    severity: Severity
    evidence: dict[str, Any] | None = None
    created_at: datetime


class RunRead(BaseModel):
    """A compliance run snapshot (one drift datapoint)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    started_at: datetime
    finished_at: datetime | None = None
    triggered_by_id: uuid.UUID | None = None
    total_assets: int
    org_score: float
    passed_count: int
    failed_count: int
    not_applicable_count: int
    severity_failing: dict[str, int] = Field(default_factory=dict)


class ScoreRead(BaseModel):
    """Organisation rollup score for the latest run."""

    run_id: uuid.UUID | None = None
    org_score: float
    total_assets: int
    passed_count: int
    failed_count: int
    not_applicable_count: int
    severity_failing: dict[str, int] = Field(default_factory=dict)
    started_at: datetime | None = None


class DriftPoint(BaseModel):
    """One point on the org-score-over-time drift series."""

    run_id: uuid.UUID
    org_score: float
    started_at: datetime
    severity_failing: dict[str, int] = Field(default_factory=dict)


class NewlyFailingItem(BaseModel):
    """A (rule, asset) pair that started failing in the latest run."""

    asset_id: uuid.UUID
    rule_id: str
    severity: Severity
    title: str
    control: str


class ReportRead(BaseModel):
    """Audit-ready compliance report for a single run.

    The ``per_asset`` and ``failing_controls`` bodies are intentionally typed
    as plain dict/list payloads — they are deeply nested presentation
    structures assembled by the service layer.
    """

    run_id: uuid.UUID
    generated_for: datetime
    org_score: float
    total_assets: int
    status_counts: dict[str, int] = Field(default_factory=dict)
    severity_failing: dict[str, int] = Field(default_factory=dict)
    per_asset: list[dict[str, Any]] = Field(default_factory=list)
    failing_controls: list[dict[str, Any]] = Field(default_factory=list)
