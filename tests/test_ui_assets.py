"""The bundled assets are data, not code, so nothing else fails loudly when
one goes missing -- an absent SVG renders as a blank icon and an absent TTF
silently falls back to Segoe UI. This inventory is the only thing that
notices."""
from pathlib import Path

import pytest

ASSETS_DIR = Path(__file__).resolve().parent.parent / "shared" / "assets"

EXPECTED_ICONS = [
    "circle-minus", "clipboard-list", "copy", "folder", "folder-open",
    "folder-plus", "funnel-x", "info", "menu", "message-square", "package",
    "refresh-cw", "settings", "table", "tag", "tags", "trash-2", "wrench",
    "plus", "ellipsis-vertical", "check", "chevron-up", "chevron-down",
]


@pytest.mark.parametrize("name", EXPECTED_ICONS)
def test_every_expected_icon_is_vendored(name):
    assert (ASSETS_DIR / "icons" / f"{name}.svg").is_file()


@pytest.mark.parametrize("name", EXPECTED_ICONS)
def test_every_icon_uses_the_currentcolor_token(name):
    """shared/icons.py recolours by substituting this exact string. A glyph
    drawn with a literal colour would render in Lucide's default black and
    vanish against the dark theme."""
    source = (ASSETS_DIR / "icons" / f"{name}.svg").read_text(encoding="utf-8")
    assert "currentColor" in source


@pytest.mark.parametrize("filename", ["Inter-Regular.ttf", "Inter-Bold.ttf"])
def test_both_inter_faces_are_vendored(filename):
    path = ASSETS_DIR / "fonts" / filename
    assert path.is_file()
    assert path.stat().st_size > 100_000, "truncated download?"


def test_licenses_travel_with_the_assets():
    """Both ISC and SIL OFL require the notice ship alongside the files."""
    assert (ASSETS_DIR / "icons" / "LICENSE").is_file()
    assert (ASSETS_DIR / "fonts" / "OFL.txt").is_file()
