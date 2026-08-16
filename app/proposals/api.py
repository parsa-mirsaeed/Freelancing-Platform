from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from app.common.http import (
    ValidationError,
    optional_string,
    parse_uuid,
    require_currency,
    require_int,
    require_json_object,
    require_string,
)
from app.errors import ApiError
from app.identity.auth import require_roles
from app.identity.models import User
from app.projects.service import get_project
from app.proposals.models import Proposal, ProposalVersion
from app.proposals.service import (
    MilestoneInput,
    add_proposal_version,
    create_proposal,
    get_proposal,
    list_project_proposals,
    transition_proposal,
)

proposals_bp = Blueprint("proposals", __name__, url_prefix="/api/v1")


@proposals_bp.post("/projects/<project_id>/proposals")
@require_roles("freelancer")
def post_proposal(project_id: str):  # type: ignore[no-untyped-def]
    user: User = g.current_user
    payload = require_json_object(request)
    proposal = create_proposal(
        user=user,
        project_id=parse_uuid(project_id, "project_id"),
        amount_minor=require_int(payload, "amount_minor", minimum=0),
        currency=require_currency(payload),
        delivery_days=require_int(payload, "delivery_days", minimum=1, maximum=3650),
        cover_letter=optional_string(payload, "cover_letter") or "",
        milestones=_parse_milestones(payload),
    )
    return jsonify(_serialize_proposal(proposal)), 201


@proposals_bp.get("/projects/<project_id>/proposals")
@require_roles("employer")
def get_project_proposals(project_id: str):  # type: ignore[no-untyped-def]
    user: User = g.current_user
    proposals = list_project_proposals(user=user, project_id=parse_uuid(project_id, "project_id"))
    return jsonify({"items": [_serialize_proposal(proposal) for proposal in proposals]})


@proposals_bp.get("/proposals/<proposal_id>")
@require_roles("freelancer", "employer")
def get_proposal_detail(proposal_id: str):  # type: ignore[no-untyped-def]
    user: User = g.current_user
    proposal = get_proposal(parse_uuid(proposal_id, "proposal_id"))
    if (
        proposal.freelancer_user_id != user.id
        and get_project(proposal.project_id).employer_user_id != user.id
    ):
        raise ApiError("forbidden", "Forbidden", 403, "Proposal is private")
    return jsonify(_serialize_proposal(proposal))


@proposals_bp.post("/proposals/<proposal_id>/versions")
@require_roles("freelancer")
def post_proposal_version(proposal_id: str):  # type: ignore[no-untyped-def]
    user: User = g.current_user
    payload = require_json_object(request)
    proposal = add_proposal_version(
        user=user,
        proposal_id=parse_uuid(proposal_id, "proposal_id"),
        amount_minor=require_int(payload, "amount_minor", minimum=0),
        currency=require_currency(payload),
        delivery_days=require_int(payload, "delivery_days", minimum=1, maximum=3650),
        cover_letter=optional_string(payload, "cover_letter") or "",
        milestones=_parse_milestones(payload),
    )
    return jsonify(_serialize_proposal(proposal)), 201


@proposals_bp.post("/proposals/<proposal_id>/<action>")
@require_roles("freelancer", "employer")
def post_transition(proposal_id: str, action: str):  # type: ignore[no-untyped-def]
    mapping = {
        "submit": "SUBMITTED",
        "negotiate": "UNDER_NEGOTIATION",
        "withdraw": "WITHDRAWN",
        "reject": "REJECTED",
        "accept": "ACCEPTED",
    }
    target = mapping.get(action)
    if target is None:
        raise ApiError("not_found", "Not found", 404, "Proposal action was not found")
    user: User = g.current_user
    proposal = transition_proposal(
        user=user, proposal_id=parse_uuid(proposal_id, "proposal_id"), target=target
    )
    return jsonify(_serialize_proposal(proposal))


def _parse_milestones(payload: dict[str, object]) -> list[MilestoneInput]:
    raw_milestones = payload.get("milestones", [])
    if not isinstance(raw_milestones, list) or len(raw_milestones) > 50:
        raise ValidationError("milestones must be an array containing at most 50 items")
    result: list[MilestoneInput] = []
    for raw_milestone in raw_milestones:
        if not isinstance(raw_milestone, dict):
            raise ValidationError("Each milestone must be an object")
        result.append(
            MilestoneInput(
                title=require_string(raw_milestone, "title", max_length=180),
                amount_minor=require_int(raw_milestone, "amount_minor", minimum=0),
                delivery_days=require_int(raw_milestone, "delivery_days", minimum=1, maximum=3650),
            )
        )
    return result


def _serialize_proposal(proposal: Proposal) -> dict[str, object]:
    return {
        "id": str(proposal.id),
        "project_id": str(proposal.project_id),
        "freelancer_user_id": str(proposal.freelancer_user_id),
        "status": proposal.status,
        "current_version": proposal.current_version,
        "versions": [_serialize_version(version) for version in proposal.versions],
    }


def _serialize_version(version: ProposalVersion) -> dict[str, object]:
    return {
        "id": str(version.id),
        "version_number": version.version_number,
        "amount_minor": version.amount_minor,
        "currency": version.currency,
        "delivery_days": version.delivery_days,
        "cover_letter": version.cover_letter,
        "milestones": [
            {
                "id": str(milestone.id),
                "sequence": milestone.sequence,
                "title": milestone.title,
                "amount_minor": milestone.amount_minor,
                "delivery_days": milestone.delivery_days,
            }
            for milestone in version.milestones
        ],
    }
