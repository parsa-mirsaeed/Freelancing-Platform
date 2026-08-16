from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    environment: str
    secret_key: str
    database_url: str
    redis_url: str
    elasticsearch_url: str
    elasticsearch_index_prefix: str
    access_token_ttl_seconds: int
    refresh_token_ttl_seconds: int

    @classmethod
    def from_env(cls) -> Settings:
        environment = os.getenv("APP_ENV", "development")
        secret_key = os.getenv("SECRET_KEY", "development-only-change-me")
        if environment == "production" and secret_key == "development-only-change-me":
            raise RuntimeError("SECRET_KEY must be configured in production")

        return cls(
            environment=environment,
            secret_key=secret_key,
            database_url=os.getenv(
                "DATABASE_URL",
                "postgresql+psycopg://freelancing:freelancing@localhost:5432/freelancing",
            ),
            redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
            elasticsearch_url=os.getenv("ELASTICSEARCH_URL", "http://localhost:9200"),
            elasticsearch_index_prefix=os.getenv(
                "ELASTICSEARCH_INDEX_PREFIX", "freelancing-development"
            ),
            access_token_ttl_seconds=int(os.getenv("ACCESS_TOKEN_TTL_SECONDS", "900")),
            refresh_token_ttl_seconds=int(os.getenv("REFRESH_TOKEN_TTL_SECONDS", "2592000")),
        )

    def flask_mapping(self) -> dict[str, object]:
        return {
            "APP_ENV": self.environment,
            "SECRET_KEY": self.secret_key,
            "SQLALCHEMY_DATABASE_URI": self.database_url,
            "SQLALCHEMY_TRACK_MODIFICATIONS": False,
            "REDIS_URL": self.redis_url,
            "ELASTICSEARCH_URL": self.elasticsearch_url,
            "ELASTICSEARCH_INDEX_PREFIX": self.elasticsearch_index_prefix,
            "ACCESS_TOKEN_TTL_SECONDS": self.access_token_ttl_seconds,
            "REFRESH_TOKEN_TTL_SECONDS": self.refresh_token_ttl_seconds,
            "JSON_SORT_KEYS": False,
        }
