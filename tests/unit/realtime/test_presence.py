from __future__ import annotations

import uuid

import pytest

from app.realtime.presence import _presence_key, _socket_key

pytestmark = pytest.mark.unit


def test_presence_keys_are_scoped() -> None:
    user_id = uuid.uuid4()
    assert _presence_key(user_id) == f"presence:user:{user_id}"
    assert _socket_key("sid-123") == "socket-principal:sid-123"
