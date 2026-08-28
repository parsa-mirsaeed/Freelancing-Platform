from pathlib import Path

import pytest

from ci.impact import calculate, load_config, write_github_output
from ci.validate_adrs import REQUIRED_ARCHITECTURE_DECISIONS, validate_required_adrs

pytestmark = pytest.mark.unit


def test_identity_change_selects_only_identity_core() -> None:
    result = calculate(["app/identity/service.py"], load_config())
    assert result["domains"] == ["identity"]
    assert result["flags"]["database"] is True
    assert result["flags"]["redis"] is False
    assert result["flags"]["search"] is False
    assert result["unit_targets"] == ["tests/unit/identity"]


def test_bootstrap_change_uses_focused_app_smoke_without_search_or_socket() -> None:
    result = calculate(["app/__init__.py"], load_config())
    assert result["domains"] == ["bootstrap"]
    assert result["flags"]["database"] is True
    assert result["flags"]["search"] is False
    assert result["flags"]["realtime"] is False
    assert result["unit_targets"] == ["tests/unit/test_app.py"]
    assert result["integration_targets"] == ["tests/integration/test_database.py"]


def test_contract_change_selects_contract_unit_and_database_integration() -> None:
    result = calculate(["app/contracts/service.py"], load_config())
    assert result["domains"] == ["contracts"]
    assert result["flags"]["database"] is True
    assert result["flags"]["redis"] is False
    assert result["flags"]["search"] is False
    assert result["unit_targets"] == ["tests/unit/contracts"]
    assert result["integration_targets"] == ["tests/integration/test_contracts.py"]


def test_money_change_selects_only_money_unit_and_postgres_integration() -> None:
    result = calculate(["app/payments/service.py"], load_config())
    assert result["domains"] == ["payments"]
    assert result["flags"]["database"] is True
    assert result["flags"]["redis"] is False
    assert result["flags"]["search"] is False
    assert result["unit_targets"] == ["tests/unit/payments"]
    assert result["integration_targets"] == ["tests/integration/test_money.py"]


def test_ledger_change_selects_money_invariants_without_external_services() -> None:
    result = calculate(["app/ledger/service.py"], load_config())
    assert result["domains"] == ["ledger"]
    assert result["flags"]["database"] is True
    assert result["flags"]["redis"] is False
    assert result["flags"]["search"] is False
    assert result["unit_targets"] == ["tests/unit/ledger"]
    assert result["integration_targets"] == ["tests/integration/test_money.py"]


def test_dispute_change_selects_only_unit_and_postgres_invariants() -> None:
    result = calculate(["app/disputes/service.py"], load_config())
    assert result["domains"] == ["disputes"]
    assert result["flags"]["database"] is True
    assert result["flags"]["redis"] is False
    assert result["flags"]["search"] is False
    assert result["flags"]["realtime"] is False
    assert result["flags"]["files"] is False
    assert result["unit_targets"] == ["tests/unit/disputes"]
    assert result["integration_targets"] == ["tests/integration/test_disputes.py"]


def test_messaging_change_selects_postgres_and_realtime_only() -> None:
    result = calculate(["app/messaging/service.py"], load_config())
    assert result["domains"] == ["messaging"]
    assert result["flags"]["database"] is True
    assert result["flags"]["realtime"] is True
    assert result["flags"]["files"] is False
    assert result["flags"]["search"] is False
    assert result["unit_targets"] == ["tests/unit/messaging"]
    assert result["integration_targets"] == ["tests/integration/test_communication.py"]


def test_realtime_change_selects_redis_socket_without_postgres_job() -> None:
    result = calculate(["app/realtime/socket.py"], load_config())
    assert result["domains"] == ["realtime"]
    assert result["flags"]["realtime"] is True
    assert result["flags"]["database"] is False
    assert result["flags"]["files"] is False
    assert result["unit_targets"] == ["tests/unit/realtime"]


def test_file_change_selects_minio_and_postgres_without_search() -> None:
    result = calculate(["app/files/service.py"], load_config())
    assert result["domains"] == ["files"]
    assert result["flags"]["database"] is True
    assert result["flags"]["files"] is True
    assert result["flags"]["realtime"] is False
    assert result["flags"]["search"] is False
    assert result["unit_targets"] == ["tests/unit/files"]


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
    assert result["flags"]["realtime"] is True
    assert result["flags"]["files"] is True


def test_frontend_change_runs_frontend_only_with_targeted_browser_smoke() -> None:
    result = calculate(["frontend/src/app/page.tsx"], load_config())
    assert result["domains"] == ["frontend"]
    assert result["flags"]["frontend"] is True
    assert result["flags"]["frontend_e2e"] is True
    assert result["flags"]["python"] is False
    assert result["flags"]["database"] is False
    assert result["frontend_unit_targets"] == [
        "tests/unit/intl.test.ts",
        "tests/unit/proxy-policy.test.ts",
    ]
    assert result["frontend_e2e_targets"] == ["tests/e2e/smoke.spec.ts"]


def test_frontend_discovery_change_adds_only_discovery_tests() -> None:
    result = calculate(["frontend/src/app/talent/page.tsx"], load_config())
    assert result["domains"] == ["frontend", "frontend-discovery"]
    assert result["flags"]["frontend"] is True
    assert result["flags"]["frontend_e2e"] is True
    assert result["flags"]["python"] is False
    assert result["flags"]["database"] is False
    assert result["flags"]["search"] is False
    assert result["frontend_unit_targets"] == [
        "tests/unit/intl.test.ts",
        "tests/unit/marketplace.test.ts",
        "tests/unit/proxy-policy.test.ts",
    ]
    assert result["frontend_e2e_targets"] == [
        "tests/e2e/discovery.spec.ts",
        "tests/e2e/smoke.spec.ts",
    ]


def test_frontend_work_change_adds_only_work_tests() -> None:
    result = calculate(["frontend/src/app/services/page.tsx"], load_config())
    assert result["domains"] == ["frontend", "frontend-work"]
    assert result["flags"]["frontend"] is True
    assert result["flags"]["frontend_e2e"] is True
    assert result["flags"]["python"] is False
    assert result["flags"]["database"] is False
    assert result["flags"]["redis"] is False
    assert result["flags"]["search"] is False
    assert result["frontend_unit_targets"] == [
        "tests/unit/intl.test.ts",
        "tests/unit/proxy-policy.test.ts",
        "tests/unit/work.test.ts",
    ]
    assert result["frontend_e2e_targets"] == [
        "tests/e2e/smoke.spec.ts",
        "tests/e2e/work.spec.ts",
    ]


def test_frontend_proposal_change_adds_only_proposal_tests() -> None:
    result = calculate(["frontend/src/features/proposals/proposal-detail.tsx"], load_config())
    assert result["domains"] == ["frontend", "frontend-proposals"]
    assert result["flags"]["frontend"] is True
    assert result["flags"]["frontend_e2e"] is True
    assert result["flags"]["python"] is False
    assert result["flags"]["database"] is False
    assert result["flags"]["redis"] is False
    assert result["flags"]["search"] is False
    assert result["frontend_unit_targets"] == [
        "tests/unit/intl.test.ts",
        "tests/unit/proposals.test.ts",
        "tests/unit/proxy-policy.test.ts",
    ]
    assert result["frontend_e2e_targets"] == [
        "tests/e2e/proposals.spec.ts",
        "tests/e2e/smoke.spec.ts",
    ]


def test_frontend_contract_change_adds_only_contract_tests() -> None:
    result = calculate(["frontend/src/features/contracts/contract-workspace.tsx"], load_config())
    assert result["domains"] == ["frontend", "frontend-contracts"]
    assert result["flags"]["frontend"] is True
    assert result["flags"]["frontend_e2e"] is True
    assert result["flags"]["python"] is False
    assert result["flags"]["database"] is False
    assert result["flags"]["redis"] is False
    assert result["flags"]["search"] is False
    assert result["frontend_unit_targets"] == [
        "tests/unit/contracts.test.ts",
        "tests/unit/intl.test.ts",
        "tests/unit/proxy-policy.test.ts",
    ]
    assert result["frontend_e2e_targets"] == [
        "tests/e2e/contracts.spec.ts",
        "tests/e2e/smoke.spec.ts",
    ]


def test_frontend_money_change_adds_only_money_tests() -> None:
    result = calculate(["frontend/src/features/money/wallet-workspace.tsx"], load_config())
    assert result["domains"] == ["frontend", "frontend-money"]
    assert result["flags"]["frontend"] is True
    assert result["flags"]["frontend_e2e"] is True
    assert result["flags"]["python"] is False
    assert result["flags"]["database"] is False
    assert result["flags"]["redis"] is False
    assert result["flags"]["search"] is False
    assert result["frontend_unit_targets"] == [
        "tests/unit/intl.test.ts",
        "tests/unit/money.test.ts",
        "tests/unit/proxy-policy.test.ts",
    ]
    assert result["frontend_e2e_targets"] == [
        "tests/e2e/money.spec.ts",
        "tests/e2e/smoke.spec.ts",
    ]


def test_frontend_dependency_change_adds_audit_without_backend_services() -> None:
    result = calculate(["frontend/package.json"], load_config())
    assert result["domains"] == ["frontend", "frontend-dependencies"]
    assert result["flags"]["frontend"] is True
    assert result["flags"]["frontend_dependencies"] is True
    assert result["flags"]["database"] is False
    assert result["flags"]["search"] is False


def test_kubernetes_change_runs_policy_validation_only() -> None:
    result = calculate(["infra/kubernetes/base.yaml"], load_config())
    assert result["domains"] == ["kubernetes"]
    assert result["flags"]["k8s"] is True
    assert result["flags"]["python"] is False
    assert result["flags"]["database"] is False
    assert result["unit_targets"] == []
    assert result["integration_targets"] == []


def test_dependency_change_runs_audit_and_full_core() -> None:
    result = calculate(["pyproject.toml"], load_config())
    assert result["domains"] == ["dependencies"]
    assert result["flags"]["dependencies"] is True
    assert result["flags"]["database"] is True
    assert result["flags"]["redis"] is True
    assert result["flags"]["search"] is True
    assert result["flags"]["realtime"] is True
    assert result["flags"]["files"] is True
    assert result["unit_targets"] == ["tests/unit"]
    assert result["integration_targets"] == ["tests/integration"]


def test_unknown_change_falls_back_to_full_core() -> None:
    result = calculate(["new-area/unknown.py"], load_config())
    assert result["domains"] == ["fallback-full-core"]
    assert result["unit_targets"] == ["tests/unit"]
    assert result["integration_targets"] == ["tests/integration"]
    assert result["flags"]["search"] is True
    assert result["flags"]["realtime"] is True
    assert result["flags"]["files"] is True


def test_github_output_is_shell_safe(tmp_path: Path) -> None:
    destination = tmp_path / "output"
    result = calculate(["README.md"], load_config())
    write_github_output(result, destination)
    text = destination.read_text()
    assert "docs=true" in text
    assert "python=false" in text
    assert "search=false" in text
    assert "realtime=false" in text
    assert "files=false" in text
    assert "k8s=false" in text
    assert "dependencies=false" in text
    assert "frontend=false" in text
    assert "frontend_e2e=false" in text
    assert "frontend_unit_targets=" in text
    assert "frontend_e2e_targets=" in text
    assert "integration_targets=" in text


def _write_accepted_adr(root: Path, filename: str, *, heading_number: int | None = None) -> None:
    root.mkdir(parents=True, exist_ok=True)
    number = int(filename[:4]) if heading_number is None else heading_number
    (root / filename).write_text(
        f"# ADR-{number:04d}: Test decision\n\n## Status\n\nAccepted.\n",
        encoding="utf-8",
    )


def _complete_required_adr_root(tmp_path: Path) -> Path:
    root = tmp_path / "adr"
    for filename in REQUIRED_ARCHITECTURE_DECISIONS.values():
        _write_accepted_adr(root, filename)
    return root


def test_required_adrs_include_outbox_and_double_entry() -> None:
    filenames = set(REQUIRED_ARCHITECTURE_DECISIONS.values())
    assert "0019-transactional-outbox.md" in filenames
    assert "0013-double-entry-money.md" in filenames
    assert "0004-versioned-proposals.md" not in filenames


def test_adr_validation_rejects_duplicate_identifier(tmp_path: Path) -> None:
    root = _complete_required_adr_root(tmp_path)
    _write_accepted_adr(root, "0013-second-decision.md")

    errors = validate_required_adrs(root)

    assert any("duplicate ADR-0013 identifier" in error for error in errors)


def test_adr_validation_rejects_heading_mismatch(tmp_path: Path) -> None:
    root = _complete_required_adr_root(tmp_path)
    _write_accepted_adr(root, "0007-redis-ephemeral-state.md", heading_number=99)

    errors = validate_required_adrs(root)

    assert any("filename is ADR-0007 but heading is ADR-0099" in error for error in errors)
