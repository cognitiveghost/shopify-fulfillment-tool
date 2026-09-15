import logging
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTreeView

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


def test_wrapping_switches_off_per_pixel_vertical_scrolling(qapp):
    """Per-pixel scrolling needs a total pixel height.

    Without uniform row heights it can only get one by measuring every row
    in the buffer, which costs ~40ms per arriving entry at 4800 rows against
    ~0.6ms with uniform rows -- a freeze during the burst an analysis run
    produces. Wrapped rows scroll per item instead.
    """
    viewer = LogViewer()

    viewer.set_wrap(False)
    assert viewer.view.verticalScrollMode() == QTreeView.ScrollPerPixel

    viewer.set_wrap(True)
    assert viewer.view.verticalScrollMode() == QTreeView.ScrollPerItem


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
    # No _sync_footer() here on purpose: append must have kept the footer up
    # to date by itself, which is the thing worth asserting.
    assert viewer.follow.pending == 2
    assert "2" in viewer.footer_label.text()


def test_jump_to_latest_resumes_following(qapp):
    viewer = LogViewer()
    viewer.follow.scrolled(at_bottom=False)
    viewer.append(_entry(), LogBufferModel.EXECUTION)
    viewer.jump_button.click()
    assert viewer.follow.following is True
    assert viewer.follow.pending == 0


def test_source_and_level_groups_are_separated(qapp):
    from PySide6.QtWidgets import QWidget

    viewer = LogViewer()
    names = [w.objectName() for w in viewer.findChildren(QWidget)]
    assert "logs-source-group" in names
    assert "logs-level-group" in names


def test_the_current_source_and_level_are_visibly_checked(qapp):
    from PySide6.QtWidgets import QPushButton

    viewer = LogViewer()
    checked = [b.text() for b in viewer.findChildren(QPushButton) if b.isChecked()]
    assert "Execution" in checked  # a source is always active (LogBufferModel default)
    assert any(t in checked for t in ("All", "Info", "Warning", "Error"))


def test_a_checked_toggle_gets_a_visible_style(qapp):
    """A checkable button with no checked styling is invisible in the
    Windows build -- the checked button must carry a distinct stylesheet."""
    viewer = LogViewer()
    checked_button = next(b for b in viewer._source_group.buttons() if b.isChecked())
    assert checked_button.styleSheet().strip() != ""
