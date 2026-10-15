"""Audit 10: production snapshot findings and bugs found by the coverage pass.

Report: docs/audit/10-coverage-and-snapshot.md. Every AUDIT-10-k test was committed failing, as
xfail(strict=True), before its fix removed the marker. Fixtures are synthetic; the production replay
lives in tests/replay/.
"""
from pathlib import Path

import pandas as pd
import pytest

from gui.report_selection_dialog import GenerateReportsDialog
from shopify_tool import report_jobs
from test_stale_session import _open_with_state, main_window  # noqa: F401  main_window is a fixture


@pytest.mark.parametrize(
    ("report_type", "filename", "expected"),
    [("packing_lists", "ALL.xls", "ALL.xlsx"), ("stock_exports", "ERP", "ERP.xls")],
)
def test_report_names_already_normalised(report_type, filename, expected, tmp_path):
    out = report_jobs._output_file(report_type, "X", {"output_filename": filename}, tmp_path)
    assert Path(out).name == expected


@pytest.mark.parametrize(
    ("report_type", "filename", "expected"),
    [
        ("packing_lists", "MASKS.XLSX", "MASKS.xlsx"),
        ("packing_lists", "ALL", "ALL.xlsx"),
        ("packing_lists", "ALL.v2", "ALL.v2.xlsx"),
        ("stock_exports", "ERP.XLS", "ERP.xls"),
        ("stock_exports", "ERP.xlsx", "ERP.xls"),
    ],
)
def test_audit_10_1_report_names_get_one_lower_case_extension(report_type, filename, expected, tmp_path):
    out = report_jobs._output_file(report_type, "X", {"output_filename": filename}, tmp_path)
    assert Path(out).name == expected


def test_audit_10_1_an_upper_case_name_still_writes_the_packing_list(tmp_path):
    frame = pd.DataFrame(
        {"Order_Number": ["#1001"], "SKU": ["A"], "Quantity": [1], "Stock": [5],
         "Order_Fulfillment_Status": ["Fulfillable"], "Shipping_Provider": ["DHL"],
         "Destination_Country": ["BG"], "Warehouse_Name": ["W-A"], "Product_Name": ["PA"],
         "Internal_Tags": ["[]"]}
    )
    config = {"name": "MASKS", "report_type": "packing_lists", "output_filename": "MASKS.XLSX", "filters": []}
    outcome = report_jobs.generate_report(config, tmp_path, frame, {}, "s")
    assert not outcome.failed
    assert (tmp_path / "packing_lists" / "MASKS.xlsx").exists()
    assert (tmp_path / "packing_lists" / "MASKS.json").exists()


PACKING = [{"name": "ALL", "filters": []}]
STOCK = [{"name": "ERP", "filters": []}]
ONE_ORDER = pd.DataFrame(
    {"Order_Number": ["#1001"], "SKU": ["A"], "Quantity": [1], "Order_Fulfillment_Status": ["Fulfillable"]}
)


@pytest.mark.xfail(strict=True, reason="AUDIT-10-2: the dialog cannot preselect a mode")
@pytest.mark.parametrize("mode", ["off", "merged", "separate"])
def test_audit_10_2_the_dialog_preselects_the_given_mode(qapp, mode):
    dialog = GenerateReportsDialog(PACKING, STOCK, ONE_ORDER, lambda df, f: df, writeoff_mode=mode)
    checked = {"off": dialog.writeoff_off, "merged": dialog.writeoff_merged,
               "separate": dialog.writeoff_separate}
    assert checked[mode].isChecked()


@pytest.mark.xfail(strict=True, reason="AUDIT-10-2: the choice is not stored")
def test_audit_10_2_generating_stores_the_mode_without_a_backup(main_window, monkeypatch):
    from shopify_tool import report_jobs as jobs
    path = _open_with_state(main_window, ONE_ORDER.assign(Stock=5))
    monkeypatch.setattr(jobs, "generate_reports", lambda *a, **k: [])
    backups = Path(main_window.profile_manager.get_client_directory("acme")) / "backups"
    before = set(backups.glob("*")) if backups.exists() else set()

    main_window.actions_handler._generate_reports(
        [{"name": "ERP", "report_type": "stock_exports", "writeoff_mode": "merged"}], path
    )
    main_window.threadpool.waitForDone(5000)

    saved = main_window.profile_manager.load_shopify_config("acme")
    assert saved["last_writeoff_mode"] == "merged"
    assert main_window.active_profile_config["last_writeoff_mode"] == "merged"
    after = set(backups.glob("*")) if backups.exists() else set()
    assert after == before
