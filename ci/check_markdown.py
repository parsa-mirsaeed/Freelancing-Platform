from __future__ import annotations

import argparse
from pathlib import Path


def validate(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    errors: list[str] = []
    if text and not text.endswith("\n"):
        errors.append("missing final newline")
    for number, line in enumerate(text.splitlines(), start=1):
        if line.rstrip() != line:
            errors.append(f"line {number}: trailing whitespace")
        if "\t" in line:
            errors.append(f"line {number}: tab character")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()
    failures: list[str] = []
    for path in args.paths:
        if not path.exists():
            continue
        for error in validate(path):
            failures.append(f"{path}: {error}")
    if failures:
        raise SystemExit("\n".join(failures))
    print(f"validated {len(args.paths)} Markdown files")


if __name__ == "__main__":
    main()
