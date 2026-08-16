from __future__ import annotations

import uuid
from datetime import UTC, datetime

from celery import shared_task
from sqlalchemy import select

from app.common.models import OutboxEvent
from app.extensions import db
from app.freelancers.models import FreelancerProfile
from app.freelancers.service import SEARCH_REFRESH_EVENT
from app.search.service import index_freelancer


@shared_task(name="search.drain_outbox")  # type: ignore[untyped-decorator]
def drain_search_outbox_task(limit: int = 100) -> int:
    return drain_search_outbox(limit=limit)


def drain_search_outbox(*, limit: int = 100, refresh: bool = False) -> int:
    events = list(
        db.session.scalars(
            select(OutboxEvent)
            .where(
                OutboxEvent.event_type == SEARCH_REFRESH_EVENT,
                OutboxEvent.published_at.is_(None),
            )
            .order_by(OutboxEvent.created_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    )
    processed = 0
    for event in events:
        profile = db.session.scalar(
            select(FreelancerProfile).where(
                FreelancerProfile.user_id == uuid.UUID(event.aggregate_id)
            )
        )
        if profile is not None:
            index_freelancer(profile, refresh=refresh)
        event.published_at = datetime.now(UTC)
        processed += 1
    db.session.commit()
    return processed
