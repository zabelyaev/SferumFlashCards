# syntax=docker/dockerfile:1

FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS base

RUN groupadd --system --gid 999 nonroot \
 && useradd --system --gid 999 --uid 999 --create-home nonroot

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1 \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --locked --no-dev --no-install-project

COPY --chown=nonroot:nonroot src /app/src

FROM base AS test

ENV UV_NO_DEV=0 \
    PYTEST_ADDOPTS="-p no:cacheprovider"

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --locked --no-install-project --group dev

COPY --chown=nonroot:nonroot pyproject.toml uv.lock Dockerfile /app/
COPY --chown=nonroot:nonroot tests /app/tests

USER nonroot

CMD ["python", "-m", "pytest", "-q", "-ra", "tests"]

FROM base AS optimizer

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --locked --no-dev --no-install-project --extra fsrs-optimizer

USER nonroot
CMD ["python", "-m", "cli.fsrs_scheduler"]

FROM base AS api

USER nonroot

EXPOSE 8000

CMD ["python", "src/main.py"]
