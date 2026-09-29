"""One simulated PC: a Qt app driven by JSON lines on stdin, answering on the real stdout.

Imported by both agents before their app. It must never import either app.
Importing it moves fd 1 onto stderr, so an app print() cannot corrupt the
protocol channel.
"""

import json
import logging
import os
import sys
import threading
import time
import traceback

_PROTO = os.fdopen(os.dup(1), "w", buffering=1, encoding="utf-8")
os.dup2(2, 1)
sys.stdout = sys.stderr

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

_EVENTS: list[dict] = []
_ANSWERS: dict[str, str] = {}


def record(kind: str, **fields) -> None:
    _EVENTS.append({"kind": kind, **fields})


def _scripted(title: str, text: str) -> str | None:
    """The answer the current op scripted for a dialog, matched on a title/text substring."""
    haystack = f"{title}\n{text}".lower()
    for key, answer in _ANSWERS.items():
        if key.lower() in haystack:
            return answer
    return None


def _static_box(level: str):
    def box(parent, title, text, *args, **kwargs):
        answer = _scripted(str(title), str(text))
        record("dialog", level=level, title=str(title), text=str(text), answer=answer,
               unexpected=level == "question" and answer is None)
        if level == "question":
            return QMessageBox.StandardButton.Yes if answer == "yes" else QMessageBox.StandardButton.No
        return QMessageBox.StandardButton.Ok
    return box


def _exec(self):
    title = self.windowTitle()
    text = self.text() if isinstance(self, QMessageBox) else type(self).__name__
    answer = _scripted(title, text)
    record("dialog", level="exec", title=title, text=text, answer=answer, unexpected=answer is None)
    if isinstance(self, QMessageBox):
        return QMessageBox.StandardButton.Yes if answer == "yes" else QMessageBox.StandardButton.No
    return QDialog.DialogCode.Accepted if answer in ("yes", "accept") else QDialog.DialogCode.Rejected


class _LogCapture(logging.Handler):
    def emit(self, rec: logging.LogRecord) -> None:
        record("log", level=rec.levelname, source=rec.name, text=rec.getMessage()[:500])


def _on_exception(exc_type, exc, tb) -> None:
    record("exception", text="".join(traceback.format_exception(exc_type, exc, tb))[-4000:])


def install_capture() -> None:
    """Patch every modal and hook every crash. Call before building the window."""
    for level in ("question", "warning", "information", "critical"):
        setattr(QMessageBox, level, staticmethod(_static_box(level)))
    QDialog.exec = _exec
    QMessageBox.exec = _exec
    sys.excepthook = _on_exception
    threading.excepthook = lambda a: _on_exception(a.exc_type, a.exc_value, a.exc_traceback)


def capture_logs() -> None:
    """Record WARNING and above. Call after the app has set up its own logging."""
    handler = _LogCapture(level=logging.WARNING)
    logging.getLogger().addHandler(handler)


def capture_calls(module_name: str, func_name: str, kind: str) -> None:
    """Record every call of module.func_name, wherever it has been imported to."""
    import importlib

    original = getattr(importlib.import_module(module_name), func_name)

    def recorder(*args, **kwargs):
        record(kind, text=" | ".join(str(a) for a in args[1:]))
        return original(*args, **kwargs)

    for module in list(sys.modules.values()):
        if getattr(module, func_name, None) is original:
            setattr(module, func_name, recorder)


def pump_until(cond, timeout: float, what: str) -> None:
    deadline = time.monotonic() + timeout
    while not cond():
        if time.monotonic() > deadline:
            raise TimeoutError(f"{what} did not finish within {timeout}s")
        QApplication.processEvents()
        time.sleep(0.02)


def _reply(req_id, ok: bool, result, error) -> None:
    events = _EVENTS[:]
    _EVENTS.clear()
    _PROTO.write(json.dumps(
        {"id": req_id, "ok": ok, "result": result, "error": error, "events": events}, default=str
    ) + "\n")


class _Inbox(QObject):
    request = Signal(dict)


def serve(ops: dict) -> None:
    """Answer requests on the Qt thread until `quit` or stdin closes. Needs the QApplication built."""
    app = QApplication.instance()
    inbox = _Inbox()

    def handle(req: dict) -> None:
        args = dict(req.get("args") or {})
        _ANSWERS.clear()
        _ANSWERS.update(args.pop("answers", None) or {})
        try:
            result, ok, error = ops[req["op"]](**args), True, None
        except Exception:
            result, ok, error = None, False, traceback.format_exc()[-4000:]
        if req.get("id") is not None:
            _reply(req["id"], ok, result, error)
        if req["op"] == "quit":
            app.quit()

    inbox.request.connect(handle, Qt.ConnectionType.QueuedConnection)

    def read_stdin() -> None:
        for line in sys.stdin:
            if line.strip():
                inbox.request.emit(json.loads(line))
        inbox.request.emit({"id": None, "op": "quit"})

    threading.Thread(target=read_stdin, daemon=True).start()
    ops.setdefault("ping", lambda: {"pid": os.getpid()})
    ops.setdefault("print_probe", lambda: print("stray app output") or {"printed": True})
    ops.setdefault("dialog_probe", lambda: {"answer": str(QMessageBox.question(None, "Probe", "unscripted?"))})
    app.exec()
