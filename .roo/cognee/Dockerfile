FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS uv

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1

ENV UV_LINK_MODE=copy

RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev

# Verify uv installation
# Verify uv installation (Removed as per previous discussion)
# RUN uv --version
# RUN which uv

COPY .roo/cognee/pyproject.toml .roo/cognee/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-install-project --no-dev --no-editable

# Try copying the specific env file instead of using a wildcard
COPY .env.devcontainer /app/
COPY .roo/cognee /app
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-editable

FROM python:3.12-slim-bookworm

WORKDIR /app

# Copy the virtual environment created by uv in the first stage
COPY --from=uv /app/.venv /app/.venv
# Copy the application code from the first stage
COPY --from=uv /app /app

# Ensure the virtual environment's bin directory is in the PATH
ENV PATH="/app/.venv/bin:$PATH"

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

ENTRYPOINT ["cognee"]
