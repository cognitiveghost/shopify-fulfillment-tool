import logging
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from gui.log_entry import LogEntry
from gui.log_model import LogBufferModel
from gui.theme_manager import get_theme_manager


def _error_background(theme_name):
    manager = get_theme_manager()
    manager.set_theme(theme_name)
    model = LogBufferModel()
    model.append(
        LogEntry(datetime.now().astimezone(), logging.ERROR, "root", "boom"),
        LogBufferModel.EXECUTION,
    )
    return model.index(0, 0).data(Qt.BackgroundRole)


def test_the_error_tint_is_a_token_in_both_themes(qapp):
    light = _error_background("light")
    dark = _error_background("dark")
    assert isinstance(light, QColor)
    assert isinstance(dark, QColor)
    # Both themes define status_danger_bg, and they are not the same colour.
    assert light != dark
