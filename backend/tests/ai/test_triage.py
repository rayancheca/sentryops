"""Unit tests for run_triage: disabled path, budget path, and a mocked success.

These tests are DB-free: a tiny fake Session captures added rows and serves the
single aggregate query (tokens used today). The Anthropic client and the shared
incident_service are stubbed so no network call or cross-vertical import is made.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

import app.ai.triage as triage_mod
from app.ai.schema import TriageOutput
from app.models.ai import AITriageResult
from app.models.enums import IncidentEventType, Severity, TriageStatus


class _FakeScalar:
    def __init__(self, value: Any) -> None:
        self._value = value

    def scalar_one(self) -> Any:
        return self._value


class FakeSession:
    """Minimal Session double: records adds and serves the token-sum query."""

    def __init__(self, tokens_used_today: int = 0) -> None:
        self.added: list[Any] = []
        self.flushes = 0
        self._tokens_used = tokens_used_today

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        self.flushes += 1

    def execute(self, _statement: Any) -> _FakeScalar:
        # The only execute() in run_triage is the daily-token-sum aggregate.
        return _FakeScalar(self._tokens_used)


class FakeIncident:
    def __init__(self) -> None:
        self.id = uuid.uuid4()
        self.title = "Service down"
        self.status = "open"
        self.severity = "high"
        self.asset_id = None
        self.health_check_id = None
        self.opened_at = None


@pytest.fixture
def stub_incident_service(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Install a fake app.services.incident_service capturing record_event calls."""
    recorded: list[dict[str, Any]] = []

    def record_event(
        db: Any,
        incident: Any,
        event_type: Any,
        *,
        message: str | None = None,
        actor_id: Any = None,
        payload: Any = None,
    ) -> None:
        recorded.append(
            {
                "incident": incident,
                "event_type": event_type,
                "message": message,
                "payload": payload,
            }
        )

    # triage._record_event does `from app.services import incident_service` and
    # calls incident_service.record_event(...); patch that attribute directly so
    # the binding is intercepted (replacing sys.modules would not be).
    monkeypatch.setattr("app.services.incident_service.record_event", record_event)
    return recorded


def _added_result(session: FakeSession) -> AITriageResult:
    results = [obj for obj in session.added if isinstance(obj, AITriageResult)]
    assert len(results) == 1
    return results[0]


def test_disabled_path_persists_disabled_and_never_calls_client(
    monkeypatch: pytest.MonkeyPatch, stub_incident_service: list[dict[str, Any]]
) -> None:
    # Arrange: feature off.
    monkeypatch.setattr(triage_mod.get_settings(), "ai_triage_enabled", False, raising=False)
    # Guard: any client call should fail the test if reached.
    monkeypatch.setattr(
        triage_mod.AnthropicTriageClient,
        "call",
        lambda *a, **k: pytest.fail("client must not be called when disabled"),
    )
    session = FakeSession()
    incident = FakeIncident()

    # Act
    result = triage_mod.run_triage(session, incident)  # type: ignore[arg-type]

    # Assert
    assert result.status is TriageStatus.disabled
    assert _added_result(session).status is TriageStatus.disabled
    assert len(stub_incident_service) == 1
    assert stub_incident_service[0]["event_type"] is IncidentEventType.ai_triaged


def test_budget_exhausted_persists_failed(
    monkeypatch: pytest.MonkeyPatch, stub_incident_service: list[dict[str, Any]]
) -> None:
    # Arrange: feature active, but the daily budget is already consumed.
    settings = triage_mod.get_settings()
    monkeypatch.setattr(settings, "ai_triage_enabled", True, raising=False)
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-test", raising=False)
    monkeypatch.setattr(settings, "ai_daily_token_budget", 1000, raising=False)
    monkeypatch.setattr(
        triage_mod.AnthropicTriageClient,
        "call",
        lambda *a, **k: pytest.fail("client must not be called over budget"),
    )
    session = FakeSession(tokens_used_today=5000)
    incident = FakeIncident()

    # Act
    result = triage_mod.run_triage(session, incident)  # type: ignore[arg-type]

    # Assert
    assert result.status is TriageStatus.failed
    assert result.error is not None and "budget" in result.error.lower()


def test_success_path_with_mocked_client(
    monkeypatch: pytest.MonkeyPatch, stub_incident_service: list[dict[str, Any]]
) -> None:
    # Arrange: feature active, plenty of budget, client returns clean JSON.
    settings = triage_mod.get_settings()
    monkeypatch.setattr(settings, "ai_triage_enabled", True, raising=False)
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-test", raising=False)
    monkeypatch.setattr(settings, "ai_daily_token_budget", 1_000_000, raising=False)
    monkeypatch.setattr(triage_mod, "build_context", lambda db, inc: {"ok": True})
    monkeypatch.setattr(triage_mod, "render_user_message", lambda ctx: "user-msg")
    monkeypatch.setattr(triage_mod, "_load_system_prompt", lambda: "system-prompt")

    raw_json = {
        "root_cause_hypothesis": "auth-db outage",
        "confidence": 0.66,
        "severity_assessment": "critical",
        "remediation_steps": [{"step": "failover", "priority": 1}],
        "stakeholder_comms_draft": "Investigating.",
    }

    def fake_call(self: Any, system: str, user: str) -> tuple[dict[str, Any], int, int]:
        return raw_json, 1200, 340

    monkeypatch.setattr(triage_mod.AnthropicTriageClient, "call", fake_call)
    session = FakeSession()
    incident = FakeIncident()

    # Act
    result = triage_mod.run_triage(session, incident)  # type: ignore[arg-type]

    # Assert
    assert result.status is TriageStatus.success
    assert result.severity_assessment is Severity.critical
    assert result.input_tokens == 1200
    assert result.output_tokens == 340
    assert result.estimated_cost_usd > 0
    assert result.raw_output == raw_json


def test_malformed_model_output_persists_failed(
    monkeypatch: pytest.MonkeyPatch, stub_incident_service: list[dict[str, Any]]
) -> None:
    # Arrange: client returns JSON missing the required root-cause hypothesis.
    settings = triage_mod.get_settings()
    monkeypatch.setattr(settings, "ai_triage_enabled", True, raising=False)
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-test", raising=False)
    monkeypatch.setattr(settings, "ai_daily_token_budget", 1_000_000, raising=False)
    monkeypatch.setattr(triage_mod, "build_context", lambda db, inc: {})
    monkeypatch.setattr(triage_mod, "render_user_message", lambda ctx: "u")
    monkeypatch.setattr(triage_mod, "_load_system_prompt", lambda: "s")
    monkeypatch.setattr(
        triage_mod.AnthropicTriageClient,
        "call",
        lambda self, s, u: ({"confidence": 0.5}, 10, 10),
    )
    session = FakeSession()
    incident = FakeIncident()

    # Act
    result = triage_mod.run_triage(session, incident)  # type: ignore[arg-type]

    # Assert: failure is captured, not raised.
    assert result.status is TriageStatus.failed
    assert result.error is not None


def test_seed_triage_marks_seeded(stub_incident_service: list[dict[str, Any]]) -> None:
    session = FakeSession()
    incident = FakeIncident()
    payload = {
        "root_cause_hypothesis": "illustrative",
        "confidence": 0.5,
        "severity_assessment": "medium",
        "remediation_steps": [],
        "stakeholder_comms_draft": "demo",
    }
    result = triage_mod.seed_triage(session, incident, payload)  # type: ignore[arg-type]
    assert result.is_seeded is True
    assert result.status is TriageStatus.success
    assert isinstance(TriageOutput.parse_clamped(payload), TriageOutput)
