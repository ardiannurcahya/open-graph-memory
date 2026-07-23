FROM python:3.12-slim
WORKDIR /app
ARG UV_VERSION=0.11.31
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,id=opengraphrag-pip,target=/root/.cache/pip,sharing=locked \
    --mount=type=cache,id=opengraphrag-uv,target=/root/.cache/uv,sharing=locked \
    pip install "uv==${UV_VERSION}" && uv sync --frozen --no-dev
COPY apps/api/app ./app
COPY apps/worker/worker ./worker
COPY packages/core/src ./packages/core/src
COPY packages/contracts/src ./packages/contracts/src
ENV PATH="/app/.venv/bin:$PATH" PYTHONPATH="/app:/app/packages/core/src:/app/packages/contracts/src"
USER 65532
CMD ["arq","app.arq_worker.WorkerSettings"]
