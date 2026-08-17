from __future__ import annotations

import uuid

from celery import shared_task
from sqlalchemy import select

from app.common.models import OutboxEvent
from app.extensions import db
from app.notifications.models import NotificationEventReceipt
from app.notifications.service import create_notification
from app.realtime.publisher import publish_notification


@shared_task(
    name="notifications.drain_outbox",
    autoretry_for=(OSError,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
    soft_time_limit=20,
    time_limit=30,
)  # type: ignore[untyped-decorator]
def drain_notification_outbox(limit: int = 100) -> int:
    event_ids = list(
        db.session.scalars(
            select(OutboxEvent.id)
            .outerjoin(
                NotificationEventReceipt,
                NotificationEventReceipt.outbox_event_id == OutboxEvent.id,
            )
            .where(
                OutboxEvent.event_type == "notification.requested",
                NotificationEventReceipt.id.is_(None),
            )
            .order_by(OutboxEvent.created_at.asc())
            .limit(limit)
        )
    )
    processed = 0
    for event_id in event_ids:
        if _consume(event_id):
            processed += 1
    return processed


def _consume(event_id: uuid.UUID) -> bool:
    event = db.session.scalar(
        select(OutboxEvent).where(OutboxEvent.id == event_id).with_for_update()
    )
    if event is None:
        return False
    if (
        db.session.scalar(
            select(NotificationEventReceipt.id).where(
                NotificationEventReceipt.outbox_event_id == event.id
            )
        )
        is not None
    ):
        return False

    payload = event.payload
    raw_notification_payload = payload.get("payload", {})
    notification_payload = (
        raw_notification_payload if isinstance(raw_notification_payload, dict) else {}
    )
    notification = create_notification(
        user_id=uuid.UUID(str(payload["user_id"])),
        event_type=str(payload["event_type"]),
        title=str(payload["title"]),
        body=str(payload["body"]),
        payload=notification_payload,
        dedupe_key=str(payload["dedupe_key"]),
    )
    db.session.add(NotificationEventReceipt(outbox_event_id=event.id))
    db.session.commit()
    publish_notification(
        user_id=notification.user_id,
        payload={
            "id": str(notification.id),
            "event_type": notification.event_type,
            "title": notification.title,
            "body": notification.body,
            "payload": notification.payload,
            "created_at": notification.created_at.isoformat(),
        },
    )
    return True
