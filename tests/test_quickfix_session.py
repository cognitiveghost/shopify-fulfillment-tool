"""Quickfix: the bar announces a client only when it changed (spec §4.1)."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from gui.components.commandbar import ROW_ACTION, CommandBar


def _activate_action(bar, label):
    """What a click on an action row does: the box lands on it, then activated()."""
    model = bar.client_selector.model()
    for i in range(model.rowCount()):
        item = model.item(i)
        if item.data(Qt.UserRole) == ROW_ACTION and item.data(Qt.UserRole + 1) == label:
            bar.client_selector.setCurrentIndex(i)
            bar.client_selector.activated.emit(i)
            return
    raise AssertionError(f"no action row {label!r}")


def _action_labels(bar):
    model = bar.client_selector.model()
    return [
        model.item(i).data(Qt.UserRole + 1)
        for i in range(model.rowCount())
        if model.item(i).data(Qt.UserRole) == ROW_ACTION
    ]


@pytest.fixture
def bar(qapp):
    bar = CommandBar()
    bar.set_clients(["A", "B"])
    bar.set_current_client("A")
    return bar


def test_an_action_row_does_not_re_announce_the_client(bar):
    seen = []
    bar.clientChanged.connect(seen.append)
    for label in _action_labels(bar):
        _activate_action(bar, label)
    assert seen == []
    assert bar.current_client() == "A"


def test_a_refresh_does_not_re_announce_the_client(bar):
    seen = []
    bar.clientChanged.connect(seen.append)
    bar.set_clients(["A", "B", "C"])
    assert seen == []
    assert bar.current_client() == "A"


def test_a_real_change_still_emits(bar):
    seen = []
    bar.clientChanged.connect(seen.append)
    bar.set_current_client("B")
    bar.set_current_client("B")
    bar.set_current_client("A")
    assert seen == ["B", "A"]


@pytest.fixture
def main_window(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("FULFILLMENT_SERVER_PATH", str(tmp_path))
    from gui.main_window_pyside import MainWindow

    win = MainWindow()
    win.show()
    QApplication.processEvents()
    yield win
    win.close()


def test_an_open_session_survives_the_client_menu(main_window, qtbot, monkeypatch):
    win = main_window
    win.profile_manager.create_client_profile("M", "Client M")
    win.command_bar.set_clients(["M"])
    win.command_bar.set_current_client("M")
    qtbot.waitUntil(lambda: win.current_client_id == "M", timeout=5000)
    qtbot.waitUntil(lambda: not win._client_load_workers, timeout=5000)

    win.session_path = "/tmp/session-under-test"
    resets = []
    monkeypatch.setattr(win, "_reset_session_state", lambda: resets.append(1))
    # The dialogs are modal; the bar's behaviour is what is under test.
    monkeypatch.setattr(win.client_directory, "open_create_client_dialog", lambda _p: None)
    monkeypatch.setattr(win.client_directory, "open_groups_dialog", lambda _p: None)

    for label in _action_labels(win.command_bar):
        _activate_action(win.command_bar, label)
    win.client_directory.loaded.emit(win.client_directory.gather())
    QApplication.processEvents()
    qtbot.wait(200)  # a wrongly-started client load would land in here

    assert resets == []
    assert win.session_path == "/tmp/session-under-test"
