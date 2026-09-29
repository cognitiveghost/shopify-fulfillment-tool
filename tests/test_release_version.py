"""The Release button's version logic (scripts/release_version.py)."""
from pathlib import Path

import pytest

from scripts.release_version import next_version, stamp

ROOT = Path(__file__).resolve().parent.parent
PACKAGE_INIT = ROOT / "shopify_tool" / "__init__.py"


@pytest.mark.parametrize(
    "tags, bump, expected",
    [
        (["1.9.11.0", "1.9.10.8"], "major", "2.0.0"),
        (["1.9.11.0", "1.9.10.8"], "patch", "1.9.12"),
        (["1.3.10.2", "1.3.2.0.2"], "minor", "1.4.0"),
        (["2.0.0", "1.9.11.0"], "patch", "2.0.1"),
        (["1.10.0", "1.9.0"], "patch", "1.10.1"),  # numeric, not string, order
        ([], "patch", "0.0.1"),
        (["v3", "nightly", "1.2"], "minor", "0.1.0"),  # non-version tags ignored
    ],
)
def test_next_version(tags, bump, expected):
    assert next_version(tags, bump) == expected


def test_an_unknown_bump_is_refused():
    with pytest.raises(ValueError):
        next_version(["1.0.0"], "huge")


def test_stamp_rewrites_only_the_version_line(tmp_path):
    init = tmp_path / "__init__.py"
    init.write_text('"""Pkg."""\n__version__ = "dev"\nAPP_NAME = "X"\n', encoding="utf-8")
    stamp(init, "2.0.0")
    assert init.read_text(encoding="utf-8") == '"""Pkg."""\n__version__ = "2.0.0"\nAPP_NAME = "X"\n'


def test_stamp_refuses_a_file_without_the_line(tmp_path):
    init = tmp_path / "__init__.py"
    init.write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(ValueError):
        stamp(init, "2.0.0")


def test_the_package_ships_as_dev():
    """CI stamps this exact line. If it drifts, stamp() raises and the
    release fails loudly instead of shipping a build that says "dev"."""
    source = PACKAGE_INIT.read_text(encoding="utf-8")
    assert source.count('__version__ = "dev"') == 1
