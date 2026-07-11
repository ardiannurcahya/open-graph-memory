FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv && uv sync --frozen --no-dev
COPY apps/api/app ./app
COPY apps/worker/worker ./worker
COPY packages/core/src ./packages/core/src
ENV PATH="/app/.venv/bin:$PATH" PYTHONPATH="/app/packages/core/src"
USER 65532
CMD ["celery","-A","worker.main.celery_app","worker","--loglevel=INFO","--concurrency=1"]
