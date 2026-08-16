from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.audit.service import record_audit_event
from app.errors import ApiError
from app.extensions import db
from app.freelancers.models import FreelancerProfile
from app.freelancers.service import get_profile_by_user_id
from app.gigs.models import Gig, GigPackage, GigRequirement
from app.gigs.policies import can_edit_gig
from app.identity.models import User

ALLOWED_TIERS = {"BASIC", "STANDARD", "PREMIUM"}


@dataclass(frozen=True, slots=True)
class PackageInput:
    tier: str
    amount_minor: int
    currency: str
    delivery_days: int
    revisions: int
    description: str


@dataclass(frozen=True, slots=True)
class RequirementInput:
    prompt: str
    required: bool


def list_gigs(*, active_only: bool = True) -> list[Gig]:
    statement = select(Gig).options(selectinload(Gig.packages), selectinload(Gig.requirements))
    if active_only:
        statement = statement.where(Gig.is_active.is_(True))
    return list(db.session.scalars(statement.order_by(Gig.created_at.desc())))


def get_gig(gig_id: uuid.UUID) -> Gig:
    gig = db.session.scalar(
        select(Gig)
        .options(selectinload(Gig.packages), selectinload(Gig.requirements))
        .where(Gig.id == gig_id)
    )
    if gig is None:
        raise ApiError("gig_not_found", "Gig not found", 404, "Gig was not found")
    return gig


def create_gig(
    *,
    user: User,
    title: str,
    description: str,
    packages: list[PackageInput],
    requirements: list[RequirementInput],
) -> Gig:
    profile = get_profile_by_user_id(user.id)
    normalized_packages = _validate_packages(packages)
    gig = Gig(freelancer_profile_id=profile.id, title=title, description=description)
    gig.packages.extend(_package_model(package) for package in normalized_packages)
    gig.requirements.extend(
        GigRequirement(prompt=requirement.prompt, required=requirement.required)
        for requirement in requirements
    )
    db.session.add(gig)
    db.session.flush()
    record_audit_event(
        action="gig.created",
        resource_type="gig",
        resource_id=str(gig.id),
        actor_user_id=user.id,
        metadata={"package_tiers": [package.tier for package in normalized_packages]},
    )
    db.session.commit()
    return get_gig(gig.id)


def replace_gig(
    *,
    user: User,
    gig_id: uuid.UUID,
    title: str,
    description: str,
    is_active: bool,
    packages: list[PackageInput],
    requirements: list[RequirementInput],
) -> Gig:
    gig = get_gig(gig_id)
    profile = db.session.scalar(
        select(FreelancerProfile).where(FreelancerProfile.user_id == user.id)
    )
    if not can_edit_gig(user, gig, profile):
        raise ApiError("forbidden", "Forbidden", 403, "Gig cannot be edited by this user")
    normalized_packages = _validate_packages(packages)
    gig.title = title
    gig.description = description
    gig.is_active = is_active
    gig.packages.clear()
    gig.packages.extend(_package_model(package) for package in normalized_packages)
    gig.requirements.clear()
    gig.requirements.extend(
        GigRequirement(prompt=requirement.prompt, required=requirement.required)
        for requirement in requirements
    )
    record_audit_event(
        action="gig.updated",
        resource_type="gig",
        resource_id=str(gig.id),
        actor_user_id=user.id,
        metadata={"active": is_active},
    )
    db.session.commit()
    return get_gig(gig.id)


def _validate_packages(packages: list[PackageInput]) -> list[PackageInput]:
    if not packages or len(packages) > 3:
        raise ApiError(
            "validation_error", "Invalid packages", 422, "A gig must contain one to three packages"
        )
    tiers = [package.tier.upper() for package in packages]
    if "BASIC" not in tiers:
        raise ApiError(
            "validation_error", "Invalid packages", 422, "Every gig must include a BASIC package"
        )
    if len(set(tiers)) != len(tiers) or any(tier not in ALLOWED_TIERS for tier in tiers):
        raise ApiError(
            "validation_error",
            "Invalid packages",
            422,
            "Package tiers must be unique BASIC, STANDARD, or PREMIUM values",
        )
    currencies = {package.currency for package in packages}
    if len(currencies) != 1:
        raise ApiError(
            "validation_error",
            "Invalid packages",
            422,
            "All packages in a gig must use the same currency",
        )
    order = {"BASIC": 0, "STANDARD": 1, "PREMIUM": 2}
    normalized = [
        PackageInput(
            tier=package.tier.upper(),
            amount_minor=package.amount_minor,
            currency=package.currency,
            delivery_days=package.delivery_days,
            revisions=package.revisions,
            description=package.description,
        )
        for package in packages
    ]
    return sorted(normalized, key=lambda package: order[package.tier])


def _package_model(package: PackageInput) -> GigPackage:
    return GigPackage(
        tier=package.tier,
        amount_minor=package.amount_minor,
        currency=package.currency,
        delivery_days=package.delivery_days,
        revisions=package.revisions,
        description=package.description,
    )
