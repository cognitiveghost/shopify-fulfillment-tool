"""Versioning for the Release button (see .github/workflows).

The git tag is the app's only version. `next` picks the tag the release will
get; `stamp` writes it into the package's `__version__ = "dev"` line before
PyInstaller runs.

    python scripts/release_version.py next patch|minor|major
    python scripts/release_version.py stamp <package>/__init__.py <version>
"""
import re
import subprocess
import sys
from pathlib import Path

# Old releases used 4- and 5-part tags (1.9.11.0, 1.3.2.0.2); they count by
# their first three numbers.
_TAG = re.compile(r"\d+(\.\d+){2,}")
_VERSION_LINE = re.compile(r'^__version__ = ".*"$', re.MULTILINE)


def next_version(tags, bump):
    versions = [tuple(int(part) for part in tag.split(".")[:3]) for tag in tags if _TAG.fullmatch(tag)]
    major, minor, patch = max(versions, default=(0, 0, 0))
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    if bump == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError(f"bump must be major, minor or patch, not {bump!r}")


def stamp(path, version):
    path = Path(path)
    text, count = _VERSION_LINE.subn(f'__version__ = "{version}"', path.read_text(encoding="utf-8"))
    if count != 1:
        raise ValueError(f"expected one __version__ line in {path}, found {count}")
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    command, *args = sys.argv[1:]
    if command == "next":
        tags = subprocess.run(
            ["git", "tag", "--list"], capture_output=True, text=True, check=True
        ).stdout.split()
        print(next_version(tags, args[0]))
    elif command == "stamp":
        stamp(args[0], args[1])
    else:
        sys.exit(f"unknown command {command!r}")
