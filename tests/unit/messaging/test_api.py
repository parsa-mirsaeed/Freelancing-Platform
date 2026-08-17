from __future__ import annotations

import uuid

import pytest

from app.extensions import db
from app.files.models import FileObject
from app.notifications.tasks import drain_notification_outbox
from tests.helpers import auth_header, register_user

pytestmark = pytest.mark.unit


def _contract_chat(client, *, suffix: str):  # type: ignore[no-untyped-def]
    employer = register_user(client, email=f"{suffix}-employer@example.com", role="employer")
    freelancer = register_user(client, email=f"{suffix}-freelancer@example.com", role="freelancer")
    project = client.post(
        "/api/v1/projects",
        headers=auth_header(employer),
        json={"title": "Chat project", "description": "Discuss delivery", "skills": []},
    ).get_json()
    proposal = client.post(
        f"/api/v1/projects/{project['id']}/proposals",
        headers=auth_header(freelancer),
        json={"amount_minor": 7000, "currency": "USD", "delivery_days": 3},
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
    conversation_response = client.post(
        f"/api/v1/contracts/{contract['id']}/conversation",
        headers=auth_header(employer),
    )
    assert conversation_response.status_code == 200
    return employer, freelancer, contract, conversation_response.get_json()


def test_message_persists_orders_reconnects_and_deduplicates(
    client,
    app,  # type: ignore[no-untyped-def]
) -> None:
    employer, freelancer, _contract, conversation = _contract_chat(client, suffix="message")
    headers = auth_header(employer)

    first = client.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        headers=headers,
        json={"client_message_id": "client-1", "body": "hello"},
    )
    assert first.status_code == 201
    assert first.get_json()["sequence"] == 1

    duplicate = client.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        headers=headers,
        json={"client_message_id": "client-1", "body": "hello"},
    )
    assert duplicate.status_code == 201
    assert duplicate.get_json()["id"] == first.get_json()["id"]

    conflict = client.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        headers=headers,
        json={"client_message_id": "client-1", "body": "different"},
    )
    assert conflict.status_code == 409

    malformed = client.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        headers=headers,
        json={"client_message_id": "bad-file-list", "attachment_ids": "not-a-list"},
    )
    assert malformed.status_code == 422

    second = client.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        headers=auth_header(freelancer),
        json={"client_message_id": "client-2", "body": "reply"},
    )
    assert second.status_code == 201
    assert second.get_json()["sequence"] == 2

    missing = client.get(
        f"/api/v1/conversations/{conversation['id']}/messages?after=1&limit=50",
        headers=headers,
    )
    assert missing.status_code == 200
    assert [item["sequence"] for item in missing.get_json()] == [2]

    delivered = client.post(
        f"/api/v1/conversations/{conversation['id']}/delivered",
        headers=headers,
        json={"through_sequence": 2},
    )
    assert delivered.status_code == 200
    assert delivered.get_json()["through_sequence"] == 2

    read = client.post(
        f"/api/v1/conversations/{conversation['id']}/read",
        headers=headers,
        json={"through_sequence": 2},
    )
    assert read.status_code == 200
    assert read.get_json()["through_sequence"] == 2

    with app.app_context():
        assert drain_notification_outbox() == 2
        assert drain_notification_outbox() == 0
    notifications = client.get("/api/v1/notifications", headers=headers)
    assert notifications.status_code == 200
    assert len(notifications.get_json()) == 1


def test_chat_is_contract_party_only_and_attachment_must_be_safe(
    client,
    app,  # type: ignore[no-untyped-def]
) -> None:
    employer, freelancer, contract, conversation = _contract_chat(client, suffix="attachment")
    intruder = register_user(client, email="attachment-intruder@example.com", role="employer")
    forbidden = client.post(
        f"/api/v1/contracts/{contract['id']}/conversation",
        headers=auth_header(intruder),
    )
    assert forbidden.status_code == 403

    with app.app_context():
        owner_id = uuid.UUID(str(freelancer["user"]["id"]))
        file_object = FileObject(
            owner_user_id=owner_id,
            object_key=f"quarantine/{owner_id}/{uuid.uuid4()}/proof.pdf",
            original_name="proof.pdf",
            mime_type="application/pdf",
            size_bytes=20,
            purpose="MESSAGE_ATTACHMENT",
            status="QUARANTINED",
        )
        db.session.add(file_object)
        db.session.commit()
        file_id = file_object.id

    unsafe = client.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        headers=auth_header(freelancer),
        json={"client_message_id": "file-1", "attachment_ids": [str(file_id)]},
    )
    assert unsafe.status_code == 409

    with app.app_context():
        file_object = db.session.get(FileObject, file_id)
        assert file_object is not None
        file_object.status = "SAFE"
        db.session.commit()

    safe = client.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        headers=auth_header(freelancer),
        json={"client_message_id": "file-2", "attachment_ids": [str(file_id)]},
    )
    assert safe.status_code == 201
    assert safe.get_json()["attachments"] == [str(file_id)]
