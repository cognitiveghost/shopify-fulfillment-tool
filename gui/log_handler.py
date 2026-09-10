"""Bridges Python logging to Qt, as structure rather than as text.

This handler runs on whatever thread logged, so it must only emit a signal --
never touch a widget. That is the whole reason it exists.

It emits a LogEntry, not a formatted line: the viewer filters by level, and a
level parsed back out of a formatted string is a level you can get wrong.

Spec: docs/superpowers/specs/2026-09-07-phase9-bundle7-info-becomes-logs-design.md
"""

import logging
import traceback
from datetime import datetime

from PySide6.QtCore import QObject, Signal

from gui.log_entry import LogEntry


class QtLogHandler(logging.Handler, QObject):
    """Emits one LogEntry per record, on the thread that logged it.

    Signals:
        entry_received (object): the LogEntry for each record.
    """

    entry_received = Signal(object)

    def __init__(self):
        QObject.__init__(self)
        logging.Handler.__init__(self)

    def emit(self, record):
        """Turn a LogRecord into a LogEntry and emit it.

        An exception's one-line summary rides on the message: the error banner
        (9.25) sends the operator here for the cause, and a row per record
        keeps the viewer one line per entry. The full traceback stays in the
        JSON file log.
        """
        message = record.getMessage()
        if record.exc_info and record.exc_info[1] is not None:
            etype, value = record.exc_info[:2]
            summary = traceback.format_exception_only(etype, value)[-1].strip()
            message = f"{message} — {summary}"
        entry = LogEntry(
            timestamp=datetime.fromtimestamp(record.created).astimezone(),
            level=record.levelno,
            source=record.name,
            message=message,
        )
        self.entry_received.emit(entry)
