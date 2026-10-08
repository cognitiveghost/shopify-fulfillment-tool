"""A page never shows an old session (2026-10-08 web tier freshness spec).

Driven through a real Chromium. Never mark skip.
"""

import pytest
from PySide6.QtWebEngineWidgets import QWebEngineView
from test_results_bridge import _eval, _until_js

from gui.browse_bridge import mount_browse_page
from gui.logs_bridge import mount_logs_page
from gui.results_bridge import mount_results_page
from gui.settings.bridge import mount_settings_page
from gui.setup_bridge import mount_setup_page
from gui.tools_bridge import mount_tools_page

MOUNTS = {
    "setup": mount_setup_page,
    "results": mount_results_page,
    "browse": mount_browse_page,
    "logs": mount_logs_page,
    "tools": mount_tools_page,
    "settings": mount_settings_page,
}


def _ready(qtbot, view):
    _until_js(qtbot, view, "document.documentElement.dataset.bridge === 'ready'")


def _painted(qtbot, view, bridge):
    """Wait until the page has reported the bridge's current revision."""
    qtbot.waitUntil(lambda: bridge.painted_revision == bridge.revision, timeout=15000)
    assert _eval(qtbot, view, "Number(document.documentElement.dataset.painted)") == bridge.revision


@pytest.mark.parametrize("name", sorted(MOUNTS))
def test_every_page_reports_the_revision_it_painted(qtbot, name):
    view = QWebEngineView()
    qtbot.addWidget(view)
    bridge = MOUNTS[name](view)
    view.resize(1166, 720)
    view.show()
    _ready(qtbot, view)
    _painted(qtbot, view, bridge)
    bridge.set_theme_css(bridge.themeCss + "\n/* again */")
    _painted(qtbot, view, bridge)
