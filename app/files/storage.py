from __future__ import annotations

from collections.abc import Iterator
from typing import Any, cast

import boto3
from botocore.config import Config

from app.files.config import FileSettings


class ObjectStorage:
    def __init__(self, settings: FileSettings) -> None:
        self.settings = settings
        self.client: Any = boto3.client(
            "s3",
            endpoint_url=settings.endpoint_url,
            aws_access_key_id=settings.access_key,
            aws_secret_access_key=settings.secret_key,
            region_name=settings.region,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    def presign_upload(self, *, object_key: str, mime_type: str) -> str:
        return cast(
            str,
            self.client.generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": self.settings.bucket,
                    "Key": object_key,
                    "ContentType": mime_type,
                },
                ExpiresIn=self.settings.upload_ttl_seconds,
            ),
        )

    def presign_download(self, *, object_key: str, filename: str) -> str:
        return cast(
            str,
            self.client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": self.settings.bucket,
                    "Key": object_key,
                    "ResponseContentDisposition": f'attachment; filename="{filename}"',
                },
                ExpiresIn=self.settings.download_ttl_seconds,
            ),
        )

    def head(self, *, object_key: str) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self.client.head_object(Bucket=self.settings.bucket, Key=object_key),
        )

    def iter_bytes(self, *, object_key: str, chunk_size: int = 64 * 1024) -> Iterator[bytes]:
        response = self.client.get_object(Bucket=self.settings.bucket, Key=object_key)
        body = response["Body"]
        while True:
            chunk = body.read(chunk_size)
            if not chunk:
                break
            yield cast(bytes, chunk)

    def ensure_bucket(self) -> None:
        try:
            self.client.head_bucket(Bucket=self.settings.bucket)
        except Exception:  # noqa: BLE001 - provider exception types vary across S3 implementations
            self.client.create_bucket(Bucket=self.settings.bucket)
