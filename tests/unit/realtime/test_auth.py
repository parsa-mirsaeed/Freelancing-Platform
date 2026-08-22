from datetime import UTC

import pytest

from app.extensions import db
from app.identity.models import UserSession
from app.realtime.auth import authenticate_socket_token
from tests.helpers import auth_header, register_user

pytestmark = pytest.mark.unit


def test_realtime_ticket_authenticates_active_socket_session(client) -> None:  # type: ignore[no-untyped-def]
    registered = register_user(
        client,
        email="realtime-ticket@example.com",
        role="freelancer",
    )
    ticket = client.post(
        "/api/v1/auth/realtime-ticket",
        headers=auth_header(registered),
    )
    assert ticket.status_code == 200

    principal = authenticate_socket_token(ticket.get_json()["token"])
    assert principal is not None
    assert principal.user.email == "realtime-ticket@example.com"

    session = db.session.get(UserSession, principal.session_id)
    assert session is not None
    session_expires_at = session.expires_at
    if session_expires_at.tzinfo is None:
        session_expires_at = session_expires_at.replace(tzinfo=UTC)
    assert principal.access_expires_at == session_expires_at


def test_access_token_socket_auth_remains_compatible(client) -> None:  # type: ignore[no-untyped-def]
    registered = register_user(
        client,
        email="realtime-access-compat@example.com",
        role="employer",
    )
    principal = authenticate_socket_token(registered["access_token"])
    assert principal is not None
    assert principal.user.email == "realtime-access-compat@example.com"

    session = db.session.get(UserSession, principal.session_id)
    assert session is not None
    session_expires_at = session.expires_at
    if session_expires_at.tzinfo is None:
        session_expires_at = session_expires_at.replace(tzinfo=UTC)
    assert principal.access_expires_at < session_expires_at
