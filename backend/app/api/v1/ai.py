"""AI incident-triage endpoints.

Triage is advisory, human-in-the-loop, and OFF unless ``ai_active``. The run
endpoint respects the flag and degrades gracefully (it returns a ``disabled``
result rather than erroring), is operator-gated, and is rate limited.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Request
from sqlalchemy import select

from app.ai.triage import run_triage
from app.api.deps import CurrentUser, DbSession, RequireOperator
from app.core.exceptions import NotFoundError
from app.core.rate_limit import SCAN_LIMIT, limiter
from app.models.ai import AITriageResult
from app.models.observability import Incident
from app.schemas.ai import TokenCostRead, TriageResultRead
from app.schemas.common import Envelope

router = APIRouter(prefix="/incidents", tags=["ai-triage"])


def _get_incident(db: DbSession, incident_id: uuid.UUID) -> Incident:
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise NotFoundError(f"Incident '{incident_id}' not found.")
    return incident


@router.get(
    "/{incident_id}/triage",
    response_model=Envelope[TriageResultRead],
    summary="Latest AI triage result for an incident",
)
def get_latest_triage(
    incident_id: uuid.UUID,
    db: DbSession,
    _user: CurrentUser,
) -> Envelope[TriageResultRead]:
    _get_incident(db, incident_id)
    latest = db.execute(
        select(AITriageResult)
        .where(AITriageResult.incident_id == incident_id)
        .order_by(AITriageResult.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if latest is None:
        raise NotFoundError(f"No triage result exists for incident '{incident_id}'.")
    return Envelope.ok(TriageResultRead.model_validate(latest))


@router.post(
    "/{incident_id}/triage/run",
    response_model=Envelope[TriageResultRead],
    summary="Run AI triage for an incident (operator only)",
)
@limiter.limit(SCAN_LIMIT)
def run_incident_triage(
    request: Request,
    incident_id: uuid.UUID,
    db: DbSession,
    _user: RequireOperator,
) -> Envelope[TriageResultRead]:
    # Respects the feature flag: run_triage persists a `disabled` result when the
    # feature is off and never raises for that case. Advisory only; no automated
    # action is taken on the result (human in the loop).
    incident = _get_incident(db, incident_id)
    result = run_triage(db, incident)
    db.commit()
    db.refresh(result)
    return Envelope.ok(TriageResultRead.model_validate(result))


@router.get(
    "/{incident_id}/triage/cost",
    response_model=Envelope[TokenCostRead],
    summary="Aggregate token usage and estimated cost for an incident",
)
def get_triage_cost(
    incident_id: uuid.UUID,
    db: DbSession,
    _user: CurrentUser,
) -> Envelope[TokenCostRead]:
    _get_incident(db, incident_id)
    rows = db.execute(
        select(
            AITriageResult.input_tokens,
            AITriageResult.output_tokens,
            AITriageResult.estimated_cost_usd,
        ).where(AITriageResult.incident_id == incident_id)
    ).all()
    total_input = sum(int(r[0] or 0) for r in rows)
    total_output = sum(int(r[1] or 0) for r in rows)
    total_cost = round(sum(float(r[2] or 0.0) for r in rows), 6)
    aggregate = TokenCostRead(
        incident_id=incident_id,
        total_input_tokens=total_input,
        total_output_tokens=total_output,
        total_cost_usd=total_cost,
        calls=len(rows),
    )
    return Envelope.ok(aggregate)
