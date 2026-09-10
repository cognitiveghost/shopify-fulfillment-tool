import logging
from datetime import datetime

from PySide6.QtCore import Qt

from gui.log_entry import LogEntry
from gui.log_model import LogBufferModel
from gui.pandas_model import ROLE_STATUS


def _entry(message="hello", level=logging.INFO, source="root"):
    return LogEntry(datetime(2026, 9, 7, 12, 0, 0).astimezone(), level, source, message)


def test_newest_entry_is_row_zero(qapp):
    model = LogBufferModel()
    model.append(_entry("first"), LogBufferModel.EXECUTION)
    model.append(_entry("second"), LogBufferModel.EXECUTION)
    assert model.rowCount() == 2
    assert model.index(0, 3).data(Qt.DisplayRole) == "second"


def test_the_buffer_evicts_the_oldest_at_capacity(qapp):
    model = LogBufferModel()
    for n in range(LogBufferModel.CAPACITY + 10):
        model.append(_entry(f"m{n}"), LogBufferModel.EXECUTION)
    assert model.rowCount() == LogBufferModel.CAPACITY
    # Newest survives, oldest is gone.
    assert model.index(0, 3).data(Qt.DisplayRole) == f"m{LogBufferModel.CAPACITY + 9}"
    messages = {model.index(r, 3).data(Qt.DisplayRole) for r in range(model.rowCount())}
    assert "m0" not in messages


def test_the_two_sources_keep_separate_buffers(qapp):
    model = LogBufferModel()
    model.append(_entry("did a thing", source="Report"), LogBufferModel.ACTIVITY)
    model.append(_entry("debug noise"), LogBufferModel.EXECUTION)

    model.set_source(LogBufferModel.ACTIVITY)
    assert model.rowCount() == 1
    assert model.index(0, 3).data(Qt.DisplayRole) == "did a thing"

    model.set_source(LogBufferModel.EXECUTION)
    assert model.rowCount() == 1
    assert model.index(0, 3).data(Qt.DisplayRole) == "debug noise"


def test_columns_are_time_level_source_message(qapp):
    model = LogBufferModel()
    model.append(
        _entry("boom", level=logging.ERROR, source="ShopifyToolLogger"),
        LogBufferModel.EXECUTION,
    )
    assert model.columnCount() == 4
    assert model.index(0, 1).data(Qt.DisplayRole) == "ERROR"
    assert model.index(0, 2).data(Qt.DisplayRole) == "ShopifyToolLogger"
    assert model.index(0, 3).data(Qt.DisplayRole) == "boom"


def test_error_rows_carry_the_danger_status_role(qapp):
    model = LogBufferModel()
    model.append(_entry("boom", level=logging.ERROR), LogBufferModel.EXECUTION)
    model.append(_entry("fine", level=logging.INFO), LogBufferModel.EXECUTION)
    # Row 0 is the newest -- "fine".
    assert model.index(0, 0).data(ROLE_STATUS) is None
    assert model.index(1, 0).data(ROLE_STATUS) == "status_danger"


def test_critical_counts_as_danger_too(qapp):
    model = LogBufferModel()
    model.append(_entry("worse", level=logging.CRITICAL), LogBufferModel.EXECUTION)
    assert model.index(0, 0).data(ROLE_STATUS) == "status_danger"


def test_clear_empties_only_the_current_source(qapp):
    model = LogBufferModel()
    model.append(_entry("a"), LogBufferModel.EXECUTION)
    model.append(_entry("b"), LogBufferModel.ACTIVITY)
    model.set_source(LogBufferModel.EXECUTION)
    model.clear()
    assert model.rowCount() == 0
    model.set_source(LogBufferModel.ACTIVITY)
    assert model.rowCount() == 1
