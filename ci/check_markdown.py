from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IGNORED_PARTS = {".git", "node_modules"}


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


def _markdown_paths(explicit_paths: list[Path]) -> list[Path]:
    if explicit_paths:
        return explicit_paths
    return sorted(
        path
        for path in ROOT.rglob("*.md")
        if not any(part in IGNORED_PARTS for part in path.relative_to(ROOT).parts)
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", type=Path)
    args = parser.parse_args()
    paths = _markdown_paths(args.paths)
    failures: list[str] = []
    for path in paths:
        if not path.exists():
            continue
        for error in validate(path):
            failures.append(f"{path}: {error}")
    if failures:
        raise SystemExit("\n".join(failures))
    print(f"validated {len(paths)} Markdown files")


if __name__ == "__main__":
    main()
