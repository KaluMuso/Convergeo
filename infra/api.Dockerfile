# syntax=docker/dockerfile:1

# Multi-stage API image for Vergeo5 (build context: repo root)
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app

COPY services/api/pyproject.toml services/api/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY services/api/ ./
RUN uv sync --frozen --no-dev

FROM python:3.12-slim-bookworm AS runtime

ARG GIT_SHA=unknown
ARG API_IMAGE_TAG=unknown

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    GIT_SHA=${GIT_SHA} \
    API_IMAGE_TAG=${API_IMAGE_TAG}

RUN groupadd --system vergeo && useradd --system --gid vergeo --create-home vergeo

WORKDIR /app

COPY --from=builder --chown=vergeo:vergeo /app /app

USER vergeo

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
