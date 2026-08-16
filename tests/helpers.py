from __future__ import annotations

from typing import Any


def register_user(client: Any, *, email: str, role: str) -> dict[str, Any]:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "correct horse battery staple",
            "role": role,
        },
    )
    assert response.status_code == 201
    body = response.get_json()
    assert isinstance(body, dict)
    return body


def auth_header(body: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {body['access_token']}"}
