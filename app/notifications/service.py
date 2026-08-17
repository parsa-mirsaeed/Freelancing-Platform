from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from app.errors import ApiError
from app.extensions import db
from app.identity.models import User
from app.notifications.models import Notification, NotificationDelivery, NotificationPreference

_CHANNELS = ("IN_APP", "EMAIL", "PUSH", "SMS")


def create_notification(
    *,
    user_id: uuid.UUID,
    event_type: str,
    title: str,
    body: str,
    payload: dict[str, object],
    dedupe_key: str,
) -> Notification:
    existing = db.session.scalar(
        select(Notification).where(
            Notification.user_id == user_id,
            Notification.dedupe_key == dedupe_key,
        )
    )
    if existing is not None:
        return existing

    notification = Notification(
        user_id=user_id,
        event_type=event_type,
        title=title[:160],
        body=body[:500],
        payload=payload,
        dedupe_key=dedupe_key[:180],
    )
    preferences = {
        preference.channel: preference.enabled
        for preference in db.session.scalars(
            select(NotificationPreference).where(
                NotificationPreference.user_id == user_id,
                NotificationPreference.event_type == event_type,
            )
        )
    }
    for channel in _CHANNELS:
        enabled = preferences.get(channel, channel == "IN_APP")
        if not enabled:
            continue
        notification.deliveries.append(
            NotificationDelivery(
                channel=channel,
                status="DELIVERED" if channel == "IN_APP" else "PENDING",
            )
        )
    db.session.add(notification)
    db.session.flush()
    return notification


def list_notifications(*, user: User, after: datetime | None, limit: int) -> list[Notification]:
    if limit < 1 or limit > 100:
        raise ApiError("validation_error", "Invalid limit", 422, "limit must be between 1 and 100")
    query = select(Notification).where(Notification.user_id == user.id)
    if after is not None:
        query = query.where(Notification.created_at > after)
    return list(db.session.scalars(query.order_by(Notification.created_at.asc()).limit(limit)))


def mark_notification_read(*, user: User, notification_id: uuid.UUID) -> Notification:
    notification = db.session.get(Notification, notification_id)
    if notification is None:
        raise ApiError(
            "notification_not_found", "Notification not found", 404, "Notification was not found"
        )
    if notification.user_id != user.id:
        raise ApiError("forbidden", "Forbidden", 403, "You may not read this notification")
    if notification.read_at is None:
        notification.read_at = datetime.now(UTC)
        db.session.commit()
    return notification


def set_preference(
    *, user: User, event_type: str, channel: str, enabled: bool
) -> NotificationPreference:
    normalized_event_type = event_type.strip()
    if not normalized_event_type or len(normalized_event_type) > 120:
        raise ApiError(
            "validation_error", "Invalid event type", 422, "event_type must be 1 to 120 chars"
        )
    normalized_channel = channel.upper()
    if normalized_channel not in _CHANNELS:
        raise ApiError("validation_error", "Invalid channel", 422, "Unknown notification channel")
    preference = db.session.scalar(
        select(NotificationPreference).where(
            NotificationPreference.user_id == user.id,
            NotificationPreference.event_type == normalized_event_type,
            NotificationPreference.channel == normalized_channel,
        )
    )
    if preference is None:
        preference = NotificationPreference(
            user_id=user.id,
            event_type=normalized_event_type,
            channel=normalized_channel,
            enabled=enabled,
        )
        db.session.add(preference)
    else:
        preference.enabled = enabled
    db.session.commit()
    return preference


def list_preferences(*, user: User) -> list[NotificationPreference]:
    return list(
        db.session.scalars(
            select(NotificationPreference)
            .where(NotificationPreference.user_id == user.id)
            .order_by(NotificationPreference.event_type, NotificationPreference.channel)
        )
    )


def serialize_notification(notification: Notification) -> dict[str, Any]:
    return {
        "id": str(notification.id),
        "event_type": notification.event_type,
        "title": notification.title,
        "body": notification.body,
        "payload": notification.payload,
        "dedupe_key": notification.dedupe_key,
        "read_at": notification.read_at.isoformat() if notification.read_at else None,
        "created_at": notification.created_at.isoformat(),
        "deliveries": [
            {
                "channel": delivery.channel,
                "status": delivery.status,
                "attempt_count": delivery.attempt_count,
            }
            for delivery in notification.deliveries
        ],
    }


def serialize_preference(preference: NotificationPreference) -> dict[str, Any]:
    return {
        "event_type": preference.event_type,
        "channel": preference.channel,
        "enabled": preference.enabled,
    }
