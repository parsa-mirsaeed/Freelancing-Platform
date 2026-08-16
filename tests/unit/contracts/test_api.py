from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.contracts.models import Contract, ContractVersion
from app.extensions import db
from tests.helpers import auth_header, register_user

pytestmark = pytest.mark.unit


def _accepted_contract(client, *, suffix: str = "contract", with_milestone: bool = True):  # type: ignore[no-untyped-def]
    employer = register_user(client, email=f"{suffix}-employer@example.com", role="employer")
    freelancer = register_user(client, email=f"{suffix}-freelancer@example.com", role="freelancer")
    project_response = client.post(
        "/api/v1/projects",
        headers=auth_header(employer),
        json={
            "title": "Contract project",
            "description": "Immutable scope",
            "budget_min_minor": 100000,
            "budget_max_minor": 200000,
            "currency": "USD",
            "skills": ["Python"],
        },
    )
    assert project_response.status_code == 201
    project = project_response.get_json()
    proposal_payload = {
        "amount_minor": 150000,
        "currency": "USD",
        "delivery_days": 12,
        "cover_letter": "Signed scope",
    }
    if with_milestone:
        proposal_payload["milestones"] = [
            {
                "title": "Backend delivery",
                "amount_minor": 150000,
                "delivery_days": 12,
            }
        ]
    proposal_response = client.post(
        f"/api/v1/projects/{project['id']}/proposals",
        headers=auth_header(freelancer),
        json=proposal_payload,
    )
    assert proposal_response.status_code == 201
    proposal = proposal_response.get_json()
    assert (
        client.post(
            f"/api/v1/proposals/{proposal['id']}/submit",
            headers=auth_header(freelancer),
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/proposals/{proposal['id']}/accept",
            headers=auth_header(employer),
        ).status_code
        == 200
    )
    contract_response = client.get(
        f"/api/v1/projects/{project['id']}/contract", headers=auth_header(employer)
    )
    assert contract_response.status_code == 200
    return employer, freelancer, project, proposal, contract_response.get_json()


def _sign(client, contract: dict[str, object], user: dict[str, object], key: str):  # type: ignore[no-untyped-def]
    version = contract["version"]
    assert isinstance(version, dict)
    response = client.post(
        f"/api/v1/contracts/{contract['id']}/sign",
        headers={**auth_header(user), "Idempotency-Key": key},
        json={"document_hash": version["document_hash"]},
    )
    assert response.status_code == 200
    return response.get_json()


def test_acceptance_is_owner_only_and_creates_one_snapshot_contract(
    client,  # type: ignore[no-untyped-def]
) -> None:
    employer = register_user(client, email="owner-employer@example.com", role="employer")
    intruder = register_user(client, email="owner-intruder@example.com", role="employer")
    freelancer = register_user(client, email="owner-freelancer@example.com", role="freelancer")
    second_freelancer = register_user(
        client, email="owner-second-freelancer@example.com", role="freelancer"
    )
    project = client.post(
        "/api/v1/projects",
        headers=auth_header(employer),
        json={"title": "Snapshot", "description": "Original scope", "skills": []},
    ).get_json()
    proposal = client.post(
        f"/api/v1/projects/{project['id']}/proposals",
        headers=auth_header(freelancer),
        json={
            "amount_minor": 120000,
            "currency": "USD",
            "delivery_days": 20,
            "cover_letter": "Initial terms",
            "milestones": [{"title": "Phase 1", "amount_minor": 120000, "delivery_days": 20}],
        },
    ).get_json()
    assert (
        client.post(
            f"/api/v1/proposals/{proposal['id']}/submit", headers=auth_header(freelancer)
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/proposals/{proposal['id']}/negotiate", headers=auth_header(employer)
        ).status_code
        == 200
    )
    revised = client.post(
        f"/api/v1/proposals/{proposal['id']}/versions",
        headers=auth_header(freelancer),
        json={
            "amount_minor": 140000,
            "currency": "USD",
            "delivery_days": 15,
            "cover_letter": "Final terms",
            "milestones": [{"title": "Phase 1", "amount_minor": 140000, "delivery_days": 15}],
        },
    )
    assert revised.status_code == 201

    forbidden = client.post(
        f"/api/v1/proposals/{proposal['id']}/accept", headers=auth_header(intruder)
    )
    assert forbidden.status_code == 403
    accepted = client.post(
        f"/api/v1/proposals/{proposal['id']}/accept", headers=auth_header(employer)
    )
    assert accepted.status_code == 200

    contract_response = client.get(
        f"/api/v1/projects/{project['id']}/contract", headers=auth_header(employer)
    )
    assert contract_response.status_code == 200
    contract = contract_response.get_json()
    assert contract["status"] == "PENDING_SIGNATURES"
    snapshot = contract["version"]["snapshot"]
    assert snapshot["scope"]["project_description"] == "Original scope"
    assert snapshot["scope"]["proposal_cover_letter"] == "Final terms"
    assert snapshot["price"]["amount_minor"] == 140000
    assert snapshot["currency"] == "USD"
    assert snapshot["delivery_days"] == 15
    assert snapshot["milestones"] == [
        {
            "sequence": 1,
            "title": "Phase 1",
            "amount_minor": 140000,
            "currency": "USD",
            "delivery_days": 15,
        }
    ]
    milestone = contract["version"]["milestones"][0]
    milestone_fields = ("sequence", "title", "amount_minor", "currency", "delivery_days")
    assert {key: milestone[key] for key in milestone_fields} == snapshot["milestones"][0]

    private = client.get(f"/api/v1/contracts/{contract['id']}", headers=auth_header(intruder))
    assert private.status_code == 403

    second = client.post(
        f"/api/v1/projects/{project['id']}/proposals",
        headers=auth_header(second_freelancer),
        json={"amount_minor": 130000, "currency": "USD", "delivery_days": 10},
    ).get_json()
    assert (
        client.post(
            f"/api/v1/proposals/{second['id']}/submit",
            headers=auth_header(second_freelancer),
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/proposals/{second['id']}/accept", headers=auth_header(employer)
        ).status_code
        == 409
    )
    assert len(list(db.session.scalars(select(Contract)))) == 1


def test_signatures_are_hash_bound_idempotent_and_both_required(
    client,  # type: ignore[no-untyped-def]
) -> None:
    employer, freelancer, _project, _proposal, contract = _accepted_contract(
        client, suffix="signing"
    )
    bad_hash = client.post(
        f"/api/v1/contracts/{contract['id']}/sign",
        headers={**auth_header(employer), "Idempotency-Key": "signing-bad-hash"},
        json={"document_hash": "0" * 64},
    )
    assert bad_hash.status_code == 409

    employer_signed = _sign(client, contract, employer, "signing-employer")
    assert employer_signed["status"] == "PENDING_SIGNATURES"
    assert len(employer_signed["version"]["signatures"]) == 1

    repeated = _sign(client, employer_signed, employer, "signing-employer")
    assert len(repeated["version"]["signatures"]) == 1

    active = _sign(client, repeated, freelancer, "signing-freelancer")
    assert active["status"] == "ACTIVE"
    assert len(active["version"]["signatures"]) == 2
    required = {party["user_id"] for party in active["parties"] if party["required_signature"]}
    signed = {signature["user_id"] for signature in active["version"]["signatures"]}
    assert required == signed


def test_contract_snapshot_cannot_be_silently_mutated(
    client,  # type: ignore[no-untyped-def]
) -> None:
    _employer, _freelancer, _project, _proposal, contract = _accepted_contract(
        client, suffix="immutable"
    )
    version_id = uuid.UUID(contract["version"]["id"])
    version = db.session.get(ContractVersion, version_id)
    assert version is not None
    original_hash = version.document_hash
    version.snapshot = {"tampered": True}
    with pytest.raises(ValueError, match="immutable"):
        db.session.commit()
    db.session.rollback()

    restored = db.session.get(ContractVersion, version_id)
    assert restored is not None
    assert restored.document_hash == original_hash
    assert restored.snapshot.get("tampered") is None


def test_cancelled_contract_rejects_new_milestone_submissions(
    client,  # type: ignore[no-untyped-def]
) -> None:
    employer, freelancer, _project, _proposal, contract = _accepted_contract(
        client, suffix="cancelled"
    )
    contract = _sign(client, contract, employer, "cancelled-employer")
    contract = _sign(client, contract, freelancer, "cancelled-freelancer")
    milestone_id = contract["version"]["milestones"][0]["id"]

    cancelled = client.post(
        f"/api/v1/contracts/{contract['id']}/cancel", headers=auth_header(employer)
    )
    assert cancelled.status_code == 200
    assert cancelled.get_json()["status"] == "CANCELLED"

    submission = client.post(
        f"/api/v1/milestones/{milestone_id}/submit",
        headers=auth_header(freelancer),
        json={"note": "should not persist"},
    )
    assert submission.status_code == 409
