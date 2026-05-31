"""Unit tests for the QR-code rendering service (pure logic, no DB)."""

from __future__ import annotations

import pytest

from app.services.qr_service import qr_png, qr_svg

pytestmark = pytest.mark.unit

# PNG files always start with this 8-byte magic signature.
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def test_qr_png_returns_png_magic_bytes() -> None:
    # Act
    payload = qr_png("HST-7Q2KX")

    # Assert — real PNG bytes, not an empty buffer.
    assert isinstance(payload, bytes)
    assert payload.startswith(b"\x89PNG")
    assert payload.startswith(_PNG_MAGIC)
    assert len(payload) > len(_PNG_MAGIC)


def test_qr_png_differs_for_different_payloads() -> None:
    # Act — distinct short codes must encode to distinct images.
    first = qr_png("HST-AAAAA")
    second = qr_png("SVC-BBBBB")

    # Assert
    assert first != second


def test_qr_svg_returns_svg_document_string() -> None:
    # Act
    document = qr_svg("HST-7Q2KX")

    # Assert — a decoded SVG document with the expected root element.
    assert isinstance(document, str)
    assert "<svg" in document
    assert "</svg>" in document


def test_qr_svg_encodes_payload_into_a_nontrivial_document() -> None:
    # Act
    document = qr_svg("CLD-Z9X8W")

    # Assert — the SVG carries drawing instructions (a path), not just a stub.
    assert "<path" in document or "<rect" in document
    assert len(document) > len("<svg></svg>")
