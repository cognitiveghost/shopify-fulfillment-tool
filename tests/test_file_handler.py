"""FileHandler reads FileSlot state, not a check mark rendered into a QLabel.

The bug this replaces: validity was the string "✓" in a QLabel, read back by
check_files_ready(). FileSlot (Task 3) now owns that fact as data.
"""

import os
from pathlib import Path

import pandas as pd
import pytest
from PySide6.QtWidgets import QApplication, QFileDialog


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def main_window(tmp_path, monkeypatch):
    """A real MainWindow rooted at a throwaway server path, with one client
    loaded synchronously -- load_client_config() reads profile_manager
    directly and has no thread-pool round trip, unlike the full
    on_client_changed() flow a real client switch goes through."""
    monkeypatch.setenv("FULFILLMENT_SERVER_PATH", str(tmp_path))
    from gui.main_window_pyside import MainWindow

    win = MainWindow()
    win.resize(1100, 900)
    win.show()
    QApplication.processEvents()

    win.profile_manager.create_client_profile("acme", "Client Acme")
    win.current_client_id = "acme"
    win.current_client_config = win.profile_manager.load_shopify_config("acme")
    win.load_client_config("acme")

    yield win
    win.close()


def test_check_files_ready_reads_the_slots_not_a_check_mark(main_window, tmp_path):
    """The bug this replaces: validity was the string "✓" in a QLabel."""
    handler = main_window.file_handler
    orders = tmp_path / "orders.csv"
    stock = tmp_path / "stock.csv"
    orders.write_text("x")
    stock.write_text("x")

    main_window.orders_slot.set_loaded(orders, "1 row")
    main_window.stock_slot.set_loaded(stock, "1 row")
    assert handler.check_files_ready() is True

    main_window.stock_slot.set_invalid(stock, ["Stock"], ["SKU"])
    assert handler.check_files_ready() is False


def test_a_stock_file_missing_its_quantity_column_puts_the_slot_in_error(
    main_window, tmp_path
):
    stock = tmp_path / "stock.csv"
    stock.write_text("Артикул;Име;Цена\nA1;Widget;9.99\n")
    main_window.stock_file_path = str(stock)

    main_window.file_handler.validate_file("stock")

    slot = main_window.stock_slot
    assert slot.is_valid is False
    assert slot.missing_columns
    assert slot.map_columns_button.isEnabled()
    assert slot.choose_other_button.isEnabled()
    assert "Nothing can be allocated" in slot.error_text()


def test_an_orders_file_with_every_required_column_loads_the_slot(
    main_window, tmp_path
):
    orders = tmp_path / "orders.csv"
    orders.write_text(
        "Name,Lineitem sku,Lineitem quantity,Shipping Method\n#1,A1,2,Standard\n"
    )
    main_window.orders_file_path = str(orders)

    main_window.file_handler.validate_file("orders")

    slot = main_window.orders_slot
    assert slot.is_valid is True
    assert slot.path == orders


def test_a_dropped_folder_merges_its_csvs_into_the_slot(
    main_window, tmp_path, monkeypatch
):
    """Spec 4.2: the slot accepts a file *or* a folder. Before the folder
    branch, a dropped directory reached pandas and raised IsADirectoryError.
    """
    folder = tmp_path / "exports"
    folder.mkdir()
    header = "Name,Lineitem sku,Lineitem quantity,Shipping Method\n"
    (folder / "a.csv").write_text(header + "#1,A1,2,Standard\n")
    (folder / "b.csv").write_text(header + "#2,B2,1,Express\n")

    # The merge is confirmed by a modal in real use; the question here is
    # what happens to the slot, not whether the dialog appears.
    monkeypatch.setattr(
        main_window.file_handler, "show_file_preview", lambda *a, **k: True
    )

    main_window.file_handler.accept_dropped_path("orders", str(folder))

    slot = main_window.orders_slot
    assert slot.is_valid is True
    assert "2 files merged" in slot._loaded_summary.text()
    assert "2 rows" in slot._loaded_summary.text()


def test_a_dropped_missing_file_shows_the_invalid_state_instead_of_raising(
    main_window, tmp_path
):
    """read_csv_headers runs only on the branch where the file already
    failed to read, so every unreadable shape has to land in the slot."""
    main_window.file_handler.accept_dropped_path(
        "orders", str(tmp_path / "not-here.csv")
    )

    assert main_window.orders_slot.is_valid is False


def test_a_semicolon_orders_file_loads_under_auto_without_a_toast(
    main_window, tmp_path, monkeypatch
):
    orders = tmp_path / "orders.csv"
    orders.write_text(
        "Name;Lineitem sku;Lineitem quantity;Shipping Method\n#1;A1;2;Standard\n"
    )
    main_window.active_profile_config.setdefault("settings", {})[
        "orders_csv_delimiter"
    ] = "auto"
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName", lambda *a, **k: (str(orders), "")
    )

    main_window.file_handler.select_orders_file()

    assert main_window.orders_slot.is_valid is True


def test_a_folder_merge_keeps_repeat_lines_and_reports_overlaps(
    main_window, tmp_path, monkeypatch
):
    folder = tmp_path / "exports"
    folder.mkdir()
    header = "Name,Lineitem sku,Lineitem quantity,Shipping Method\n"
    old, new = folder / "a.csv", folder / "b.csv"
    old.write_text(header + "#4148,501,1,Standard\n#4148,501,1,\n#9,X,1,Standard\n")
    new.write_text(header + "#9,X,1,Standard\n")
    os.utime(old, (1000, 1000))
    os.utime(new, (2000, 2000))
    monkeypatch.setattr(
        main_window.file_handler, "show_file_preview", lambda *a, **k: True
    )

    main_window.file_handler.accept_dropped_path("orders", str(folder))

    text = main_window.orders_slot._loaded_summary.text()
    assert "2 files merged" in text
    assert "3 rows" in text
    assert "1 overlapping order skipped" in text
    merged = pd.read_csv(main_window.orders_file_path)
    assert (merged["Name"] == "#4148").sum() == 2


def test_the_merged_file_is_written_with_the_override(main_window, tmp_path):
    header = "Name;Lineitem sku;Lineitem quantity;Shipping Method\n"
    f = tmp_path / "a.csv"
    f.write_text(header + "#1;A1;1;Standard\n")
    main_window.active_profile_config.setdefault("settings", {})[
        "orders_csv_delimiter"
    ] = ";"

    path, rows, skipped = main_window.file_handler.merge_and_save_files(
        [str(f)], "orders", str(tmp_path)
    )

    header_line = Path(path).read_text(encoding="utf-8-sig").splitlines()[0]
    assert header_line.count(";") == 4
    assert (rows, skipped) == (1, 0)


def _memory(skus: dict, total: int) -> dict:
    return {"enabled": True, "skus": skus, "total_units": total}


def test_a_sku_listed_once_per_location_is_not_a_hundred_percent_jump(main_window):
    """The stock file lists each SKU once per warehouse location. Memory sums a
    SKU's rows (AUDIT-02-10), so the saved snapshot and a freshly loaded file
    compare equal instead of reading as a doubling on every load."""
    handler = main_window.file_handler
    new_stock = pd.DataFrame({"SKU": ["A", "A", "B", "B"], "Stock": [10, 10, 5, 5]})
    is_anomaly, msg = handler._check_inventory_anomaly(
        new_stock, _memory({"A": 20.0, "B": 10.0}, 30)
    )
    assert is_anomaly is False, msg


def test_float_skus_from_pandas_still_match_normalised_memory(main_window):
    """pandas reads numeric SKUs as float64; memory stores normalise_sku'd
    strings. Comparing them raw made every overlap 0%."""
    handler = main_window.file_handler
    new_stock = pd.DataFrame({"SKU": [5170.0, 5171.0], "Stock": [4, 6]})
    is_anomaly, msg = handler._check_inventory_anomaly(
        new_stock, _memory({"5170": 4.0, "5171": 6.0}, 10)
    )
    assert is_anomaly is False, msg


def test_a_real_collapse_in_stock_still_asks(main_window):
    handler = main_window.file_handler
    new_stock = pd.DataFrame({"SKU": ["A", "B"], "Stock": [1, 1]})
    is_anomaly, msg = handler._check_inventory_anomaly(
        new_stock, _memory({"A": 50.0, "B": 50.0}, 100)
    )
    assert is_anomaly is True
    assert "-98%" in msg


def test_a_genuinely_different_client_file_still_asks(main_window):
    handler = main_window.file_handler
    new_stock = pd.DataFrame({"SKU": ["X", "Y"], "Stock": [10, 10]})
    is_anomaly, msg = handler._check_inventory_anomaly(
        new_stock, _memory({"A": 10.0, "B": 10.0}, 20)
    )
    assert is_anomaly is True
    assert "0% SKU overlap" in msg


def test_clearing_a_slot_forgets_the_path_and_regates_run_analysis(
    main_window, tmp_path
):
    handler = main_window.file_handler
    orders = tmp_path / "orders.csv"
    stock = tmp_path / "stock.csv"
    orders.write_text("x")
    stock.write_text("x")
    main_window.orders_file_path = str(orders)
    main_window.stock_file_path = str(stock)
    main_window.orders_slot.set_loaded(orders, "1 row")
    main_window.stock_slot.set_loaded(stock, "1 row")
    assert handler.check_files_ready() is True

    handler.clear_file("stock")

    assert main_window.stock_file_path is None
    assert main_window.stock_slot.is_valid is False
    assert main_window.run_analysis_button.isEnabled() is False


def test_clearing_the_stock_slot_keeps_run_analysis_alive_in_memory_mode(
    main_window, tmp_path
):
    """Memory mode can run without a stock file. check_files_ready only knows
    about the two slots, so re-gating through it alone greyed Run Analysis out
    for good -- for exactly the user who wanted the wrong file gone."""
    handler = main_window.file_handler
    orders = tmp_path / "orders.csv"
    stock = tmp_path / "stock.csv"
    orders.write_text("x")
    stock.write_text("x")
    main_window.orders_file_path = str(orders)
    main_window.stock_file_path = str(stock)
    main_window.orders_slot.set_loaded(orders, "1 row")
    main_window.stock_slot.set_loaded(stock, "1 row")
    main_window.session_path = main_window.session_manager.create_session("acme")
    main_window.active_profile_config["inventory_memory"] = {
        "enabled": True,
        "skus": {"A": 10.0},
        "total_units": 10,
    }
    main_window.inventory_memory_checkbox.setChecked(True)

    handler.clear_file("stock")

    assert main_window.stock_file_path is None
    assert main_window.run_analysis_button.isEnabled() is True
