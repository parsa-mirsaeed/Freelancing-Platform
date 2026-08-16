import pytest

from tests.helpers import auth_header, register_user

pytestmark = pytest.mark.unit


def _create_profile(client, headers) -> None:  # type: ignore[no-untyped-def]
    response = client.put(
        "/api/v1/freelancers/me/profile",
        headers=headers,
        json={"title": "API Engineer", "skills": ["Flask"]},
    )
    assert response.status_code == 200


def test_gig_packages_use_minor_units_and_unique_tiers(
    client,  # type: ignore[no-untyped-def]
) -> None:
    freelancer = register_user(client, email="gig@example.com", role="freelancer")
    headers = auth_header(freelancer)
    _create_profile(client, headers)
    created = client.post(
        "/api/v1/gigs",
        headers=headers,
        json={
            "title": "Build a Flask API",
            "description": "Production-ready API",
            "packages": [
                {
                    "tier": "basic",
                    "amount_minor": 4999,
                    "currency": "USD",
                    "delivery_days": 5,
                    "revisions": 1,
                },
                {
                    "tier": "premium",
                    "amount_minor": 14999,
                    "currency": "USD",
                    "delivery_days": 10,
                    "revisions": 3,
                },
            ],
            "requirements": [{"prompt": "Describe your API", "required": True}],
        },
    )
    assert created.status_code == 201
    body = created.get_json()
    assert [package["tier"] for package in body["packages"]] == ["BASIC", "PREMIUM"]
    assert body["packages"][0]["amount_minor"] == 4999


def test_gig_requires_basic_package(client) -> None:  # type: ignore[no-untyped-def]
    freelancer = register_user(client, email="gig-invalid@example.com", role="freelancer")
    headers = auth_header(freelancer)
    _create_profile(client, headers)
    response = client.post(
        "/api/v1/gigs",
        headers=headers,
        json={
            "title": "Build API",
            "description": "API",
            "packages": [
                {
                    "tier": "PREMIUM",
                    "amount_minor": 10000,
                    "currency": "USD",
                    "delivery_days": 7,
                    "revisions": 1,
                }
            ],
        },
    )
    assert response.status_code == 422
