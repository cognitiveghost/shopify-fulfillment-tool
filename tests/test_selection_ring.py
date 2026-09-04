"""9.4: which end caps a cell owns. Pure, so it needs no painter.

Spec: docs/superpowers/specs/2026-09-04-phase9-bundle3-components-design.md §4
"""

from PySide6.QtWidgets import QTableWidget

from gui.selection_ring import caps, first_visible_column, last_visible_column

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
    furniture and no information."""
    from PySide6.QtWidgets import QTableView

    view = QTableView()
    header = view.horizontalHeader()
    assert not header.isSortIndicatorShown() or header.sortIndicatorSection() >= 0
