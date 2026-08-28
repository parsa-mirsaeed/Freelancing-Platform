from pathlib import Path

import pytest

from ci.validate_adrs import REQUIRED_ARCHITECTURE_DECISIONS, validate_required_adrs

pytestmark = pytest.mark.unit


def _write_accepted_adr(root: Path, filename: str, *, heading_number: int | None = None) -> None:
    root.mkdir(parents=True, exist_ok=True)
    number = int(filename[:4]) if heading_number is None else heading_number
    (root / filename).write_text(
        f"# ADR-{number:04d}: Test decision\n\n## Status\n\nAccepted.\n",
        encoding="utf-8",
    )


def _complete_required_root(tmp_path: Path) -> Path:
    root = tmp_path / "adr"
    for filename in REQUIRED_ARCHITECTURE_DECISIONS.values():
        _write_accepted_adr(root, filename)
    return root


def test_required_decisions_include_outbox_and_double_entry() -> None:
    filenames = set(REQUIRED_ARCHITECTURE_DECISIONS.values())
    assert "0019-transactional-outbox.md" in filenames
    assert "0013-double-entry-money.md" in filenames
    assert "0004-versioned-proposals.md" not in filenames


def test_validate_required_adrs_rejects_duplicate_identifier(tmp_path: Path) -> None:
    root = _complete_required_root(tmp_path)
    _write_accepted_adr(root, "0013-second-decision.md")

    errors = validate_required_adrs(root)

    assert any("duplicate ADR-0013 identifier" in error for error in errors)


def test_validate_required_adrs_rejects_heading_mismatch(tmp_path: Path) -> None:
    root = _complete_required_root(tmp_path)
    _write_accepted_adr(root, "0007-redis-ephemeral-state.md", heading_number=99)

    errors = validate_required_adrs(root)

    assert any("filename is ADR-0007 but heading is ADR-0099" in error for error in errors)
