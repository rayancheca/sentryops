"""Thin, test-friendly wrapper around the Anthropic Messages API for triage.

Security notes:
- The API key is read from settings and handed only to the SDK constructor. It
  is NEVER logged, returned, or placed in an exception message.
- The full prompt body is NEVER logged (it may contain sensitive operational
  data). Only coarse metadata (token counts, model) is suitable for logging by
  callers.
- The model response is parsed defensively: we extract the first balanced JSON
  object from the text rather than trusting it to be clean JSON.
- The actual SDK call is isolated in :meth:`_invoke` so tests can monkeypatch a
  single method without a network call.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import structlog

from app.core.config import get_settings
from app.core.exceptions import ValidationAppError

log = structlog.get_logger(__name__)

# Per-million-token USD prices. Approximate, documented, and intentionally
# conservative; used only for cost estimation/observability, not billing.
# Keyed by a substring matched against the model id.
_PRICE_TABLE: dict[str, tuple[float, float]] = {
    # model-id substring: (input $/Mtok, output $/Mtok)
    "opus": (15.0, 75.0),
    "sonnet": (3.0, 15.0),
    "haiku": (0.80, 4.0),
}
_DEFAULT_PRICE: tuple[float, float] = (3.0, 15.0)
_TOKENS_PER_MILLION = 1_000_000.0


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate USD cost for a call from a small, documented price table.

    Falls back to a default mid-tier price when the model id is unrecognized.
    """
    in_price, out_price = _DEFAULT_PRICE
    lowered = model.lower()
    for needle, prices in _PRICE_TABLE.items():
        if needle in lowered:
            in_price, out_price = prices
            break
    cost = (input_tokens * in_price + output_tokens * out_price) / _TOKENS_PER_MILLION
    return round(cost, 6)


@dataclass(slots=True)
class _RawResponse:
    text: str
    input_tokens: int
    output_tokens: int


class AnthropicTriageClient:
    """Calls Claude for incident triage and returns parsed JSON + token counts."""

    def __init__(self) -> None:
        self._settings = get_settings()

    def call(self, system: str, user: str) -> tuple[dict[str, Any], int, int]:
        """Run a triage completion.

        Returns ``(parsed_json, input_tokens, output_tokens)``. Raises
        :class:`ValidationAppError` if the response contains no parseable JSON
        object. Never logs the key or the prompt body.
        """
        raw = self._invoke(system=system, user=user)
        parsed = _extract_json_object(raw.text)
        log.info(
            "ai_triage_call_complete",
            model=self._settings.anthropic_model,
            input_tokens=raw.input_tokens,
            output_tokens=raw.output_tokens,
        )
        return parsed, raw.input_tokens, raw.output_tokens

    def _invoke(self, *, system: str, user: str) -> _RawResponse:
        """Isolated SDK call. Tests monkeypatch THIS method (no network needed)."""
        from anthropic import Anthropic

        client = Anthropic(api_key=self._settings.anthropic_api_key)
        message = client.messages.create(
            model=self._settings.anthropic_model,
            max_tokens=self._settings.ai_max_output_tokens,
            system=system,
            messages=[
                {
                    "role": "user",
                    "content": user,
                },
                {
                    # Prefill an opening brace to steer the model toward emitting
                    # a single JSON object as required by the contract.
                    "role": "assistant",
                    "content": "{",
                },
            ],
        )
        text = _join_text_blocks(message)
        # The prefill "{" is not echoed in the response, so restore it.
        if not text.lstrip().startswith("{"):
            text = "{" + text
        usage = getattr(message, "usage", None)
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        return _RawResponse(text=text, input_tokens=input_tokens, output_tokens=output_tokens)


def _join_text_blocks(message: Any) -> str:
    """Concatenate text from the SDK message's content blocks, defensively."""
    content = getattr(message, "content", None)
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            parts.append(text)
        elif isinstance(block, dict) and isinstance(block.get("text"), str):
            parts.append(block["text"])
    return "".join(parts)


def _extract_json_object(text: str) -> dict[str, Any]:
    """Extract the first balanced top-level JSON object from arbitrary text.

    The model is instructed to return pure JSON, but we never trust that. We
    first try a direct parse, then scan for a brace-balanced object (ignoring
    braces inside strings). Raises :class:`ValidationAppError` on failure.
    """
    stripped = text.strip()
    try:
        loaded = json.loads(stripped)
        if isinstance(loaded, dict):
            return loaded
    except (json.JSONDecodeError, ValueError):
        pass

    candidate = _scan_balanced_object(stripped)
    if candidate is not None:
        try:
            loaded = json.loads(candidate)
            if isinstance(loaded, dict):
                return loaded
        except (json.JSONDecodeError, ValueError):
            pass

    raise ValidationAppError("Model response did not contain a JSON object.")


def _scan_balanced_object(text: str) -> str | None:
    """Return the substring of the first brace-balanced object, or ``None``."""
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None
