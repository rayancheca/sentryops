"""RQ queue and Redis connection for background jobs (AI triage)."""

from __future__ import annotations

from redis import Redis
from rq import Queue

from app.core.config import get_settings

_settings = get_settings()

redis_conn = Redis.from_url(_settings.redis_url)
triage_queue = Queue("triage", connection=redis_conn, default_timeout=120)
