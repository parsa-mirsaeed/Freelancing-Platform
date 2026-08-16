from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def _documents() -> list[Path]:
    fragments = sorted(Path("docs/openapi").glob("*.yaml"))
    if not fragments:
        raise FileNotFoundError("docs/openapi/*.yaml")
    return fragments


def validate_document(path: Path) -> None:
    document: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"{path} must contain an OpenAPI object")
    if document.get("openapi") != "3.1.0":
        raise ValueError(f"{path} must use OpenAPI 3.1.0")
    if not isinstance(document.get("paths"), dict):
        raise ValueError(f"{path} must define a paths mapping")


def main() -> None:
    for path in _documents():
        validate_document(path)
        print(f"validated {path}")


if __name__ == "__main__":
    main()
