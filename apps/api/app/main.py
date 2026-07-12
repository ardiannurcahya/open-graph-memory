from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from qdrant_client import AsyncQdrantClient

from app.config import get_settings
from app.datasets import router as datasets_router
from app.documents import router as documents_router
from app.health import router
from app.projects import router as projects_router
from app.providers import DeterministicProvider, OpenAIChatProvider, OpenAIEmbeddingProvider
from app.query import router as query_router
from app.runtime import Runtime, clear_runtime, install_runtime
from app.vector_store import QdrantVectorStore


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    structlog.configure(processors=[structlog.processors.JSONRenderer()])
    settings = get_settings()
    deterministic = DeterministicProvider(settings.embedding_dimensions)
    embedding_provider = (
        deterministic
        if settings.embedding_provider == "deterministic"
        else OpenAIEmbeddingProvider(
            settings.openai_base_url,
            settings.openai_api_key.get_secret_value(),
            settings.embedding_dimensions,
        )
    )
    chat_provider = (
        deterministic
        if settings.chat_provider == "deterministic"
        else OpenAIChatProvider(
            settings.openai_base_url, settings.openai_api_key.get_secret_value()
        )
    )
    qdrant = AsyncQdrantClient(
        url=settings.qdrant_url, api_key=settings.qdrant_api_key.get_secret_value() or None
    )
    vector_store = QdrantVectorStore(
        qdrant, settings.qdrant_collection, settings.embedding_dimensions
    )
    await vector_store.setup()
    install_runtime(Runtime(embedding_provider, chat_provider, vector_store))
    try:
        yield
    finally:
        clear_runtime()
        for provider in {
            id(embedding_provider): embedding_provider,
            id(chat_provider): chat_provider,
        }.values():
            close = getattr(provider, "close", None)
            if close is not None:
                await close()
        await qdrant.close()


app = FastAPI(title="OpenGraphRAG API", version="0.1.0", lifespan=lifespan)
app.include_router(router)
app.include_router(projects_router)
app.include_router(datasets_router)
app.include_router(documents_router)
app.include_router(query_router)
