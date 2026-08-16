from __future__ import annotations

from collections.abc import Iterator

import pytest
from flask import Flask

from app import create_app
from app.extensions import db


@pytest.fixture()
def app() -> Iterator[Flask]:
    application = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret-key-with-enough-entropy",
            "SQLALCHEMY_DATABASE_URI": "sqlite+pysqlite:///:memory:",
            "REDIS_URL": "redis://localhost:6379/15",
            "ACCESS_TOKEN_TTL_SECONDS": 60,
            "REFRESH_TOKEN_TTL_SECONDS": 3600,
        }
    )
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app: Flask):  # type: ignore[no-untyped-def]
    return app.test_client()
