from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from open_graph_contracts import PluginConfig, SecretValue

from app.agent_memory import router as agent_memory_router
from app.config import get_settings
from app.datasets import router as datasets_router
from app.documents import router as documents_router
from app.graph_api import router as graph_router
from app.health import router
from app.observability import MetricsMiddleware
from app.plugin_registry import create_graph_store
from app.projects import router as projects_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    structlog.configure(processors=[structlog.processors.JSONRenderer()])
    settings = get_settings()
    graph_store = create_graph_store(
        PluginConfig(
            {"url": settings.neo4j_url},
            {"auth": SecretValue(settings.neo4j_auth.get_secret_value())},
        )
    )
    await graph_store.bootstrap()
    yield


app = FastAPI(title="OpenGraphRAG API", version="0.1.0", lifespan=lifespan)
app.add_middleware(MetricsMiddleware)
app.include_router(router)
app.include_router(projects_router)
app.include_router(datasets_router)
app.include_router(documents_router)
app.include_router(graph_router)
app.include_router(agent_memory_router)
