import pytest

from app.config import Settings

pytestmark = pytest.mark.unit


def test_live_health_is_dependency_free(client) -> None:  # type: ignore[no-untyped-def]
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}
    assert response.headers["X-Request-ID"]


def test_unknown_route_uses_standard_error(client) -> None:  # type: ignore[no-untyped-def]
    response = client.get("/does-not-exist", headers={"X-Request-ID": "req-123"})
    assert response.status_code == 404
    assert response.get_json() == {
        "type": "not_found",
        "title": "Not found",
        "status": 404,
        "detail": "Resource was not found",
        "request_id": "req-123",
    }


def test_production_requires_explicit_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        Settings.from_env()
