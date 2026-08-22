import pytest

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


def test_access_token_socket_auth_remains_compatible(client) -> None:  # type: ignore[no-untyped-def]
    registered = register_user(
        client,
        email="realtime-access-compat@example.com",
        role="employer",
    )
    principal = authenticate_socket_token(registered["access_token"])
    assert principal is not None
    assert principal.user.email == "realtime-access-compat@example.com"
