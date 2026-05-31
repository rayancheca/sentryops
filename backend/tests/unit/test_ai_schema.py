"""Pure-logic unit tests for the AI triage output schema.

The model is untrusted input. ``TriageOutput.parse_clamped`` coerces and clamps
that output before it is persisted or shown:

* ``confidence`` is clamped to the closed unit interval [0.0, 1.0].
* ``remediation_steps`` is capped at :data:`MAX_REMEDIATION_STEPS`.
* ``severity_assessment`` is coerced from arbitrary strings onto the enum,
  falling back to ``Severity.high`` for unknown labels.
* Irrecoverable output (non-dict, or missing/empty root-cause hypothesis) raises
  :class:`ValidationAppError`.

These tests are DB-free: they call ``parse_clamped`` with plain dicts.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.ai.schema import (
    MAX_CONFIDENCE,
    MAX_REMEDIATION_STEPS,
    MIN_CONFIDENCE,
    RemediationStep,
    TriageOutput,
)
from app.core.exceptions import ValidationAppError
from app.models.enums import Severity


def _full_valid_payload() -> dict[str, object]:
    """A well-formed payload that should round-trip without coercion losses."""
    return {
        "root_cause_hypothesis": "The auth database connection pool was exhausted.",
        "confidence": 0.82,
        "severity_assessment": "critical",
        "remediation_steps": [
            {
                "step": "Increase the connection pool size",
                "rationale": "Pool was saturated under peak load",
                "priority": 1,
            },
            {"step": "Add a pool-saturation alert", "priority": 2},
        ],
        "stakeholder_comms_draft": "We identified and are mitigating an auth outage.",
    }


# ---------------------------------------------------------------------------
# Valid full payload round-trip
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_full_valid_payload_round_trips() -> None:
    # Arrange
    raw = _full_valid_payload()

    # Act
    output = TriageOutput.parse_clamped(raw)

    # Assert — every field is preserved as supplied.
    assert output.root_cause_hypothesis == raw["root_cause_hypothesis"]
    assert output.confidence == 0.82
    assert output.severity_assessment is Severity.critical
    assert output.stakeholder_comms_draft == raw["stakeholder_comms_draft"]
    assert [s.step for s in output.remediation_steps] == [
        "Increase the connection pool size",
        "Add a pool-saturation alert",
    ]
    assert output.remediation_steps[0].rationale == "Pool was saturated under peak load"
    assert output.remediation_steps[0].priority == 1
    assert output.remediation_steps[1].priority == 2


# ---------------------------------------------------------------------------
# confidence clamping to [0, 1]
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_confidence_above_one_clamps_to_one() -> None:
    # Arrange / Act
    output = TriageOutput.parse_clamped({**_full_valid_payload(), "confidence": 1.7})

    # Assert
    assert output.confidence == 1.0
    assert output.confidence == MAX_CONFIDENCE


@pytest.mark.unit
def test_confidence_below_zero_clamps_to_zero() -> None:
    # Arrange / Act
    output = TriageOutput.parse_clamped({**_full_valid_payload(), "confidence": -0.2})

    # Assert
    assert output.confidence == 0.0
    assert output.confidence == MIN_CONFIDENCE


@pytest.mark.unit
def test_confidence_boundaries_pass_through_unchanged() -> None:
    # Arrange / Act
    at_zero = TriageOutput.parse_clamped({**_full_valid_payload(), "confidence": 0.0})
    at_one = TriageOutput.parse_clamped({**_full_valid_payload(), "confidence": 1.0})

    # Assert
    assert at_zero.confidence == 0.0
    assert at_one.confidence == 1.0


@pytest.mark.unit
def test_confidence_from_numeric_string_is_coerced_then_clamped() -> None:
    # Arrange — the model returned a number as a string AND out of range.
    output = TriageOutput.parse_clamped({**_full_valid_payload(), "confidence": "2.5"})

    # Assert
    assert output.confidence == 1.0


@pytest.mark.unit
def test_confidence_non_numeric_string_defaults_to_zero() -> None:
    # Arrange / Act
    output = TriageOutput.parse_clamped({**_full_valid_payload(), "confidence": "very-sure"})

    # Assert
    assert output.confidence == 0.0


@pytest.mark.unit
def test_confidence_missing_defaults_to_zero() -> None:
    # Arrange
    raw = _full_valid_payload()
    del raw["confidence"]

    # Act
    output = TriageOutput.parse_clamped(raw)

    # Assert
    assert output.confidence == 0.0


# ---------------------------------------------------------------------------
# remediation_steps cap
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_remediation_steps_capped_at_documented_max() -> None:
    # Arrange — a runaway model produces far more than the allowed maximum.
    raw = _full_valid_payload()
    raw["remediation_steps"] = [
        {"step": f"step {i}", "priority": 3} for i in range(MAX_REMEDIATION_STEPS + 15)
    ]

    # Act
    output = TriageOutput.parse_clamped(raw)

    # Assert — exactly MAX_REMEDIATION_STEPS survive, in original order.
    assert len(output.remediation_steps) == MAX_REMEDIATION_STEPS
    assert output.remediation_steps[0].step == "step 0"
    assert output.remediation_steps[-1].step == f"step {MAX_REMEDIATION_STEPS - 1}"


@pytest.mark.unit
def test_remediation_steps_exactly_at_max_are_all_kept() -> None:
    # Arrange
    raw = _full_valid_payload()
    raw["remediation_steps"] = [{"step": f"step {i}"} for i in range(MAX_REMEDIATION_STEPS)]

    # Act
    output = TriageOutput.parse_clamped(raw)

    # Assert
    assert len(output.remediation_steps) == MAX_REMEDIATION_STEPS


@pytest.mark.unit
def test_remediation_steps_missing_defaults_to_empty_list() -> None:
    # Arrange
    raw = _full_valid_payload()
    del raw["remediation_steps"]

    # Act
    output = TriageOutput.parse_clamped(raw)

    # Assert
    assert output.remediation_steps == []


@pytest.mark.unit
def test_remediation_steps_non_list_becomes_empty() -> None:
    # Arrange — the model returned a string instead of a list of steps.
    output = TriageOutput.parse_clamped(
        {**_full_valid_payload(), "remediation_steps": "do something"}
    )

    # Assert
    assert output.remediation_steps == []


@pytest.mark.unit
def test_remediation_steps_drops_unusable_items() -> None:
    # Arrange — mix of usable and irrecoverable step entries.
    raw = _full_valid_payload()
    raw["remediation_steps"] = [
        {"step": "usable dict step"},
        {"step": ""},  # empty -> dropped
        {"rationale": "no step key"},  # missing step -> dropped
        "usable bare string",
        "",  # empty string -> dropped
        12345,  # wrong type -> dropped
    ]

    # Act
    output = TriageOutput.parse_clamped(raw)

    # Assert
    assert [s.step for s in output.remediation_steps] == [
        "usable dict step",
        "usable bare string",
    ]


# ---------------------------------------------------------------------------
# severity coercion from string
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("low", Severity.low),
        ("medium", Severity.medium),
        ("high", Severity.high),
        ("critical", Severity.critical),
        ("  CRITICAL  ", Severity.critical),  # whitespace + case-insensitive
        ("High", Severity.high),
    ],
)
def test_severity_assessment_coerced_from_string(raw_value: str, expected: Severity) -> None:
    # Arrange / Act
    output = TriageOutput.parse_clamped({**_full_valid_payload(), "severity_assessment": raw_value})

    # Assert
    assert output.severity_assessment is expected


@pytest.mark.unit
def test_unknown_severity_falls_back_to_high() -> None:
    # Arrange / Act
    output = TriageOutput.parse_clamped(
        {**_full_valid_payload(), "severity_assessment": "apocalyptic"}
    )

    # Assert
    assert output.severity_assessment is Severity.high


@pytest.mark.unit
def test_missing_severity_falls_back_to_high() -> None:
    # Arrange
    raw = _full_valid_payload()
    del raw["severity_assessment"]

    # Act
    output = TriageOutput.parse_clamped(raw)

    # Assert
    assert output.severity_assessment is Severity.high


@pytest.mark.unit
def test_severity_passthrough_when_already_enum() -> None:
    # Arrange / Act
    output = TriageOutput.parse_clamped(
        {**_full_valid_payload(), "severity_assessment": Severity.low}
    )

    # Assert
    assert output.severity_assessment is Severity.low


# ---------------------------------------------------------------------------
# stakeholder comms placeholder
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_missing_comms_draft_gets_nonempty_placeholder() -> None:
    # Arrange
    raw = _full_valid_payload()
    del raw["stakeholder_comms_draft"]

    # Act
    output = TriageOutput.parse_clamped(raw)

    # Assert — an otherwise usable hypothesis is not discarded.
    assert isinstance(output.stakeholder_comms_draft, str)
    assert output.stakeholder_comms_draft.strip()


# ---------------------------------------------------------------------------
# rejection / raise on irrecoverable garbage
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_non_dict_input_raises_validation_error() -> None:
    # Arrange / Act / Assert
    with pytest.raises(ValidationAppError):
        TriageOutput.parse_clamped(["not", "a", "dict"])  # type: ignore[arg-type]


@pytest.mark.unit
def test_none_input_raises_validation_error() -> None:
    with pytest.raises(ValidationAppError):
        TriageOutput.parse_clamped(None)  # type: ignore[arg-type]


@pytest.mark.unit
def test_missing_root_cause_raises_validation_error() -> None:
    # Arrange
    raw = _full_valid_payload()
    del raw["root_cause_hypothesis"]

    # Act / Assert — no usable hypothesis means the result is irrecoverable.
    with pytest.raises(ValidationAppError):
        TriageOutput.parse_clamped(raw)


@pytest.mark.unit
def test_blank_root_cause_raises_validation_error() -> None:
    # Arrange / Act / Assert — whitespace-only hypothesis is not salvageable.
    with pytest.raises(ValidationAppError):
        TriageOutput.parse_clamped({**_full_valid_payload(), "root_cause_hypothesis": "   "})


@pytest.mark.unit
def test_non_string_root_cause_raises_validation_error() -> None:
    # Arrange / Act / Assert
    with pytest.raises(ValidationAppError):
        TriageOutput.parse_clamped({**_full_valid_payload(), "root_cause_hypothesis": 999})


# ---------------------------------------------------------------------------
# RemediationStep / direct construction guards
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_remediation_step_priority_defaults_when_absent() -> None:
    # Arrange / Act
    step = RemediationStep(step="restart the worker")

    # Assert
    assert step.priority == 3
    assert step.rationale is None


@pytest.mark.unit
def test_remediation_step_priority_clamped_via_validator() -> None:
    # Arrange / Act — out-of-range priorities are clamped before field bounds.
    too_high = RemediationStep(step="x", priority=42)
    too_low = RemediationStep(step="y", priority=-7)

    # Assert
    assert too_high.priority == 5
    assert too_low.priority == 1


@pytest.mark.unit
def test_remediation_step_non_numeric_priority_defaults() -> None:
    # Arrange / Act
    step = RemediationStep(step="z", priority="urgent")  # type: ignore[arg-type]

    # Assert
    assert step.priority == 3


@pytest.mark.unit
def test_triage_output_forbids_extra_fields_on_direct_construction() -> None:
    # Arrange / Act / Assert — extra="forbid" keeps the persisted shape strict.
    with pytest.raises(ValidationError):
        TriageOutput(
            root_cause_hypothesis="x",
            confidence=0.5,
            severity_assessment=Severity.low,
            remediation_steps=[],
            stakeholder_comms_draft="y",
            unexpected_field="reject me",  # type: ignore[call-arg]
        )
