import pytest

from tests.helpers import auth_header, register_user

pytestmark = pytest.mark.unit


def test_portfolio_item_is_owned_and_publicly_listed(
    client,  # type: ignore[no-untyped-def]
) -> None:
    freelancer = register_user(client, email="portfolio@example.com", role="freelancer")
    headers = auth_header(freelancer)
    profile = client.put(
        "/api/v1/freelancers/me/profile",
        headers=headers,
        json={"title": "Designer", "skills": ["UX"]},
    )
    assert profile.status_code == 200

    created = client.post(
        "/api/v1/freelancers/me/portfolio",
        headers=headers,
        json={
            "title": "Marketplace redesign",
            "description": "Case study",
            "external_url": "https://example.com/case-study",
        },
    )
    assert created.status_code == 201
    item_id = created.get_json()["id"]
    user_id = freelancer["user"]["id"]

    public = client.get(f"/api/v1/freelancers/{user_id}/portfolio")
    assert public.status_code == 200
    assert public.get_json()["items"][0]["title"] == "Marketplace redesign"

    deleted = client.delete(f"/api/v1/portfolio/{item_id}", headers=headers)
    assert deleted.status_code == 204
