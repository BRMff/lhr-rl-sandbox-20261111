"""CI helper: inspect a built wheel without installing or running it.

Checks that the wheel has no runtime dependencies and ships only the package
and its metadata (no tests, CI files or examples). On success prints a single
line, ``version=<version>``, suitable for ``$GITHUB_OUTPUT``.
"""

from __future__ import annotations

from email.parser import Parser
import sys
import zipfile


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: check_wheel.py <wheel>", file=sys.stderr)
        return 2
    with zipfile.ZipFile(argv[0]) as wheel:
        names = wheel.namelist()
        metadata_name = next(n for n in names if n.endswith(".dist-info/METADATA"))
        metadata = Parser().parsestr(wheel.read(metadata_name).decode("utf-8"))

    problems = []
    requires = metadata.get_all("Requires-Dist") or []
    if requires:
        problems.append(f"unexpected runtime dependencies: {requires}")
    unexpected = [
        n for n in names
        if not n.startswith("linux_health_reporter/") and ".dist-info/" not in n
    ]
    if unexpected:
        problems.append(f"unexpected files in wheel: {unexpected}")
    if not any(n.endswith("linux_health_reporter/collectors.py") for n in names):
        problems.append("package modules missing from wheel")
    if metadata.get("License-Expression") != "MIT":
        problems.append("license metadata is not MIT")

    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1
    print(f"version={metadata['Version']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
