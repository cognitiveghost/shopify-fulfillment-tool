import json
from pathlib import Path

import pytest
from PySide6.QtWebEngineWidgets import QWebEngineView
from test_results_bridge import _eval, _until_js

from gui.web_page import PageBridge, mount_page
from shared import i18n

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "i18n_page.html"
BG = {
    "Save now": "Запази сега",
    "Search": "Търси",
    "Find": "Намери",
    "{n} of {m}": "{n} от {m}",
    "{n} order": ["{n} поръчка", "{n} поръчки"],
}


@pytest.fixture
def page(qtbot, tmp_path):
    catalogue = tmp_path / "bg.json"
    catalogue.write_text(json.dumps(BG, ensure_ascii=False), encoding="utf-8")
    i18n.set_language("bg", [catalogue])
    view = QWebEngineView()
    qtbot.addWidget(view)
    bridge = PageBridge(view)
    mount_page(view, bridge, FIXTURE, "bridge")
    _until_js(qtbot, view, "document.documentElement.dataset.bridge === 'ready'")
    yield view
    i18n.set_language("en", [])


def test_bridge_carries_language_and_catalogue():
    i18n.set_language("bg", [])
    bridge = PageBridge()
    assert bridge.property("language") == "bg"
    assert json.loads(bridge.property("strings")) == {}
    i18n.set_language("en", [])


def test_marked_text_and_attributes_are_translated(qtbot, page):
    assert _eval(qtbot, page, "document.getElementById('save').textContent") == "Запази сега"
    assert _eval(qtbot, page, "document.getElementById('search').placeholder") == "Търси"
    assert _eval(qtbot, page, "document.getElementById('search').title") == "Намери"
    assert _eval(qtbot, page, "document.getElementById('missing').textContent") == "Not translated"
    assert _eval(qtbot, page, "document.documentElement.lang") == "bg"


def test_js_built_text_uses_t_and_tn(qtbot, page):
    assert _eval(qtbot, page, "document.getElementById('built').textContent") == "2 от 5"
    assert _eval(qtbot, page, "document.getElementById('plural').textContent") == "3 поръчки"
