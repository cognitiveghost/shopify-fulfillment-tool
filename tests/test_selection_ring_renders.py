"""The selection ring is a rendered property, not a stylesheet property.

QSS styles cells. A four-sided border on QTableView::item draws a box around
every cell in the row; top-and-bottom borders join across cell edges into one
band. Only pixels can tell those apart, so this test renders.
"""
import pytest
from PySide6.QtGui import QImage
from PySide6.QtWidgets import (
    QApplication,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableWidget,
    QTableWidgetItem,
)

from gui.theme_manager import get_theme_manager
from shared.theme import build_stylesheet


class _BlankingDelegate(QStyledItemDelegate):
    """The gui/session_row_delegates.py pattern: blank the text, let the
    style paint the row, draw the content yourself."""

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter, opt.widget)


def _hex_at(image, x, y):
    c = image.pixelColor(x, y)
    return f"#{c.red():02X}{c.green():02X}{c.blue():02X}".upper()


@pytest.fixture
def selected_row(qapp, request):
    theme = get_theme_manager().get_current_theme()
    table = QTableWidget(3, 4)
    table.setStyleSheet(build_stylesheet(theme))
    table.horizontalHeader().hide()
    table.verticalHeader().hide()
    table.setShowGrid(False)
    table.setSelectionBehavior(QTableWidget.SelectRows)
    table.setItemDelegateForColumn(2, _BlankingDelegate())
    for r in range(3):
        for c in range(4):
            table.setItem(r, c, QTableWidgetItem(f"r{r}c{c}"))
    table.resize(400, 120)
    table.selectRow(1)
    table.show()
    qapp.processEvents()
    image = QImage(table.size(), QImage.Format_RGB32)
    table.render(image)
    rect = table.visualRect(table.model().index(1, 0))
    return theme, image, rect


def test_the_ring_is_continuous_across_a_cell_boundary(selected_row):
    theme, image, rect = selected_row
    ring = theme.selection_border.upper()
    for x in (100, 199, 201, 300):
        assert _hex_at(image, x, rect.top() + 1) == ring, f"gap at x={x}"


def test_a_delegate_painted_column_matches_a_plain_one(selected_row):
    # Column 0 is left as the current item by selectRow(), and Fusion tints
    # the current cell's focus decoration even under a flat QSS background
    # -- so the plain comparison point is column 1, not column 0.
    theme, image, rect = selected_row
    y = rect.center().y()
    assert _hex_at(image, 250, y) == _hex_at(image, 150, y)
    assert _hex_at(image, 250, y) == theme.selection_bg.upper()


def test_the_accent_fill_is_gone_from_a_selected_row(selected_row):
    theme, image, rect = selected_row
    accent = theme.accent_fill.upper()
    for y in range(rect.top(), rect.bottom() + 1):
        for x in range(0, 400, 5):
            assert _hex_at(image, x, y) != accent
