from __future__ import annotations

from datetime import time

from flask import Blueprint, g, jsonify, request

from app.common.http import (
    ValidationError,
    optional_bool,
    optional_currency,
    optional_int,
    optional_string,
    optional_string_list,
    optional_time,
    parse_uuid,
    require_date,
    require_int,
    require_json_object,
    require_string,
    require_string_list,
    require_time,
)
from app.freelancers.models import AvailabilityException, AvailabilityRule, FreelancerProfile
from app.freelancers.service import (
    get_profile_by_user_id,
    replace_availability_rules,
    upsert_availability_exception,
    upsert_profile,
)
from app.identity.auth import require_access_token, require_roles
from app.identity.models import User

freelancers_bp = Blueprint("freelancers", __name__, url_prefix="/api/v1/freelancers")


@freelancers_bp.put("/me/profile")
@require_roles("freelancer")
def put_my_profile():  # type: ignore[no-untyped-def]
    user: User = g.current_user
    payload = require_json_object(request)
    hourly_rate_minor = optional_int(payload, "hourly_rate_minor", minimum=0)
    currency = optional_currency(payload)
    accepting_work = optional_bool(payload, "accepting_work")
    profile = upsert_profile(
        user=user,
        title=require_string(payload, "title", max_length=160),
        bio=optional_string(payload, "bio") or "",
        hourly_rate_minor=hourly_rate_minor,
        currency=currency,
        timezone=optional_string(payload, "timezone", max_length=64) or "UTC",
        accepting_work=True if accepting_work is None else accepting_work,
        languages=optional_string_list(payload, "languages", max_items=20, item_max_length=16)
        or [],
        skills=require_string_list(payload, "skills", max_items=50, item_max_length=80),
    )
    return jsonify(_serialize_profile(profile))


@freelancers_bp.get("/me/profile")
@require_access_token
def get_my_profile():  # type: ignore[no-untyped-def]
    user: User = g.current_user
    return jsonify(_serialize_profile(get_profile_by_user_id(user.id)))


@freelancers_bp.get("/<user_id>")
def get_profile(user_id: str):  # type: ignore[no-untyped-def]
    return jsonify(_serialize_profile(get_profile_by_user_id(parse_uuid(user_id, "user_id"))))


@freelancers_bp.put("/me/availability/rules")
@require_roles("freelancer")
def put_availability_rules():  # type: ignore[no-untyped-def]
    user: User = g.current_user
    payload = require_json_object(request)
    raw_rules = payload.get("rules")
    if not isinstance(raw_rules, list) or len(raw_rules) > 50:
        raise ValidationError("rules must be an array containing at most 50 items")
    rules: list[tuple[int, time, time, str]] = []
    for raw_rule in raw_rules:
        if not isinstance(raw_rule, dict):
            raise ValidationError("Each availability rule must be an object")
        rules.append(
            (
                require_int(raw_rule, "weekday", minimum=0, maximum=6),
                require_time(raw_rule, "start_time"),
                require_time(raw_rule, "end_time"),
                optional_string(raw_rule, "timezone", max_length=64) or "UTC",
            )
        )
    saved = replace_availability_rules(user=user, rules=rules)
    return jsonify({"rules": [_serialize_rule(rule) for rule in saved]})


@freelancers_bp.put("/me/availability/exceptions")
@require_roles("freelancer")
def put_availability_exception():  # type: ignore[no-untyped-def]
    user: User = g.current_user
    payload = require_json_object(request)
    value = payload.get("available")
    if not isinstance(value, bool):
        raise ValidationError("available must be a boolean")
    exception = upsert_availability_exception(
        user=user,
        exception_date=require_date(payload, "date"),
        available=value,
        start_time=optional_time(payload, "start_time"),
        end_time=optional_time(payload, "end_time"),
        reason=optional_string(payload, "reason", max_length=240),
    )
    return jsonify(_serialize_exception(exception))


def _serialize_profile(profile: FreelancerProfile) -> dict[str, object]:
    return {
        "id": str(profile.id),
        "user_id": str(profile.user_id),
        "title": profile.title,
        "bio": profile.bio,
        "hourly_rate_minor": profile.hourly_rate_minor,
        "currency": profile.currency,
        "timezone": profile.timezone,
        "accepting_work": profile.accepting_work,
        "languages": list(profile.languages),
        "skills": [link.skill.name for link in profile.skill_links],
        "projection_version": profile.projection_version,
        "availability": {
            "rules": [_serialize_rule(rule) for rule in profile.availability_rules],
            "exceptions": [
                _serialize_exception(exception) for exception in profile.availability_exceptions
            ],
        },
    }


def _serialize_rule(rule: AvailabilityRule) -> dict[str, object]:
    return {
        "id": str(rule.id),
        "weekday": rule.weekday,
        "start_time": rule.start_time.isoformat(timespec="minutes"),
        "end_time": rule.end_time.isoformat(timespec="minutes"),
        "timezone": rule.timezone,
    }


def _serialize_exception(exception: AvailabilityException) -> dict[str, object]:
    return {
        "id": str(exception.id),
        "date": exception.exception_date.isoformat(),
        "available": exception.available,
        "start_time": exception.start_time.isoformat(timespec="minutes")
        if exception.start_time
        else None,
        "end_time": exception.end_time.isoformat(timespec="minutes")
        if exception.end_time
        else None,
        "reason": exception.reason,
    }
