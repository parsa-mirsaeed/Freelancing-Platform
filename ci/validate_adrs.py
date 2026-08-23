from __future__ import annotations

import re
from pathlib import Path

ADR_ROOT = Path("docs/adr")
REQUIRED_ADRS = {
    1: "0001-modular-monolith.md",
    2: "0002-postgresql-system-of-record.md",
    3: "0003-search-projection-outbox.md",
    4: "0004-versioned-proposals.md",
    5: "0005-payment-provider-abstraction.md",
    6: "0006-elasticsearch-projection.md",
    7: "0007-redis-ephemeral-state.md",
    8: "0008-socketio-scaling.md",
    9: "0009-direct-s3-upload.md",
    10: "0010-idempotent-financial-operations.md",
    11: "0011-contract-snapshotting.md",
    12: "0012-impact-based-pr-testing.md",
}


def validate_required_adrs(root: Path = ADR_ROOT) -> list[str]:
    errors: list[str] = []
    for number, filename in REQUIRED_ADRS.items():
        path = root / filename
        if not path.is_file():
            errors.append(f"missing required ADR-{number:04d}: {path}")
            continue

        text = path.read_text(encoding="utf-8")
        first_line = text.splitlines()[0] if text else ""
        accepted_numbers = f"(?:{number:03d}|{number:04d})"
        if re.match(rf"^# ADR(?:-| ){accepted_numbers}(?::| )", first_line) is None:
            errors.append(
                f"{path} must start with an ADR-{number:03d} or ADR-{number:04d} heading; "
                f"got {first_line!r}"
            )
        if "## Status\n\nAccepted." not in text:
            errors.append(f"{path} must record an Accepted status")
    return errors


def main() -> int:
    errors = validate_required_adrs()
    if errors:
        for error in errors:
            print(f"ADR validation error: {error}")
        return 1
    print(f"Validated {len(REQUIRED_ADRS)} required architecture decisions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
