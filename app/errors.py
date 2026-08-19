from __future__ import annotations

from dataclasses import dataclass

from flask import Flask, g, jsonify

from app.common.http import ValidationError


@dataclass(slots=True)
class ApiError(Exception):
    type: str
    title: str
    status: int
    detail: str


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(ApiError)
    def handle_api_error(error: ApiError):  # type: ignore[no-untyped-def]
        return _error_response(error.type, error.title, error.status, error.detail)

    @app.errorhandler(ValidationError)
    def handle_validation_error(error: ValidationError):  # type: ignore[no-untyped-def]
        return _error_response("validation_error", "Invalid request", 422, str(error))

    @app.errorhandler(404)
    def handle_not_found(_error: Exception):  # type: ignore[no-untyped-def]
        return _error_response("not_found", "Not found", 404, "Resource was not found")

    @app.errorhandler(413)
    def handle_payload_too_large(_error: Exception):  # type: ignore[no-untyped-def]
        return _error_response(
            "payload_too_large",
            "Payload too large",
            413,
            "Request body exceeds the configured size limit",
        )


def _error_response(error_type: str, title: str, status: int, detail: str):  # type: ignore[no-untyped-def]
    return (
        jsonify(
            {
                "type": error_type,
                "title": title,
                "status": status,
                "detail": detail,
                "request_id": getattr(g, "request_id", None),
            }
        ),
        status,
    )
