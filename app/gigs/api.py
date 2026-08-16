from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from app.common.http import (
    ValidationError,
    optional_bool,
    optional_string,
    parse_uuid,
    require_currency,
    require_int,
    require_json_object,
    require_string,
)
from app.gigs.models import Gig
from app.gigs.service import (
    PackageInput,
    RequirementInput,
    create_gig,
    get_gig,
    list_gigs,
    replace_gig,
)
from app.identity.auth import require_roles
from app.identity.models import User

gigs_bp = Blueprint("gigs", __name__, url_prefix="/api/v1/gigs")


@gigs_bp.get("")
def get_gigs():  # type: ignore[no-untyped-def]
    return jsonify({"items": [_serialize_gig(gig) for gig in list_gigs()]})


@gigs_bp.get("/<gig_id>")
def get_gig_detail(gig_id: str):  # type: ignore[no-untyped-def]
    return jsonify(_serialize_gig(get_gig(parse_uuid(gig_id, "gig_id"))))


@gigs_bp.post("")
@require_roles("freelancer")
def post_gig():  # type: ignore[no-untyped-def]
    user: User = g.current_user
    payload = require_json_object(request)
    gig = create_gig(
        user=user,
        title=require_string(payload, "title", max_length=160),
        description=require_string(payload, "description"),
        packages=_parse_packages(payload),
        requirements=_parse_requirements(payload),
    )
    return jsonify(_serialize_gig(gig)), 201


@gigs_bp.put("/<gig_id>")
@require_roles("freelancer")
def put_gig(gig_id: str):  # type: ignore[no-untyped-def]
    user: User = g.current_user
    payload = require_json_object(request)
    active = optional_bool(payload, "is_active")
    gig = replace_gig(
        user=user,
        gig_id=parse_uuid(gig_id, "gig_id"),
        title=require_string(payload, "title", max_length=160),
        description=require_string(payload, "description"),
        is_active=True if active is None else active,
        packages=_parse_packages(payload),
        requirements=_parse_requirements(payload),
    )
    return jsonify(_serialize_gig(gig))


def _parse_packages(payload: dict[str, object]) -> list[PackageInput]:
    raw_packages = payload.get("packages")
    if not isinstance(raw_packages, list):
        raise ValidationError("packages must be an array")
    packages: list[PackageInput] = []
    for raw_package in raw_packages:
        if not isinstance(raw_package, dict):
            raise ValidationError("Each package must be an object")
        packages.append(
            PackageInput(
                tier=require_string(raw_package, "tier", max_length=16).upper(),
                amount_minor=require_int(raw_package, "amount_minor", minimum=0),
                currency=require_currency(raw_package),
                delivery_days=require_int(raw_package, "delivery_days", minimum=1, maximum=3650),
                revisions=require_int(raw_package, "revisions", minimum=0, maximum=1000),
                description=optional_string(raw_package, "description") or "",
            )
        )
    return packages


def _parse_requirements(payload: dict[str, object]) -> list[RequirementInput]:
    raw_requirements = payload.get("requirements", [])
    if not isinstance(raw_requirements, list) or len(raw_requirements) > 50:
        raise ValidationError("requirements must be an array containing at most 50 items")
    requirements: list[RequirementInput] = []
    for raw_requirement in raw_requirements:
        if not isinstance(raw_requirement, dict):
            raise ValidationError("Each requirement must be an object")
        required = raw_requirement.get("required", True)
        if not isinstance(required, bool):
            raise ValidationError("requirement.required must be a boolean")
        requirements.append(
            RequirementInput(
                prompt=require_string(raw_requirement, "prompt", max_length=500), required=required
            )
        )
    return requirements


def _serialize_gig(gig: Gig) -> dict[str, object]:
    return {
        "id": str(gig.id),
        "freelancer_profile_id": str(gig.freelancer_profile_id),
        "title": gig.title,
        "description": gig.description,
        "is_active": gig.is_active,
        "packages": [
            {
                "id": str(package.id),
                "tier": package.tier,
                "amount_minor": package.amount_minor,
                "currency": package.currency,
                "delivery_days": package.delivery_days,
                "revisions": package.revisions,
                "description": package.description,
            }
            for package in gig.packages
        ],
        "requirements": [
            {
                "id": str(requirement.id),
                "prompt": requirement.prompt,
                "required": requirement.required,
            }
            for requirement in gig.requirements
        ],
    }
