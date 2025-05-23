FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ARG WEB_WORKSPACE_PATH
ARG WORKSPACE_PATH

WORKDIR ${WORKSPACE_PATH}${WEB_WORKSPACE_PATH}

COPY .roo/cognee/pyproject.toml .roo/cognee/uv.lock* ${WORKSPACE_PATH}${WEB_WORKSPACE_PATH}/.roo/cognee/

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

RUN uv venv ${WORKSPACE_PATH}${WEB_WORKSPACE_PATH}/.roo/cognee/.venv --python python3.12

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync  --frozen --no-editable --no-install-project \
            --python ${WORKSPACE_PATH}${WEB_WORKSPACE_PATH}/.roo/cognee/.venv/bin/python \
            --project ${WORKSPACE_PATH}${WEB_WORKSPACE_PATH}/.roo/cognee

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

COPY --from=builder ${WORKSPACE_PATH}${WEB_WORKSPACE_PATH}/.roo/cognee/.venv" "${BUILD_PATH}/.venv

COPY .roo/cognee/entrypoint.sh ${BUILD_PATH}/entrypoint.sh
RUN chmod +x ${BUILD_PATH}/entrypoint.sh
ENTRYPOINT ["/bin/sh", "-c", "exec \"$BUILD_PATH/entrypoint.sh\" \"$@\"", "_"]

ENV PYTHONUNBUFFERED=1
ENV PATH=${WORKSPACE_PATH}${WEB_WORKSPACE_PATH}/.roo/cognee/.venv/bin:$PATH
