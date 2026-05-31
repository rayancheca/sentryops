"""Rate limiting via slowapi, backed by Redis so limits hold across replicas."""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import get_settings

_settings = get_settings()

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=_settings.redis_url,
    default_limits=[],
    # Headers disabled: enabling them requires every limited route to declare a
    # `response: Response` param. Enforcement (429 on exceed) is unaffected.
    headers_enabled=False,
)

# Convenience handles for decorators on auth + scan endpoints.
AUTH_LIMIT = _settings.rate_limit_auth
SCAN_LIMIT = _settings.rate_limit_scan
