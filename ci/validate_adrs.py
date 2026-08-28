from __future__ import annotations

import re
from pathlib import Path

ADR_ROOT = Path("docs/adr")
ADR_FILENAME_RE = re.compile(r"^(?P<number>\d{4})-.+\.md$")
ADR_HEADING_RE = re.compile(r"^# ADR(?:-| )(?P<number>\d{3,4})(?::| )")

# These are the architecture decisions required by the source blueprint. Existing
# ADR identifiers are historical and therefore do not need to match the source
# document's illustrative ordinal numbers; the decision itself must be present.
REQUIRED_ARCHITECTURE_DECISIONS = {
    "Modular Monolith": "0001-modular-monolith.md",
    "PostgreSQL as System of Record": "0002-postgresql-system-of-record.md",
    "Transactional Outbox": "0019-transactional-outbox.md",
    "Double-entry Ledger": "0013-double-entry-money.md",
    "Payment Provider Abstraction": "0005-payment-provider-abstraction.md",
    "Elasticsearch Projection": "0006-elasticsearch-projection.md",
    "Redis for Ephemeral State": "0007-redis-ephemeral-state.md",
    "Socket.IO Scaling": "0008-socketio-scaling.md",
    "Direct S3 Upload": "0009-direct-s3-upload.md",
    "Idempotent Financial Operations": "0010-idempotent-financial-operations.md",
    "Contract Snapshotting": "0011-contract-snapshotting.md",
    "PR Impact-based Testing": "0012-impact-based-pr-testing.md",
}


def validate_required_adrs(root: Path = ADR_ROOT) -> list[str]:
    errors: list[str] = []
    seen_numbers: dict[int, Path] = {}

    for path in sorted(root.glob("*.md")):
        filename_match = ADR_FILENAME_RE.match(path.name)
        if filename_match is None:
            errors.append(f"ADR filename must start with a four-digit identifier: {path}")
            continue

        filename_number = int(filename_match.group("number"))
        text = path.read_text(encoding="utf-8")
        first_line = text.splitlines()[0] if text else ""
        heading_match = ADR_HEADING_RE.match(first_line)
        if heading_match is None:
            errors.append(f"{path} must start with an ADR heading; got {first_line!r}")
        else:
            heading_number = int(heading_match.group("number"))
            if heading_number != filename_number:
                errors.append(
                    f"{path} filename is ADR-{filename_number:04d} but heading is "
                    f"ADR-{heading_number:04d}"
                )

        previous = seen_numbers.get(filename_number)
        if previous is not None:
            errors.append(f"duplicate ADR-{filename_number:04d} identifier: {previous} and {path}")
        else:
            seen_numbers[filename_number] = path

    for decision, filename in REQUIRED_ARCHITECTURE_DECISIONS.items():
        path = root / filename
        if not path.is_file():
            errors.append(f"missing required architecture decision {decision}: {path}")
            continue
        text = path.read_text(encoding="utf-8")
        if "## Status\n\nAccepted." not in text:
            errors.append(f"{path} must record an Accepted status for {decision}")

    return errors


def main() -> int:
    errors = validate_required_adrs()
    if errors:
        for error in errors:
            print(f"ADR validation error: {error}")
        return 1
    print(
        "Validated "
        f"{len(REQUIRED_ARCHITECTURE_DECISIONS)} required architecture decisions "
        "with unique ADR identifiers"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
