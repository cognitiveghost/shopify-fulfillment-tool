"""Run one command after the app has really quit (ADR 0021, ADR 0022).

A restart for a new language and an update's swap script both wait for
QCoreApplication.aboutToQuit, so a close the app vetoes starts nothing.
An update's command is never replaced by a plain relaunch: its script
starts the app itself.
"""

from __future__ import annotations

import subprocess
import sys

from PySide6.QtCore import QCoreApplication

_pending: list[str] | None = None
_is_update = False
_connected = False


def relaunch_argv() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, *sys.argv[1:]]
    return [sys.executable, *sys.argv]


def _quit_signal():
    # A seam: tests emit their own signal, because Qt WebEngine shuts itself
    # down on the application's aboutToQuit and crashes once a view has run.
    return QCoreApplication.instance().aboutToQuit


def on_quit(argv: list[str], *, update: bool = False) -> None:
    global _pending, _is_update, _connected
    if _is_update and not update:
        return
    _pending, _is_update = list(argv), update
    if not _connected:
        _quit_signal().connect(_fire)
        _connected = True


def pending() -> list[str] | None:
    return _pending


def _fire() -> None:
    global _pending
    if _pending is None:
        return
    argv, _pending = _pending, None
    _start(argv, _is_update)


def _start(argv: list[str], update: bool) -> None:
    if sys.platform == "win32":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        if update:
            flags |= subprocess.CREATE_NO_WINDOW
        subprocess.Popen(argv, close_fds=True, creationflags=flags)
    else:
        subprocess.Popen(argv, close_fds=True, start_new_session=True)


def _reset() -> None:
    """Tests only."""
    global _pending, _is_update, _connected
    _pending, _is_update, _connected = None, False, False
