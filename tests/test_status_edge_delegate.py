"""Spec §9 tests 5-7: the edge rule, tested without a painter."""

import pandas as pd
import pytest
from PySide6.QtWidgets import QTableView

from gui.orders_view import REPEAT_COLUMN
from gui.pandas_model import PandasModel
from gui.status_edge_delegate import StatusEdgeDelegate
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
    """Spec §10. These are every custom item role in the repo."""
    from PySide6.QtCore import Qt

    from gui.pandas_model import ROLE_STATUS
    from gui.session_row_delegates import ROLE_MANUAL, ROLE_TOKEN

    assert ROLE_STATUS not in (Qt.ItemDataRole.UserRole, ROLE_TOKEN, ROLE_MANUAL)
