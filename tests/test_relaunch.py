import sys

import pytest
from PySide6.QtCore import QCoreApplication

from shared import relaunch


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    started = []
    monkeypatch.setattr(relaunch, "_start", lambda argv, update: started.append((argv, update)))
    relaunch._reset()
    yield started
    relaunch._reset()


def test_nothing_runs_until_the_app_quits(qapp, clean):
    relaunch.on_quit(["app.exe"])
    assert clean == []
    QCoreApplication.instance().aboutToQuit.emit()
    assert clean == [(["app.exe"], False)]


def test_runs_once(qapp, clean):
    relaunch.on_quit(["app.exe"])
    relaunch.on_quit(["app.exe"])
    QCoreApplication.instance().aboutToQuit.emit()
    QCoreApplication.instance().aboutToQuit.emit()
    assert clean == [(["app.exe"], False)]


def test_an_update_is_never_replaced_by_a_plain_relaunch(qapp, clean):
    relaunch.on_quit(["cmd", "/c", "swap.cmd"], update=True)
    relaunch.on_quit(["app.exe"])
    assert relaunch.pending() == ["cmd", "/c", "swap.cmd"]
    QCoreApplication.instance().aboutToQuit.emit()
    assert clean == [(["cmd", "/c", "swap.cmd"], True)]


def test_an_update_replaces_a_plain_relaunch(qapp, clean):
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
