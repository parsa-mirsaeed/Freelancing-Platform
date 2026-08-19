from __future__ import annotations

import os
from dataclasses import dataclass

FEATURE_FLAG_NAMES = (
    "new_payment_flow",
    "new_matching_model",
    "new_commission_formula",
    "new_search_ranking",
    "new_dispute_engine",
)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().casefold() in {"1", "true", "yes", "on"}


def _comma_list(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


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
    max_content_length: int
    cors_allowed_origins: tuple[str, ...]
    rate_limit_enabled: bool
    rate_limit_per_minute: int
    log_json: bool
    feature_flag_rollouts: dict[str, int]

    @classmethod
    def from_env(cls) -> Settings:
        environment = os.getenv("APP_ENV", "development").strip().casefold()
        secret_key = os.getenv("SECRET_KEY", "development-only-change-me")
        cors_allowed_origins = _comma_list(os.getenv("CORS_ALLOWED_ORIGINS", ""))
        max_content_length = int(os.getenv("MAX_CONTENT_LENGTH", str(16 * 1024 * 1024)))
        rate_limit_per_minute = int(os.getenv("RATE_LIMIT_PER_MINUTE", "120"))
        feature_flag_rollouts = {
            name: int(os.getenv(f"FEATURE_FLAG_{name.upper()}_PERCENT", "0"))
            for name in FEATURE_FLAG_NAMES
        }

        if environment == "production":
            if secret_key == "development-only-change-me":
                raise RuntimeError("SECRET_KEY must be configured in production")
            if "*" in cors_allowed_origins:
                raise RuntimeError("CORS_ALLOWED_ORIGINS cannot contain '*' in production")
        if max_content_length <= 0:
            raise RuntimeError("MAX_CONTENT_LENGTH must be positive")
        if rate_limit_per_minute <= 0:
            raise RuntimeError("RATE_LIMIT_PER_MINUTE must be positive")
        if any(percent < 0 or percent > 100 for percent in feature_flag_rollouts.values()):
            raise RuntimeError("feature flag rollout percentages must be between 0 and 100")

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
            max_content_length=max_content_length,
            cors_allowed_origins=cors_allowed_origins,
            rate_limit_enabled=_env_bool(
                "RATE_LIMIT_ENABLED",
                default=environment == "production",
            ),
            rate_limit_per_minute=rate_limit_per_minute,
            log_json=_env_bool("LOG_JSON", default=True),
            feature_flag_rollouts=feature_flag_rollouts,
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
            "MAX_CONTENT_LENGTH": self.max_content_length,
            "CORS_ALLOWED_ORIGINS": self.cors_allowed_origins,
            "RATE_LIMIT_ENABLED": self.rate_limit_enabled,
            "RATE_LIMIT_PER_MINUTE": self.rate_limit_per_minute,
            "LOG_JSON": self.log_json,
            "FEATURE_FLAG_ROLLOUTS": self.feature_flag_rollouts,
            "JSON_SORT_KEYS": False,
        }
