import pytest
from sqlalchemy import select

from app.extensions import db
from app.identity.models import UserSession

pytestmark = pytest.mark.unit


def test_register_refresh_me_and_logout(client) -> None:  # type: ignore[no-untyped-def]
    register = client.post(
        "/api/v1/auth/register",
        json={
            "email": " Freelancer@Example.com ",
            "password": "correct horse battery staple",
            "role": "freelancer",
        },
    )
    assert register.status_code == 201
    body = register.get_json()
    assert body["user"]["email"] == "freelancer@example.com"
    assert body["user"]["roles"] == ["freelancer"]

    me = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert me.status_code == 200
    assert me.get_json()["email"] == "freelancer@example.com"

    refreshed = client.post("/api/v1/auth/refresh", json={"refresh_token": body["refresh_token"]})
    assert refreshed.status_code == 200
    refreshed_body = refreshed.get_json()
    assert refreshed_body["refresh_token"] != body["refresh_token"]

    replay = client.post("/api/v1/auth/refresh", json={"refresh_token": body["refresh_token"]})
    assert replay.status_code == 401

    logout = client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {refreshed_body['access_token']}"},
    )
    assert logout.status_code == 204

    me_after_logout = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {refreshed_body['access_token']}"},
    )
    assert me_after_logout.status_code == 401

    session = db.session.scalar(select(UserSession))
    assert session is not None
    assert session.revoked_at is not None


def test_duplicate_email_is_rejected(client) -> None:  # type: ignore[no-untyped-def]
    payload = {
        "email": "person@example.com",
        "password": "correct horse battery staple",
        "role": "employer",
    }
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201
    duplicate = client.post("/api/v1/auth/register", json=payload)
    assert duplicate.status_code == 409
    assert duplicate.get_json()["type"] == "email_in_use"


def test_self_service_admin_role_is_rejected(client) -> None:  # type: ignore[no-untyped-def]
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "person@example.com",
            "password": "correct horse battery staple",
            "role": "admin",
        },
    )
    assert response.status_code == 422


def test_invalid_email_is_rejected(client) -> None:  # type: ignore[no-untyped-def]
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "not-an-email",
            "password": "correct horse battery staple",
            "role": "freelancer",
        },
    )
    assert response.status_code == 422
    assert response.get_json()["type"] == "validation_error"
