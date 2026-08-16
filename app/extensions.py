from __future__ import annotations

from typing import cast

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from redis import Redis
from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


db = SQLAlchemy(model_class=Base)


class RedisExtension:
    extension_key = "redis"

    def init_app(self, app: Flask) -> None:
        client = Redis.from_url(str(app.config["REDIS_URL"]), decode_responses=True)
        app.extensions[self.extension_key] = client

    def get_client(self, app: Flask) -> Redis:
        return cast(Redis, app.extensions[self.extension_key])


redis_extension = RedisExtension()
