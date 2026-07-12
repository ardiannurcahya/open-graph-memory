import asyncio
from typing import IO, Protocol

import boto3

from app.config import Settings, get_settings


class ObjectStore(Protocol):
    async def upload(self, key: str, stream: IO[bytes], content_type: str) -> None: ...
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


def get_object_store() -> ObjectStore:
    return S3ObjectStore(get_settings())
