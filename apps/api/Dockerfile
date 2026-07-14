FROM python:3.12-slim AS runtime
WORKDIR /app
ARG UV_VERSION=0.6.3
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,id=opengraphrag-pip,target=/root/.cache/pip,sharing=locked \
    --mount=type=cache,id=opengraphrag-uv,target=/root/.cache/uv,sharing=locked \
    pip install "uv==${UV_VERSION}" && uv sync --frozen --no-dev
COPY apps/api/app ./app
COPY apps/api/migrations ./migrations
COPY apps/api/alembic.ini ./alembic.ini
COPY packages/core/src ./packages/core/src
COPY packages/contracts/src ./packages/contracts/src
ENV PATH="/app/.venv/bin:$PATH" PYTHONPATH="/app:/app/packages/core/src:/app/packages/contracts/src"
USER 65532
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]
