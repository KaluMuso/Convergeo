FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

RUN apt-get update \
    && apt-get install --yes --no-install-recommends postgresql-client bash \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /testenv
COPY services/api/pyproject.toml services/api/uv.lock ./
RUN uv sync --frozen --dev --no-install-project

WORKDIR /workspace/services/api
ENV PATH=/testenv/.venv/bin:/usr/local/bin:/usr/local/sbin:/usr/bin:/bin
ENV PYTHONPATH=/workspace/services/api
