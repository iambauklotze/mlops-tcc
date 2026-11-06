# syntax=docker/dockerfile:1

# ---- build stage: resolve locked dependencies into a virtualenv
FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# ---- runtime stage: minimal image, non-root, no secrets baked in
FROM python:3.12-slim
# UID/GID match the host user so the bind-mounted ./data stays writable.
ARG APP_UID=1000
ARG APP_GID=1000
RUN groupadd --gid ${APP_GID} app && \
    useradd --uid ${APP_UID} --gid ${APP_GID} --no-create-home --shell /usr/sbin/nologin app
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY ingest/ ingest/
COPY scripts/ scripts/
COPY config/ config/
ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
USER app
CMD ["python", "-m", "ingest.collector", "--config", "config/collect.yaml"]
