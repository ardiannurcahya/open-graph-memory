import asyncio
from pathlib import Path
from typing import IO, Protocol

import boto3
from botocore.config import Config
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
            config=Config(
                s3={"addressing_style": "path" if settings.s3_force_path_style else "virtual"}
            ),
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
        force_path_style = config.get("force_path_style", True)
        if not isinstance(force_path_style, bool):
            raise TypeError("force_path_style must be a boolean")
        instance.bucket = bucket
        instance.client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=config.require_secret("secret_key").get(),
            region_name=region,
            config=Config(s3={"addressing_style": "path" if force_path_style else "virtual"}),
        )
        return instance

    async def upload(self, key: str, stream: IO[bytes], content_type: str) -> None:
        position = stream.tell()
        stream.seek(0, 2)
        content_length = stream.tell() - position
        stream.seek(position)
        await asyncio.to_thread(
            self.client.put_object,
            Bucket=self.bucket,
            Key=key,
            Body=stream,
            ContentType=content_type,
            ContentLength=content_length,
        )

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self.client.delete_object, Bucket=self.bucket, Key=key)

    async def download(self, key: str) -> bytes:
        response = await asyncio.to_thread(self.client.get_object, Bucket=self.bucket, Key=key)
        return await asyncio.to_thread(response["Body"].read)


class LocalObjectStore:
    def __init__(self, base_dir: str | Path) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_plugin_config(cls, config: PluginConfig) -> "LocalObjectStore":
        base_dir = config.get("base_dir", "./data/uploads")
        if not isinstance(base_dir, str):
            raise TypeError("base_dir must be a string")
        return cls(base_dir=base_dir)

    async def upload(self, key: str, stream: IO[bytes], content_type: str) -> None:
        file_path = self.base_dir / key
        file_path.parent.mkdir(parents=True, exist_ok=True)
        content = stream.read()
        await asyncio.to_thread(file_path.write_bytes, content)

    async def delete(self, key: str) -> None:
        file_path = self.base_dir / key
        if file_path.exists():
            await asyncio.to_thread(file_path.unlink)

    async def download(self, key: str) -> bytes:
        file_path = self.base_dir / key
        if not file_path.exists():
            raise FileNotFoundError(f"Key not found in local object store: {key}")
        return await asyncio.to_thread(file_path.read_bytes)


def get_object_store() -> ObjectStore:
    settings = get_settings()
    from app.plugin_registry import create_object_store

    provider = settings.object_store_provider.lower()
    if provider == "local":
        return create_object_store(
            provider="local",
            config=PluginConfig({"base_dir": settings.local_storage_dir}),
        )

    return create_object_store(
        provider="s3",
        config=PluginConfig(
            {
                "bucket": settings.s3_bucket,
                "endpoint_url": settings.s3_endpoint_url,
                "access_key": settings.s3_access_key,
                "region": settings.s3_region,
                "force_path_style": settings.s3_force_path_style,
            },
            {"secret_key": SecretValue(settings.s3_secret_key.get_secret_value())},
        ),
    )
