from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from app.agent_memory import router as agent_memory_router
from app.audit import router as audit_router
from app.codebase import router as codebase_router
from app.datasets import router as datasets_router
from app.documents import router as documents_router
from app.export_import import router as export_import_router
from app.graph_api import router as graph_router
from app.health import router
from app.legal_hold import router as legal_hold_router
from app.mcp_server import router as mcp_router
from app.observability import MetricsMiddleware
from app.projects import router as projects_router
from app.retention import router as retention_router


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
app.include_router(legal_hold_router)
app.include_router(retention_router)
app.include_router(audit_router)
app.include_router(export_import_router)
app.include_router(mcp_router)
app.include_router(codebase_router)
