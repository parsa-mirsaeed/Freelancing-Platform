from __future__ import annotations

from flask import Blueprint, Response, current_app, jsonify
from sqlalchemy import text

from app.extensions import db, redis_extension

health_bp = Blueprint("health", __name__)


@health_bp.get("/health/live")
def live() -> Response:
    return jsonify({"status": "ok"})


@health_bp.get("/health/ready")
def ready() -> tuple[Response, int]:
    checks = _dependency_checks()
    status = 200 if all(checks.values()) else 503
    return jsonify({"status": "ok" if status == 200 else "degraded", "checks": checks}), status


@health_bp.get("/health/startup")
def startup() -> tuple[Response, int]:
    return ready()


def _dependency_checks() -> dict[str, bool]:
    checks = {"database": False, "redis": False}
    try:
        db.session.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception:  # noqa: BLE001
        db.session.rollback()
    try:
        redis_extension.get_client(current_app).ping()
        checks["redis"] = True
    except Exception:  # noqa: BLE001
        checks["redis"] = False
    return checks
