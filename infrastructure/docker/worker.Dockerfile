# Inland Resilience worker image: same Python, same dependencies, on any machine.
# Build context is the repo root (the worker's tests read /contracts).
#   docker compose -f infrastructure/docker-compose.yml build worker

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /repo/apps/worker

# 1) dependencies only: cached until pyproject.toml / uv.lock change
COPY apps/worker/pyproject.toml apps/worker/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-install-project

# 2) the code and the shared contracts
COPY contracts /repo/contracts
COPY apps/worker /repo/apps/worker
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen

# never run as root
RUN useradd --create-home --uid 10001 app && chown -R app /repo
USER app

ENTRYPOINT ["python", "-m", "inland_worker"]
CMD ["providers"]
