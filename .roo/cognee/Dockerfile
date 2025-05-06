FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ARG BUILD_PATH
WORKDIR ${BUILD_PATH}

COPY .roo/cognee/pyproject.toml ./.roo/cognee/uv.lock* ${BUILD_PATH}

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

RUN uv venv ${BUILD_PATH}/.venv --python python3.12

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-editable --no-install-project --python ${BUILD_PATH}/.venv/bin/python
        # --no-dev

#COPY ./.roo/cognee/src ${BUILD_PATH}/src

#RUN --mount=type=cache,target=/root/.cache/uv \
#   uv pip install --python ${BUILD_PATH}/.venv/bin/python .

FROM python:3.12-slim-bookworm

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libpq5 \
        git && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

ARG BUILD_PATH
ARG WORKSPACE_PATH
WORKDIR ${WORKSPACE_PATH}

COPY --from=builder ${BUILD_PATH}/.venv ${BUILD_PATH}/.venv

COPY .roo/cognee/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["/entrypoint.sh"]
#ENTRYPOINT ["cognee-mcp"]
