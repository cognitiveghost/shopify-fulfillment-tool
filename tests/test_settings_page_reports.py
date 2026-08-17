"""The merged Reports settings page.

PackingListsPage and StockExportsPage were ~90% identical; they are one page
now, owning both config keys. The round-trip tests below are the merged
successors of test_settings_page_packing_lists.py and
test_settings_page_stock_exports.py.
"""
import pytest
from PySide6.QtWidgets import QApplication

from gui.settings.reports import ReportsPage


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


# "columns" is in the picker's own (sorted) order -- see the note in the plan
# about column ordering being the picker's, not an arbitrary user order.
PACKING = [{
    "name": "DHL Express",
    "output_filename": "dhl.xlsx",
    "filters": [{"field": "Shipping_Provider", "operator": "equals", "value": "DHL"}],
    "exclude_skus": ["SHIP-01"],
    "columns": ["Quantity", "SKU"],
}]

STOCK = [{
    "name": "Daily ERP",
    "output_filename": "erp.xls",
    "filters": [{"field": "SKU", "operator": "in list", "value": "A,B"}],
}]


def test_round_trips_both_config_keys():
    page = ReportsPage(PACKING, STOCK, analysis_df=None)

    collected = page.collect()

    assert collected["packing_list_configs"] == PACKING
    assert collected["stock_export_configs"] == STOCK


def test_starts_empty_with_no_configs():
    page = ReportsPage([], [], analysis_df=None)

    assert page.collect() == {
        "packing_list_configs": [],
        "stock_export_configs": [],
    }


def test_only_packing_lists_carry_exclude_skus_and_columns():
    """Stock export configs must not grow packing-list-only keys."""
    page = ReportsPage(PACKING, STOCK, analysis_df=None)

    stock = page.collect()["stock_export_configs"][0]

    assert "exclude_skus" not in stock
    assert "columns" not in stock


def test_added_packing_list_appears_in_collect():
    page = ReportsPage([], [], analysis_df=None)

    page.add_report("packing_lists")

    assert len(page.collect()["packing_list_configs"]) == 1


@pytest.mark.parametrize("stored, expected", [
    ("==", "equals"),
    ("!=", "does not equal"),
    ("in", "in list"),
    ("not in", "not in list"),
    ("contains", "contains"),
])
def test_legacy_operators_survive_a_load_and_save(stored, expected):
    """Opening the page must not rewrite a saved filter's meaning.

    add_filter_row does op_combo.setCurrentText(stored), and on a non-editable
    QComboBox that silently does nothing when the string is absent from the
    list -- leaving "equals" selected. Without normalising first, merely
    opening settings and pressing Save would turn every stored "!=" and
    "not in" filter into "equals", inverting it against live client data.
    """
    config = [{
        "name": "legacy",
        "output_filename": "legacy.xlsx",
        "filters": [{"field": "SKU", "operator": stored, "value": "AB-01"}],
        "exclude_skus": [],
    }]
    page = ReportsPage(config, [], analysis_df=None)

    saved = page.collect()["packing_list_configs"][0]["filters"][0]

    assert saved["operator"] == expected
    assert saved["value"] == "AB-01"
