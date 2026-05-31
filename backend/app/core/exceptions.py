"""Typed application exceptions and a consistent API error envelope."""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = structlog.get_logger(__name__)


class AppError(Exception):
    """Base for expected, mapped application errors."""

    status_code: int = 500
    code: str = "internal_error"

    def __init__(self, message: str, *, details: Any | None = None) -> None:
        self.message = message
        self.details = details
        super().__init__(message)


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class PermissionDeniedError(AppError):
    status_code = 403
    code = "forbidden"


class AuthError(AppError):
    status_code = 401
    code = "unauthorized"


class ValidationAppError(AppError):
    status_code = 422
    code = "validation_error"


class FeatureDisabledError(AppError):
    status_code = 409
    code = "feature_disabled"


def error_body(
    code: str, message: str, *, details: Any | None = None, request_id: str | None = None
) -> dict[str, Any]:
    """The single error shape every endpoint returns (mirrors the success envelope)."""
    return {
        "success": False,
        "data": None,
        "error": {"code": code, "message": message, "details": details},
        "meta": {"request_id": request_id},
    }


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(
                exc.code, exc.message, details=exc.details, request_id=_request_id(request)
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=error_body(
                "validation_error",
                "Request validation failed.",
                details=exc.errors(),
                request_id=_request_id(request),
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(
                "http_error",
                str(exc.detail),
                request_id=_request_id(request),
            ),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # Detailed context is logged server-side; the client gets a generic message.
        log.error("unhandled_exception", error=str(exc), path=request.url.path)
        return JSONResponse(
            status_code=500,
            content=error_body(
                "internal_error",
                "An unexpected error occurred.",
                request_id=_request_id(request),
            ),
        )
