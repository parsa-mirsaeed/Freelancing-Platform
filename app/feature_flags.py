from __future__ import annotations

import hashlib
import uuid
from collections.abc import Mapping

from flask import current_app

from app.config import FEATURE_FLAG_NAMES


def is_feature_enabled(
    name: str,
    *,
    subject_id: uuid.UUID | str | None = None,
    rollouts: Mapping[str, int] | None = None,
) -> bool:
    if name not in FEATURE_FLAG_NAMES:
        raise ValueError(f"unknown feature flag: {name}")
    configured = rollouts
    if configured is None:
        configured = current_app.config["FEATURE_FLAG_ROLLOUTS"]
    percent = int(configured.get(name, 0))
    if percent <= 0:
        return False
    if percent >= 100:
        return True
    if subject_id is None:
        return False
    digest = hashlib.sha256(f"{name}:{subject_id}".encode()).digest()
    bucket = int.from_bytes(digest[:8], "big") % 100
    return bucket < percent


def feature_flag_snapshot(*, subject_id: uuid.UUID | str | None = None) -> dict[str, bool]:
    return {name: is_feature_enabled(name, subject_id=subject_id) for name in FEATURE_FLAG_NAMES}
