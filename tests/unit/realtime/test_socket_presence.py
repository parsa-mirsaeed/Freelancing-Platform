import uuid
from types import SimpleNamespace

import pytest

import app.realtime.socket as socket_module

pytestmark = pytest.mark.unit


def test_presence_query_returns_only_authorized_conversation_members(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    user_id = uuid.UUID("11111111-1111-4111-8111-111111111111")
    peer_id = uuid.UUID("22222222-2222-4222-8222-222222222222")
    conversation_id = uuid.UUID("33333333-3333-4333-8333-333333333333")
    user = SimpleNamespace(id=user_id)
    conversation = SimpleNamespace(
        id=conversation_id,
        members=[SimpleNamespace(user_id=user_id), SimpleNamespace(user_id=peer_id)],
    )

    monkeypatch.setattr(socket_module, "_require_socket_user", lambda: user)
    monkeypatch.setattr(
        socket_module,
        "get_conversation_for_user",
        lambda *, user, conversation_id: conversation,
    )
    monkeypatch.setattr(socket_module, "is_online", lambda member_id: member_id == peer_id)

    result = socket_module.presence_query({"conversation_id": str(conversation_id)})
    assert result == {
        "ok": True,
        "conversation_id": str(conversation_id),
        "members": [
            {"user_id": str(user_id), "online": False},
            {"user_id": str(peer_id), "online": True},
        ],
    }
