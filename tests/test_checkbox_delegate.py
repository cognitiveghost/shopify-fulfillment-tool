"""Regression test for Bulk mode's checkbox cells rendering as plain white
boxes instead of the app's themed, bordered checkbox indicator --
gui.checkbox_delegate.CheckboxDelegate.

Root cause: paint() drew the checkbox via
`QApplication.style().drawControl(QStyle.CE_CheckBox, checkbox_option, painter)`
with no widget argument. Qt's QStyleSheetStyle (which wraps the base style
once the app has ANY stylesheet applied, as this app's theme system always
does) needs a real widget to resolve QSS rules like `QTableView::indicator`.
With no widget, it silently falls back to the base style's unthemed default
checkbox appearance -- a plain box that doesn't match the surrounding
themed row, i.e. exactly the reported "blank white box".
"""
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest
from PySide6.QtCore import QRect
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication, QStyle, QStyleOptionViewItem, QTableView

from gui.checkbox_delegate import CheckboxDelegate

THEMED_BORDER = "#ff00ff"
THEMED_BACKGROUND = "#00ffff"


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(
        f"""
        QTableView::indicator {{
            width: 18px; height: 18px;
            border: 2px solid {THEMED_BORDER};
            background-color: {THEMED_BACKGROUND};
        }}
        """
    )
    yield app


@pytest.fixture
def table(qapp):
    t = QTableView()
    t.show()
    return t


def _paint_checkbox(table):
    df = pd.DataFrame([{"Order_Number": "1001", "SKU": "SKU-A"}])
    selection_helper = SimpleNamespace(
        main_window=SimpleNamespace(analysis_results_df=df),
        is_row_checked=lambda row: False,
    )
    delegate = CheckboxDelegate(selection_helper)

    index = Mock()
    index.model.return_value = object()  # no mapToSource -> falls back to index.row()
    index.row.return_value = 0

    option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, 30, 30)
    option.state = QStyle.State_None  # not selected
    option.widget = table
    option.palette = table.palette()

    img = QImage(30, 30, QImage.Format_ARGB32)
    img.fill(0xFFFFFFFF)
    painter = QPainter(img)
    delegate.paint(painter, option, index)
    painter.end()
    return img


def test_checkbox_picks_up_themed_indicator_style(table):
    img = _paint_checkbox(table)
    # Checkbox is centered in the 30x30 cell as a 20x20 box (see
    # _get_checkbox_rect): rect (5, 5, 20, 20). Scan it for the themed
    # border color rather than assume the native style's exact sub-pixel
    # layout of the indicator within that rect.
    found_border = any(
        img.pixelColor(x, y).name() == THEMED_BORDER
        for x in range(5, 25)
        for y in range(5, 25)
    )
    assert found_border, "themed QTableView::indicator border color not found in checkbox rect"
