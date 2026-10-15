"""The app's language is read at startup and shown in the sidebar (ADR 0021, ADR 0022)."""

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

import gui_main
from shared import i18n


@pytest.fixture
def main_window(tmp_path, monkeypatch):
    """Same construction tests/test_shell.py uses."""
    monkeypatch.setenv("FULFILLMENT_SERVER_PATH", str(tmp_path))
    from gui.main_window_pyside import MainWindow

    win = MainWindow()
    win.show()
    QApplication.processEvents()
    yield win
    win.close()


def test_saved_language_is_applied_before_the_window(monkeypatch):
    QSettings("ShopifyFulfillmentTool", "FulfillmentApp").setValue("language", "bg")
    assert gui_main.apply_saved_language() == "bg"
    assert i18n.language() == "bg"
    assert i18n._("Restart now") == "Рестартирай сега"


def test_default_is_english():
    QSettings("ShopifyFulfillmentTool", "FulfillmentApp").remove("language")
    assert gui_main.apply_saved_language() == "en"


def test_sidebar_has_language_segment_and_hidden_update_button(qtbot):
    from gui.components.sidebar import Sidebar
    bar = Sidebar()
    qtbot.addWidget(bar)
    bar.show()
    assert bar.language_segment.buttons["en"].isChecked()
    assert bar.update_button.objectName() == "UpdateButton"
    assert bar.update_button.isHidden()
    bar.set_expanded(False)
    assert bar.language_segment.isHidden()


def test_sidebar_language_click_is_forwarded(qtbot):
    from gui.components.sidebar import Sidebar
    bar = Sidebar()
    qtbot.addWidget(bar)
    with qtbot.waitSignal(bar.languageRequested) as blocker:
        bar.language_segment.buttons["bg"].click()
    assert blocker.args == ["bg"]


def test_main_window_has_update_flow_and_overflow_item(main_window):
    assert main_window.update_flow is not None
    main_window.ui_manager._populate_overflow(main_window.command_bar)
    labels = [a.text() for a in main_window.command_bar.overflow.actions()]
    assert "Check for updates…" in labels
