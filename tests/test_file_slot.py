"""The file slot as a record (phase 3 spec section 4.1).

It replaces the Qt widget of the same name: the facts about one input file,
and the only thing that knows whether that file is usable.
"""

from pathlib import Path

from gui.setup_state import FileSlot


def _slot(kind="orders"):
    calls = []
    return FileSlot(kind, on_change=lambda: calls.append(1)), calls


def test_a_new_slot_is_empty_and_not_valid():
    slot, _ = _slot()
    assert slot.path is None
    assert slot.is_valid is False
    assert slot.problem is None


def test_loading_a_file_makes_the_slot_valid_and_says_so_once():
    slot, calls = _slot()
    slot.set_loaded("/data/acme-orders.csv", rows=1204, keys=312, delimiter=",")
    assert slot.is_valid is True
    assert slot.path == Path("/data/acme-orders.csv")
    assert slot.name == "acme-orders.csv"
    assert (slot.rows, slot.keys, slot.delimiter) == (1204, 312, ",")
    assert slot.is_folder is False
    assert calls == [1]


def test_a_folder_merge_keeps_its_parts_and_its_own_name():
    slot, _ = _slot()
    parts = [{"name": "a.csv", "rows": 512}, {"name": "b.csv", "rows": 480}]
    slot.set_loaded(
        "/tmp/merged_orders.csv",
        rows=992,
        keys=300,
        delimiter="mixed",
        parts=parts,
        note="2 overlapping orders skipped",
        name="exports\\  ·  2 CSVs merged",
    )
    assert slot.is_folder is True
    assert slot.parts == parts
    assert slot.note == "2 overlapping orders skipped"
    assert slot.name == "exports\\  ·  2 CSVs merged"


def test_one_missing_column_names_it_and_what_it_is_mapped_to():
    slot, calls = _slot("orders")
    slot.set_invalid(
        "/data/orders.csv",
        ["Lineitem sku"],
        ["Name", "Total"],
        {"Lineitem sku": "SKU"},
        rows=1204,
        delimiter=",",
    )
    assert slot.is_valid is False
    assert slot.missing_columns == ["Lineitem sku"]
    assert slot.present_columns == ["Name", "Total"]
    assert slot.problem == {
        "title": "No SKU column",
        "text": "The orders file's header row has no “Lineitem sku” column, "
        "which is mapped to SKU.",
        "fix_page": "Orders mapping",
        "fix_label": "Open Orders mapping",
    }
    assert (slot.rows, slot.keys, slot.delimiter) == (1204, None, ",")
    assert calls == [1]


def test_several_missing_columns_are_listed():
    slot, _ = _slot("stock")
    slot.set_invalid(
        "/data/stock.csv",
        ["Артикул", "Наличност"],
        ["Име"],
        {"Артикул": "SKU", "Наличност": "Stock"},
    )
    assert slot.problem["title"] == "2 mapped columns missing"
    assert slot.problem["text"] == (
        "The stock file's header row has none of: “Артикул” (SKU), “Наличност” (stock)."
    )
    assert slot.problem["fix_page"] == "Stock mapping"


def test_a_problem_without_a_fix_has_no_link():
    slot, calls = _slot()
    slot.set_problem(
        "/data/exports",
        "No CSV files in this folder",
        "Choose a folder that holds the exported CSV files.",
    )
    assert slot.is_valid is False
    assert slot.name == "exports"
    assert slot.problem["fix_page"] == ""
    assert slot.problem["fix_label"] == ""
    assert calls == [1]


def test_a_problem_with_a_fix_names_the_page():
    slot, _ = _slot("stock")
    slot.set_problem("/data/stock.csv", "The stock file couldn't be read", "…", "General")
    assert slot.problem["fix_label"] == "Open General"


def test_loading_after_a_problem_forgets_the_problem():
    slot, _ = _slot()
    slot.set_invalid("/data/o.csv", ["Name"], ["X"], {"Name": "Order_Number"})
    slot.set_loaded("/data/o.csv", rows=1, keys=1, delimiter=",")
    assert slot.problem is None
    assert slot.missing_columns == []


def test_clearing_returns_the_slot_to_empty_and_says_so():
    slot, calls = _slot()
    slot.set_loaded("/data/o.csv", rows=1, keys=1, delimiter=",")
    slot.clear()
    assert slot.path is None
    assert slot.is_valid is False
    assert slot.name == ""
    assert calls == [1, 1]
