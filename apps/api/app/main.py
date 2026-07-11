from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from app.health import router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    structlog.configure(processors=[structlog.processors.JSONRenderer()])
    yield


app = FastAPI(title="OpenGraphRAG API", version="0.1.0", lifespan=lifespan)
app.include_router(router)
