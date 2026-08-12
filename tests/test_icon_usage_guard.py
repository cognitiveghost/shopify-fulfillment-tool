"""Two guards, not unit tests.

The first is the whole point of this track: without it, the next dialog
someone adds reaches for a stock icon and the app drifts back to mixed
iconography one widget at a time. The second catches the failure mode
icon()'s KeyError cannot -- a typo in a rarely-opened dialog that no test
ever constructs.
"""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GUI_DIR = REPO_ROOT / "gui"
ICONS_DIR = GUI_DIR / "assets" / "icons"

# rglob, not glob: gui/ is flat today but Track 3 adds gui/components/, and a
# non-recursive scan would let the first package inside it escape silently.
_PY_FILES = sorted(GUI_DIR.rglob("*.py")) + [REPO_ROOT / "gui_main.py"]

_ICON_CALL = re.compile(r'\bicon\(\s*["\']([a-z0-9-]+)["\']')


def test_no_stock_icons_remain_anywhere_in_the_gui():
    offenders = []
    for path in _PY_FILES:
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "QStyle.SP_" in line:
                offenders.append(f"{path.name}:{lineno}: {line.strip()}")
    assert not offenders, (
        "Use gui.icons.icon() instead of OS-native stock icons:\n" + "\n".join(offenders)
    )


def test_every_referenced_icon_name_is_vendored():
    missing = []
    for path in _PY_FILES:
        if path.name == "icons.py":
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for name in _ICON_CALL.findall(line):
                if not (ICONS_DIR / f"{name}.svg").is_file():
                    missing.append(f"{path.name}:{lineno}: {name}")
    assert not missing, (
        "Referenced icons with no vendored SVG (see gui/assets/README.md to add "
        "one):\n" + "\n".join(missing)
    )


def test_ui_managers_icon_tables_are_vendored():
    """_TAB_ICONS and _BUTTON_ICONS hold bare string literals, not icon()
    calls, so the regex guard above cannot see them -- and they are the names
    most worth catching, since a typo there blanks the app's five tabs."""
    from gui.ui_manager import UIManager

    names = list(UIManager._TAB_ICONS) + list(UIManager._BUTTON_ICONS.values())
    missing = [n for n in names if not (ICONS_DIR / f"{n}.svg").is_file()]
    assert not missing, f"UIManager references unvendored icons: {missing}"


def test_the_guard_can_actually_see_icon_calls():
    """A regex guard that matches nothing passes vacuously forever. Assert it
    finds the call sites we know exist."""
    found = set()
    for path in _PY_FILES:
        found.update(_ICON_CALL.findall(path.read_text(encoding="utf-8")))
    assert {"package", "trash-2", "copy"} <= found
