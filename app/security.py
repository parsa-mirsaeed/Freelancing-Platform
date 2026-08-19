from __future__ import annotations

import time

from flask import Flask, Response, request

from app.errors import ApiError
from app.extensions import redis_extension


def install_security_controls(app: Flask) -> None:
    @app.before_request
    def enforce_origin_and_rate_limit() -> None:
        origin = request.headers.get("Origin")
        allowed_origins = set(app.config.get("CORS_ALLOWED_ORIGINS", ()))
        if origin and origin not in allowed_origins:
            raise ApiError(
                "origin_not_allowed",
                "Origin not allowed",
                403,
                "The request Origin is not allowed",
            )
        if not app.config.get("RATE_LIMIT_ENABLED", False):
            return
        if request.endpoint in {
            "health.live",
            "health.ready",
            "health.startup",
            "metrics.metrics",
        }:
            return
        remote = request.remote_addr or "unknown"
        window = int(time.time() // 60)
        key = f"rate:{window}:{remote}"
        client = redis_extension.get_client(app)
        pipeline = client.pipeline()
        pipeline.incr(key)
        pipeline.expire(key, 120)
        count, _ = pipeline.execute()
        limit = int(app.config["RATE_LIMIT_PER_MINUTE"])
        if int(count) > limit:
            raise ApiError(
                "rate_limited",
                "Too many requests",
                429,
                "Rate limit exceeded",
            )

    @app.after_request
    def apply_security_headers(response: Response) -> Response:
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(self), microphone=(self), geolocation=()",
        )
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
        )
        if app.config.get("APP_ENV") == "production":
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        origin = request.headers.get("Origin")
        allowed_origins = set(app.config.get("CORS_ALLOWED_ORIGINS", ()))
        if origin and origin in allowed_origins:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Vary"] = "Origin"
        return response
