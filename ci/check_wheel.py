"""CI helper: inspect a built wheel without installing or running it.

Checks that the wheel has no runtime dependencies and ships exactly the
package modules plus one expected .dist-info directory (no tests, CI files or
stray metadata). On success prints a single line, ``version=<version>``,
suitable for ``$GITHUB_OUTPUT``.
"""

from __future__ import annotations

from email.parser import Parser
import re
import sys
import zipfile

PACKAGE = "linux_health_reporter"
DIST_INFO_MEMBERS = {
    "METADATA",
    "WHEEL",
    "RECORD",
    "entry_points.txt",
    "top_level.txt",
    "licenses/LICENSE",
}
_MODULE = re.compile(rf"{PACKAGE}/[A-Za-z_][A-Za-z0-9_]*\.py")


def find_problems(names: list[str], metadata_text: str) -> tuple[list[str], str | None]:
    """Return (problems, version) for a wheel's member names and METADATA text."""
    problems: list[str] = []
    metadata = Parser().parsestr(metadata_text)
    version = metadata.get("Version")
    if not version:
        return ["METADATA has no Version"], None

    dist_info = f"{PACKAGE}-{version}.dist-info/"
    dist_dirs = {name.split("/", 1)[0] for name in names if ".dist-info/" in name}
    if dist_dirs != {dist_info.rstrip("/")}:
        problems.append(f"expected exactly one {dist_info!r}, found {sorted(dist_dirs)}")

    allowed = {dist_info + member for member in DIST_INFO_MEMBERS}
    for name in names:
        if name in allowed or _MODULE.fullmatch(name):
            continue
        problems.append(f"unexpected file in wheel: {name}")
    if dist_info + "METADATA" not in names:
        problems.append("METADATA missing from the expected .dist-info")
    if PACKAGE + "/collectors.py" not in names:
        problems.append("package modules missing from wheel")

    requires = metadata.get_all("Requires-Dist") or []
    if requires:
        problems.append(f"unexpected runtime dependencies: {requires}")
    if metadata.get("License-Expression") != "MIT":
        problems.append("license metadata is not MIT")
    return problems, version


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: check_wheel.py <wheel>", file=sys.stderr)
        return 2
    with zipfile.ZipFile(argv[0]) as wheel:
        names = wheel.namelist()
        metadata_names = [n for n in names if n.endswith(".dist-info/METADATA")]
        if len(metadata_names) != 1:
            print(f"expected one METADATA file, found {metadata_names}", file=sys.stderr)
            return 1
        metadata_text = wheel.read(metadata_names[0]).decode("utf-8")

    problems, version = find_problems(names, metadata_text)
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1
    print(f"version={version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
