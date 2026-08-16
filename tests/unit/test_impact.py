from pathlib import Path

import pytest

from ci.impact import calculate, load_config, write_github_output

pytestmark = pytest.mark.unit


def test_identity_change_selects_only_identity_core() -> None:
    result = calculate(["app/identity/service.py"], load_config())
    assert result["domains"] == ["identity"]
    assert result["flags"]["database"] is True
    assert result["flags"]["redis"] is False
    assert result["flags"]["search"] is False
    assert result["unit_targets"] == ["tests/unit/identity"]


def test_bootstrap_change_uses_core_database_without_redis_or_search() -> None:
    result = calculate(["app/__init__.py"], load_config())
    assert result["domains"] == ["bootstrap"]
    assert result["flags"]["database"] is True
    assert result["flags"]["redis"] is False
    assert result["flags"]["search"] is False
    assert result["unit_targets"] == ["tests/unit"]
    assert result["integration_targets"] == ["tests/integration/test_database.py"]


def test_contract_change_selects_contract_unit_and_database_integration() -> None:
    result = calculate(["app/contracts/service.py"], load_config())
    assert result["domains"] == ["contracts"]
    assert result["flags"]["database"] is True
    assert result["flags"]["redis"] is False
    assert result["flags"]["search"] is False
    assert result["unit_targets"] == ["tests/unit/contracts"]
    assert result["integration_targets"] == ["tests/integration/test_contracts.py"]


def test_freelancer_change_selects_search_projection() -> None:
    result = calculate(["app/freelancers/service.py"], load_config())
    assert result["domains"] == ["freelancers"]
    assert result["flags"]["database"] is True
    assert result["flags"]["search"] is True
    assert result["unit_targets"] == ["tests/unit/freelancers"]


def test_gig_change_does_not_start_elasticsearch() -> None:
    result = calculate(["app/gigs/service.py"], load_config())
    assert result["domains"] == ["gigs"]
    assert result["flags"]["database"] is True
    assert result["flags"]["search"] is False
    assert result["unit_targets"] == ["tests/unit/gigs"]


def test_shared_change_runs_full_unit_and_core_services() -> None:
    result = calculate(["app/extensions.py"], load_config())
    assert result["domains"] == ["shared"]
    assert result["unit_targets"] == ["tests/unit"]
    assert result["flags"]["redis"] is True
    assert result["flags"]["search"] is True


def test_unknown_change_falls_back_to_full_core() -> None:
    result = calculate(["new-area/unknown.py"], load_config())
    assert result["domains"] == ["fallback-full-core"]
    assert result["unit_targets"] == ["tests/unit"]
    assert result["integration_targets"] == ["tests/integration"]
    assert result["flags"]["search"] is True


def test_github_output_is_shell_safe(tmp_path: Path) -> None:
    destination = tmp_path / "output"
    result = calculate(["README.md"], load_config())
    write_github_output(result, destination)
    text = destination.read_text()
    assert "docs=true" in text
    assert "python=false" in text
    assert "search=false" in text
    assert "integration_targets=" in text
