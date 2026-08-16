from __future__ import annotations

import argparse

ALLOWED = {"success", "skipped"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("results", nargs="+")
    args = parser.parse_args()

    failures: list[str] = []
    for item in args.results:
        name, separator, result = item.partition("=")
        if not separator or result not in ALLOWED:
            failures.append(item)
    if failures:
        raise SystemExit("PR gate failed: " + ", ".join(failures))
    print("PR gate passed")


if __name__ == "__main__":
    main()
