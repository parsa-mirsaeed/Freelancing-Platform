import pytest

from app.identity.security import hash_password, verify_password

pytestmark = pytest.mark.unit


def test_password_hash_round_trip() -> None:
    encoded = hash_password("correct horse battery staple")
    assert encoded != "correct horse battery staple"
    assert verify_password(encoded, "correct horse battery staple") is True
    assert verify_password(encoded, "incorrect-password") is False


def test_short_password_is_rejected() -> None:
    with pytest.raises(ValueError, match="12"):
        hash_password("short")
