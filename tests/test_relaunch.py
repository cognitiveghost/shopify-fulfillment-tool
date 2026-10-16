import sys

import pytest
from PySide6.QtCore import QObject, Signal

from shared import relaunch


class _App(QObject):
    aboutToQuit = Signal()


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    started = []
    # The real aboutToQuit is never emitted here: Qt WebEngine's own shutdown
    # handler on it crashes the process once any test has used a web view.
    app = _App()
    monkeypatch.setattr(relaunch, "_quit_signal", lambda: app.aboutToQuit)
    monkeypatch.setattr(relaunch, "_start", lambda argv, update: started.append((argv, update)))
    relaunch._reset()
    yield started
    relaunch._reset()


def test_nothing_runs_until_the_app_quits(clean):
    relaunch.on_quit(["app.exe"])
    assert clean == []
    relaunch._quit_signal().emit()
    assert clean == [(["app.exe"], False)]


def test_runs_once(clean):
    relaunch.on_quit(["app.exe"])
    relaunch.on_quit(["app.exe"])
    relaunch._quit_signal().emit()
    relaunch._quit_signal().emit()
    assert clean == [(["app.exe"], False)]


def test_an_update_is_never_replaced_by_a_plain_relaunch(clean):
    relaunch.on_quit(["cmd", "/c", "swap.cmd"], update=True)
    relaunch.on_quit(["app.exe"])
    assert relaunch.pending() == ["cmd", "/c", "swap.cmd"]
    relaunch._quit_signal().emit()
    assert clean == [(["cmd", "/c", "swap.cmd"], True)]


def test_an_update_replaces_a_plain_relaunch(clean):
    relaunch.on_quit(["app.exe"])
    relaunch.on_quit(["cmd", "/c", "swap.cmd"], update=True)
    assert relaunch.pending() == ["cmd", "/c", "swap.cmd"]


def test_relaunch_argv(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["gui_main.py", "--x"])
    monkeypatch.setattr(sys, "executable", "/py")
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert relaunch.relaunch_argv() == ["/py", "gui_main.py", "--x"]
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert relaunch.relaunch_argv() == ["/py", "--x"]


def test_cancel_drops_a_relaunch_but_keeps_an_update(clean):
    relaunch.on_quit(["app.exe"])
    relaunch.cancel()
    assert relaunch.pending() is None
    relaunch.on_quit("cmd /c swap.cmd", update=True)
    relaunch.cancel()
    assert relaunch.pending() == "cmd /c swap.cmd"
