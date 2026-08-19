from __future__ import annotations

import os
import threading
import uuid

import pytest
from sqlalchemy import select

from app import create_app
from app.calls.models import CallSession
from app.calls.service import invite_call
from app.errors import ApiError
from app.extensions import db
from app.identity.models import User
from app.messaging.models import Conversation, ConversationMember
from tests.helpers import register_user

pytestmark = pytest.mark.db


def _app():  # type: ignore[no-untyped-def]
    return create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "call-postgres-integration-secret-key",
            "SQLALCHEMY_DATABASE_URI": os.environ["DATABASE_URL"],
            "REDIS_URL": "redis://localhost:6379/15",
            "ELASTICSEARCH_URL": "http://localhost:9200",
            "ELASTICSEARCH_INDEX_PREFIX": "calls-db-integration-unused",
        }
    )


def test_postgres_serializes_competing_live_call_invites() -> None:
    app = _app()
    suffix = str(uuid.uuid4())
    with app.test_client() as client:
        first = register_user(
            client,
            email=f"calls-db-first-{suffix}@example.com",
            role="employer",
        )
        second = register_user(
            client,
            email=f"calls-db-second-{suffix}@example.com",
            role="freelancer",
        )
    first_id = uuid.UUID(first["user"]["id"])
    second_id = uuid.UUID(second["user"]["id"])
    with app.app_context():
        conversation = Conversation()
        conversation.members.extend(
            [
                ConversationMember(user_id=first_id),
                ConversationMember(user_id=second_id),
            ]
        )
        db.session.add(conversation)
        db.session.commit()
        conversation_id = conversation.id

    barrier = threading.Barrier(2)
    results: list[int] = []
    errors: list[BaseException] = []

    def invite(user_id: uuid.UUID, client_call_id: str) -> None:
        try:
            thread_app = _app()
            with thread_app.app_context():
                user = db.session.get(User, user_id)
                assert user is not None
                barrier.wait()
                try:
                    invite_call(
                        user=user,
                        conversation_id=conversation_id,
                        client_call_id=client_call_id,
                        call_type="VIDEO",
                    )
                    results.append(201)
                except ApiError as exc:
                    db.session.rollback()
                    results.append(exc.status)
        except BaseException as exc:  # pragma: no cover - diagnostic capture
            errors.append(exc)

    threads = [
        threading.Thread(target=invite, args=(first_id, f"{suffix}-first")),
        threading.Thread(target=invite, args=(second_id, f"{suffix}-second")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)

    assert not errors
    assert sorted(results) == [201, 409]
    with app.app_context():
        live_calls = list(
            db.session.scalars(
                select(CallSession).where(
                    CallSession.conversation_id == conversation_id,
                    CallSession.status.in_(("INVITED", "ACTIVE")),
                )
            )
        )
        assert len(live_calls) == 1
