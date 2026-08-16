from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from flask import Flask, g, request

from app.config import Settings
from app.errors import register_error_handlers
from app.extensions import db, redis_extension
from app.health import health_bp
from app.identity.api import identity_bp


def create_app(config_overrides: Mapping[str, Any] | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_mapping(Settings.from_env().flask_mapping())
    if config_overrides:
        app.config.from_mapping(config_overrides)

    db.init_app(app)
    redis_extension.init_app(app)
    _register_models()
    app.register_blueprint(health_bp)
    app.register_blueprint(identity_bp)
    register_error_handlers(app)
    _register_request_context(app)
    return app


def _register_models() -> None:
    from app.audit import models as audit_models  # noqa: F401
    from app.identity import models as identity_models  # noqa: F401


def _register_request_context(app: Flask) -> None:
    @app.before_request
    def assign_request_id() -> None:
        incoming = request.headers.get("X-Request-ID")
        g.request_id = incoming[:64] if incoming else str(uuid.uuid4())

    @app.after_request
    def attach_request_id(response):  # type: ignore[no-untyped-def]
        response.headers["X-Request-ID"] = g.request_id
        return response
