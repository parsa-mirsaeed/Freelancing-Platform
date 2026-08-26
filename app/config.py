from __future__ import annotations

import base64
import binascii
import hashlib
import os
from dataclasses import dataclass

FEATURE_FLAG_NAMES = (
    "new_payment_flow",
    "new_matching_model",
    "new_commission_formula",
    "new_search_ranking",
    "new_dispute_engine",
)
_DEVELOPMENT_SECRET_KEY = "-".join(("development", "only", "change", "me"))
_DEVELOPMENT_PAYMENT_WEBHOOK_SECRET = "-".join(
    ("development", "only", "payment", "webhook", "secret")
)
_SUPPORTED_PAYMENT_PROVIDERS = {"sandbox", "stripe"}


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().casefold() in {"1", "true", "yes", "on"}


def _comma_list(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _derived_local_key(secret_key: str, *, purpose: str) -> str:
    material = hashlib.sha256(f"{purpose}\0{secret_key}".encode()).digest()
    return base64.urlsafe_b64encode(material).decode("ascii").rstrip("=")


def _validate_base64_key(name: str, value: str) -> None:
    try:
        padding = "=" * (-len(value) % 4)
        decoded = base64.b64decode((value + padding).encode("ascii"), altchars=b"-_", validate=True)
    except (UnicodeEncodeError, binascii.Error, ValueError) as exc:
        raise RuntimeError(f"{name} must be URL-safe base64") from exc
    if len(decoded) != 32:
        raise RuntimeError(f"{name} must decode to exactly 32 bytes")


def _validate_pii_encryption_keys(value: str) -> None:
    entries = _comma_list(value)
    if not entries:
        raise RuntimeError("PII_ENCRYPTION_KEYS must contain at least one key")
    seen: set[str] = set()
    for entry in entries:
        key_id, separator, encoded_key = entry.partition(":")
        if (
            not separator
            or not key_id
            or len(key_id) > 40
            or not key_id.isascii()
            or any(not (char.isalnum() or char in "._-") for char in key_id)
        ):
            raise RuntimeError(
                "PII_ENCRYPTION_KEYS entries must use ASCII key-id:base64-key format"
            )
        if key_id in seen:
            raise RuntimeError(f"PII_ENCRYPTION_KEYS contains duplicate key id: {key_id}")
        seen.add(key_id)
        _validate_base64_key(f"PII encryption key {key_id}", encoded_key)


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
    pii_encryption_keys: str
    pii_lookup_key: str
    payment_default_provider: str
    payment_webhook_secret: str
    stripe_secret_key: str
    stripe_publishable_key: str
    stripe_webhook_secret: str
    stripe_max_network_retries: int
    max_content_length: int
    cors_allowed_origins: tuple[str, ...]
    rate_limit_enabled: bool
    rate_limit_per_minute: int
    log_json: bool
    feature_flag_rollouts: dict[str, int]

    @classmethod
    def from_env(cls) -> Settings:
        environment = os.getenv("APP_ENV", "development").strip().casefold()
        secret_key = os.getenv("SECRET_KEY", _DEVELOPMENT_SECRET_KEY)
        cors_allowed_origins = _comma_list(os.getenv("CORS_ALLOWED_ORIGINS", ""))
        max_content_length = int(os.getenv("MAX_CONTENT_LENGTH", str(16 * 1024 * 1024)))
        rate_limit_per_minute = int(os.getenv("RATE_LIMIT_PER_MINUTE", "120"))
        feature_flag_rollouts = {
            name: int(os.getenv(f"FEATURE_FLAG_{name.upper()}_PERCENT", "0"))
            for name in FEATURE_FLAG_NAMES
        }
        pii_encryption_keys = os.getenv("PII_ENCRYPTION_KEYS", "").strip()
        pii_lookup_key = os.getenv("PII_LOOKUP_KEY", "").strip()
        payment_default_provider = os.getenv(
            "PAYMENT_DEFAULT_PROVIDER",
            "stripe" if environment == "production" else "sandbox",
        ).strip().casefold()
        payment_webhook_secret = os.getenv(
            "PAYMENT_WEBHOOK_SECRET", _DEVELOPMENT_PAYMENT_WEBHOOK_SECRET
        ).strip()
        stripe_secret_key = os.getenv("STRIPE_SECRET_KEY", "").strip()
        stripe_publishable_key = os.getenv("STRIPE_PUBLISHABLE_KEY", "").strip()
        stripe_webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()
        stripe_max_network_retries = int(os.getenv("STRIPE_MAX_NETWORK_RETRIES", "2"))

        if payment_default_provider not in _SUPPORTED_PAYMENT_PROVIDERS:
            raise RuntimeError(
                "PAYMENT_DEFAULT_PROVIDER must be one of: "
                + ", ".join(sorted(_SUPPORTED_PAYMENT_PROVIDERS))
            )
        if stripe_max_network_retries < 0 or stripe_max_network_retries > 5:
            raise RuntimeError("STRIPE_MAX_NETWORK_RETRIES must be between 0 and 5")

        if environment == "production":
            if secret_key == _DEVELOPMENT_SECRET_KEY:
                raise RuntimeError("SECRET_KEY must be configured in production")
            if "*" in cors_allowed_origins:
                raise RuntimeError("CORS_ALLOWED_ORIGINS cannot contain '*' in production")
            if not pii_encryption_keys:
                raise RuntimeError("PII_ENCRYPTION_KEYS must be configured in production")
            if not pii_lookup_key:
                raise RuntimeError("PII_LOOKUP_KEY must be configured in production")
            if payment_default_provider == "sandbox":
                raise RuntimeError("PAYMENT_DEFAULT_PROVIDER cannot be sandbox in production")
            if payment_default_provider == "stripe":
                missing = [
                    name
                    for name, value in (
                        ("STRIPE_SECRET_KEY", stripe_secret_key),
                        ("STRIPE_PUBLISHABLE_KEY", stripe_publishable_key),
                        ("STRIPE_WEBHOOK_SECRET", stripe_webhook_secret),
                    )
                    if not value
                ]
                if missing:
                    raise RuntimeError(
                        "Stripe production configuration is incomplete: " + ", ".join(missing)
                    )
        else:
            if not pii_encryption_keys:
                pii_encryption_keys = "local-v1:" + _derived_local_key(
                    secret_key, purpose="pii-encryption-local-v1"
                )
            if not pii_lookup_key:
                pii_lookup_key = _derived_local_key(secret_key, purpose="pii-lookup-local-v1")

        _validate_pii_encryption_keys(pii_encryption_keys)
        _validate_base64_key("PII_LOOKUP_KEY", pii_lookup_key)
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
            pii_encryption_keys=pii_encryption_keys,
            pii_lookup_key=pii_lookup_key,
            payment_default_provider=payment_default_provider,
            payment_webhook_secret=payment_webhook_secret,
            stripe_secret_key=stripe_secret_key,
            stripe_publishable_key=stripe_publishable_key,
            stripe_webhook_secret=stripe_webhook_secret,
            stripe_max_network_retries=stripe_max_network_retries,
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
            "PII_ENCRYPTION_KEYS": self.pii_encryption_keys,
            "PII_LOOKUP_KEY": self.pii_lookup_key,
            "PAYMENT_DEFAULT_PROVIDER": self.payment_default_provider,
            "PAYMENT_WEBHOOK_SECRET": self.payment_webhook_secret,
            "STRIPE_SECRET_KEY": self.stripe_secret_key,
            "STRIPE_PUBLISHABLE_KEY": self.stripe_publishable_key,
            "STRIPE_WEBHOOK_SECRET": self.stripe_webhook_secret,
            "STRIPE_MAX_NETWORK_RETRIES": self.stripe_max_network_retries,
            "MAX_CONTENT_LENGTH": self.max_content_length,
            "CORS_ALLOWED_ORIGINS": self.cors_allowed_origins,
            "RATE_LIMIT_ENABLED": self.rate_limit_enabled,
            "RATE_LIMIT_PER_MINUTE": self.rate_limit_per_minute,
            "LOG_JSON": self.log_json,
            "FEATURE_FLAG_ROLLOUTS": self.feature_flag_rollouts,
            "JSON_SORT_KEYS": False,
        }
