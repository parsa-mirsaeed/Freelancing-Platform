from __future__ import annotations

import uuid
from datetime import date, time
from typing import Any

from flask import Request


class ValidationError(ValueError):
    pass


def require_json_object(request: Request) -> dict[str, Any]:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ValidationError("Request body must be a JSON object")
    return payload


def require_string(payload: dict[str, Any], field: str, *, max_length: int | None = None) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field} is required")
    normalized = value.strip()
    if max_length is not None and len(normalized) > max_length:
        raise ValidationError(f"{field} must be at most {max_length} characters")
    return normalized


def optional_string(
    payload: dict[str, Any], field: str, *, max_length: int | None = None
) -> str | None:
    value = payload.get(field)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be a string")
    normalized = value.strip()
    if not normalized:
        return None
    if max_length is not None and len(normalized) > max_length:
        raise ValidationError(f"{field} must be at most {max_length} characters")
    return normalized


def require_int(
    payload: dict[str, Any],
    field: str,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    value = payload.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError(f"{field} must be an integer")
    if minimum is not None and value < minimum:
        raise ValidationError(f"{field} must be at least {minimum}")
    if maximum is not None and value > maximum:
        raise ValidationError(f"{field} must be at most {maximum}")
    return value


def optional_int(
    payload: dict[str, Any],
    field: str,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int | None:
    if payload.get(field) is None:
        return None
    return require_int(payload, field, minimum=minimum, maximum=maximum)


def optional_bool(payload: dict[str, Any], field: str) -> bool | None:
    value = payload.get(field)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ValidationError(f"{field} must be a boolean")
    return value


def require_string_list(
    payload: dict[str, Any], field: str, *, max_items: int = 50, item_max_length: int = 80
) -> list[str]:
    value = payload.get(field)
    if not isinstance(value, list):
        raise ValidationError(f"{field} must be an array")
    if len(value) > max_items:
        raise ValidationError(f"{field} must contain at most {max_items} items")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValidationError(f"{field} items must be non-empty strings")
        normalized = item.strip()
        if len(normalized) > item_max_length:
            raise ValidationError(f"{field} items must be at most {item_max_length} characters")
        result.append(normalized)
    return result


def optional_string_list(
    payload: dict[str, Any], field: str, *, max_items: int = 50, item_max_length: int = 80
) -> list[str] | None:
    if payload.get(field) is None:
        return None
    return require_string_list(payload, field, max_items=max_items, item_max_length=item_max_length)


def require_currency(payload: dict[str, Any], field: str = "currency") -> str:
    value = require_string(payload, field, max_length=3).upper()
    if len(value) != 3 or not value.isalpha() or not value.isascii():
        raise ValidationError(f"{field} must be a three-letter currency code")
    return value


def optional_currency(payload: dict[str, Any], field: str = "currency") -> str | None:
    if payload.get(field) is None:
        return None
    return require_currency(payload, field)


def parse_uuid(value: str, field: str = "id") -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError) as exc:
        raise ValidationError(f"{field} must be a valid UUID") from exc


def require_date(payload: dict[str, Any], field: str) -> date:
    raw = require_string(payload, field, max_length=10)
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ValidationError(f"{field} must be an ISO date") from exc


def optional_time(payload: dict[str, Any], field: str) -> time | None:
    raw = optional_string(payload, field, max_length=8)
    if raw is None:
        return None
    try:
        parsed = time.fromisoformat(raw)
    except ValueError as exc:
        raise ValidationError(f"{field} must be an ISO local time") from exc
    if parsed.tzinfo is not None:
        raise ValidationError(f"{field} must not contain a timezone offset")
    return parsed


def require_time(payload: dict[str, Any], field: str) -> time:
    parsed = optional_time(payload, field)
    if parsed is None:
        raise ValidationError(f"{field} is required")
    return parsed
