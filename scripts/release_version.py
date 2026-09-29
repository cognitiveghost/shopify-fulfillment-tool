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
    """Bump the newest version tag. `tags` is newest first.

    Newest, not highest: 2025's releases were numbered up to 5.0.0 (packing)
    and 12.1.9 (Shopify), before the 1.x line that 2.0.0 continues.
    """
    base = next((tag for tag in tags if _TAG.fullmatch(tag)), "0.0.0")
    major, minor, patch = (int(part) for part in base.split(".")[:3])
    if bump == "major":
        version = f"{major + 1}.0.0"
    elif bump == "minor":
        version = f"{major}.{minor + 1}.0"
    elif bump == "patch":
        version = f"{major}.{minor}.{patch + 1}"
    else:
        raise ValueError(f"bump must be major, minor or patch, not {bump!r}")
    if version in tags:
        raise ValueError(f"{version} is already a tag")
    return version


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
            ["git", "tag", "--list", "--sort=-creatordate"], capture_output=True, text=True, check=True
        ).stdout.split()
        print(next_version(tags, args[0]))
    elif command == "stamp":
        stamp(args[0], args[1])
    else:
        sys.exit(f"unknown command {command!r}")
