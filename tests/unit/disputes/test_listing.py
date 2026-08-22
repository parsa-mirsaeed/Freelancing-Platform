from __future__ import annotations

import uuid

import pytest

from tests.helpers import auth_header, register_user
from tests.unit.disputes.test_api import _admin, _funded_approved_milestone

pytestmark = pytest.mark.unit


def test_dispute_inbox_is_authorized_and_cursor_bounded(client) -> None:  # type: ignore[no-untyped-def]
    employer, freelancer, milestone_id = _funded_approved_milestone(
        client,
        suffix="inbox",
    )
    opened = client.post(
        f"/api/v1/milestones/{milestone_id}/disputes",
        headers=auth_header(employer),
        json={"reason": "Inbox authorization coverage"},
    )
    assert opened.status_code == 201
    dispute_id = opened.get_json()["id"]

    outsider = register_user(
        client,
        email=f"dispute-outsider-{uuid.uuid4()}@example.com",
        role="employer",
    )
    admin = _admin(client)

    for user in (employer, freelancer, admin):
        response = client.get("/api/v1/disputes?limit=1", headers=auth_header(user))
        assert response.status_code == 200
        body = response.get_json()
        assert [item["id"] for item in body["items"]] == [dispute_id]
        assert body["items"][0]["milestone"]["id"] == str(milestone_id)
        assert body["items"][0]["milestone"]["amount_minor"] == 10000
        assert body["items"][0]["milestone"]["currency"] == "USD"

    forbidden_list = client.get("/api/v1/disputes", headers=auth_header(outsider))
    assert forbidden_list.status_code == 200
    assert forbidden_list.get_json() == {"items": [], "next_after": None}

    after = client.get(
        f"/api/v1/disputes?after={dispute_id}&limit=1",
        headers=auth_header(employer),
    )
    assert after.status_code == 200
    assert after.get_json() == {"items": [], "next_after": None}

    status_filter = client.get(
        "/api/v1/disputes?status=RESOLVED",
        headers=auth_header(employer),
    )
    assert status_filter.status_code == 200
    assert status_filter.get_json() == {"items": [], "next_after": None}

    invalid_limit = client.get("/api/v1/disputes?limit=101", headers=auth_header(employer))
    assert invalid_limit.status_code == 422

    invisible_cursor = client.get(
        f"/api/v1/disputes?after={dispute_id}",
        headers=auth_header(outsider),
    )
    assert invisible_cursor.status_code == 422
