"""Unit tests for defensive JSON extraction and cost estimation (no network)."""

from __future__ import annotations

import pytest

from app.ai.client import (
    AnthropicTriageClient,
    _extract_json_object,
    _RawResponse,
    _scan_balanced_object,
    estimate_cost,
)
from app.core.exceptions import ValidationAppError


def test_extract_clean_json() -> None:
    assert _extract_json_object('{"a": 1}') == {"a": 1}


def test_extract_json_with_surrounding_prose() -> None:
    text = 'Here is my analysis:\n{"root": "cause", "n": 2}\nThanks!'
    assert _extract_json_object(text) == {"root": "cause", "n": 2}


def test_extract_json_ignores_braces_inside_strings() -> None:
    text = '{"msg": "a } brace { inside", "k": 1}'
    expected: dict[str, object] = {"msg": "a } brace { inside", "k": 1}
    assert _extract_json_object(text) == expected


def test_scan_balanced_handles_nested_objects() -> None:
    text = 'prefix {"outer": {"inner": [1,2]}} suffix'
    found = _scan_balanced_object(text)
    assert found == '{"outer": {"inner": [1,2]}}'


def test_extract_raises_when_no_object() -> None:
    with pytest.raises(ValidationAppError):
        _extract_json_object("no json here at all")


def test_extract_raises_on_array_only() -> None:
    # A top-level array is not the required object.
    with pytest.raises(ValidationAppError):
        _extract_json_object("[1, 2, 3]")


def test_estimate_cost_sonnet() -> None:
    # 1M input + 1M output at sonnet pricing (3 + 15).
    assert estimate_cost("claude-sonnet-4-6", 1_000_000, 1_000_000) == pytest.approx(18.0)


def test_estimate_cost_unknown_model_uses_default() -> None:
    cost = estimate_cost("some-future-model", 1_000_000, 0)
    assert cost == pytest.approx(3.0)


def test_estimate_cost_zero_tokens() -> None:
    assert estimate_cost("claude-haiku", 0, 0) == 0.0


def test_call_parses_invoke_result(monkeypatch: pytest.MonkeyPatch) -> None:
    client = AnthropicTriageClient()
    monkeypatch.setattr(
        AnthropicTriageClient,
        "_invoke",
        lambda self, *, system, user: _RawResponse(
            text='{"root_cause_hypothesis": "x"}', input_tokens=11, output_tokens=22
        ),
    )
    parsed, in_tok, out_tok = client.call("sys", "usr")
    assert parsed == {"root_cause_hypothesis": "x"}
    assert (in_tok, out_tok) == (11, 22)
