"""What every web page's bridge shares (phase 3 spec section 3.2)."""

import pytest
from PySide6.QtWidgets import QApplication

from gui.results_bridge import ResultsBridge
from gui.web_page import THEME_MARKER, WEB_DIR, PageBridge


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


def test_a_theme_is_announced_once_per_change():
    bridge = PageBridge()
    seen = []
    bridge.themeCssChanged.connect(lambda: seen.append(bridge.themeCss))
    bridge.set_theme_css(":root { --a: 1 }")
    bridge.set_theme_css(":root { --a: 1 }")
    assert seen == [":root { --a: 1 }"]


def test_a_toast_carries_its_text_and_whether_it_can_be_undone():
    bridge = PageBridge()
    seen = []
    bridge.toastRaised.connect(lambda text, undoable: seen.append((text, undoable)))
    bridge.raise_toast("Saved")
    bridge.raise_toast("3 orders held", undoable=True)
    assert seen == [("Saved", False), ("3 orders held", True)]


def test_the_results_bridge_is_a_page_bridge():
    assert issubclass(ResultsBridge, PageBridge)


def test_the_results_module_still_exports_what_its_tests_import():
    import gui.results_bridge as results

    assert results.WEB_DIR == WEB_DIR
    assert results.THEME_MARKER == THEME_MARKER
    assert results.PAGE == WEB_DIR / "results.html"
