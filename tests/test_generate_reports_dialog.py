"""One dialog generating any number of reports of both kinds in one pass.

Previously two buttons opened two modal dialogs, each emitting exactly one
config, so producing a packing list and its stock export took two full
round-trips.
"""

import logging
from types import SimpleNamespace

import pandas as pd
import pytest
from PySide6.QtWidgets import QApplication

from gui.report_selection_dialog import GenerateReportsDialog


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


PACKING = [
    {"name": "DHL", "output_filename": "dhl.xlsx", "filters": []},
    {"name": "DPD", "output_filename": "dpd.xlsx", "filters": []},
]
STOCK = [{"name": "Daily ERP", "output_filename": "erp.xls", "filters": []}]


def _df():
    return pd.DataFrame(
        {
            "Order_Number": ["#1001"],
            "SKU": ["AB-01"],
            "Quantity": [1],
            "Order_Fulfillment_Status": ["Fulfillable"],
        }
    )


def _dialog():
    return GenerateReportsDialog(PACKING, STOCK, _df(), lambda df, f: df)


def test_emits_every_checked_report_with_its_type():
    dialog = _dialog()
    emitted = []
    dialog.reportsSelected.connect(emitted.append)

    dialog.set_checked("packing_lists", 0, True)
    dialog.set_checked("packing_lists", 1, True)
    dialog.set_checked("stock_exports", 0, True)
    dialog._on_generate()

    (batch,) = emitted
    assert [(r["name"], r["report_type"]) for r in batch] == [
        ("DHL", "packing_lists"),
        ("DPD", "packing_lists"),
        ("Daily ERP", "stock_exports"),
    ]


def test_emits_nothing_when_no_report_is_checked():
    dialog = _dialog()
    emitted = []
    dialog.reportsSelected.connect(emitted.append)

    dialog._on_generate()

    assert emitted == []


def test_generate_button_is_disabled_until_something_is_checked():
    dialog = _dialog()
    assert dialog.generate_button.isEnabled() is False

    dialog.set_checked("packing_lists", 0, True)

    assert dialog.generate_button.isEnabled() is True


def test_report_list_is_not_editable():
    """A double-click on a row must toggle its checkbox, not open an editor
    that renders over it -- the default QListWidget edit triggers do the
    latter for any checkable row."""
    from PySide6.QtWidgets import QAbstractItemView

    dialog = _dialog()
    assert dialog.report_list.editTriggers() == QAbstractItemView.NoEditTriggers


def test_the_checkbox_indicator_is_themed_not_native():
    dialog = _dialog()
    assert "indicator" in dialog.report_list.styleSheet()


def test_one_failing_report_does_not_cost_the_user_the_others(monkeypatch):
    """The whole point of generating a batch in one pass.

    The batch runs on a Worker and one failure never stops the others
    (tests/test_report_jobs.py). Back on the GUI thread, the reports that
    were written are announced and the one that failed is named, once.
    """
    from unittest.mock import Mock

    from gui import actions_handler
    from gui.actions_handler import ActionsHandler
    from shopify_tool.report_jobs import ReportOutcome

    errors = Mock()
    monkeypatch.setattr(actions_handler, "show_error", errors)
    toasts = []
    handler = SimpleNamespace(
        log=logging.getLogger(__name__),
        mw=SimpleNamespace(log_activity=lambda *a: None, session_browser=Mock()),
        _results_toast=lambda text, **k: toasts.append(text),
    )

    ActionsHandler._on_reports_generated(handler, [
        ReportOutcome("DHL", "packing_lists", output_file="/s/packing_lists/DHL.xlsx"),
        ReportOutcome("DPD", "packing_lists", failed=True),
        ReportOutcome("Daily ERP", "stock_exports", output_file="/s/stock_exports/ERP_0101_1200.xls"),
    ])

    assert toasts == ["Report saved: DHL.xlsx", "Report saved: ERP_0101_1200.xls"]
    errors.assert_called_once()
    assert "DPD" in errors.call_args.args[1]
