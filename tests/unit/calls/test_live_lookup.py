from __future__ import annotations

import uuid

import pytest

from app.calls.service import invite_call
from app.extensions import db
from app.identity.models import User
from app.messaging.models import Conversation, ConversationMember
from tests.helpers import auth_header, register_user

pytestmark = pytest.mark.unit


def test_live_call_lookup_is_member_scoped_and_recoverable(client, app) -> None:  # type: ignore[no-untyped-def]
    caller = register_user(
        client,
        email="call-recovery-caller@example.com",
        role="employer",
    )
    callee = register_user(
        client,
        email="call-recovery-callee@example.com",
        role="freelancer",
    )
    intruder = register_user(
        client,
        email="call-recovery-intruder@example.com",
        role="employer",
    )
    caller_id = uuid.UUID(caller["user"]["id"])
    callee_id = uuid.UUID(callee["user"]["id"])

    with app.app_context():
        conversation = Conversation()
        conversation.members.extend(
            [
                ConversationMember(user_id=caller_id),
                ConversationMember(user_id=callee_id),
            ]
        )
        db.session.add(conversation)
        db.session.commit()
        conversation_id = conversation.id

        caller_user = db.session.get(User, caller_id)
        assert caller_user is not None
        call, created = invite_call(
            user=caller_user,
            conversation_id=conversation_id,
            client_call_id="recoverable-browser-call",
            call_type="VIDEO",
        )
        assert created is True
        call_id = call.id

    caller_response = client.get(
        f"/api/v1/conversations/{conversation_id}/call",
        headers=auth_header(caller),
    )
    assert caller_response.status_code == 200
    assert caller_response.get_json()["call"]["id"] == str(call_id)
    assert caller_response.get_json()["call"]["status"] == "INVITED"

    callee_response = client.get(
        f"/api/v1/conversations/{conversation_id}/call",
        headers=auth_header(callee),
    )
    assert callee_response.status_code == 200
    assert callee_response.get_json()["call"]["id"] == str(call_id)

    forbidden = client.get(
        f"/api/v1/conversations/{conversation_id}/call",
        headers=auth_header(intruder),
    )
    assert forbidden.status_code == 403
