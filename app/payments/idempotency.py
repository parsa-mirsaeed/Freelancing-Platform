from __future__ import annotations

import hashlib
import json
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.errors import ApiError
from app.extensions import db
from app.payments.models import FinancialIdempotencyKey


def claim_idempotency(
    *,
    user_id: uuid.UUID,
    operation: str,
    raw_key: str,
    request_payload: dict[str, object],
) -> tuple[FinancialIdempotencyKey, bool]:
    key = raw_key.strip()
    if not key or len(key) > 200:
        raise ApiError(
            "invalid_idempotency_key",
            "Invalid idempotency key",
            422,
            "Idempotency-Key must contain 1 to 200 characters",
        )
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    request_hash = hashlib.sha256(
        json.dumps(request_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    existing = db.session.scalar(
        select(FinancialIdempotencyKey)
        .where(
            FinancialIdempotencyKey.user_id == user_id,
            FinancialIdempotencyKey.operation == operation,
            FinancialIdempotencyKey.key_hash == key_hash,
        )
        .with_for_update()
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise ApiError(
                "idempotency_conflict",
                "Idempotency conflict",
                409,
                "The idempotency key was already used with a different request",
            )
        return existing, False

    record = FinancialIdempotencyKey(
        user_id=user_id,
        operation=operation,
        key_hash=key_hash,
        request_hash=request_hash,
    )
    try:
        with db.session.begin_nested():
            db.session.add(record)
            db.session.flush()
    except IntegrityError:
        existing = db.session.scalar(
            select(FinancialIdempotencyKey)
            .where(
                FinancialIdempotencyKey.user_id == user_id,
                FinancialIdempotencyKey.operation == operation,
                FinancialIdempotencyKey.key_hash == key_hash,
            )
            .with_for_update()
        )
        if existing is None:
            raise
        if existing.request_hash != request_hash:
            raise ApiError(
                "idempotency_conflict",
                "Idempotency conflict",
                409,
                "The idempotency key was already used with a different request",
            ) from None
        return existing, False
    return record, True


def complete_idempotency(
    record: FinancialIdempotencyKey, *, status: int, body: dict[str, object]
) -> None:
    record.response_status = status
    record.response_body = body
