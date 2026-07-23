from __future__ import annotations

import asyncio
import base64
import json
import urllib.error
import urllib.request

import boto3
from app.config import get_settings
from botocore.config import Config
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def check_async_dependencies() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    async with engine.connect() as connection:
        if (await connection.execute(text("SELECT 1"))).scalar() != 1:
            raise RuntimeError("PostgreSQL preflight failed")
    await engine.dispose()

    redis = Redis.from_url(settings.redis_url)
    if not await redis.ping():
        raise RuntimeError("Redis preflight failed")
    await redis.aclose()


def check_neo4j() -> None:
    settings = get_settings()
    username, password = settings.neo4j_auth.get_secret_value().split("/", 1)
    auth = base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
    request = urllib.request.Request(
        f"{settings.neo4j_url}/db/neo4j/tx/commit",
        data=json.dumps({"statements": [{"statement": "RETURN 1 AS ok"}]}).encode(),
        headers={"Authorization": f"Basic {auth}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        raise RuntimeError(error.read().decode("utf-8")) from error
    if result["errors"]:
        raise RuntimeError(f"Neo4j preflight failed: {result['errors']}")
    if result["results"][0]["data"][0]["row"] != [1]:
        raise RuntimeError("Neo4j preflight returned an unexpected result")


def check_cos() -> None:
    settings = get_settings()
    client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key.get_secret_value(),
        region_name=settings.s3_region,
        config=Config(s3={"addressing_style": "virtual"}),
    )
    client.head_bucket(Bucket=settings.s3_bucket)


def main() -> None:
    get_settings()
    asyncio.run(check_async_dependencies())
    check_neo4j()
    check_cos()
    print("preflight passed")


if __name__ == "__main__":
    main()
