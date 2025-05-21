FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ARG WEB_WORKSPACE_PATH
ARG WEB_WORKSPACE_USER
ARG WORKSPACE_PATH

ARG BUILD_PATH
ARG WEB_COGNEE_BUILD_CONTEXT_PATH
WORKDIR ${BUILD_PATH}

COPY ${WEB_COGNEE_BUILD_CONTEXT_PATH}/.roo/cognee/pyproject.toml ${WEB_COGNEE_BUILD_CONTEXT_PATH}/.roo/cognee/uv.lock* ${BUILD_PATH}

ENV UV_LINK_MODE=copy

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    git \
    gcc \
    rustc \
    cargo \
    libpq-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

RUN uv venv "${WORKSPACE_PATH}${WEB_WORKSPACE_PATH}/.roo/cognee/.venv" --python python3.12

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-editable --no-install-project --python "${WORKSPACE_PATH}${WEB_WORKSPACE_PATH}/.roo/cognee/.venv/bin/python" --project "${BUILD_PATH}"

FROM python:3.12-slim-bookworm

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libpq5 \
        git && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

ARG BUILD_PATH
ARG WORKSPACE_PATH
ARG WEB_WORKSPACE_PATH
WORKDIR ${WORKSPACE_PATH}${WEB_WORKSPACE_PATH}

COPY --from=builder "${WORKSPACE_PATH}${WEB_WORKSPACE_PATH}/.roo/cognee/.venv" ${BUILD_PATH}/.venv

COPY .roo/cognee/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENV PYTHONUNBUFFERED=1
ENV PATH="${WORKSPACE_PATH}${WEB_WORKSPACE_PATH}/.roo/cognee/.venv/bin:$PATH"

ENTRYPOINT ["/entrypoint.sh"]
#ENTRYPOINT ["cognee-mcp"]
