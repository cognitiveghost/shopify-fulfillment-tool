"""FileHandler reads FileSlot state, not a check mark rendered into a QLabel.

The bug this replaces: validity was the string "✓" in a QLabel, read back by
check_files_ready(). FileSlot (Task 3) now owns that fact as data.
"""

from unittest.mock import Mock

import pytest
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox


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


def test_a_delimiter_mismatch_loads_with_the_detected_one_and_offers_to_save_it(
    main_window, tmp_path, monkeypatch
):
    orders = tmp_path / "orders.csv"
    orders.write_text(
        "Name;Lineitem sku;Lineitem quantity;Shipping Method\n#1;A1;2;Standard\n"
    )
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName", lambda *a, **k: (str(orders), "")
    )
    monkeypatch.setattr(
        QMessageBox, "question", Mock(side_effect=AssertionError("no question"))
    )
    toasts = Mock()
    monkeypatch.setattr("gui.file_handler.toast", toasts)

    main_window.file_handler.select_orders_file()

    toasts.assert_called_once()
    assert toasts.call_args.kwargs["role"] == "info"
    assert toasts.call_args.kwargs["action_text"] == "Save as default"
    assert ";" in toasts.call_args.args[1]


def test_a_failed_delimiter_save_tells_the_user(main_window, monkeypatch):
    """A save that raises must not leave the user believing it worked."""
    from shopify_tool.profile_manager import ProfileManagerError

    def boom(*a, **kw):
        raise ProfileManagerError("share unreachable")

    monkeypatch.setattr(main_window.profile_manager, "save_shopify_config", boom)

    seen = []
    monkeypatch.setattr(
        "gui.file_handler.toast",
        lambda parent, text, **kw: seen.append((text, kw.get("role"))),
    )

    main_window.file_handler._save_default_delimiter("orders", ";", "ACME")

    assert seen, "a failed save must raise a toast"
    assert seen[-1][1] == "error"
    assert "couldn't" in seen[-1][0].lower() or "not saved" in seen[-1][0].lower()
