"""Audit 10: production snapshot findings and bugs found by the coverage pass.

Report: docs/audit/10-coverage-and-snapshot.md. Every AUDIT-10-k test was committed failing, as
xfail(strict=True), before its fix removed the marker. Fixtures are synthetic; the production replay
lives in tests/replay/.
"""
from pathlib import Path

import pandas as pd
import pytest

import gui.main_window_pyside as main_window_module
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


@pytest.mark.parametrize("mode", ["off", "merged", "separate"])
def test_audit_10_2_the_dialog_preselects_the_given_mode(qapp, mode):
    dialog = GenerateReportsDialog(PACKING, STOCK, ONE_ORDER, lambda df, f: df, writeoff_mode=mode)
    checked = {"off": dialog.writeoff_off, "merged": dialog.writeoff_merged,
               "separate": dialog.writeoff_separate}
    assert checked[mode].isChecked()


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


def test_audit_10_4_a_failed_regeneration_withdraws_the_old_list(tmp_path, monkeypatch):
    lists = tmp_path / "packing_lists"
    lists.mkdir()
    (lists / "ALL.json").write_text("{}", encoding="utf-8")

    def held(session_path, stem):
        raise PermissionError(13, "open in a viewer", f"{stem}_barcodes.pdf")

    monkeypatch.setattr(report_jobs.barcode_processor, "invalidate_label_pdfs", held)
    config = {"name": "ALL", "report_type": "packing_lists", "output_filename": "ALL.xlsx", "filters": []}
    outcome = report_jobs.generate_report(config, tmp_path, pd.DataFrame(), {}, "s")
    assert outcome.failed and outcome.locked_file
    assert not (lists / "ALL.json").exists()


LISTED = pd.DataFrame(
    {"Order_Number": ["#1001", "#1002"], "SKU": ["A", "B"], "Quantity": [1, 1], "Stock": [5, 5],
     "Order_Fulfillment_Status": ["Fulfillable", "Fulfillable"], "Internal_Tags": ["[]", "[]"],
     "Tags": ["", ""]}
)


def _with_list(win, name="ALL", started=False):
    path = _open_with_state(win, LISTED)
    lists = Path(path) / "packing_lists"
    lists.mkdir(exist_ok=True)
    (lists / f"{name}.json").write_text('{"total_orders": 2}', encoding="utf-8")
    (lists / f"{name}.xlsx").write_bytes(b"x")
    if started:
        (Path(path) / "packing" / name).mkdir(parents=True)
    win._list_fingerprints = {name: report_jobs.packing_fingerprint(LISTED)}
    return path


@pytest.fixture
def toasts(monkeypatch):
    seen = []
    monkeypatch.setattr(main_window_module, "toast", lambda src, text, **k: seen.append(text))
    return seen


@pytest.mark.xfail(strict=True, reason="AUDIT-10-4: an edit leaves the old list for the Packer")
def test_audit_10_4_an_edit_withdraws_the_out_of_date_list_once(main_window, toasts):
    path = _with_list(main_window)
    toasts.clear()  # opening the session toasted
    main_window.actions_handler.bulk_change_status(["#1001"], False)
    assert main_window.write_queue.flush(timeout=10)
    assert not (Path(path) / "packing_lists" / "ALL.json").exists()
    assert (Path(path) / "packing_lists" / "withdrawn" / "ALL.json").exists()
    assert toasts == [report_jobs.out_of_date_message(["ALL"], [])]
    main_window.actions_handler.bulk_change_status(["#1002"], False)
    assert toasts == [report_jobs.out_of_date_message(["ALL"], [])]  # once, not per edit


def test_audit_10_8_a_bulk_tag_edit_does_not_raise(main_window, toasts):
    _with_list(main_window)
    main_window.actions_handler.bulk_add_tag(["#1001"], "VIP")
    main_window.actions_handler.bulk_remove_tag(["#1001"], "VIP")


def test_a_tag_edit_withdraws_nothing(main_window, toasts):
    path = _with_list(main_window)
    toasts.clear()
    main_window.actions_handler.bulk_add_tag(["#1001"], "VIP")
    assert main_window.write_queue.flush(timeout=10)
    assert (Path(path) / "packing_lists" / "ALL.json").exists()
    assert toasts == []


@pytest.mark.xfail(strict=True, reason="AUDIT-10-4: a started list is not named")
def test_a_started_list_stays_and_is_named(main_window, toasts):
    path = _with_list(main_window, started=True)
    toasts.clear()
    main_window.actions_handler.bulk_change_status(["#1001"], False)
    assert main_window.write_queue.flush(timeout=10)
    assert (Path(path) / "packing_lists" / "ALL.json").exists()
    assert toasts == [report_jobs.out_of_date_message([], ["ALL"])]


def test_a_session_without_fingerprints_withdraws_nothing(main_window, toasts):
    path = _with_list(main_window)
    main_window._list_fingerprints = {}
    main_window.actions_handler.bulk_change_status(["#1001"], False)
    assert main_window.write_queue.flush(timeout=10)
    assert (Path(path) / "packing_lists" / "ALL.json").exists()


@pytest.mark.xfail(strict=True, reason="AUDIT-10-4: a re-run leaves the old list")
def test_a_rerun_analysis_withdraws_out_of_date_lists(main_window, toasts):
    path = _with_list(main_window)
    toasts.clear()
    rerun = LISTED.assign(Quantity=[2, 1])
    main_window.actions_handler.on_analysis_complete((True, "report.xlsx", rerun, {}))
    assert main_window.write_queue.flush(timeout=10)
    assert not (Path(path) / "packing_lists" / "ALL.json").exists()


@pytest.mark.xfail(strict=True, reason="AUDIT-10-4: fingerprints are not loaded with a session")
def test_opening_a_session_loads_its_recorded_fingerprints(main_window):
    path = main_window.session_manager.create_session("acme")
    main_window.session_manager.update_session_info(
        path, {"statistics": {"packing_list_fingerprints": {"ALL": "ab"}}}
    )
    from shopify_tool import session_state

    session_state.save_state(path, LISTED, None)
    main_window.load_existing_session(path)
    assert main_window._list_fingerprints == {"ALL": "ab"}
