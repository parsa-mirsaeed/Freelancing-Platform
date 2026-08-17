from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FileSettings:
    endpoint_url: str
    access_key: str
    secret_key: str
    bucket: str
    region: str
    max_upload_bytes: int
    upload_ttl_seconds: int
    download_ttl_seconds: int
    scanner_mode: str
    clamav_host: str
    clamav_port: int

    @classmethod
    def from_env(cls, *, environment: str) -> FileSettings:
        default_scanner = "clamav" if environment == "production" else "basic"
        return cls(
            endpoint_url=os.getenv("S3_ENDPOINT_URL", "http://localhost:9000"),
            access_key=os.getenv("S3_ACCESS_KEY", "minioadmin"),
            secret_key=os.getenv("S3_SECRET_KEY", "minioadmin"),
            bucket=os.getenv("S3_BUCKET", "freelancing-files"),
            region=os.getenv("S3_REGION", "us-east-1"),
            max_upload_bytes=int(os.getenv("FILE_MAX_UPLOAD_BYTES", str(10 * 1024 * 1024))),
            upload_ttl_seconds=int(os.getenv("FILE_UPLOAD_TTL_SECONDS", "900")),
            download_ttl_seconds=int(os.getenv("FILE_DOWNLOAD_TTL_SECONDS", "300")),
            scanner_mode=os.getenv("FILE_SCANNER_MODE", default_scanner),
            clamav_host=os.getenv("CLAMAV_HOST", "localhost"),
            clamav_port=int(os.getenv("CLAMAV_PORT", "3310")),
        )
