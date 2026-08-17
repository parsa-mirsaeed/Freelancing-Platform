from __future__ import annotations

from uuid import UUID

import pytest

from app.notifications.service import create_notification
from tests.helpers import auth_header, register_user

pytestmark = pytest.mark.unit


def test_notification_dedupe_and_preferences(client, app) -> None:  # type: ignore[no-untyped-def]
    user = register_user(client, email="notify@example.com", role="employer")
    headers = auth_header(user)
    preference = client.put(
        "/api/v1/notifications/preferences",
        headers=headers,
        json={"event_type": "message.created", "channel": "EMAIL", "enabled": True},
    )
    assert preference.status_code == 200

    with app.app_context():
        user_id = user["user"]["id"]
        first = create_notification(
            user_id=UUID(str(user_id)),
            event_type="message.created",
            title="Message",
            body="hello",
            payload={},
            dedupe_key="same",
        )
        second = create_notification(
            user_id=UUID(str(user_id)),
            event_type="message.created",
            title="Message",
            body="hello",
            payload={},
            dedupe_key="same",
        )
        assert first.id == second.id
        assert {item.channel for item in first.deliveries} == {"IN_APP", "EMAIL"}
