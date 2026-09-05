"""9.4: which end caps a cell owns. Pure, so it needs no painter.

Spec: docs/superpowers/specs/2026-09-04-phase9-bundle3-components-design.md §4
"""

from PySide6.QtWidgets import QTableWidget, QTreeWidget

from gui.selection_ring import (
    caps,
    first_visible_column,
    header_of,
    last_visible_column,
)

_KEEPALIVE = []


def _header(columns=4, hidden=(), moves=()):
    table = QTableWidget(1, columns)
    header = table.horizontalHeader()
    for frm, to in moves:
        header.moveSection(frm, to)
    for col in hidden:
        header.setSectionHidden(col, True)
    _KEEPALIVE.append(table)
    return header


def test_the_caps_land_on_the_first_and_last_columns(qapp):
    header = _header(4)
    assert caps(header, 0) == (True, False)
    assert caps(header, 3) == (False, True)
    assert caps(header, 1) == (False, False)


def test_a_single_column_row_owns_both_caps(qapp):
    header = _header(1)
    assert caps(header, 0) == (True, True)


def test_a_hidden_last_column_hands_its_cap_to_the_one_before(qapp):
    header = _header(4, hidden=(3,))
    assert caps(header, 3) == (False, False)
    assert caps(header, 2) == (False, True)


def test_a_hidden_first_column_hands_its_cap_along(qapp):
    header = _header(4, hidden=(0,))
    assert caps(header, 0) == (False, False)
    assert caps(header, 1) == (True, False)


def test_a_dragged_column_takes_the_cap_with_it(qapp):
    # Visual index, not logical: a user who drags column 2 to the front must
    # get the cap on the left of the row.
    header = _header(4, moves=((2, 0),))
    assert caps(header, 2) == (True, False)
    assert caps(header, 0) == (False, False)


def test_no_header_means_no_caps(qapp):
    assert caps(None, 0) == (False, False)
    assert first_visible_column(None) is None
    assert last_visible_column(None) is None


def test_every_column_hidden_means_no_caps(qapp):
    header = _header(2, hidden=(0, 1))
    assert caps(header, 0) == (False, False)


def test_a_selected_and_blocked_row_draws_the_ring_around_the_edge(qapp):
    """The bundle's acceptance case, asserted on geometry rather than pixels.

    A blocked row carries a status token, so StatusEdgeDelegate paints its 3px
    bar; selected, the bar must start RING_WIDTH in from the row's left, which
    is exactly where the ring's left cap ends.

    The pixel half of the same claim is the test below: caps() and edge_rect()
    can both be right while paint_selection_ring() draws nothing.
    """
    from PySide6.QtCore import QRect
    from PySide6.QtWidgets import QStyle, QStyleOptionViewItem

    from gui.selection_ring import RING_WIDTH
    from gui.status_edge_delegate import EDGE_WIDTH, StatusEdgeDelegate

    option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, 120, 28)
    option.state |= QStyle.State_Selected
    edge = StatusEdgeDelegate().edge_rect(option)

    assert edge.left() == RING_WIDTH                     # starts where the cap ends
    assert edge.left() + EDGE_WIDTH <= option.rect.width() - RING_WIDTH
    assert edge.top() == RING_WIDTH and edge.height() == 28 - 2 * RING_WIDTH


def test_the_ring_actually_closes_around_a_selected_blocked_row(qapp):
    """Four ring segments in pixels, with the status edge inside them.

    The two vertical segments come from paint_selection_ring, the two
    horizontal ones from build_stylesheet's QTableView::item:selected rule --
    the split §4.3 chose. Sampling all four in one render is the only thing
    that proves the two halves meet rather than merely agreeing on paper.
    """
    import pandas as pd
    from PySide6.QtGui import QColor, QImage
    from PySide6.QtWidgets import QTableView

    from gui.pandas_model import PandasModel
    from gui.selection_ring import RING_WIDTH
    from gui.status_edge_delegate import StatusEdgeDelegate
    from gui.theme_manager import get_theme_manager
    from shared.theme import build_stylesheet

    theme = get_theme_manager().get_current_theme()
    ring = theme.selection_border.upper()

    view = QTableView()
    model = PandasModel(
        pd.DataFrame([{"Order_Number": "1", "Order_Fulfillment_Status": "Not Fulfillable"}])
    )
    view.setModel(model)
    view.setItemDelegate(StatusEdgeDelegate(view))
    view.setStyleSheet(build_stylesheet(theme))
    view.resize(400, 120)
    view.selectRow(0)
    _KEEPALIVE.append((view, model))

    image = QImage(view.viewport().size(), QImage.Format.Format_ARGB32)
    image.fill(0)
    view.viewport().render(image)

    def pixel(x, y):
        return QColor(image.pixel(x, y)).name().upper()

    first = view.visualRect(model.index(0, 0))
    last = view.visualRect(model.index(0, model.columnCount() - 1))
    mid_y = first.center().y()

    assert pixel(first.left(), mid_y) == ring                    # left cap
    assert pixel(last.right(), mid_y) == ring                    # right cap
    assert pixel(first.center().x(), first.top()) == ring        # QSS top
    assert pixel(first.center().x(), first.bottom()) == ring     # QSS bottom
    # ...and the status edge sits inside the left cap, not on top of it.
    assert pixel(first.left() + RING_WIDTH + 1, mid_y) == theme.status_danger.upper()


def test_the_ring_width_matches_the_qss_rule(qapp):
    """§4.3 accepted naming the ring's width and colour twice; this holds them.

    RING_WIDTH also drives StatusEdgeDelegate's inset, so a QSS bump to 3px
    without this guard yields 2px caps *and* a mis-inset edge -- the exact
    collision 9.4 exists to remove.
    """
    from gui.selection_ring import RING_WIDTH
    from gui.theme_manager import get_theme_manager
    from shared.theme import build_stylesheet

    theme = get_theme_manager().get_current_theme()
    sheet = build_stylesheet(theme)

    for side in ("top", "bottom"):
        assert f"border-{side}: {RING_WIDTH}px solid {theme.selection_border};" in sheet


def test_zebra_striping_stays_off(qapp):
    """A stripe on surface_raised is the same value as a panel, so a striped
    table stops reading as one plane. Separation is the row rhythm and a
    border_subtle gridline, not alternating fills."""
    import gui.session_browser_widget as browser
    import gui.ui_manager as ui

    for module in (browser, ui):
        with open(module.__file__, encoding="utf-8") as f:
            source = f.read()
        assert "setAlternatingRowColors(True)" not in source


def test_the_sort_caret_is_not_forced_onto_every_header(qapp):
    """Qt draws the indicator on the sorted section alone. What the artboard
    rejects is a permanent grey caret on all of them -- eight pieces of
    furniture and no information.

    setSortingEnabled() gives the wanted behaviour on its own; it is
    setSortIndicatorShown(True) that pins a caret to every header, so that is
    what this guards -- in the app's own tables, not in a throwaway QTableView
    that no screen ever builds.
    """
    import gui.main_window_pyside as main_window
    import gui.session_browser_widget as browser
    import gui.ui_manager as ui

    for module in (browser, ui, main_window):
        with open(module.__file__, encoding="utf-8") as f:
            source = f.read()
        assert "setSortIndicatorShown(True)" not in source


class _Option:
    """A QStyleOptionViewItem carries `widget`; this is the part caps() reads."""

    def __init__(self, widget):
        self.widget = widget


def test_header_of_finds_a_tree_header(qapp):
    tree = QTreeWidget()
    tree.setColumnCount(3)
    assert header_of(_Option(tree)) is tree.header()


def test_a_tree_still_gets_both_end_caps(qapp):
    tree = QTreeWidget()
    tree.setColumnCount(3)
    assert caps(header_of(_Option(tree)), 0) == (True, False)
    assert caps(header_of(_Option(tree)), 2) == (False, True)
    assert caps(header_of(_Option(tree)), 1) == (False, False)


def test_a_widget_with_neither_header_is_still_none():
    assert header_of(_Option(object())) is None
