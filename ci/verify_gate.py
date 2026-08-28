from __future__ import annotations

import argparse
import json
import os

ALLOWED = {"success", "skipped"}


def _workflow_results(explicit_results: list[str]) -> list[str]:
    if explicit_results:
        return explicit_results

    raw = os.environ.get("NEEDS_JSON", "").strip()
    if not raw:
        raise SystemExit("gate results are required via arguments or NEEDS_JSON")

    payload: object = json.loads(raw)
    if not isinstance(payload, dict):
        raise SystemExit("NEEDS_JSON must be a JSON object")

    results: list[str] = []
    for name, job in payload.items():
        if not isinstance(name, str) or not isinstance(job, dict):
            raise SystemExit("NEEDS_JSON contains an invalid job entry")
        result = job.get("result")
        if not isinstance(result, str):
            raise SystemExit(f"NEEDS_JSON job {name!r} has no result")
        results.append(f"{name}={result}")
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("results", nargs="*")
    args = parser.parse_args()

    failures: list[str] = []
    for item in _workflow_results(args.results):
        name, separator, result = item.partition("=")
        if not separator or result not in ALLOWED:
            failures.append(item)
    if failures:
        raise SystemExit("PR gate failed: " + ", ".join(failures))
    print("PR gate passed")


if __name__ == "__main__":
    main()
