from io import BytesIO

import pytest
from app.storage import S3ObjectStore


class RecordingS3Client:
    def __init__(self) -> None:
        self.request: dict[str, object] | None = None

    def put_object(self, **kwargs: object) -> None:
        body = kwargs["Body"]
        assert isinstance(body, BytesIO)
        self.request = {**kwargs, "Body": body.read()}


@pytest.mark.asyncio
async def test_upload_sends_content_length_without_multipart() -> None:
    content = b"x" * (9 * 1024 * 1024)
    client = RecordingS3Client()
    store = S3ObjectStore.__new__(S3ObjectStore)
    store.bucket = "documents"
    store.client = client

    await store.upload("large.pdf", BytesIO(content), "application/pdf")

    assert client.request == {
        "Bucket": "documents",
        "Key": "large.pdf",
        "Body": content,
        "ContentType": "application/pdf",
        "ContentLength": len(content),
    }
