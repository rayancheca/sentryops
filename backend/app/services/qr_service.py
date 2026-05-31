"""QR-code rendering for asset labels, backed by segno (pure-Python, no native deps).

The default payload is an asset's ``short_code`` so a scanned label maps straight
back to the CMDB record.
"""

from __future__ import annotations

import io

import segno

# Medium error correction: legible after the inevitable scuffs on a printed label.
_ERROR_CORRECTION = "m"
_PNG_SCALE = 6
_PNG_BORDER = 2
_SVG_SCALE = 4
_SVG_BORDER = 2


def qr_png(payload: str) -> bytes:
    """Render ``payload`` as a PNG byte string."""
    qr = segno.make(payload, error=_ERROR_CORRECTION)
    buffer = io.BytesIO()
    qr.save(buffer, kind="png", scale=_PNG_SCALE, border=_PNG_BORDER)
    return buffer.getvalue()


def qr_svg(payload: str) -> str:
    """Render ``payload`` as an SVG document string."""
    qr = segno.make(payload, error=_ERROR_CORRECTION)
    buffer = io.BytesIO()
    qr.save(buffer, kind="svg", scale=_SVG_SCALE, border=_SVG_BORDER)
    return buffer.getvalue().decode("utf-8")
