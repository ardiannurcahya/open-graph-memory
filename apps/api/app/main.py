from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from app.agent_memory import router as agent_memory_router
from app.datasets import router as datasets_router
from app.documents import router as documents_router
from app.graph_api import router as graph_router
from app.health import router
from app.observability import MetricsMiddleware
from app.projects import router as projects_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    structlog.configure(processors=[structlog.processors.JSONRenderer()])
    yield


app = FastAPI(title="OpenGraphRAG API", version="0.1.0", lifespan=lifespan)
app.add_middleware(MetricsMiddleware)
app.include_router(router)
app.include_router(projects_router)
app.include_router(datasets_router)
app.include_router(documents_router)
app.include_router(graph_router)
app.include_router(agent_memory_router)
