"""Validated/clamped representation of the AI triage model's output.

The model is UNTRUSTED INPUT. Everything it returns is coerced and clamped here
before it is persisted or shown. ``TriageOutput.parse_clamped`` is deliberately
defensive: it tolerates the model omitting optional fields, returning numbers as
strings, over-producing remediation steps, or returning slightly off-spec
severity labels, but it raises :class:`ValidationAppError` when the output is
irrecoverable (e.g. no usable root-cause hypothesis at all).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.exceptions import ValidationAppError
from app.models.enums import Severity

# Bounds applied to clamp the untrusted model output.
MIN_CONFIDENCE = 0.0
MAX_CONFIDENCE = 1.0
MIN_PRIORITY = 1
MAX_PRIORITY = 5
DEFAULT_PRIORITY = 3
MAX_REMEDIATION_STEPS = 8
# Defensive truncation so a runaway model cannot bloat the row / response.
MAX_TEXT_CHARS = 4000
MAX_STEP_CHARS = 1000


def _clamp_float(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _clamp_int(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def _truncate(text: str, limit: int) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[:limit]


class RemediationStep(BaseModel):
    """A single advisory remediation action proposed by the model."""

    model_config = ConfigDict(extra="forbid")

    step: str
    rationale: str | None = None
    priority: int = Field(default=DEFAULT_PRIORITY, ge=MIN_PRIORITY, le=MAX_PRIORITY)

    @field_validator("priority", mode="before")
    @classmethod
    def _clamp_priority(cls, value: Any) -> int:
        try:
            ivalue = int(value)
        except (TypeError, ValueError):
            return DEFAULT_PRIORITY
        return _clamp_int(ivalue, MIN_PRIORITY, MAX_PRIORITY)


class TriageOutput(BaseModel):
    """Strict, clamped triage payload. Extra keys from the model are rejected."""

    model_config = ConfigDict(extra="forbid")

    root_cause_hypothesis: str
    confidence: float = Field(default=0.0)
    severity_assessment: Severity
    remediation_steps: list[RemediationStep] = Field(default_factory=list)
    stakeholder_comms_draft: str

    @field_validator("confidence", mode="before")
    @classmethod
    def _clamp_confidence(cls, value: Any) -> float:
        try:
            fvalue = float(value)
        except (TypeError, ValueError):
            return 0.0
        return _clamp_float(fvalue, MIN_CONFIDENCE, MAX_CONFIDENCE)

    @field_validator("remediation_steps", mode="after")
    @classmethod
    def _cap_steps(cls, steps: list[RemediationStep]) -> list[RemediationStep]:
        return steps[:MAX_REMEDIATION_STEPS]

    @classmethod
    def parse_clamped(cls, raw: dict[str, Any]) -> TriageOutput:
        """Coerce/clamp arbitrary model output into a valid :class:`TriageOutput`.

        Defensive by design: the model is untrusted, so we normalize types,
        clamp numeric ranges, cap list lengths, and truncate long strings before
        validation. Raises :class:`ValidationAppError` when the output cannot be
        salvaged into a meaningful triage result.
        """
        if not isinstance(raw, dict):
            raise ValidationAppError("Model output was not a JSON object.")

        root_cause = _coerce_required_text(raw.get("root_cause_hypothesis"))
        if root_cause is None:
            raise ValidationAppError("Model output missing a root-cause hypothesis.")

        comms = _coerce_required_text(raw.get("stakeholder_comms_draft"))
        if comms is None:
            # Communications draft is required by the contract; supply a neutral
            # placeholder rather than discarding an otherwise-usable hypothesis.
            comms = "No stakeholder communication draft was produced."

        severity = _coerce_severity(raw.get("severity_assessment"))
        steps = _coerce_steps(raw.get("remediation_steps"))

        try:
            return cls(
                root_cause_hypothesis=root_cause,
                confidence=raw.get("confidence", 0.0),
                severity_assessment=severity,
                remediation_steps=steps,
                stakeholder_comms_draft=comms,
            )
        except Exception as exc:  # pydantic ValidationError and friends
            raise ValidationAppError("Model output failed schema validation.") from exc


def _coerce_required_text(value: Any) -> str | None:
    """Return a non-empty, length-bounded string, or ``None`` when unusable."""
    if not isinstance(value, str):
        return None
    cleaned = _truncate(value, MAX_TEXT_CHARS)
    return cleaned or None


def _coerce_severity(value: Any) -> Severity:
    """Map arbitrary model severity output onto the enum, defaulting to high."""
    if isinstance(value, Severity):
        return value
    if isinstance(value, str):
        candidate = value.strip().lower()
        for member in Severity:
            if member.value == candidate:
                return member
    return Severity.high


def _coerce_steps(value: Any) -> list[RemediationStep]:
    """Coerce a list of step dicts/strings into validated, clamped steps."""
    if not isinstance(value, list):
        return []
    steps: list[RemediationStep] = []
    for item in value[:MAX_REMEDIATION_STEPS]:
        coerced = _coerce_step(item)
        if coerced is not None:
            steps.append(coerced)
    return steps


def _coerce_step(item: Any) -> RemediationStep | None:
    if isinstance(item, str):
        text = _truncate(item, MAX_STEP_CHARS)
        return RemediationStep(step=text) if text else None
    if isinstance(item, dict):
        step_text = item.get("step")
        if not isinstance(step_text, str):
            return None
        step_text = _truncate(step_text, MAX_STEP_CHARS)
        if not step_text:
            return None
        rationale = item.get("rationale")
        rationale_text = (
            _truncate(rationale, MAX_STEP_CHARS) if isinstance(rationale, str) else None
        )
        try:
            return RemediationStep(
                step=step_text,
                rationale=rationale_text or None,
                priority=item.get("priority", DEFAULT_PRIORITY),
            )
        except Exception:
            return None
    return None
