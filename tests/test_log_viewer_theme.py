"""The error row's tint and 3px edge, rendered, in both themes.

A model-level assertion that `data(BackgroundRole)` returns a colour proves
nothing: an application stylesheet targets `QTreeView::item`, so
QStyleSheetStyle draws the cell and silently discards both that brush and
the palette initStyleOption filled in. This file renders the real widget
with the real stylesheet applied and counts pixels, because that is the
only version of the question the user can see the answer to.
"""

import logging
from datetime import datetime

import pytest
from PySide6.QtGui import QImage

from gui.log_entry import LogEntry
from gui.log_model import LogBufferModel
from gui.log_viewer import LogViewer
from gui.theme_manager import get_theme_manager


def _rendered(theme_name, qapp):
    """A LogViewer holding one ERROR row, painted under the live stylesheet."""
    manager = get_theme_manager()
    manager.set_theme(theme_name)
    manager.apply_theme()

    viewer = LogViewer()
    viewer.resize(900, 200)
    viewer.append(
        LogEntry(datetime.now().astimezone(), logging.ERROR, "root", "boom"),
        LogBufferModel.EXECUTION,
    )
    viewer.show()
    qapp.processEvents()

    image = QImage(viewer.size(), QImage.Format_ARGB32)
    viewer.render(image)
    return viewer, image, manager.get_current_theme()


def _count(image, hex_colour):
    wanted = hex_colour.lower()
    return sum(
        image.pixelColor(x, y).name().lower() == wanted
        for y in range(image.height())
        for x in range(image.width())
    )


@pytest.mark.parametrize("theme_name", ["light", "dark"])
def test_an_error_row_shows_its_tint_and_its_edge(theme_name, qapp):
    viewer, image, theme = _rendered(theme_name, qapp)
    try:
        tint = _count(image, theme.status_danger_bg)
        edge = _count(image, theme.status_danger)
        # The tint covers a row; the edge is 3px of one. Exact counts depend
        # on row metrics, so assert only that each actually reached a pixel.
        assert tint > 100, f"{theme_name}: error row is not tinted ({tint}px)"
        assert edge > 0, f"{theme_name}: 3px status edge is missing ({edge}px)"
    finally:
        viewer.deleteLater()


@pytest.mark.parametrize("theme_name", ["light", "dark"])
def test_the_two_themes_do_not_paint_the_same_error_row(theme_name, qapp):
    """Guards against a hardcoded colour surviving a theme switch."""
    viewer, image, theme = _rendered(theme_name, qapp)
    try:
        other = "dark" if theme_name == "light" else "light"
        other_theme = get_theme_manager()
        other_theme.set_theme(other)
        foreign = other_theme.get_current_theme().status_danger_bg
        assert _count(image, theme.status_danger_bg) > 0
        assert _count(image, foreign) == 0
    finally:
        viewer.deleteLater()
