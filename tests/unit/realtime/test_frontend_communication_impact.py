import pytest

from ci.impact import calculate, load_config

pytestmark = pytest.mark.unit


def test_frontend_communication_change_selects_only_focused_frontend_checks() -> None:
    result = calculate(
        ["frontend/src/features/communication/communication-workspace.tsx"],
        load_config(),
    )
    assert result["domains"] == ["frontend", "frontend-communication"]
    assert result["flags"]["frontend"] is True
    assert result["flags"]["frontend_e2e"] is True
    assert result["flags"]["python"] is False
    assert result["flags"]["database"] is False
    assert result["flags"]["redis"] is False
    assert result["flags"]["search"] is False
    assert result["frontend_unit_targets"] == [
        "tests/unit/communication.test.ts",
        "tests/unit/intl.test.ts",
        "tests/unit/proxy-policy.test.ts",
    ]
    assert result["frontend_e2e_targets"] == [
        "tests/e2e/communication.spec.ts",
        "tests/e2e/smoke.spec.ts",
    ]
