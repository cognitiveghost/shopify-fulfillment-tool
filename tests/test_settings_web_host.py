"""SettingsWebHost: one web view, three drafts (phase 7 spec section 6.5).

Nothing here waits for Chromium: the bridge's state is read on the Python
side, and the page's requests are made by calling the bridge's slots.
"""

import pytest
from PySide6.QtWidgets import QFileDialog

from gui.settings.page_state import (
    FileColumns,
    GeneralDraft,
    OrdersDraft,
    StockDraft,
)
from gui.settings.web_host import SettingsWebHost, read_file_columns


@pytest.fixture
def host(qtbot):
    mappings = {
        "version": 2,
        "orders": {
            "Name": "Order_Number",
            "Lineitem sku": "SKU",
            "Lineitem quantity": "Quantity",
            "Shipping Method": "Shipping_Method",
        },
        "stock": {"Article": "SKU", "Available": "Stock"},
        "additional_columns": [],
    }
    drafts = {
        "general": GeneralDraft({"low_stock_threshold": 5}, "ACME"),
        "orders": OrdersDraft(mappings, {}, "ACME"),
        "stock": StockDraft(mappings, "ACME"),
    }
    widget = SettingsWebHost(drafts)
    qtbot.addWidget(widget)
    return widget


def _edits(host):
    seen = []
    host.edited.connect(lambda: seen.append(True))
    return seen


def _pick(monkeypatch, path):
    asked = []

    def choose(parent, title, start, filters):
        asked.append((title, filters))
        return str(path), ""

    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(choose))
    return asked


def _errors(monkeypatch):
    seen = []
    monkeypatch.setattr(
        "gui.settings.web_host.show_error",
        lambda parent, headline, what: seen.append((headline, what)),
    )
    return seen


def test_it_opens_on_the_first_draft(host):
    assert host.bridge.state["page"] == "general"


def test_show_page_draws_that_draft(host):
    host.show_page("stock")
    assert host.bridge.state["page"] == "stock"
    assert host.bridge.state["title"] == "Stock mapping"


def test_an_edit_reaches_the_draft_is_drawn_and_is_announced(host):
    seen = _edits(host)
    host.bridge.edit("threshold", ["9"])
    assert host.drafts["general"].threshold == "9"
    assert host.bridge.state["general"]["threshold"]["value"] == "9"
    assert seen == [True]


def test_an_edit_that_changes_nothing_is_not_announced(host):
    seen = _edits(host)
    host.bridge.edit("threshold", ["5"])
    host.bridge.edit("no_such_action", [])
    assert seen == []


def test_an_edit_goes_to_the_page_that_is_showing(host):
    host.show_page("orders")
    host.bridge.edit("threshold", ["9"])
    assert host.drafts["general"].threshold == "5"
    host.bridge.edit("courier_add", [])
    assert host.drafts["orders"].courier_rows == [["", ""]]


def test_read_columns_offers_the_chosen_files_columns(host, monkeypatch, tmp_path):
    path = tmp_path / "picked.csv"
    path.write_text("Name,Lineitem sku,Notes\n#1,ABC,leave at door\n", encoding="utf-8")
    asked = _pick(monkeypatch, path)
    seen = _edits(host)
    host.show_page("orders")

    host.bridge.readColumns()

    assert asked == [("Select Orders CSV", "CSV Files (*.csv);;All Files (*)")]
    assert host.drafts["orders"].file == FileColumns(
        "picked.csv",
        ("Name", "Lineitem sku", "Notes"),
        {"Name": "#1", "Lineitem sku": "ABC", "Notes": "leave at door"},
        False,
    )
    assert host.drafts["stock"].file is None
    mapping = host.bridge.state["mapping"]
    assert mapping["can_pick"] is True
    assert mapping["source"] == {
        "lead": "Columns read from",
        "file": "picked.csv",
        "tail": ".",
    }
    assert seen == [True]


def test_read_columns_changes_no_mapping(host, monkeypatch, tmp_path):
    path = tmp_path / "picked.csv"
    path.write_text("A,B\n1,2\n", encoding="utf-8")
    _pick(monkeypatch, path)
    host.show_page("orders")
    before = dict(host.drafts["orders"].chosen)
    host.bridge.readColumns()
    assert host.drafts["orders"].chosen == before


def test_a_cancelled_dialog_changes_nothing(host, monkeypatch):
    _pick(monkeypatch, "")
    seen = _edits(host)
    host.show_page("stock")
    host.bridge.readColumns()
    assert host.drafts["stock"].file is None
    assert seen == []


def test_a_file_that_cannot_be_read_says_so_and_changes_nothing(
    host, monkeypatch, tmp_path
):
    _pick(monkeypatch, tmp_path / "gone.csv")
    errors = _errors(monkeypatch)
    seen = _edits(host)
    host.show_page("orders")
    host.bridge.readColumns()
    assert errors == [("The column names couldn't be read", "Details are in Logs.")]
    assert host.drafts["orders"].file is None
    assert seen == []


def test_an_empty_file_cannot_be_read(host, monkeypatch, tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("", encoding="utf-8")
    _pick(monkeypatch, path)
    errors = _errors(monkeypatch)
    host.show_page("orders")
    host.bridge.readColumns()
    assert errors == [("The column names couldn't be read", "Details are in Logs.")]


def test_general_has_no_columns_to_read(host, monkeypatch, tmp_path):
    asked = _pick(monkeypatch, tmp_path / "x.csv")
    host.bridge.readColumns()
    assert asked == []


def test_focus_problem_asks_the_page_for_that_control(host):
    seen = []
    host.bridge.problemFocusRequested.connect(seen.append)
    host.focus_problem("threshold")
    assert seen == ["threshold"]


def test_read_file_columns_names_the_file_and_marks_where_it_came_from(tmp_path):
    path = tmp_path / "stock-30-09.csv"
    path.write_text("Артикул;Наличност\nABC;4\nXYZ;9\n", encoding="utf-8")
    assert read_file_columns(path, loaded=True) == FileColumns(
        "stock-30-09.csv",
        ("Артикул", "Наличност"),
        {"Артикул": "ABC", "Наличност": "4"},
        True,
    )
