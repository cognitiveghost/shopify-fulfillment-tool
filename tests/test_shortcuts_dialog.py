"""The Keyboard shortcuts list must stay true to what the window binds."""

import pytest
from PySide6.QtGui import QShortcut
from PySide6.QtWidgets import QApplication

from gui.shortcuts_dialog import SHORTCUTS, ShortcutsDialog


@pytest.fixture
def main_window(tmp_path, monkeypatch):
    monkeypatch.setenv("FULFILLMENT_SERVER_PATH", str(tmp_path))
    from gui.main_window_pyside import MainWindow

    win = MainWindow()
    win.show()
    QApplication.processEvents()
    yield win
    win.close()


def _listed_keys():
    keys = []
    for combo, _action in SHORTCUTS:
        if combo == "Ctrl+1 … Ctrl+5":
            keys += [f"Ctrl+{n}" for n in range(1, 6)]
        else:
            keys.append(combo)
    return keys


def test_every_listed_shortcut_is_bound(main_window):
    bound = {s.key().toString() for s in main_window.findChildren(QShortcut)}
    missing = [k for k in _listed_keys() if k not in bound]
    assert missing == []


def test_the_dialog_shows_every_row(qapp):
    from PySide6.QtWidgets import QLabel

    dialog = ShortcutsDialog()
    try:
        assert dialog.windowTitle() == "Keyboard shortcuts"
        texts = {label.text() for label in dialog.findChildren(QLabel)}
        for combo, action in SHORTCUTS:
            assert combo in texts
            assert action in texts
    finally:
        dialog.deleteLater()
