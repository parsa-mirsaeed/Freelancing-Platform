from __future__ import annotations

import uuid

from sqlalchemy import select

from app.calls.models import CallSession
from app.extensions import db
from app.identity.models import User
from app.messaging.service import get_conversation_for_user


def get_live_call_for_conversation(
    *,
    user: User,
    conversation_id: uuid.UUID,
) -> CallSession | None:
    """Return the invited/active call visible to a conversation member, if any."""
    conversation = get_conversation_for_user(user=user, conversation_id=conversation_id)
    return db.session.scalar(
        select(CallSession)
        .where(
            CallSession.conversation_id == conversation.id,
            CallSession.status.in_(("INVITED", "ACTIVE")),
        )
        .order_by(CallSession.created_at.desc())
    )
