FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ARG FINAL_VENV_PATH=/.roo/cognee/.venv
WORKDIR /build_tmp

ENV UV_LINK_MODE=copy

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    git \
    gcc \
    libpq-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

RUN uv venv ${FINAL_VENV_PATH}

COPY ./.roo/cognee/pyproject.toml* ./.roo/cognee/uv.lock* /build_tmp/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable --no-install-project --python ${FINAL_VENV_PATH}/bin/python

COPY ./.roo/cognee/src /build_tmp/src

RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --python ${FINAL_VENV_PATH}/bin/python .

FROM python:3.12-slim-bookworm

ARG FINAL_VENV_PATH=/.roo/cognee/.venv

RUN apt-get update && \
    apt-get install -y --no-install-recommends libpq5 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

COPY --from=builder ${FINAL_VENV_PATH} ${FINAL_VENV_PATH}

ENV PATH="${FINAL_VENV_PATH}/bin:$PATH"
ENV PYTHONPATH=/workspace/.roo/cognee
ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["cognee"]
