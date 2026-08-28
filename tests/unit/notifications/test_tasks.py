from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select

from app.common.models import OutboxEvent
from app.extensions import db
from app.notifications.models import Notification, NotificationEventReceipt
from app.notifications.tasks import _consume, drain_notification_outbox
from tests.helpers import register_user

pytestmark = pytest.mark.unit


def test_notification_retry_after_post_commit_publish_failure_is_idempotent(
    client,
    app,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # type: ignore[no-untyped-def]
    user = register_user(client, email="notify-retry@example.com", role="employer")
    user_id = uuid.UUID(user["user"]["id"])

    with app.app_context():
        event = OutboxEvent(
            event_type="notification.requested",
            aggregate_type="notification",
            aggregate_id=str(user_id),
            payload={
                "user_id": str(user_id),
                "event_type": "message.created",
                "title": "Message",
                "body": "hello",
                "payload": {},
                "dedupe_key": "notification-retry-invariant",
            },
        )
        db.session.add(event)
        db.session.commit()
        event_id = event.id

        publish_attempts = 0

        def fail_after_commit(*_args: object, **_kwargs: object) -> None:
            nonlocal publish_attempts
            publish_attempts += 1
            raise OSError("realtime publisher unavailable")

        monkeypatch.setattr("app.notifications.tasks.publish_notification", fail_after_commit)
        with pytest.raises(OSError, match="realtime publisher unavailable"):
            _consume(event_id)

        # _consume commits the durable notification and receipt before realtime
        # publication. Celery is configured to retry this OSError, so the next
        # worker attempt must treat the event as already consumed.
        assert db.session.scalar(
            select(func.count(Notification.id)).where(
                Notification.user_id == user_id,
                Notification.dedupe_key == "notification-retry-invariant",
            )
        ) == 1
        assert db.session.scalar(
            select(func.count(NotificationEventReceipt.id)).where(
                NotificationEventReceipt.outbox_event_id == event_id
            )
        ) == 1

        monkeypatch.setattr(
            "app.notifications.tasks.publish_notification",
            lambda *_args, **_kwargs: None,
        )
        assert drain_notification_outbox.run(limit=100) == 0
        assert publish_attempts == 1
        assert db.session.scalar(
            select(func.count(Notification.id)).where(
                Notification.user_id == user_id,
                Notification.dedupe_key == "notification-retry-invariant",
            )
        ) == 1
        assert db.session.scalar(
            select(func.count(NotificationEventReceipt.id)).where(
                NotificationEventReceipt.outbox_event_id == event_id
            )
        ) == 1
