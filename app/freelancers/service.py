from __future__ import annotations

import re
import unicodedata
import uuid
from datetime import date, time

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.audit.service import record_audit_event
from app.common.outbox import enqueue_outbox_event
from app.errors import ApiError
from app.extensions import db
from app.freelancers.models import (
    AvailabilityException,
    AvailabilityRule,
    FreelancerProfile,
    FreelancerSkill,
    Skill,
)
from app.freelancers.policies import can_edit_profile
from app.identity.models import User

SEARCH_REFRESH_EVENT = "search.freelancer.refresh"


def get_profile_by_user_id(user_id: uuid.UUID) -> FreelancerProfile:
    profile = db.session.scalar(
        select(FreelancerProfile)
        .options(
            selectinload(FreelancerProfile.skill_links).selectinload(FreelancerSkill.skill),
            selectinload(FreelancerProfile.availability_rules),
            selectinload(FreelancerProfile.availability_exceptions),
        )
        .where(FreelancerProfile.user_id == user_id)
    )
    if profile is None:
        raise ApiError(
            "profile_not_found",
            "Profile not found",
            404,
            "Freelancer profile not found",
        )
    return profile


def upsert_profile(
    *,
    user: User,
    title: str,
    bio: str,
    hourly_rate_minor: int | None,
    currency: str | None,
    timezone: str,
    accepting_work: bool,
    languages: list[str],
    skills: list[str],
) -> FreelancerProfile:
    if not any(role.role == "freelancer" for role in user.roles):
        raise ApiError("forbidden", "Forbidden", 403, "A freelancer role is required")
    if hourly_rate_minor is None and currency is not None:
        raise ApiError(
            "validation_error",
            "Invalid hourly rate",
            422,
            "currency must be omitted when hourly_rate_minor is omitted",
        )
    if hourly_rate_minor is not None and currency is None:
        raise ApiError(
            "validation_error",
            "Invalid hourly rate",
            422,
            "currency is required when hourly_rate_minor is provided",
        )

    profile = db.session.scalar(
        select(FreelancerProfile).where(FreelancerProfile.user_id == user.id)
    )
    created = profile is None
    if profile is None:
        profile = FreelancerProfile(user_id=user.id, title=title)
        db.session.add(profile)
        db.session.flush()
    elif not can_edit_profile(user, profile):
        raise ApiError("forbidden", "Forbidden", 403, "Profile cannot be edited by this user")

    profile.title = title
    profile.bio = bio
    profile.hourly_rate_minor = hourly_rate_minor
    profile.currency = currency
    profile.timezone = timezone
    profile.accepting_work = accepting_work
    profile.languages = _dedupe_strings(languages)
    _replace_skills(profile, skills)
    touch_search_projection(profile)
    record_audit_event(
        action="freelancer.profile_created" if created else "freelancer.profile_updated",
        resource_type="freelancer_profile",
        resource_id=str(profile.id),
        actor_user_id=user.id,
        metadata={"projection_version": profile.projection_version},
    )
    db.session.commit()
    return get_profile_by_user_id(user.id)


def replace_availability_rules(
    *, user: User, rules: list[tuple[int, time, time, str]]
) -> list[AvailabilityRule]:
    profile = get_profile_by_user_id(user.id)
    if not can_edit_profile(user, profile):
        raise ApiError("forbidden", "Forbidden", 403, "Availability cannot be edited")
    profile.availability_rules.clear()
    for weekday, start_time, end_time, timezone in rules:
        if start_time >= end_time:
            raise ApiError(
                "validation_error",
                "Invalid availability",
                422,
                "start_time must be before end_time",
            )
        profile.availability_rules.append(
            AvailabilityRule(
                weekday=weekday,
                start_time=start_time,
                end_time=end_time,
                timezone=timezone,
            )
        )
    touch_search_projection(profile)
    record_audit_event(
        action="freelancer.availability_rules_replaced",
        resource_type="freelancer_profile",
        resource_id=str(profile.id),
        actor_user_id=user.id,
        metadata={"rule_count": len(rules)},
    )
    db.session.commit()
    return list(profile.availability_rules)


def upsert_availability_exception(
    *,
    user: User,
    exception_date: date,
    available: bool,
    start_time: time | None,
    end_time: time | None,
    reason: str | None,
) -> AvailabilityException:
    profile = get_profile_by_user_id(user.id)
    if not can_edit_profile(user, profile):
        raise ApiError("forbidden", "Forbidden", 403, "Availability cannot be edited")
    if (start_time is None) != (end_time is None) or (
        start_time is not None and end_time is not None and start_time >= end_time
    ):
        raise ApiError(
            "validation_error",
            "Invalid availability",
            422,
            "start_time and end_time must both be omitted or define a valid range",
        )
    exception = db.session.scalar(
        select(AvailabilityException).where(
            AvailabilityException.freelancer_profile_id == profile.id,
            AvailabilityException.exception_date == exception_date,
        )
    )
    if exception is None:
        exception = AvailabilityException(
            freelancer_profile_id=profile.id,
            exception_date=exception_date,
            available=available,
        )
        db.session.add(exception)
        db.session.flush()
    exception.available = available
    exception.start_time = start_time
    exception.end_time = end_time
    exception.reason = reason
    touch_search_projection(profile)
    record_audit_event(
        action="freelancer.availability_exception_upserted",
        resource_type="availability_exception",
        resource_id=str(exception.id),
        actor_user_id=user.id,
        metadata={"date": exception_date.isoformat(), "available": available},
    )
    db.session.commit()
    return exception


def touch_search_projection(profile: FreelancerProfile) -> None:
    profile.projection_version += 1
    enqueue_outbox_event(
        event_type=SEARCH_REFRESH_EVENT,
        aggregate_type="freelancer_profile",
        aggregate_id=str(profile.user_id),
        payload={"projection_version": profile.projection_version},
    )


def _replace_skills(profile: FreelancerProfile, values: list[str]) -> None:
    skills = [get_or_create_skill(value) for value in _dedupe_strings(values)]
    profile.skill_links.clear()
    profile.skill_links.extend(FreelancerSkill(skill=skill) for skill in skills)


def get_or_create_skill(value: str) -> Skill:
    normalized_name = unicodedata.normalize("NFKC", value).strip()
    slug = normalize_skill_slug(normalized_name)
    skill = db.session.scalar(select(Skill).where(Skill.slug == slug))
    if skill is not None:
        return skill
    try:
        with db.session.begin_nested():
            skill = Skill(name=normalized_name, slug=slug)
            db.session.add(skill)
            db.session.flush()
    except IntegrityError as exc:
        skill = db.session.scalar(select(Skill).where(Skill.slug == slug))
        if skill is None:
            raise ApiError(
                "skill_conflict",
                "Skill unavailable",
                409,
                "Skill taxonomy changed concurrently; retry the request",
            ) from exc
    return skill


def normalize_skill_slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip().casefold()
    slug = re.sub(
        r"-+",
        "-",
        "".join(char if char.isalnum() else "-" for char in normalized),
    ).strip("-")
    if not slug:
        raise ApiError(
            "validation_error",
            "Invalid skill",
            422,
            "Skill must contain letters or digits",
        )
    return slug[:80]


def _dedupe_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        key = normalized.casefold()
        if normalized and key not in seen:
            result.append(normalized)
            seen.add(key)
    return result
