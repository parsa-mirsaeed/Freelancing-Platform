from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.recommendations.features import (
    DEFAULT_RANKING_CONFIG,
    FEATURE_VERSION,
    MODEL_NAME,
    MODEL_VERSION,
)
from app.recommendations.models import ModelRegistryEntry


def ensure_matching_model() -> ModelRegistryEntry:
    existing = db.session.scalar(
        select(ModelRegistryEntry).where(
            ModelRegistryEntry.name == MODEL_NAME,
            ModelRegistryEntry.version == MODEL_VERSION,
        )
    )
    if existing is not None:
        return existing

    entry = ModelRegistryEntry(
        name=MODEL_NAME,
        version=MODEL_VERSION,
        model_type="RULE_BASED",
        feature_version=FEATURE_VERSION,
        status="ACTIVE",
        config_json={"weights": DEFAULT_RANKING_CONFIG.weights()},
        metrics_json={},
    )
    try:
        with db.session.begin_nested():
            db.session.add(entry)
            db.session.flush()
    except IntegrityError:
        existing = db.session.scalar(
            select(ModelRegistryEntry).where(
                ModelRegistryEntry.name == MODEL_NAME,
                ModelRegistryEntry.version == MODEL_VERSION,
            )
        )
        if existing is None:
            raise
        return existing
    return entry


def list_models() -> list[ModelRegistryEntry]:
    return list(
        db.session.scalars(
            select(ModelRegistryEntry).order_by(
                ModelRegistryEntry.name,
                ModelRegistryEntry.created_at.desc(),
            )
        )
    )
