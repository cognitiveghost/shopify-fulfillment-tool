import logging
from datetime import datetime

from PySide6.QtCore import Qt

from gui.log_entry import LogEntry
from gui.log_filter import LogFilterProxy
from gui.log_model import LogBufferModel


def _model_with(*entries):
    model = LogBufferModel()
    for entry in entries:
        model.append(entry, LogBufferModel.EXECUTION)
    return model


def _entry(message, level=logging.INFO, source="root"):
    return LogEntry(datetime(2026, 9, 7, 12, 0, 0).astimezone(), level, source, message)


def _messages(proxy):
    return [proxy.index(r, 3).data(Qt.DisplayRole) for r in range(proxy.rowCount())]


def test_level_floor_hides_everything_below_it(qapp):
    model = _model_with(
        _entry("chatty", logging.DEBUG),
        _entry("normal", logging.INFO),
        _entry("careful", logging.WARNING),
        _entry("boom", logging.ERROR),
    )
    proxy = LogFilterProxy()
    proxy.setSourceModel(model)
    proxy.set_level_floor(logging.WARNING)
    assert sorted(_messages(proxy)) == ["boom", "careful"]


def test_search_matches_the_message(qapp):
    model = _model_with(_entry("picklist generated"), _entry("stock loaded"))
    proxy = LogFilterProxy()
    proxy.setSourceModel(model)
    proxy.set_search("pick")
    assert _messages(proxy) == ["picklist generated"]


def test_search_also_matches_the_source(qapp):
    model = _model_with(
        _entry("something", source="Report"),
        _entry("other", source="Session"),
    )
    proxy = LogFilterProxy()
    proxy.setSourceModel(model)
    proxy.set_search("repo")
    assert _messages(proxy) == ["something"]


def test_search_is_case_insensitive(qapp):
    model = _model_with(_entry("Picklist Generated"))
    proxy = LogFilterProxy()
    proxy.setSourceModel(model)
    proxy.set_search("PICKLIST")
    assert _messages(proxy) == ["Picklist Generated"]


def test_the_two_filters_compose(qapp):
    model = _model_with(
        _entry("picklist ok", logging.INFO),
        _entry("picklist failed", logging.ERROR),
        _entry("stock failed", logging.ERROR),
    )
    proxy = LogFilterProxy()
    proxy.setSourceModel(model)
    proxy.set_level_floor(logging.ERROR)
    proxy.set_search("picklist")
    assert _messages(proxy) == ["picklist failed"]


def test_an_empty_search_matches_everything(qapp):
    model = _model_with(_entry("a"), _entry("b"))
    proxy = LogFilterProxy()
    proxy.setSourceModel(model)
    proxy.set_search("")
    assert len(_messages(proxy)) == 2
