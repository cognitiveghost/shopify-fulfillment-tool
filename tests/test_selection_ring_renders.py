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


@pytest.fixture(params=["light", "dark"])
def selected_row(qapp, request):
    """A selected row rendered under both themes.

    The premise of the whole change is theme-dependent -- accent_fill was the
    same blue in both while the foregrounds were not -- so rendering only
    whichever theme the QSettings-backed singleton happens to hold proves half
    of it. Restores the theme afterwards; other test modules in this suite set
    it and do not.
    """
    manager = get_theme_manager()
    before = manager.get_current_theme().name
    manager.set_theme(request.param)
    theme = manager.get_current_theme()
    try:
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
        yield theme, image, table
    finally:
        manager.set_theme(before)


def _cell(table, column):
    return table.visualRect(table.model().index(1, column))


def test_the_ring_is_continuous_across_a_cell_boundary(selected_row):
    theme, image, table = selected_row
    ring = theme.selection_border.upper()
    # Derived, not hard-coded: the claim is "continuous across a boundary", and
    # an x baked in from today's 100px default section width keeps passing while
    # sampling the interior of a single cell if that width ever changes.
    edge = _cell(table, 1).right()
    y = _cell(table, 0).top() + 1
    for x in (edge - 20, edge, edge + 1, edge + 20):
        assert _hex_at(image, x, y) == ring, f"gap at x={x}"


def test_a_delegate_painted_column_matches_a_plain_one(selected_row):
    # Column 0 is left as the current item by selectRow(), and Fusion tints the
    # current cell's focus decoration even under a flat QSS background -- so the
    # plain comparison point is column 1, not column 0. Sample each cell's right
    # margin, which no glyph reaches at any font size the app ships.
    theme, image, table = selected_row
    painted, plain = _cell(table, 2), _cell(table, 1)
    y = painted.center().y()
    assert _hex_at(image, painted.right() - 3, y) == theme.selection_bg.upper()
    assert _hex_at(image, plain.right() - 3, y) == theme.selection_bg.upper()


def test_the_accent_fill_is_gone_from_a_selected_row(selected_row):
    theme, image, table = selected_row
    accent = theme.accent_fill.upper()
    rect = _cell(table, 0)
    for y in range(rect.top(), rect.bottom() + 1):
        for x in range(0, 400, 5):
            assert _hex_at(image, x, y) != accent


def test_the_analysis_table_delegates_do_not_punch_an_accent_block(qapp):
    """The delegate that shipped the bug this change had to find.

    TagDelegate filled a selected cell with `palette.highlight()`. That is
    still accent_fill -- QPalette.Highlight drives text selection, and
    packing-tool derives a Packer Mode cell colour from it -- so once
    selection stopped being an accent fill, its column of the Analysis
    Results table would have rendered a solid blue block with no ring
    segment, breaking the band the tests above protect.
    """
    from gui.tag_delegate import TagDelegate

    manager = get_theme_manager()
    before = manager.get_current_theme().name
    try:
        for name in ("light", "dark"):
            manager.set_theme(name)
            theme = manager.get_current_theme()
            table = QTableWidget(3, 4)
            table.setStyleSheet(build_stylesheet(theme))
            table.horizontalHeader().hide()
            table.verticalHeader().hide()
            table.setShowGrid(False)
            table.setSelectionBehavior(QTableWidget.SelectRows)
            table.setItemDelegateForColumn(1, TagDelegate({}))
            for r in range(3):
                for c in range(4):
                    table.setItem(r, c, QTableWidgetItem(f"r{r}c{c}"))
            table.resize(400, 120)
            table.selectRow(1)
            table.show()
            qapp.processEvents()
            image = QImage(table.size(), QImage.Format_RGB32)
            table.render(image)

            accent = theme.accent_fill.upper()
            ring = theme.selection_border.upper()
            row = table.visualRect(table.model().index(1, 0))
            for y in range(row.top(), row.bottom() + 1):
                for x in range(0, 400, 5):
                    assert _hex_at(image, x, y) != accent, f"{name}: accent at {x},{y}"
            # and the band still crosses the delegate-painted column
            edge = table.visualRect(table.model().index(1, 0)).right()
            for x in (edge - 20, edge, edge + 1, edge + 20):
                assert _hex_at(image, x, row.top() + 1) == ring, f"{name}: gap at {x}"
    finally:
        manager.set_theme(before)
