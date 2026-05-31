"""Unit tests for defensive parsing/clamping of untrusted model output."""

from __future__ import annotations

import pytest

from app.ai.schema import (
    MAX_REMEDIATION_STEPS,
    RemediationStep,
    TriageOutput,
)
from app.core.exceptions import ValidationAppError
from app.models.enums import Severity


def _valid_raw() -> dict[str, object]:
    return {
        "root_cause_hypothesis": "Upstream auth-db went down before the service.",
        "confidence": 0.7,
        "severity_assessment": "high",
        "remediation_steps": [
            {"step": "Failover auth-db", "rationale": "Restore dependency", "priority": 1}
        ],
        "stakeholder_comms_draft": "We are investigating an auth outage.",
    }


def test_parse_clamped_accepts_well_formed_output() -> None:
    # Arrange
    raw = _valid_raw()

    # Act
    output = TriageOutput.parse_clamped(raw)

    # Assert
    assert output.root_cause_hypothesis.startswith("Upstream auth-db")
    assert output.confidence == 0.7
    assert output.severity_assessment is Severity.high
    assert len(output.remediation_steps) == 1
    assert output.remediation_steps[0].priority == 1


def test_confidence_is_clamped_to_unit_interval() -> None:
    high = TriageOutput.parse_clamped({**_valid_raw(), "confidence": 5.0})
    low = TriageOutput.parse_clamped({**_valid_raw(), "confidence": -3.0})
    assert high.confidence == 1.0
    assert low.confidence == 0.0


def test_confidence_non_numeric_defaults_to_zero() -> None:
    output = TriageOutput.parse_clamped({**_valid_raw(), "confidence": "not-a-number"})
    assert output.confidence == 0.0


def test_remediation_steps_capped_at_eight() -> None:
    raw = _valid_raw()
    raw["remediation_steps"] = [
        {"step": f"step {i}", "priority": 2} for i in range(20)
    ]
    output = TriageOutput.parse_clamped(raw)
    assert len(output.remediation_steps) == MAX_REMEDIATION_STEPS


def test_step_priority_is_clamped() -> None:
    raw = _valid_raw()
    raw["remediation_steps"] = [
        {"step": "too high", "priority": 99},
        {"step": "too low", "priority": -4},
    ]
    output = TriageOutput.parse_clamped(raw)
    assert output.remediation_steps[0].priority == 5
    assert output.remediation_steps[1].priority == 1


def test_string_step_is_coerced() -> None:
    raw = _valid_raw()
    raw["remediation_steps"] = ["just a bare string step"]
    output = TriageOutput.parse_clamped(raw)
    assert output.remediation_steps[0].step == "just a bare string step"
    assert output.remediation_steps[0].priority == 3  # default


def test_unknown_severity_defaults_to_high() -> None:
    output = TriageOutput.parse_clamped({**_valid_raw(), "severity_assessment": "armageddon"})
    assert output.severity_assessment is Severity.high


def test_missing_comms_draft_gets_placeholder() -> None:
    raw = _valid_raw()
    del raw["stakeholder_comms_draft"]
    output = TriageOutput.parse_clamped(raw)
    assert output.stakeholder_comms_draft  # non-empty placeholder


def test_missing_root_cause_is_irrecoverable() -> None:
    raw = _valid_raw()
    del raw["root_cause_hypothesis"]
    with pytest.raises(ValidationAppError):
        TriageOutput.parse_clamped(raw)


def test_empty_root_cause_is_irrecoverable() -> None:
    with pytest.raises(ValidationAppError):
        TriageOutput.parse_clamped({**_valid_raw(), "root_cause_hypothesis": "   "})


def test_non_dict_input_raises() -> None:
    with pytest.raises(ValidationAppError):
        TriageOutput.parse_clamped(["not", "a", "dict"])  # type: ignore[arg-type]


def test_extra_keys_are_rejected_then_recovered_by_parse_clamped() -> None:
    # parse_clamped only forwards known fields, so extraneous keys are dropped.
    raw = {**_valid_raw(), "ignore_me": "drop this", "secret": "leak"}
    output = TriageOutput.parse_clamped(raw)
    assert not hasattr(output, "ignore_me")


def test_direct_construction_forbids_extra() -> None:
    with pytest.raises(Exception):
        TriageOutput(
            root_cause_hypothesis="x",
            confidence=0.5,
            severity_assessment=Severity.low,
            remediation_steps=[],
            stakeholder_comms_draft="y",
            bonus_field="nope",  # type: ignore[call-arg]
        )


def test_remediation_step_defaults() -> None:
    step = RemediationStep(step="do the thing")
    assert step.priority == 3
    assert step.rationale is None
