"""Opening a past session restores what it ran on, not just its results.

The bug: load_existing_session set analysis_results_df and left
stock_file_path at None, so update_ui_state disabled Add Product to Order
in a session that plainly had a stock file.
"""

import pandas as pd
import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def main_window(tmp_path, monkeypatch):
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


def _session_with_inputs(win):
    """A session directory holding the two files an analysis copies into it.

    Their columns are the ones the client profile requires, because that is
    what a session's inputs are: files that already passed validation once.
    Anything else drives the restored slots into the invalid face.
    """
    path = win.session_manager.create_session("acme")
    input_dir = win.session_manager.get_input_dir(path)
    pd.DataFrame(
        {
            "Name": ["#1001"],
            "Lineitem sku": ["A"],
            "Lineitem quantity": [1],
            "Shipping Method": ["DHL"],
        }
    ).to_csv(input_dir / "orders_export.csv", index=False)
    # Semicolons: the profile's stock_csv_delimiter default, and validation
    # reads the file with it.
    pd.DataFrame({"Артикул": ["A"], "Наличност": [5]}).to_csv(
        input_dir / "inventory.csv", index=False, sep=";"
    )
    win.session_manager.update_session_info(
        path, {"orders_file": "orders_export.csv", "stock_file": "inventory.csv"}
    )
    return path


def test_restoring_a_session_points_at_the_files_it_ran_on(main_window):
    path = _session_with_inputs(main_window)
    main_window._restore_session_inputs(path)

    assert main_window.stock_file_path is not None
    assert main_window.stock_file_path.endswith("inventory.csv")
    # The slot, not just the path -- a restored path the Setup screen still
    # shows as an empty slot is the half of this defect the user actually sees.
    assert main_window.stock_slot.is_valid is True


def test_the_orders_file_is_deliberately_not_restored(main_window):
    """Restoring it would re-enable Run Analysis in a resumed session, and
    run_analysis reuses the open session_path -- one click would overwrite the
    session's results with no confirm. Owner's call, 2026-09-20."""
    path = _session_with_inputs(main_window)
    main_window.session_path = path
    main_window._restore_session_inputs(path)
    main_window.update_ui_state()

    assert main_window.orders_file_path is None
    assert main_window.run_analysis_button.isEnabled() is False


def test_add_product_is_reachable_in_a_restored_session(main_window):
    path = _session_with_inputs(main_window)
    main_window.session_path = path
    main_window.analysis_results_df = pd.DataFrame(
        {"Order_Number": [1], "SKU": ["A"], "Final_Stock": [4]}
    )
    main_window._restore_session_inputs(path)
    main_window.update_ui_state()

    assert main_window.add_product_button_tab2.isEnabled() is True


def test_a_session_whose_input_files_are_gone_restores_nothing(main_window):
    path = main_window.session_manager.create_session("acme")
    # Seed the path first, or this passes against an empty method body.
    main_window.stock_file_path = "/gone/inventory.csv"

    main_window._restore_session_inputs(path)

    assert main_window.stock_file_path == "/gone/inventory.csv"
    assert main_window.stock_slot.is_valid is False


def test_opening_a_session_restores_its_inputs(main_window):
    """The seam the user actually reaches: load_existing_session, not the
    private helper. Nothing covered the call site itself."""
    path = _session_with_inputs(main_window)
    main_window.load_existing_session(path)

    assert main_window.stock_file_path.endswith("inventory.csv")
    assert main_window.stock_slot.is_valid is True


def test_opening_a_session_re_derives_stock_left(main_window):
    """A session saved by an older build can hold a Final_Stock that edits let
    drift; opening it makes the ledger true again (spec 2026-09-25 D4)."""
    path = _session_with_inputs(main_window)

    def load_stale_analysis(_path):
        main_window.analysis_results_df = pd.DataFrame(
            {
                "Order_Number": ["#1001"],
                "SKU": ["A"],
                "Quantity": [2],
                "Order_Fulfillment_Status": ["Fulfillable"],
                "Stock": [5],
                "Final_Stock": [5.0],
            }
        )
        return True

    main_window._load_session_analysis = load_stale_analysis
    main_window.load_existing_session(path)

    assert main_window.analysis_results_df["Final_Stock"].tolist() == [3.0]
