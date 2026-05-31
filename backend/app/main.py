"""FastAPI application factory and wiring."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.platform import platform_router
from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestIDMiddleware, SecurityHeadersMiddleware
from app.core.rate_limit import limiter


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()

    app = FastAPI(
        title="SentryOps API",
        version="0.1.0",
        summary="Self-hosted IT operations command center.",
        docs_url="/docs",
        redoc_url=None,
        openapi_url="/openapi.json",
    )

    # Rate limiting (slowapi) — used on auth + scan endpoints.
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]  # slowapi handler signature is intentionally broad

    # Middleware runs bottom-up: request-ID is outermost so logs are tagged.
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(RequestIDMiddleware)

    register_exception_handlers(app)

    app.include_router(platform_router)
    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
