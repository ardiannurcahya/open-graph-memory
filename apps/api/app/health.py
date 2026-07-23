import asyncio

import boto3
from botocore.config import Config
from fastapi import APIRouter, Response, status
from redis.asyncio import Redis
from sqlalchemy import text

from app.config import get_settings
from app.db import engine
from app.observability import render_metrics

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    return Response(render_metrics(), media_type="text/plain; version=0.0.4")


async def checks() -> dict[str, bool]:
    cfg = get_settings()
    timeout = cfg.readiness_timeout_seconds

    async def postgres() -> bool:
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    async def redis() -> bool:
        client = Redis.from_url(
            cfg.redis_url, socket_connect_timeout=timeout, socket_timeout=timeout
        )
        try:
            return bool(await client.ping())
        except Exception:
            return False
        finally:
            await client.aclose()

    async def s3() -> bool:
        def bucket_exists() -> bool:
            client = boto3.client(
                "s3",
                endpoint_url=cfg.s3_endpoint_url,
                aws_access_key_id=cfg.s3_access_key,
                aws_secret_access_key=cfg.s3_secret_key.get_secret_value(),
                config=Config(
                    connect_timeout=timeout,
                    read_timeout=timeout,
                    retries={"max_attempts": 1},
                    s3={"addressing_style": "path" if cfg.s3_force_path_style else "virtual"},
                ),
            )
            client.head_bucket(Bucket=cfg.s3_bucket)
            return True

        try:
            return await asyncio.wait_for(asyncio.to_thread(bucket_exists), timeout=timeout)
        except Exception:
            return False

    values = await asyncio.gather(
        asyncio.wait_for(postgres(), timeout=timeout),
        asyncio.wait_for(redis(), timeout=timeout),
        s3(),
        return_exceptions=True,
    )
    names = ("postgres", "redis", "s3")
    return {name: value is True for name, value in zip(names, values, strict=True)}


@router.get("/ready")
async def ready(response: Response) -> dict[str, object]:
    result = await checks()
    is_ready = all(result.values())
    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ready" if is_ready else "not_ready", "checks": result}
