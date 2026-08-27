"""A guard, not a unit test. Without it the next dialog someone adds reaches
for a hex string and the palette escapes the theme one widget at a time.

The checker's own behaviour is tested in packing-tool's tests/test_style_lint.py;
this file only asserts the repo is clean.
"""
from pathlib import Path

from shared.style_lint import _CSS_NAME, find_style_literals
from shared.theme import DARK_THEME, LIGHT_THEME, build_stylesheet

REPO_ROOT = Path(__file__).resolve().parent.parent
SCOPE = [REPO_ROOT / "gui", REPO_ROOT / "gui_main.py"]


def test_no_style_literals_anywhere_in_the_gui():
    findings = find_style_literals(SCOPE)
    assert not findings, (
        "Use a shared.theme token instead of a literal (see "
        "docs/superpowers/specs/2026-08-26-phase8-unified-design-system.md "
        "sections 3 and 4):\n" + "\n".join(findings)
    )


def test_the_built_stylesheet_names_no_css_colour():
    """shared/theme.py is not scanned as source -- it is where colour values
    belong -- so check its product instead. build_stylesheet used to emit five
    literal `color: white` declarations that on_accent exists to replace."""
    for theme in (LIGHT_THEME, DARK_THEME):
        hits = _CSS_NAME.findall(build_stylesheet(theme))
        assert not hits, f"{theme.name} stylesheet still names colours: {hits}"


def test_the_guard_can_actually_see_a_literal(tmp_path):
    offender = tmp_path / "offender.py"
    offender.write_text('S = "color: #ff0000;"', encoding="utf-8")
    assert find_style_literals([offender])


def test_every_detection_path_survived_the_shared_sync(tmp_path):
    """style_lint.py arrives here via scripts/sync_shared.py, and its unit
    tests stay in packing-tool. A truncated or half-synced copy would still
    catch the hex above while silently losing the other three rules, and the
    guard would keep passing. One offender per rule closes that."""
    offender = tmp_path / "offender.py"
    offender.write_text(
        'S = "color: red; font-size: 13px; background: rgb(1,2,3)"\n'
        'V = theme.accent_blue\n',
        encoding="utf-8",
    )
    kinds = {f.split(": ")[1] for f in find_style_literals([offender])}
    assert kinds == {"css-name", "px-font", "css-func", "alias"}, kinds
