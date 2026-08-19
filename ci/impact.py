from __future__ import annotations

import argparse
import fnmatch
import json
import os
from pathlib import Path
from typing import Any

import yaml

CONFIG_PATH = Path(__file__).with_name("impact.yml")
ALL_FLAGS = (
    "python",
    "database",
    "redis",
    "search",
    "realtime",
    "files",
    "ci",
    "docker",
    "docs",
    "k8s",
    "dependencies",
    "frontend",
    "frontend_e2e",
    "frontend_dependencies",
)


def load_config() -> dict[str, Any]:
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    if not isinstance(config, dict) or not isinstance(config.get("domains"), dict):
        raise ValueError("impact.yml must contain a domains mapping")
    for domain, mapping in config["domains"].items():
        if not isinstance(mapping, dict) or not mapping.get("paths"):
            raise ValueError(f"domain {domain!r} must define non-empty paths")
    return config


def matches(path: str, pattern: str) -> bool:
    if pattern.endswith("/**"):
        prefix = pattern[:-3]
        return path == prefix or path.startswith(prefix + "/")
    return fnmatch.fnmatch(path, pattern)


def calculate(changed_paths: list[str], config: dict[str, Any]) -> dict[str, Any]:
    flags = {flag: False for flag in ALL_FLAGS}
    domains: list[str] = []
    unit_targets: set[str] = set()
    integration_targets: set[str] = set()
    frontend_unit_targets: set[str] = set()
    frontend_e2e_targets: set[str] = set()

    for domain, mapping in config["domains"].items():
        if any(matches(path, pattern) for path in changed_paths for pattern in mapping["paths"]):
            domains.append(domain)
            for flag in mapping.get("flags", []):
                if flag not in flags:
                    raise ValueError(f"unknown flag {flag!r} in domain {domain!r}")
                flags[flag] = True
            unit_targets.update(mapping.get("unit", []))
            integration_targets.update(mapping.get("integration", []))
            frontend_unit_targets.update(mapping.get("frontend_unit", []))
            frontend_e2e_targets.update(mapping.get("frontend_e2e", []))

    if not domains and changed_paths:
        for flag in ("python", "database", "redis", "search", "realtime", "files"):
            flags[flag] = True
        unit_targets.add("tests/unit")
        integration_targets.add("tests/integration")
        domains.append("fallback-full-core")

    return {
        "domains": domains,
        "flags": flags,
        "unit_targets": _minimize_targets(unit_targets),
        "integration_targets": _minimize_targets(integration_targets),
        "frontend_unit_targets": _minimize_targets(frontend_unit_targets),
        "frontend_e2e_targets": _minimize_targets(frontend_e2e_targets),
    }


def _minimize_targets(targets: set[str]) -> list[str]:
    ordered = sorted(targets, key=lambda path: (path.count("/"), path))
    selected: list[str] = []
    for target in ordered:
        if not any(target == parent or target.startswith(parent + "/") for parent in selected):
            selected.append(target)
    return selected


def write_github_output(result: dict[str, Any], destination: Path) -> None:
    lines = [f"domains={json.dumps(result['domains'], separators=(',', ':'))}"]
    for flag, enabled in result["flags"].items():
        lines.append(f"{flag}={'true' if enabled else 'false'}")
    lines.append("unit_targets=" + " ".join(result["unit_targets"]))
    lines.append("integration_targets=" + " ".join(result["integration_targets"]))
    lines.append("frontend_unit_targets=" + " ".join(result["frontend_unit_targets"]))
    lines.append("frontend_e2e_targets=" + " ".join(result["frontend_e2e_targets"]))
    with destination.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*")
    parser.add_argument("--paths-file", type=Path)
    parser.add_argument("--validate-config", action="store_true")
    parser.add_argument("--github-output", action="store_true")
    args = parser.parse_args()

    config = load_config()
    if args.validate_config:
        print("impact config valid")
        return

    changed = list(args.paths)
    if args.paths_file:
        changed.extend(
            line.strip() for line in args.paths_file.read_text().splitlines() if line.strip()
        )
    result = calculate(changed, config)
    print(json.dumps(result, indent=2, sort_keys=True))
    if args.github_output:
        output = os.environ.get("GITHUB_OUTPUT")
        if not output:
            raise RuntimeError("GITHUB_OUTPUT is required with --github-output")
        write_github_output(result, Path(output))


if __name__ == "__main__":
    main()
