from __future__ import annotations

import re
import unicodedata
from typing import Any

from sqlalchemy import select

from app.errors import ApiError
from app.extensions import db
from app.freelancers.models import FreelancerProfile, Skill
from app.identity.models import User
from app.portfolios.models import PortfolioItem

SKILL_MODEL_VERSION = "skill-rules-v1"
SKILL_FEATURE_VERSION = "skill-text-features-v1"


def suggest_skills(*, user: User, limit: int = 20) -> dict[str, object]:
    profile = db.session.scalar(
        select(FreelancerProfile).where(FreelancerProfile.user_id == user.id)
    )
    if profile is None:
        raise ApiError(
            "profile_not_found",
            "Freelancer profile not found",
            404,
            "Create a freelancer profile before requesting skill suggestions",
        )
    existing = {link.skill_id for link in profile.skill_links}
    portfolio_items = list(
        db.session.scalars(
            select(PortfolioItem).where(PortfolioItem.freelancer_profile_id == profile.id)
        )
    )
    sources = [
        ("profile_title", profile.title, 0.96),
        ("profile_bio", profile.bio, 0.89),
        *[("portfolio", f"{item.title} {item.description}", 0.81) for item in portfolio_items],
    ]
    suggestions: list[dict[str, Any]] = []
    for skill in db.session.scalars(select(Skill).where(Skill.is_active.is_(True))):
        if skill.id in existing:
            continue
        best: tuple[str, float] | None = None
        for source_name, text, confidence in sources:
            if _contains_skill(text, skill) and (best is None or confidence > best[1]):
                best = (source_name, confidence)
        if best is not None:
            suggestions.append(
                {
                    "skill_id": str(skill.id),
                    "name": skill.name,
                    "slug": skill.slug,
                    "confidence": best[1],
                    "evidence_source": best[0],
                }
            )
    suggestions.sort(key=lambda item: (-float(item["confidence"]), str(item["slug"])))
    return {
        "model_version": SKILL_MODEL_VERSION,
        "feature_version": SKILL_FEATURE_VERSION,
        "profile_mutated": False,
        "suggestions": suggestions[:limit],
    }


def _contains_skill(text: str, skill: Skill) -> bool:
    normalized = _normalize(text)
    variants = {_normalize(skill.name), _normalize(skill.slug.replace("-", " "))}
    for variant in variants:
        if not variant:
            continue
        pattern = rf"(?<!\w){re.escape(variant)}(?!\w)"
        if re.search(pattern, normalized):
            return True
    return False


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = re.sub(r"[^\w+#. -]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()
