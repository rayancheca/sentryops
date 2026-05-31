"""Integration tests for AI incident triage end to end.

These run against the real database with real incident/asset rows and the real
``build_context`` / ``render_user_message`` / clamping pipeline. The ONLY thing
stubbed is the Anthropic SDK call: it is isolated in
``AnthropicTriageClient._invoke`` (the ``from anthropic import Anthropic`` lives
inside that method), so monkeypatching ``_invoke`` means the network is never
touched. We assert the persisted ``AITriageResult`` rows and the recorded
``ai_triaged`` incident events.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy.orm import Session

import app.ai.triage as triage_mod
from app.ai.client import AnthropicTriageClient, _RawResponse
from app.models.ai import AITriageResult
from app.models.asset import Asset
from app.models.enums import (
    AssetType,
    CheckStatus,
    CheckType,
    Environment,
    IncidentEventType,
    IncidentStatus,
    Severity,
    TriageStatus,
)
from app.models.observability import (
    CheckResult,
    HealthCheck,
    Incident,
    IncidentEvent,
    Service,
)

pytestmark = pytest.mark.integration


_VALID_OUTPUT: dict[str, Any] = {
    "root_cause_hypothesis": "Upstream auth database connection pool exhausted.",
    "confidence": 0.72,
    "severity_assessment": "critical",
    "remediation_steps": [
        {"step": "Increase the connection pool size", "priority": 1},
        {"step": "Fail over to the standby replica", "rationale": "Restore writes", "priority": 2},
    ],
    "stakeholder_comms_draft": "We are investigating elevated errors on checkout.",
}


def _build_incident(db: Session) -> Incident:
    """Create an asset -> service -> check -> incident chain with one result."""
    asset = Asset(
        short_code="SVR-AI1",
        name="auth-db",
        asset_type=AssetType.host,
        environment=Environment.prod,
        attributes={"disk_encrypted": True},
    )
    db.add(asset)
    db.flush()

    service = Service(name="auth-service", asset_id=asset.id, slo_target=0.999)
    db.add(service)
    db.flush()

    check = HealthCheck(
        service_id=service.id,
        name="auth probe",
        check_type=CheckType.http,
        target="https://auth.test.local/health",
        expected_status=200,
        latency_budget_ms=1000,
    )
    db.add(check)
    db.flush()

    db.add(
        CheckResult(
            health_check_id=check.id,
            status=CheckStatus.down,
            latency_ms=None,
            status_code=503,
            error="service unavailable",
            created_at=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        )
    )
    db.flush()

    incident = Incident(
        service_id=service.id,
        health_check_id=check.id,
        asset_id=asset.id,
        title="auth-service: auth probe failing",
        status=IncidentStatus.open,
        severity=Severity.high,
        opened_at=datetime(2026, 1, 1, 12, 5, tzinfo=UTC),
    )
    db.add(incident)
    db.flush()
    return incident


def _ai_events(db: Session, incident: Incident) -> list[IncidentEvent]:
    return (
        db.query(IncidentEvent)
        .filter(
            IncidentEvent.incident_id == incident.id,
            IncidentEvent.event_type == IncidentEventType.ai_triaged,
        )
        .all()
    )


def _activate_ai(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force the cached settings singleton to report ``ai_active`` as True.

    ``ai_active`` is a derived property (enabled flag AND a key present); we set
    both inputs. monkeypatch restores the singleton attributes after the test.
    """
    settings = triage_mod.get_settings()
    monkeypatch.setattr(settings, "ai_triage_enabled", True, raising=False)
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-test-not-real", raising=False)
    monkeypatch.setattr(settings, "ai_daily_token_budget", 1_000_000, raising=False)
    assert settings.ai_active is True


def test_disabled_path_persists_disabled_and_never_calls_api(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — default config has AI triage disabled. Guard the SDK seam so any
    # call fails the test loudly.
    assert triage_mod.get_settings().ai_active is False
    monkeypatch.setattr(
        AnthropicTriageClient,
        "_invoke",
        lambda *a, **k: pytest.fail("the Anthropic SDK must not be invoked when disabled"),
    )
    incident = _build_incident(db)

    # Act
    result = triage_mod.run_triage(db, incident)
    db.flush()

    # Assert — a disabled result row is persisted.
    assert result.status is TriageStatus.disabled
    assert result.input_tokens == 0
    assert result.output_tokens == 0
    persisted = db.query(AITriageResult).filter(AITriageResult.incident_id == incident.id).all()
    assert len(persisted) == 1
    assert persisted[0].status is TriageStatus.disabled

    # An ai_triaged event records the disabled outcome.
    events = _ai_events(db, incident)
    assert len(events) == 1
    assert events[0].payload == {"status": TriageStatus.disabled.value}


def test_success_path_persists_parsed_fields_tokens_cost_and_event(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — activate AI and stub the SDK to return canned JSON + token usage.
    _activate_ai(monkeypatch)
    incident = _build_incident(db)

    raw_text = (
        '{"root_cause_hypothesis": "Upstream auth database connection pool exhausted.",'
        ' "confidence": 0.72, "severity_assessment": "critical",'
        ' "remediation_steps": [{"step": "Increase the connection pool size", "priority": 1},'
        ' {"step": "Fail over to the standby replica", "rationale": "Restore writes",'
        ' "priority": 2}],'
        ' "stakeholder_comms_draft": "We are investigating elevated errors on checkout."}'
    )

    def fake_invoke(self: AnthropicTriageClient, *, system: str, user: str) -> _RawResponse:
        # The fenced, untrusted context must actually reach the client.
        assert "INCIDENT_DATA" in user
        return _RawResponse(text=raw_text, input_tokens=1500, output_tokens=420)

    monkeypatch.setattr(AnthropicTriageClient, "_invoke", fake_invoke)

    # Act
    result = triage_mod.run_triage(db, incident)
    db.flush()

    # Assert — parsed fields persisted.
    assert result.status is TriageStatus.success
    assert result.root_cause_hypothesis == _VALID_OUTPUT["root_cause_hypothesis"]
    assert result.confidence == pytest.approx(0.72)
    assert result.severity_assessment is Severity.critical
    assert result.stakeholder_comms_draft == _VALID_OUTPUT["stakeholder_comms_draft"]
    assert len(result.remediation_steps) == 2
    assert result.remediation_steps[0]["step"] == "Increase the connection pool size"

    # Token / cost log populated; cost derived from the model price table.
    assert result.input_tokens == 1500
    assert result.output_tokens == 420
    assert result.estimated_cost_usd > 0
    assert result.model == triage_mod.get_settings().anthropic_model
    assert result.is_seeded is False
    assert result.raw_output == _VALID_OUTPUT

    # The success row is queryable and unique for the incident.
    persisted = db.query(AITriageResult).filter(AITriageResult.incident_id == incident.id).all()
    assert len(persisted) == 1
    assert persisted[0].status is TriageStatus.success

    # An ai_triaged event records success with confidence + severity.
    events = _ai_events(db, incident)
    assert len(events) == 1
    payload = events[0].payload
    assert payload["status"] == TriageStatus.success.value
    assert payload["severity_assessment"] == Severity.critical.value
    assert payload["confidence"] == pytest.approx(0.72)


def test_malformed_output_is_clamped_not_rejected(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — model returns out-of-range / off-spec values that the defensive
    # clamping pipeline can salvage (confidence > 1, unknown severity, too many
    # steps). This must succeed with clamped fields, not fail.
    _activate_ai(monkeypatch)
    incident = _build_incident(db)

    steps = ", ".join(f'{{"step": "step {i}", "priority": 9}}' for i in range(12))
    raw_text = (
        '{"root_cause_hypothesis": "noisy neighbour", "confidence": 5.0,'
        ' "severity_assessment": "apocalyptic",'
        f' "remediation_steps": [{steps}],'
        ' "stakeholder_comms_draft": "draft"}'
    )

    monkeypatch.setattr(
        AnthropicTriageClient,
        "_invoke",
        lambda self, *, system, user: _RawResponse(
            text=raw_text, input_tokens=10, output_tokens=10
        ),
    )

    # Act
    result = triage_mod.run_triage(db, incident)
    db.flush()

    # Assert — salvaged into a success with clamped values.
    assert result.status is TriageStatus.success
    assert result.confidence == pytest.approx(1.0)  # clamped to MAX_CONFIDENCE
    assert result.severity_assessment is Severity.high  # unknown -> default high
    assert len(result.remediation_steps) <= 8  # MAX_REMEDIATION_STEPS cap
    assert all(step["priority"] <= 5 for step in result.remediation_steps)  # MAX_PRIORITY


def test_irrecoverable_output_persists_failed(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange — output with no usable root-cause hypothesis cannot be salvaged.
    _activate_ai(monkeypatch)
    incident = _build_incident(db)
    monkeypatch.setattr(
        AnthropicTriageClient,
        "_invoke",
        lambda self, *, system, user: _RawResponse(
            text='{"confidence": 0.5}', input_tokens=8, output_tokens=8
        ),
    )

    # Act
    result = triage_mod.run_triage(db, incident)
    db.flush()

    # Assert — a failed row is persisted, never raised.
    assert result.status is TriageStatus.failed
    assert result.error is not None
    persisted = db.query(AITriageResult).filter(AITriageResult.incident_id == incident.id).all()
    assert len(persisted) == 1
    assert persisted[0].status is TriageStatus.failed

    # Failure is still recorded on the incident timeline.
    events = _ai_events(db, incident)
    assert len(events) == 1
    assert events[0].payload == {"status": TriageStatus.failed.value}


def test_no_real_api_call_made_when_invoke_unpatched_is_avoided(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Defense-in-depth: even with AI active, force a network-free failure by
    # stubbing _invoke to raise; the service must trap it as a failed result,
    # NOT propagate, and must never reach the real Anthropic SDK.
    _activate_ai(monkeypatch)
    incident = _build_incident(db)

    def boom(self: AnthropicTriageClient, *, system: str, user: str) -> _RawResponse:
        raise RuntimeError("simulated transport error")

    monkeypatch.setattr(AnthropicTriageClient, "_invoke", boom)

    # Act
    result = triage_mod.run_triage(db, incident)
    db.flush()

    # Assert — trapped as failed, with no secrets leaked into the message.
    assert result.status is TriageStatus.failed
    assert result.error is not None
    assert "sk-test-not-real" not in result.error
