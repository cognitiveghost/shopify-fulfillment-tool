"""The Client > Profile page, driven through a real Chromium (spec A4).

The page is a renderer: each test pushes a ProfileDraft view, then either
reads the DOM back or clicks and reads what the bridge was sent. Never mark skip.
"""

import copy

import pytest
from PySide6.QtWebEngineWidgets import QWebEngineView
from test_results_bridge import _eval, _until_js
from test_settings_web_page import (
    _click,
    _count,
    _key,
    _prop,
    _show,
    _text,
    _type,
    _wired,
)

from gui.settings.bridge import mount_settings_page
from gui.settings.profile_state import ProfileDraft

CONFIG = {
    "client_id": "ACME",
    "client_name": "Acme Ltd",
    "ui_settings": {"is_pinned": False, "group_id": "g1", "custom_color": "#112233"},
}
GROUPS = [{"id": "g1", "name": "Retail"}, {"id": "g2", "name": "Wholesale"}]
STATS = {"total_sessions": 3, "last_session_date": "2026-10-14", "last_accessed": None}


def profile(has_sessions=True):
    return ProfileDraft("ACME", copy.deepcopy(CONFIG), GROUPS, copy.deepcopy(STATS), has_sessions)


@pytest.fixture
def page(qtbot):
    view = QWebEngineView()
    qtbot.addWidget(view)
    bridge = mount_settings_page(view)
    view.resize(868, 700)
    view.show()
    _until_js(qtbot, view, "document.documentElement.dataset.bridge === 'ready'")
    return view, bridge


def _edit(qtbot, view, seen, action):
    """Wait for the page to have sent `action`, and return its arguments."""
    qtbot.waitUntil(lambda: any(sent == action for sent, _args in seen), timeout=3000)
    return next(args for sent, args in reversed(seen) if sent == action)


def _js(qtbot, view, script):
    return _eval(qtbot, view, f"(function () {{ {script} return true; }})()")


def test_the_page_draws_the_name_the_id_the_stats_and_the_danger_zone(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, profile())
    assert _prop(qtbot, view, _key("profile-name"), "value") == "Acme Ltd"
    assert _text(qtbot, view, _key("profile-id")) == "ACME"
    assert _count(qtbot, view, "[data-stat]") == 3
    assert _count(qtbot, view, '[data-act="profile-archive"], [data-act="profile-delete"]') == 2


def test_delete_is_disabled_while_the_client_has_sessions(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, profile(has_sessions=True))
    assert _prop(qtbot, view, _key("profile-delete"), "disabled") is True


def test_typing_the_name_sends_the_edit(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, profile())
    _type(qtbot, view, _key("profile-name"), "Acme G")
    assert _edit(qtbot, view, seen, "profile_name") == ["Acme G"]


def test_the_pin_switch_sends_the_edit(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, profile())
    _click(qtbot, view, _key("profile-pin"))
    assert _edit(qtbot, view, seen, "profile_pin") == []


def test_choosing_a_group_sends_the_edit(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, profile())
    _click(qtbot, view, _key("profile-group"))
    _click(qtbot, view, _key("profile-group-item-2"))
    assert _edit(qtbot, view, seen, "profile_group") == ["g2"]


def test_the_colour_input_sends_the_edit(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, profile())
    _js(
        qtbot,
        view,
        "const el = document.querySelector('[data-key=\"profile-colour\"]');"
        " el.value = '#abcdef';"
        " el.dispatchEvent(new Event('input', { bubbles: true }));",
    )
    assert _edit(qtbot, view, seen, "profile_colour") == ["#abcdef"]


def test_archive_asks_the_host(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, profile())
    asked = []
    bridge.clientActionRequested.connect(asked.append)
    _click(qtbot, view, _key("profile-archive"))
    qtbot.waitUntil(lambda: asked == ["archive"], timeout=3000)


def test_an_enabled_delete_asks_the_host(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, profile(has_sessions=False))
    asked = []
    bridge.clientActionRequested.connect(asked.append)
    _click(qtbot, view, _key("profile-delete"))
    qtbot.waitUntil(lambda: asked == ["delete"], timeout=3000)
