# ADR-009: Upload files directly to S3-compatible object storage

## Status

Accepted.

## Decision

Large file bodies do not pass through Flask. The API reserves a `file_objects` row and returns a short-lived presigned PUT URL. Objects begin `QUARANTINED`, move to `SCANNING` after upload metadata verification, and become `SAFE` or `REJECTED` after worker scanning.

Only `SAFE` files can be attached or downloaded. Production defaults to a ClamAV-compatible scanner; development and unit tests may use the deterministic magic-byte scanner. Declared extension/MIME, size, optional SHA-256, magic bytes, and malware scan results are validated.

Downloads are also presigned and require application authorization before the URL is issued.
