"""Run one command after the app has really quit (ADR 0021, ADR 0022).

A restart for a new language and an update's swap script both wait for
QCoreApplication.aboutToQuit, so a close the app vetoes starts nothing.
An update's command is never replaced by a plain relaunch: its script
starts the app itself.
"""

from __future__ import annotations

import logging
import subprocess
import sys

from PySide6.QtCore import QCoreApplication

_log = logging.getLogger(__name__)

# A list, or for an update's script a ready-quoted cmd line (cmd /s strips the
# outer quotes, which a list would escape).
_pending: list[str] | str | None = None
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


def on_quit(argv: list[str] | str, *, update: bool = False) -> None:
    global _pending, _is_update, _connected
    if _is_update and not update:
        return
    _pending, _is_update = (argv if isinstance(argv, str) else list(argv)), update
    if not _connected:
        _quit_signal().connect(_fire)
        _connected = True


def pending() -> list[str] | str | None:
    return _pending


def cancel() -> None:
    """Drop a plain relaunch whose close was vetoed. An armed update stays."""
    global _pending
    if not _is_update:
        _pending = None


def _fire() -> None:
    global _pending
    if _pending is None:
        return
    argv, _pending = _pending, None
    _start(argv, _is_update)


def _start(argv: list[str] | str, update: bool) -> None:
    try:
        if sys.platform == "win32":
            # CREATE_NO_WINDOW is ignored next to DETACHED_PROCESS, so the swap
            # script gets a hidden console instead: its tools then open no windows.
            flags = subprocess.CREATE_NEW_PROCESS_GROUP | (
                subprocess.CREATE_NO_WINDOW if update else subprocess.DETACHED_PROCESS)
            subprocess.Popen(argv, close_fds=True, creationflags=flags)
        else:
            subprocess.Popen(argv, close_fds=True, start_new_session=True)
    except OSError:
        _log.exception("Could not start %s after quit", argv)


def _reset() -> None:
    """Tests only."""
    global _pending, _is_update, _connected
    _pending, _is_update, _connected = None, False, False
