# syntax=docker/dockerfile:1
# ---- Builder: resolve and install dependencies into an isolated venv --------
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build
COPY pyproject.toml ./
COPY app ./app

RUN python -m venv /venv \
    && /venv/bin/pip install --upgrade pip \
    && /venv/bin/pip install .

# ---- Runtime: slim image, non-root, source mounted at /app ------------------
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/venv/bin:$PATH" \
    PYTHONPATH=/app

# curl is used by container/compose healthchecks and the demo wait-loop.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r app && useradd -r -g app -d /app app

WORKDIR /app
COPY --from=builder /venv /venv
COPY app ./app
COPY scripts ./scripts
COPY alembic.ini ./

USER app
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
