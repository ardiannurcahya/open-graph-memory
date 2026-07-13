import asyncio
from typing import IO, Protocol

import boto3
from open_graph_contracts import PluginConfig, SecretValue

from app.config import Settings, get_settings


class ObjectStore(Protocol):
    async def upload(self, key: str, stream: IO[bytes], content_type: str) -> None: ...
    async def download(self, key: str) -> bytes: ...
    async def delete(self, key: str) -> None: ...


class S3ObjectStore:
    def __init__(self, settings: Settings) -> None:
        self.bucket = settings.s3_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key.get_secret_value(),
            region_name=settings.s3_region,
        )

    @classmethod
    def from_plugin_config(cls, config: PluginConfig) -> "S3ObjectStore":
        instance = cls.__new__(cls)
        bucket = config.require("bucket")
        endpoint_url = config.require("endpoint_url")
        access_key = config.require("access_key")
        region = config.require("region")
        if not isinstance(bucket, str) or not all(
            isinstance(value, str) for value in (endpoint_url, access_key, region)
        ):
            raise TypeError("S3 config values must be strings")
        instance.bucket = bucket
        instance.client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=config.require_secret("secret_key").get(),
            region_name=region,
        )
        return instance

    async def upload(self, key: str, stream: IO[bytes], content_type: str) -> None:
        await asyncio.to_thread(
            self.client.upload_fileobj,
            stream,
            self.bucket,
            key,
            ExtraArgs={"ContentType": content_type},
        )

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self.client.delete_object, Bucket=self.bucket, Key=key)

    async def download(self, key: str) -> bytes:
        response = await asyncio.to_thread(self.client.get_object, Bucket=self.bucket, Key=key)
        return await asyncio.to_thread(response["Body"].read)


def get_object_store() -> ObjectStore:
    settings = get_settings()
    from app.plugin_registry import create_object_store

    return create_object_store(
        PluginConfig(
            {
                "bucket": settings.s3_bucket,
                "endpoint_url": settings.s3_endpoint_url,
                "access_key": settings.s3_access_key,
                "region": settings.s3_region,
            },
            {"secret_key": SecretValue(settings.s3_secret_key.get_secret_value())},
        )
    )
