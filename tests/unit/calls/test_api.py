from __future__ import annotations

import uuid

import pytest

from app.calls.models import CallSession
from app.calls.service import (
    MAX_SIGNAL_BYTES,
    accept_call,
    end_call,
    invite_call,
    signal_peer,
    validate_ice_candidate,
    validate_session_description,
)
from app.errors import ApiError
from app.extensions import db
from app.identity.models import User
from app.messaging.models import Conversation, ConversationMember
from tests.helpers import auth_header, register_user

pytestmark = pytest.mark.unit


def _conversation(client, app, *, suffix: str):  # type: ignore[no-untyped-def]
    employer = register_user(
        client,
        email=f"calls-employer-{suffix}@example.com",
        role="employer",
    )
    freelancer = register_user(
        client,
        email=f"calls-freelancer-{suffix}@example.com",
        role="freelancer",
    )
    intruder = register_user(
        client,
        email=f"calls-intruder-{suffix}@example.com",
        role="employer",
    )
    with app.app_context():
        conversation = Conversation()
        conversation.members.extend(
            [
                ConversationMember(user_id=uuid.UUID(employer["user"]["id"])),
                ConversationMember(user_id=uuid.UUID(freelancer["user"]["id"])),
            ]
        )
        db.session.add(conversation)
        db.session.commit()
        conversation_id = conversation.id
    return employer, freelancer, intruder, conversation_id


def test_call_lifecycle_authorization_and_idempotency(client, app) -> None:  # type: ignore[no-untyped-def]
    employer, freelancer, intruder, conversation_id = _conversation(
        client,
        app,
        suffix="lifecycle",
    )
    with app.app_context():
        employer_user = db.session.get(User, uuid.UUID(employer["user"]["id"]))
        freelancer_user = db.session.get(User, uuid.UUID(freelancer["user"]["id"]))
        intruder_user = db.session.get(User, uuid.UUID(intruder["user"]["id"]))
        assert employer_user is not None
        assert freelancer_user is not None
        assert intruder_user is not None

        call, created = invite_call(
            user=employer_user,
            conversation_id=conversation_id,
            client_call_id="browser-call-1",
            call_type="video",
        )
        assert created is True
        assert call.status == "INVITED"
        assert call.call_type == "VIDEO"

        duplicate, duplicate_created = invite_call(
            user=employer_user,
            conversation_id=conversation_id,
            client_call_id="browser-call-1",
            call_type="VIDEO",
        )
        assert duplicate_created is False
        assert duplicate.id == call.id

        with pytest.raises(ApiError) as busy:
            invite_call(
                user=freelancer_user,
                conversation_id=conversation_id,
                client_call_id="browser-call-2",
                call_type="VOICE",
            )
        assert busy.value.status == 409

        with pytest.raises(ApiError) as caller_accept:
            accept_call(user=employer_user, call_id=call.id)
        assert caller_accept.value.status == 403

        active, changed = accept_call(user=freelancer_user, call_id=call.id)
        assert changed is True
        assert active.status == "ACTIVE"
        repeated_active, repeated_changed = accept_call(
            user=freelancer_user,
            call_id=call.id,
        )
        assert repeated_changed is False
        assert repeated_active.id == active.id

        _call, peer_id = signal_peer(user=employer_user, call_id=call.id)
        assert peer_id == freelancer_user.id
        with pytest.raises(ApiError) as nonparty:
            signal_peer(user=intruder_user, call_id=call.id)
        assert nonparty.value.status == 403

        ended, ended_changed = end_call(
            user=freelancer_user,
            call_id=call.id,
            reason="finished",
        )
        assert ended_changed is True
        assert ended.status == "ENDED"
        ended_again, ended_again_changed = end_call(
            user=freelancer_user,
            call_id=call.id,
            reason="ignored retry",
        )
        assert ended_again_changed is False
        assert ended_again.id == ended.id
        assert db.session.get(CallSession, call.id) is not None


def test_signaling_payload_validation_is_bounded() -> None:
    offer = validate_session_description(
        {"type": "offer", "sdp": "v=0\r\n"},
        expected_type="offer",
    )
    assert offer["type"] == "offer"
    candidate = validate_ice_candidate(
        {
            "candidate": "candidate:1 1 UDP 2122260223 192.0.2.1 54400 typ host",
            "sdpMid": "0",
            "sdpMLineIndex": 0,
        }
    )
    assert candidate["sdpMid"] == "0"

    with pytest.raises(ApiError) as wrong_description:
        validate_session_description(
            {"type": "answer", "sdp": "v=0"},
            expected_type="offer",
        )
    assert wrong_description.value.status == 422

    with pytest.raises(ApiError) as oversized:
        validate_session_description(
            {"type": "offer", "sdp": "x" * MAX_SIGNAL_BYTES},
            expected_type="offer",
        )
    assert oversized.value.type == "payload_too_large"


def test_ice_credentials_are_short_lived_and_session_bound(client, app) -> None:  # type: ignore[no-untyped-def]
    user = register_user(
        client,
        email="turn-session@example.com",
        role="employer",
    )
    app.config.update(
        STUN_URLS="stun:stun.internal.example:3478",
        TURN_URLS="turn:turn.internal.example:3478?transport=udp",
        TURN_SHARED_SECRET="test-turn-shared-secret",
        TURN_CREDENTIAL_TTL_SECONDS=300,
    )

    first = client.get(
        "/api/v1/calls/ice-servers",
        headers=auth_header(user),
    )
    assert first.status_code == 200
    first_body = first.get_json()
    assert first_body["ttl_seconds"] == 300
    assert first_body["ice_servers"][0]["urls"] == ["stun:stun.internal.example:3478"]
    first_turn = first_body["ice_servers"][1]
    assert user["user"]["id"] in first_turn["username"]
    assert first_turn["credential"]

    second_session = client.post(
        "/api/v1/auth/login",
        json={
            "email": "turn-session@example.com",
            "password": "correct horse battery staple",
        },
    )
    assert second_session.status_code == 200
    second_body = client.get(
        "/api/v1/calls/ice-servers",
        headers=auth_header(second_session.get_json()),
    ).get_json()
    assert second_body["ice_servers"][1]["username"] != first_turn["username"]
    assert second_body["ice_servers"][1]["credential"] != first_turn["credential"]


def test_production_rejects_default_turn_secret(client, app) -> None:  # type: ignore[no-untyped-def]
    user = register_user(
        client,
        email="turn-production@example.com",
        role="employer",
    )
    app.config.update(
        APP_ENV="production",
        TURN_URLS="turn:turn.example.com:3478",
        TURN_SHARED_SECRET="development-only-turn-secret",
    )
    response = client.get(
        "/api/v1/calls/ice-servers",
        headers=auth_header(user),
    )
    assert response.status_code == 503
    assert response.get_json()["type"] == "turn_not_configured"
