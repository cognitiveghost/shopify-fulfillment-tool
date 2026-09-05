"""Spec §9 tests 5-7: the edge rule, tested without a painter."""

import pandas as pd
import pytest
from PySide6.QtWidgets import QTableView

from gui.orders_view import REPEAT_COLUMN
from gui.pandas_model import PandasModel
from gui.status_edge_delegate import StatusEdgeDelegate
from gui.theme_manager import get_theme_manager
from shared.theme import DARK_THEME, LIGHT_THEME

# setModel() does not take ownership of the model, and nothing else holds a
# Python reference to either object once _index() returns -- without this,
# both get garbage-collected out from under the QModelIndex, which then
# dangles and segfaults on the next access rather than raising.
_KEEPALIVE = []


def _index(rows, column=0):
    view = QTableView()
    model = PandasModel(pd.DataFrame(rows))
    view.setModel(model)
    _KEEPALIVE.append((view, model))
    return view.model().index(0, column)


@pytest.mark.parametrize(
    "row,expected",
    [
        ({"Order_Number": "1", "Order_Fulfillment_Status": "Fulfillable"},
         "status_success"),
        ({"Order_Number": "1", "Order_Fulfillment_Status": "Not Fulfillable"},
         "status_danger"),
        ({"Order_Number": "1", REPEAT_COLUMN: True}, "status_warning"),
        ({"Order_Number": "1"}, None),
    ],
)
def test_edge_token_reports_the_rows_status(qapp, row, expected):
    delegate = StatusEdgeDelegate()
    assert delegate.edge_token(_index([row])) == expected


def test_repeat_beats_not_fulfillable(qapp):
    delegate = StatusEdgeDelegate()
    index = _index(
        [{"Order_Number": "1", "Order_Fulfillment_Status": "Not Fulfillable",
          REPEAT_COLUMN: True}]
    )
    assert delegate.edge_token(index) == "status_warning"


@pytest.mark.parametrize("theme", [LIGHT_THEME, DARK_THEME])
@pytest.mark.parametrize(
    "token", ["status_success", "status_danger", "status_warning"]
)
def test_every_token_resolves_on_both_themes(theme, token):
    assert getattr(theme, token)


def test_the_edge_only_paints_on_the_leftmost_visible_column(qapp):
    """Reorder the columns and the edge follows -- visual index, not logical."""
    delegate = StatusEdgeDelegate()
    view = QTableView()
    view.setModel(
        PandasModel(
            pd.DataFrame(
                [{"Order_Number": "1", "Order_Fulfillment_Status": "Fulfillable"}]
            )
        )
    )
    header = view.horizontalHeader()
    assert delegate.paints_edge(header, 0) is True
    assert delegate.paints_edge(header, 1) is False
    header.moveSection(0, 1)
    assert delegate.paints_edge(header, 0) is False
    assert delegate.paints_edge(header, 1) is True


def test_role_status_collides_with_no_other_custom_role():
    """Spec §10. These are every custom item role in the repo.

    session_row_delegates' roles live on a different table, so they cannot
    actually collide here. The delegate that *does* share this table is
    TagDelegate, and it is safe for a different reason: it reads only
    Qt.DisplayRole (gui/tag_delegate.py), never a custom role.
    """
    from PySide6.QtCore import Qt

    from gui.pandas_model import ROLE_STATUS
    from gui.session_row_delegates import ROLE_LIVE, ROLE_SHAPE, ROLE_TOKEN

    assert ROLE_STATUS not in (
        Qt.ItemDataRole.UserRole, ROLE_TOKEN, ROLE_SHAPE, ROLE_LIVE
    )


def _rendered(view):
    """Render the viewport to an image so paint() output can be sampled."""
    from PySide6.QtGui import QImage

    image = QImage(view.viewport().size(), QImage.Format.Format_ARGB32)
    image.fill(0)
    view.viewport().render(image)
    return image


def _edge_pixel(view, image, row):
    from PySide6.QtGui import QColor

    rect = view.visualRect(view.model().index(row, 0))
    return QColor(image.pixel(rect.left() + 1, rect.center().y())).name().upper()


def test_paint_actually_draws_the_edge(qapp):
    """The other tests stop at edge_token(); this one proves a pixel lands.

    Task 10's "eyeball it in both themes" step could not run (no display on the
    build VM), so the paint path itself was uncovered -- edge_token() and
    paints_edge() can both be right while nothing is ever drawn.
    """
    theme = get_theme_manager().get_current_theme()

    view = QTableView()
    model = PandasModel(
        pd.DataFrame(
            [
                {"Order_Number": "1", "Order_Fulfillment_Status": "Fulfillable"},
                {"Order_Number": "2", "Order_Fulfillment_Status": "Not Fulfillable"},
                {"Order_Number": "3", "Order_Fulfillment_Status": ""},
            ]
        )
    )
    view.setModel(model)
    view.setItemDelegate(StatusEdgeDelegate(view))
    view.resize(400, 200)
    _KEEPALIVE.append((view, model))

    image = _rendered(view)
    assert _edge_pixel(view, image, 0) == theme.status_success.upper()
    assert _edge_pixel(view, image, 1) == theme.status_danger.upper()
    # No status token -> no edge, so the row background shows through.
    assert _edge_pixel(view, image, 2) not in (
        theme.status_success.upper(),
        theme.status_danger.upper(),
    )


def test_a_selected_row_keeps_its_edge(qapp):
    """The whole point of the edge: *selected* and *blocked* at once.

    The filled row tint this replaced could show only one of the two. 9.4
    insets the edge by RING_WIDTH on a selected row so it sits inside the
    selection ring rather than on top of it, so the sample point moves past
    the ring's own left cap.
    """
    from gui.selection_ring import RING_WIDTH

    theme = get_theme_manager().get_current_theme()

    view = QTableView()
    model = PandasModel(
        pd.DataFrame([{"Order_Number": "1", "Order_Fulfillment_Status": "Not Fulfillable"}])
    )
    view.setModel(model)
    view.setItemDelegate(StatusEdgeDelegate(view))
    view.resize(400, 200)
    view.selectRow(0)
    _KEEPALIVE.append((view, model))

    image = _rendered(view)
    rect = view.visualRect(view.model().index(0, 0))
    from PySide6.QtGui import QColor

    pixel = QColor(
        image.pixel(rect.left() + RING_WIDTH + 1, rect.center().y())
    ).name().upper()
    assert pixel == theme.status_danger.upper()


def test_the_edge_insets_inside_the_ring_on_a_selected_row(qapp):
    from PySide6.QtCore import QRect
    from PySide6.QtWidgets import QStyle, QStyleOptionViewItem

    from gui.selection_ring import RING_WIDTH

    delegate = StatusEdgeDelegate()
    option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, 120, 28)

    resting = delegate.edge_rect(option)
    assert resting == QRect(0, 0, 120, 28)

    option.state |= QStyle.State_Selected
    selected = delegate.edge_rect(option)
    assert selected.left() == RING_WIDTH
    assert selected.top() == RING_WIDTH
    assert selected.bottom() == 27 - RING_WIDTH


def test_the_edge_follows_a_hidden_first_column(qapp):
    # paints_edge shares the ring's first-visible-column rule, so hiding
    # column 0 moves the edge rather than deleting it.
    from PySide6.QtWidgets import QTableWidget

    table = QTableWidget(1, 3)
    header = table.horizontalHeader()
    header.setSectionHidden(0, True)
    delegate = StatusEdgeDelegate()
    assert not delegate.paints_edge(header, 0)
    assert delegate.paints_edge(header, 1)
