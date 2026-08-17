from __future__ import annotations

import os
import threading
import uuid

import pytest

from app import create_app
from app.extensions import db
from app.messaging.models import Message
from tests.helpers import auth_header, register_user

pytestmark = pytest.mark.db


def _app():  # type: ignore[no-untyped-def]
    return create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "communication-db-secret",
            "SQLALCHEMY_DATABASE_URI": os.environ["DATABASE_URL"],
            "REDIS_URL": "redis://localhost:6379/15",
            "ELASTICSEARCH_URL": "http://localhost:9200",
            "ELASTICSEARCH_INDEX_PREFIX": "communication-db-unused",
        }
    )


def _conversation(client, *, suffix: str):  # type: ignore[no-untyped-def]
    employer = register_user(client, email=f"comm-{suffix}-employer@example.com", role="employer")
    freelancer = register_user(
        client, email=f"comm-{suffix}-freelancer@example.com", role="freelancer"
    )
    project = client.post(
        "/api/v1/projects",
        headers=auth_header(employer),
        json={"title": "Concurrent chat", "description": "ordering", "skills": []},
    ).get_json()
    proposal = client.post(
        f"/api/v1/projects/{project['id']}/proposals",
        headers=auth_header(freelancer),
        json={"amount_minor": 9000, "currency": "USD", "delivery_days": 4},
    ).get_json()
    assert (
        client.post(
            f"/api/v1/proposals/{proposal['id']}/submit",
            headers=auth_header(freelancer),
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/proposals/{proposal['id']}/accept",
            headers=auth_header(employer),
        ).status_code
        == 200
    )
    contract = client.get(
        f"/api/v1/projects/{project['id']}/contract",
        headers=auth_header(employer),
    ).get_json()
    conversation = client.post(
        f"/api/v1/contracts/{contract['id']}/conversation",
        headers=auth_header(employer),
    ).get_json()
    return employer, freelancer, conversation


def test_postgres_serializes_concurrent_message_sequences() -> None:
    app = _app()
    suffix = str(uuid.uuid4())
    with app.test_client() as client:
        employer, _freelancer, conversation = _conversation(client, suffix=suffix)

    barrier = threading.Barrier(2)
    responses: list[tuple[int, int]] = []
    errors: list[BaseException] = []

    def send(client_id: str) -> None:
        try:
            thread_app = _app()
            with thread_app.test_client() as client:
                barrier.wait()
                response = client.post(
                    f"/api/v1/conversations/{conversation['id']}/messages",
                    headers=auth_header(employer),
                    json={"client_message_id": client_id, "body": client_id},
                )
                responses.append((response.status_code, response.get_json()["sequence"]))
        except BaseException as exc:  # pragma: no cover - diagnostic capture
            errors.append(exc)

    threads = [
        threading.Thread(target=send, args=(f"{suffix}-a",)),
        threading.Thread(target=send, args=(f"{suffix}-b",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert not errors
    assert sorted(responses) == [(201, 1), (201, 2)]
    with app.app_context():
        rows = list(
            db.session.query(Message)
            .filter(Message.conversation_id == uuid.UUID(conversation["id"]))
            .all()
        )
        assert sorted(message.sequence for message in rows) == [1, 2]
