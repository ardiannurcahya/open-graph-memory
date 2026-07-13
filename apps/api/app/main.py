from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast

import structlog
from fastapi import FastAPI
from open_graph_contracts import ChatProvider, PluginConfig, SecretValue

from app.config import get_settings
from app.datasets import router as datasets_router
from app.documents import router as documents_router
from app.graph_api import router as graph_router
from app.health import router
from app.plugin_registry import (
    create_chat,
    create_embedding,
    create_graph_store,
    create_vector_store,
)
from app.projects import router as projects_router
from app.query import router as query_router
from app.runtime import Runtime, clear_runtime, install_runtime


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    structlog.configure(processors=[structlog.processors.JSONRenderer()])
    settings = get_settings()
    provider_config = PluginConfig(
        {"base_url": settings.openai_base_url, "dimensions": settings.embedding_dimensions},
        {"api_key": SecretValue(settings.openai_api_key.get_secret_value())},
    )
    embedding_provider = create_embedding(settings.embedding_provider, provider_config)
    chat_provider: ChatProvider = (
        cast(ChatProvider, embedding_provider)
        if settings.chat_provider == "deterministic"
        and settings.embedding_provider == "deterministic"
        else create_chat(settings.chat_provider, provider_config)
    )
    vector_store = create_vector_store(
        PluginConfig(
            {
                "url": settings.qdrant_url,
                "collection": settings.qdrant_collection,
                "dimensions": settings.embedding_dimensions,
            },
            {"api_key": SecretValue(settings.qdrant_api_key.get_secret_value())},
        )
    )
    await vector_store.setup()
    graph_store = create_graph_store(
        PluginConfig(
            {"url": settings.neo4j_url},
            {"auth": SecretValue(settings.neo4j_auth.get_secret_value())},
        )
    )
    await graph_store.bootstrap()
    install_runtime(Runtime(embedding_provider, chat_provider, vector_store, graph_store))
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
        await vector_store.client.close()


app = FastAPI(title="OpenGraphRAG API", version="0.1.0", lifespan=lifespan)
app.include_router(router)
app.include_router(projects_router)
app.include_router(datasets_router)
app.include_router(documents_router)
app.include_router(query_router)
app.include_router(graph_router)
