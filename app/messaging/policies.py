from __future__ import annotations

from app.identity.models import User
from app.messaging.models import Conversation


def is_conversation_member(user: User, conversation: Conversation) -> bool:
    return any(member.user_id == user.id for member in conversation.members)
