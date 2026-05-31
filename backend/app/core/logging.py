"""Structured JSON logging with request-ID propagation."""

from __future__ import annotations

import logging
import sys
from collections.abc import MutableMapping
from contextvars import ContextVar
from typing import Any

import structlog

from app.core.config import get_settings

# Bound per request by RequestIDMiddleware; included in every log line.
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


def _add_request_id(
    _logger: Any, _name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    rid = request_id_var.get()
    if rid:
        event_dict["request_id"] = rid
    return event_dict


def configure_logging() -> None:
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    renderer: Any = (
        structlog.processors.JSONRenderer()
        if settings.is_production
        else structlog.dev.ConsoleRenderer()
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _add_request_id,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)
