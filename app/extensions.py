from __future__ import annotations

from typing import cast

from elasticsearch import Elasticsearch
from flask import Flask, current_app
from flask_sqlalchemy import SQLAlchemy
from redis import Redis
from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "%(constraint_name)s",
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


class ElasticsearchExtension:
    extension_key = "elasticsearch"

    def init_app(self, app: Flask) -> None:
        app.extensions[self.extension_key] = Elasticsearch(str(app.config["ELASTICSEARCH_URL"]))

    def get_client(self) -> Elasticsearch:
        return cast(Elasticsearch, current_app.extensions[self.extension_key])

    def index_prefix(self) -> str:
        return str(current_app.config["ELASTICSEARCH_INDEX_PREFIX"])


redis_extension = RedisExtension()
elasticsearch_extension = ElasticsearchExtension()
