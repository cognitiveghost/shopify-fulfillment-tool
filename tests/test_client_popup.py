"""The client list filters as you type (spec A2)."""

from PySide6.QtCore import Qt

from gui.components.commandbar import ROW_ACTION, ROW_CLIENT, ROW_SECTION, CommandBar

DATA = {
    "special_groups": {},
    "custom_groups": [{"id": "g", "name": "Retail"}],
    "all_clients": ["ACME", "BETA", "ZED"],
    "pinned_client_ids": set(),
    "group_members": {"g": ["ACME", "BETA"]},
    "card_data": {
        "ACME": {"client_name": "Acme Ltd", "ui_settings": {}},
        "BETA": {"client_name": "Beta", "ui_settings": {}},
        "ZED": {"client_name": "Zed Shop", "ui_settings": {}},
    },
}


def _open(qtbot):
    bar = CommandBar()
    qtbot.addWidget(bar)
    bar.show()
    bar.set_clients_from(DATA)
    bar.client_selector.showPopup()
    popup = bar.client_selector.popup
    assert popup is not None and popup.isVisible()
    return bar, popup


def _visible(popup):
    p = popup.proxy
    return [(p.index(r, 0).data(Qt.UserRole), p.index(r, 0).data(Qt.DisplayRole)) for r in range(p.rowCount())]


def test_the_popup_opens_with_an_empty_focused_filter(qtbot):
    _bar, popup = _open(qtbot)
    assert popup.filter_edit.text() == ""
    assert popup.filter_edit.placeholderText() == "Filter clients"


def test_typing_keeps_matching_clients_and_their_section(qtbot):
    _bar, popup = _open(qtbot)
    popup.filter_edit.setText("acm")
    rows = _visible(popup)
    assert (ROW_SECTION, "Retail") in rows
    assert (ROW_CLIENT, "Acme Ltd") in rows
    assert (ROW_CLIENT, "Beta") not in rows
    assert (ROW_SECTION, "All Clients") not in rows  # its only client, Zed, is hidden
    assert any(k == ROW_ACTION for k, _t in rows)


def test_the_filter_matches_the_id_too(qtbot):
    _bar, popup = _open(qtbot)
    popup.filter_edit.setText("zed")
    assert (ROW_CLIENT, "Zed Shop") in _visible(popup)


def test_enter_picks_the_first_visible_client(qtbot):
    bar, popup = _open(qtbot)
    seen = []
    bar.clientChanged.connect(seen.append)
    popup.filter_edit.setText("beta")
    qtbot.keyClick(popup.filter_edit, Qt.Key_Return)
    assert seen == ["BETA"]
    assert not popup.isVisible()


def test_a_filter_matching_nothing_keeps_the_actions_and_enter_does_nothing(qtbot):
    bar, popup = _open(qtbot)
    seen = []
    bar.clientChanged.connect(seen.append)
    popup.filter_edit.setText("qqq")
    rows = _visible(popup)
    assert not any(k == ROW_CLIENT for k, _t in rows)
    assert sum(k == ROW_ACTION for k, _t in rows) == 4
    qtbot.keyClick(popup.filter_edit, Qt.Key_Return)
    assert seen == []


def test_down_skips_sections(qtbot):
    _bar, popup = _open(qtbot)
    qtbot.keyClick(popup.filter_edit, Qt.Key_Down)
    current = popup.list_view.currentIndex()
    assert current.data(Qt.UserRole) in (ROW_CLIENT, ROW_ACTION)


def test_escape_closes_without_a_change(qtbot):
    bar, popup = _open(qtbot)
    seen = []
    bar.clientChanged.connect(seen.append)
    qtbot.keyClick(popup.filter_edit, Qt.Key_Escape)
    assert not popup.isVisible()
    assert seen == []


def test_an_action_row_still_works_from_the_popup(qtbot):
    bar, popup = _open(qtbot)
    asked = []
    bar.createClientRequested.connect(lambda: asked.append(True))
    popup.filter_edit.setText("zzz")
    proxy = popup.proxy
    row = next(r for r in range(proxy.rowCount()) if proxy.index(r, 0).data(Qt.DisplayRole) == "New client…")
    popup.pick(proxy.index(row, 0))
    assert asked == [True]


def test_a_right_click_on_a_client_row_in_the_popup_asks_for_its_menu(qtbot):
    bar, popup = _open(qtbot)
    asked = []
    bar.clientMenuRequested.connect(lambda cid, _pos: asked.append(cid))
    proxy = popup.proxy
    row = next(r for r in range(proxy.rowCount()) if proxy.index(r, 0).data(Qt.UserRole + 1) == "ACME")
    index = proxy.index(row, 0)
    popup.list_view.customContextMenuRequested.emit(popup.list_view.visualRect(index).center())
    assert asked == ["ACME"]
