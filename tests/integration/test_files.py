from __future__ import annotations

import os
import urllib.request
import uuid

import pytest

from app.files.config import FileSettings
from app.files.storage import ObjectStorage

pytestmark = pytest.mark.files


def test_minio_presigned_upload_round_trip() -> None:
    settings = FileSettings(
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        access_key=os.environ["S3_ACCESS_KEY"],
        secret_key=os.environ["S3_SECRET_KEY"],
        bucket=os.environ["S3_BUCKET"],
        region="us-east-1",
        max_upload_bytes=1024 * 1024,
        upload_ttl_seconds=60,
        download_ttl_seconds=60,
        scanner_mode="basic",
        clamav_host="localhost",
        clamav_port=3310,
    )
    storage = ObjectStorage(settings)
    storage.ensure_bucket()
    key = f"integration/{uuid.uuid4()}/proof.pdf"
    upload_url = storage.presign_upload(object_key=key, mime_type="application/pdf")
    request = urllib.request.Request(
        upload_url,
        data=b"%PDF-1.7\ncommunication",
        method="PUT",
        headers={"Content-Type": "application/pdf"},
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        assert response.status == 200

    metadata = storage.head(object_key=key)
    assert metadata["ContentLength"] == len(b"%PDF-1.7\ncommunication")
    assert b"".join(storage.iter_bytes(object_key=key)) == b"%PDF-1.7\ncommunication"
