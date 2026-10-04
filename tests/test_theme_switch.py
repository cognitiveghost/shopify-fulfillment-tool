"""Quickfix: pages take the theme first, the chrome follows (spec §4.4)."""

import pytest
from PySide6.QtGui import QColor
from PySide6.QtWebEngineWidgets import QWebEngineView
from test_results_bridge import _until_js

from gui import web_page
from gui.browse_bridge import mount_browse_page
from gui.logs_bridge import mount_logs_page
from gui.results_bridge import mount_results_page
from gui.settings.bridge import mount_settings_page
from gui.setup_bridge import mount_setup_page
from gui.theme_manager import get_theme_manager
from gui.tools_bridge import mount_tools_page
from gui.web_page import switch_theme
from shared.theme import theme_css_vars

MOUNTS = {
    "setup": mount_setup_page,
    "results": mount_results_page,
    "browse": mount_browse_page,
    "logs": mount_logs_page,
    "tools": mount_tools_page,
    "settings": mount_settings_page,
}
READY = "document.documentElement.dataset.bridge === 'ready'"


def _mounted(qtbot, mount, show=True):
    view = QWebEngineView()
    qtbot.addWidget(view)
    bridge = mount(view)
    view.resize(900, 600)
    if show:
        view.show()
        _until_js(qtbot, view, READY)
    return view, bridge


def _dark_css():
    return theme_css_vars(get_theme_manager().tokens_for("dark"))


def test_the_visible_page_is_themed_before_the_chrome(qtbot, qapp):
    _view, bridge = _mounted(qtbot, mount_setup_page)
    manager = get_theme_manager()
    # Hold the ack back so the in-between state can be observed.
    bridge.blockSignals(True)
    switch_theme("dark")
    assert bridge.themeCss == _dark_css()
    assert manager.get_current_theme_name() == "light"
    bridge.blockSignals(False)
    bridge.themePainted.emit()
    assert manager.get_current_theme_name() == "dark"


def test_the_page_acknowledges_and_the_chrome_follows(qtbot, qapp):
    _mounted(qtbot, mount_setup_page)
    switch_theme("dark")
    qtbot.waitUntil(
        lambda: get_theme_manager().get_current_theme_name() == "dark", timeout=2000
    )


def test_no_ack_falls_back_to_the_timeout(qtbot, qapp):
    _view, bridge = _mounted(qtbot, mount_setup_page)
    bridge.blockSignals(True)  # the page's themeApplied never arrives
    switch_theme("dark")
    assert get_theme_manager().get_current_theme_name() == "light"
    qtbot.wait(web_page.THEME_ACK_TIMEOUT_MS + 150)
    bridge.blockSignals(False)
    assert get_theme_manager().get_current_theme_name() == "dark"


def test_with_no_visible_page_the_switch_is_immediate(qtbot, qapp):
    _mounted(qtbot, mount_setup_page, show=False)
    switch_theme("dark")
    assert get_theme_manager().get_current_theme_name() == "dark"


def test_a_second_switch_wins(qtbot, qapp, monkeypatch):
    _view, bridge = _mounted(qtbot, mount_setup_page)
    manager = get_theme_manager()
    calls = []
    real = manager.set_theme
    monkeypatch.setattr(manager, "set_theme", lambda n: (calls.append(n), real(n))[1])
    bridge.blockSignals(True)
    switch_theme("dark")
    switch_theme("light")
    bridge.blockSignals(False)
    qtbot.wait(web_page.THEME_ACK_TIMEOUT_MS + 150)
    assert manager.get_current_theme_name() == "light"
    assert calls == ["dark", "light"] or calls == ["dark"]  # dark finished early, then back
    assert bridge.themeCss == theme_css_vars(manager.tokens_for("light"))


def test_switching_to_the_current_theme_does_nothing(qtbot, qapp, monkeypatch):
    manager = get_theme_manager()
    monkeypatch.setattr(manager, "set_theme", lambda n: pytest.fail("no switch expected"))
    switch_theme(manager.get_current_theme_name())


@pytest.mark.parametrize("name", sorted(MOUNTS))
def test_every_page_acknowledges_a_theme_change(qtbot, qapp, name):
    _view, bridge = _mounted(qtbot, MOUNTS[name])
    with qtbot.waitSignal(bridge.themePainted, timeout=5000):
        bridge.set_theme_css(_dark_css())


def test_a_page_does_not_acknowledge_its_first_load(qtbot, qapp):
    view = QWebEngineView()
    qtbot.addWidget(view)
    seen = []
    bridge = mount_setup_page(view)
    bridge.themePainted.connect(lambda: seen.append(1))
    view.show()
    _until_js(qtbot, view, READY)
    qtbot.wait(200)
    assert seen == []


def test_the_view_is_backed_by_the_page_plane(qtbot, qapp):
    view, _bridge = _mounted(qtbot, mount_setup_page)
    manager = get_theme_manager()
    assert view.page().backgroundColor() == QColor(manager.get_current_theme().surface_sunken)
    manager.set_theme("dark")
    assert view.page().backgroundColor() == QColor(manager.get_current_theme().surface_sunken)
