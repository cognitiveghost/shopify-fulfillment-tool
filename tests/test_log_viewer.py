import logging
from datetime import datetime

from PySide6.QtCore import Qt

from gui.log_entry import LogEntry
from gui.log_model import LogBufferModel
from gui.log_viewer import LogViewer


def _entry(message="hello", level=logging.INFO, source="root"):
    return LogEntry(datetime(2026, 9, 7, 12, 0, 0).astimezone(), level, source, message)


def test_both_sources_render_in_one_widget(qapp):
    viewer = LogViewer()
    viewer.append(
        _entry("operator did a thing", source="Report"), LogBufferModel.ACTIVITY
    )
    viewer.append(_entry("program logged a thing"), LogBufferModel.EXECUTION)

    viewer.set_source(LogBufferModel.ACTIVITY)
    assert viewer.proxy.rowCount() == 1
    assert viewer.proxy.index(0, 3).data(Qt.DisplayRole) == "operator did a thing"

    viewer.set_source(LogBufferModel.EXECUTION)
    assert viewer.proxy.rowCount() == 1
    assert viewer.proxy.index(0, 3).data(Qt.DisplayRole) == "program logged a thing"


def test_there_is_no_primary_button(qapp):
    from PySide6.QtWidgets import QPushButton

    viewer = LogViewer()
    roles = [b.property("role") for b in viewer.findChildren(QPushButton)]
    assert "primary" not in roles


def test_a_long_traceback_survives_both_wrap_modes(qapp):
    viewer = LogViewer()
    traceback = "Traceback (most recent call last): " + "x" * 300
    viewer.append(_entry(traceback, level=logging.ERROR), LogBufferModel.EXECUTION)

    viewer.set_wrap(False)
    assert viewer.view.uniformRowHeights() is True
    assert viewer.proxy.index(0, 3).data(Qt.DisplayRole) == traceback

    viewer.set_wrap(True)
    assert viewer.view.uniformRowHeights() is False
    assert viewer.view.wordWrap() is True
    # The text is never truncated in the model -- eliding is the view's job.
    assert viewer.proxy.index(0, 3).data(Qt.DisplayRole) == traceback


def test_alternating_row_colours_are_off(qapp):
    viewer = LogViewer()
    assert viewer.view.alternatingRowColors() is False


def test_the_footer_is_hidden_while_following(qapp):
    viewer = LogViewer()
    viewer.append(_entry(), LogBufferModel.EXECUTION)
    assert viewer.follow.following is True
    assert viewer.footer_label.isVisibleTo(viewer) is False


def test_the_footer_counts_arrivals_after_a_scroll_up(qapp):
    viewer = LogViewer()
    viewer.follow.scrolled(at_bottom=False)
    viewer.append(_entry("a"), LogBufferModel.EXECUTION)
    viewer.append(_entry("b"), LogBufferModel.EXECUTION)
    viewer._sync_footer()
    assert viewer.follow.pending == 2
    assert "2" in viewer.footer_label.text()


def test_jump_to_latest_resumes_following(qapp):
    viewer = LogViewer()
    viewer.follow.scrolled(at_bottom=False)
    viewer.append(_entry(), LogBufferModel.EXECUTION)
    viewer.jump_button.click()
    assert viewer.follow.following is True
    assert viewer.follow.pending == 0
