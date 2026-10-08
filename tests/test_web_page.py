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


def test_the_shared_module_imports_nothing_from_an_app():
    import ast
    from pathlib import Path

    import shared.web_page as shared_page

    tree = ast.parse(Path(shared_page.__file__).read_text(encoding="utf-8"))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    assert not roots & {"gui", "shopify_tool"}


def test_the_adapter_hands_out_the_shared_bridge():
    import gui.web_page as adapter
    import shared.web_page as shared_page

    assert adapter.PageBridge is shared_page.PageBridge
    assert adapter.THEME_MARKER == shared_page.THEME_MARKER
    assert adapter.WEB_DIR.name == "web" and adapter.WEB_DIR.parent.name == "gui"


def test_the_kit_lives_in_shared_and_every_page_links_it_there():
    import shared.web_page as shared_page

    assert (shared_page.SHARED_WEB_DIR / "kit.css").is_file()
    for page in sorted(WEB_DIR.glob("*.html")):
        html = page.read_text(encoding="utf-8")
        assert 'href="../../shared/web/kit.css"' in html, page.name
