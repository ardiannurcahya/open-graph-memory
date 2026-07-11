FROM python:3.12-slim AS runtime
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv && uv sync --frozen --no-dev
COPY apps/api/app ./app
COPY apps/api/migrations ./migrations
COPY apps/api/alembic.ini ./alembic.ini
COPY packages/core/src ./packages/core/src
ENV PATH="/app/.venv/bin:$PATH" PYTHONPATH="/app/packages/core/src"
USER 65532
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]
