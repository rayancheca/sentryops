"""Platform endpoints: liveness, readiness, and Prometheus metrics (no envelope)."""

from __future__ import annotations

from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.db.session import engine

platform_router = APIRouter(tags=["platform"])


@platform_router.get("/health", summary="Liveness probe")
def health() -> dict[str, str]:
    return {"status": "ok"}


@platform_router.get("/ready", summary="Readiness probe (verifies the database)")
def ready() -> Response:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse(status_code=503, content={"status": "not_ready"})
    return JSONResponse(status_code=200, content={"status": "ready"})


@platform_router.get("/metrics", summary="Prometheus exposition", include_in_schema=False)
def metrics() -> Response:
    # Imported lazily so liveness/readiness never depend on the metrics collector.
    from app.services.metrics_service import render_metrics

    body, content_type = render_metrics()
    return Response(content=body, media_type=content_type)
