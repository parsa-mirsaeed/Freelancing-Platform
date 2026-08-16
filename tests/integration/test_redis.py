from __future__ import annotations

import os

import pytest
from flask import current_app

from app import create_app
from app.extensions import redis_extension

pytestmark = pytest.mark.redis


def test_redis_extension_can_ping() -> None:
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "integration-secret-key",
            "SQLALCHEMY_DATABASE_URI": "sqlite+pysqlite:///:memory:",
            "REDIS_URL": os.environ["REDIS_URL"],
        }
    )
    with app.app_context():
        assert redis_extension.get_client(current_app).ping() is True
