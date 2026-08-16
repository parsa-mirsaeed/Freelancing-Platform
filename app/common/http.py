from __future__ import annotations

from typing import Any

from flask import Request


class ValidationError(ValueError):
    pass


def require_json_object(request: Request) -> dict[str, Any]:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ValidationError("Request body must be a JSON object")
    return payload


def require_string(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field} is required")
    return value.strip()
