"""One router for toasts (phase 3 spec section 9, ADR 0007).

A Qt toast is a child of the window and cannot paint above a web view, so a
toast raised while a web page shows is drawn by that page.
"""

import pytest
from PySide6.QtWidgets import QApplication, QWidget

from gui.components import Toast, toast


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def main_window(tmp_path, monkeypatch):
    monkeypatch.setenv("FULFILLMENT_SERVER_PATH", str(tmp_path))
    from gui.main_window_pyside import MainWindow

    win = MainWindow()
    win.resize(1100, 900)
    win.show()
    QApplication.processEvents()
    yield win
    win.close()


def _raised(bridge):
    seen = []
    bridge.toastRaised.connect(lambda text, undoable: seen.append((text, undoable)))
    return seen


def test_on_setup_the_page_draws_it(main_window):
    main_window.main_tabs.setCurrentIndex(0)
    seen = _raised(main_window.setup_bridge)

    shown = toast(main_window, "Session 2026-09-30_1 created.")

    assert seen == [("Session 2026-09-30_1 created.", False)]
    assert shown is None
    assert Toast.for_window(main_window) is None


def test_on_results_the_results_page_draws_it(main_window):
    main_window.main_tabs.setCurrentIndex(1)
    seen = _raised(main_window.results_bridge)
    other = _raised(main_window.setup_bridge)

    toast(main_window, "Settings saved")

    assert seen == [("Settings saved", False)]
    assert other == []


def test_on_browse_the_browse_page_draws_it(main_window):
    main_window.main_tabs.setCurrentIndex(2)
    seen = _raised(main_window.session_browser.bridge)
    other = _raised(main_window.setup_bridge)

    shown = toast(main_window, "Combined stock export saved: stock.xlsx.")

    assert seen == [("Combined stock export saved: stock.xlsx.", False)]
    assert other == []
    assert shown is None
    assert Toast.for_window(main_window) is None


def test_on_tools_the_tools_page_draws_it(main_window):
    main_window.main_tabs.setCurrentIndex(4)
    seen = _raised(main_window.tools_widget.bridge)
    other = _raised(main_window.setup_bridge)

    shown = toast(main_window, "Settings saved")

    # No action: the router's toast never offers Open folder.
    assert seen == [("Settings saved", False)]
    assert other == []
    assert shown is None
    assert Toast.for_window(main_window) is None


def test_on_a_qt_page_the_qt_toast_shows(main_window):
    main_window.main_tabs.setCurrentIndex(3)
    seen = _raised(main_window.setup_bridge)

    shown = toast(main_window, "Saved")

    assert shown is Toast.for_window(main_window)
    assert not shown.isHidden()
    assert seen == []


def test_a_child_of_the_window_is_routed_like_the_window(main_window):
    """A dialog toasts on its parent after it closes."""
    main_window.main_tabs.setCurrentIndex(0)
    seen = _raised(main_window.setup_bridge)
    child = QWidget(main_window)

    toast(child, "Settings saved")

    assert seen == [("Settings saved", False)]


def test_a_toast_with_an_action_stays_qt(main_window):
    """A web page's toast has no button to carry the action."""
    main_window.main_tabs.setCurrentIndex(0)
    seen = _raised(main_window.setup_bridge)

    shown = toast(
        main_window, "Exported 30 orders.", action_text="Open folder", on_action=lambda: None
    )

    assert shown is Toast.for_window(main_window)
    assert seen == []


def test_a_window_with_no_web_pages_keeps_the_qt_toast(qapp):
    window = QWidget()
    window.show()
    shown = toast(window, "Group created.")
    assert shown is Toast.for_window(window)
    window.close()
