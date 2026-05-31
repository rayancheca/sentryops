"""Run AI incident triage end to end and persist the result.

Human-in-the-loop, advisory-only. The model is UNTRUSTED INPUT. See the SECURITY
block at the call site documenting the prompt-injection mitigations.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.client import AnthropicTriageClient, estimate_cost
from app.ai.context import build_context, render_user_message
from app.ai.schema import TriageOutput
from app.core.config import get_settings
from app.models.ai import AITriageResult
from app.models.enums import IncidentEventType, TriageStatus
from app.models.observability import Incident

log = structlog.get_logger(__name__)

_PROMPTS_DIR = Path(__file__).parent / "prompts"


def _load_system_prompt() -> str:
    """Load the versioned system prompt (defaults to v1) from disk."""
    version = get_settings().ai_prompt_version
    path = _PROMPTS_DIR / f"system_{version}.md"
    if not path.exists():
        path = _PROMPTS_DIR / "system_v1.md"
    return path.read_text(encoding="utf-8")


def _record_event(
    db: Session,
    incident: Incident,
    *,
    event_type: IncidentEventType,
    message: str | None,
    payload: dict[str, Any] | None = None,
) -> None:
    """Record an incident event via the shared incident service.

    Imported lazily: ``incident_service`` is owned by the observability vertical,
    so a deferred import keeps this module independent at import time.
    """
    from app.services import incident_service

    incident_service.record_event(
        db,
        incident,
        event_type,
        message=message,
        payload=payload,
    )


def _persist(
    db: Session,
    incident: Incident,
    *,
    status: TriageStatus,
    model: str | None = None,
    output: TriageOutput | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    estimated_cost_usd: float = 0.0,
    error: str | None = None,
    raw_output: dict[str, Any] | None = None,
    is_seeded: bool = False,
) -> AITriageResult:
    result = AITriageResult(
        incident_id=incident.id,
        status=status,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost_usd=estimated_cost_usd,
        error=error,
        raw_output=raw_output,
        is_seeded=is_seeded,
    )
    if output is not None:
        result.root_cause_hypothesis = output.root_cause_hypothesis
        result.confidence = output.confidence
        result.severity_assessment = output.severity_assessment
        result.remediation_steps = [step.model_dump() for step in output.remediation_steps]
        result.stakeholder_comms_draft = output.stakeholder_comms_draft
    db.add(result)
    db.flush()
    return result


def _tokens_used_today(db: Session) -> int:
    """Sum of input+output tokens across all triage rows from the last 24h."""
    since = datetime.now(UTC) - timedelta(days=1)
    total = db.execute(
        select(
            func.coalesce(func.sum(AITriageResult.input_tokens + AITriageResult.output_tokens), 0)
        ).where(AITriageResult.created_at >= since)
    ).scalar_one()
    return int(total or 0)


def run_triage(db: Session, incident: Incident, *, force: bool = False) -> AITriageResult:
    """Triage ``incident`` with the AI model and persist the outcome.

    Always returns a persisted :class:`AITriageResult` and never raises for an
    expected condition (feature off, budget exhausted, model failure). ``force``
    is accepted for callers that want to bypass any future client-side caching;
    it currently has no effect on the disabled/budget guards (those are hard
    safety limits, not caches).

    SECURITY — prompt-injection mitigations applied on this path:
      * The incident context (asset/audit/dependency/compliance/check data) is
        UNTRUSTED. ``render_user_message`` fences every section with explicit
        delimiters, and the system prompt instructs the model to treat fenced
        content purely as data and NEVER follow instructions found inside it.
      * The model output is itself untrusted: ``TriageOutput.parse_clamped``
        coerces types, clamps numeric ranges, caps list lengths, and truncates
        strings before anything is persisted.
      * Output is ADVISORY ONLY and triggers NO automated action — a human
        reviews every result (human in the loop).
      * The API key and full prompt body are never logged.
    """
    settings = get_settings()

    if not settings.ai_active:
        result = _persist(
            db,
            incident,
            status=TriageStatus.disabled,
            error="AI triage is disabled (set ai_triage_enabled and provide a key).",
        )
        _record_event(
            db,
            incident,
            event_type=IncidentEventType.ai_triaged,
            message="AI triage requested but the feature is disabled.",
            payload={"status": TriageStatus.disabled.value},
        )
        return result

    tokens_used = _tokens_used_today(db)
    if tokens_used >= settings.ai_daily_token_budget:
        result = _persist(
            db,
            incident,
            status=TriageStatus.failed,
            error=(
                f"Daily AI token budget exhausted "
                f"({tokens_used}/{settings.ai_daily_token_budget})."
            ),
        )
        _record_event(
            db,
            incident,
            event_type=IncidentEventType.ai_triaged,
            message="AI triage skipped: daily token budget exhausted.",
            payload={"status": TriageStatus.failed.value},
        )
        return result

    try:
        context = build_context(db, incident)
        user_message = render_user_message(context)
        system_prompt = _load_system_prompt()

        client = AnthropicTriageClient()
        raw_json, input_tokens, output_tokens = client.call(system_prompt, user_message)
        output = TriageOutput.parse_clamped(raw_json)
        cost = estimate_cost(settings.anthropic_model, input_tokens, output_tokens)

        result = _persist(
            db,
            incident,
            status=TriageStatus.success,
            model=settings.anthropic_model,
            output=output,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=cost,
            raw_output=raw_json,
        )
        _record_event(
            db,
            incident,
            event_type=IncidentEventType.ai_triaged,
            message="AI triage completed.",
            payload={
                "status": TriageStatus.success.value,
                "confidence": output.confidence,
                "severity_assessment": output.severity_assessment.value,
            },
        )
        return result
    except Exception as exc:
        # Persist a clear failure with NO secrets/tokens/prompt body in the message.
        message = f"{type(exc).__name__}: {exc}"
        log.warning("ai_triage_failed", incident_id=str(incident.id), error=message)
        result = _persist(
            db,
            incident,
            status=TriageStatus.failed,
            model=settings.anthropic_model,
            error=message[:1000],
        )
        _record_event(
            db,
            incident,
            event_type=IncidentEventType.ai_triaged,
            message="AI triage failed.",
            payload={"status": TriageStatus.failed.value},
        )
        return result


def seed_triage(db: Session, incident: Incident, payload: dict[str, Any]) -> AITriageResult:
    """Persist a clearly-labelled, illustrative triage result for the demo seed.

    No API call is made. The result is marked ``is_seeded=True`` and validated
    through the same defensive clamping path as live output, so seed data is
    indistinguishable in shape from real output but flagged as illustrative.
    """
    output = TriageOutput.parse_clamped(payload)
    return _persist(
        db,
        incident,
        status=TriageStatus.success,
        model="seed",
        output=output,
        is_seeded=True,
        raw_output=payload,
    )
