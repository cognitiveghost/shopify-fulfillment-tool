"""Audit 10: production snapshot findings and bugs found by the coverage pass.

Report: docs/audit/10-coverage-and-snapshot.md. Every AUDIT-10-k test was committed failing, as
xfail(strict=True), before its fix removed the marker. Fixtures are synthetic; the production replay
lives in tests/replay/.
"""
# main_window is a fixture imported by name, so each test that takes it redefines it.
# ruff: noqa: F811
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest
from audit_support import (  # noqa: F401  pytest fixtures, used by name
    analysis_run_fixture,
    sessions_fixture,
)
from test_stale_session import (  # noqa: F401  main_window is a fixture
    _open_with_state,
    main_window,
)

import gui.main_window_pyside as main_window_module
from gui.report_selection_dialog import GenerateReportsDialog
from shopify_tool import core, report_jobs


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


def test_a_rerun_analysis_withdraws_out_of_date_lists(main_window, toasts):
    path = _with_list(main_window)
    toasts.clear()
    rerun = LISTED.assign(Quantity=[2, 1])
    main_window.actions_handler.on_analysis_complete((True, "report.xlsx", rerun, {}))
    assert main_window.write_queue.flush(timeout=10)
    assert not (Path(path) / "packing_lists" / "ALL.json").exists()


def test_opening_a_session_loads_its_recorded_fingerprints(main_window):
    path = main_window.session_manager.create_session("acme")
    main_window.session_manager.update_session_info(
        path, {"statistics": {"packing_list_fingerprints": {"ALL": "ab"}}}
    )
    from shopify_tool import session_state

    session_state.save_state(path, LISTED, None)
    main_window.load_existing_session(path)
    assert main_window._list_fingerprints == {"ALL": "ab"}


MAPPINGS_10 = {
    "orders": {"Name": "Order_Number", "Lineitem sku": "SKU",
               "Lineitem quantity": "Quantity", "Shipping Method": "Shipping_Method"},
    "stock": {"Артикул": "SKU", "Име": "Product_Name", "Наличност": "Stock"},
}


def _inputs(tmp_path):
    """Orders and stock read the way a run reads them (as tests/test_rule_settle.py does)."""
    (tmp_path / "orders.csv").write_text(
        "Name,Lineitem sku,Lineitem quantity,Shipping Method\n#1,A,1,DHL\n#2,B,2,DHL\n", encoding="utf-8")
    (tmp_path / "stock.csv").write_text("Артикул,Име,Наличност\nA,Alpha,5\nB,Beta,1\n", encoding="utf-8")
    config = {"column_mappings": MAPPINGS_10, "settings": {}}
    orders, stock = core._load_and_validate_files(
        str(tmp_path / "stock.csv"), str(tmp_path / "orders.csv"), ",", ",", config)
    return orders, stock, config


def test_analyse_stamps_the_given_time_and_matches_the_private_path(tmp_path):
    orders, stock, config = _inputs(tmp_path)
    when = datetime(2026, 10, 9, 9, 13, tzinfo=timezone(timedelta(hours=3)))
    result = core.analyse(orders, stock, config, now=when, current_session="S1")
    assert result.analysis_data["analyzed_at"] == when.isoformat()
    final, _, _stats = core._run_analysis_and_rules(
        orders, stock, pd.DataFrame({"Order_Number": []}), config, "S1")
    pd.testing.assert_frame_equal(result.final_df, final)
    assert result.analysis_data["total_orders"] == 2


def test_run_full_analysis_writes_what_analyse_returns(analysis_run, sessions, monkeypatch):
    seen = {}
    real = core.analyse

    def spy(*a, **k):
        seen["result"] = real(*a, **k)
        return seen["result"]

    monkeypatch.setattr(core, "analyse", spy)
    session = sessions.create_session("M")
    ok, msg, _df, _stats = analysis_run(session)
    assert ok, msg
    written = json.loads((Path(session) / "analysis" / "analysis_data.json").read_text(encoding="utf-8"))
    assert written == seen["result"].analysis_data


def test_a_session_keeps_the_config_it_ran_with(sessions, tmp_path, monkeypatch):
    from shopify_tool import fulfillment_history

    monkeypatch.setattr(core, "load_session_signals",
                        lambda _pm, _cid: (pd.DataFrame(columns=fulfillment_history.COLUMNS), None))
    (tmp_path / "o.csv").write_text(
        "Name,Lineitem sku,Lineitem quantity,Shipping Method\n#1,A,1,DHL\n", encoding="utf-8")
    (tmp_path / "s.csv").write_text("Артикул,Име,Наличност\nA,Alpha,5\n", encoding="utf-8")
    config = {"column_mappings": MAPPINGS_10, "rules": [], "inventory_memory": {"skus": {"A": 1}},
              "_client_config": {"x": 1}, "test_history_df": None}
    session = sessions.create_session("M")
    ok, msg, _df, _stats = core.run_full_analysis(
        str(tmp_path / "s.csv"), str(tmp_path / "o.csv"), str(tmp_path / "out"), ",", ",", config,
        client_id="M", session_manager=sessions, profile_manager=sessions.profile_manager,
        session_path=str(session))
    assert ok, msg
    kept = json.loads((Path(session) / "input" / "shopify_config.json").read_text(encoding="utf-8"))
    assert kept == {"column_mappings": MAPPINGS_10, "rules": []}


@pytest.mark.xfail(strict=True, reason="AUDIT-10-5: label CSS uses word-break: break-word")
def test_audit_10_5_label_css_has_no_property_weasyprint_ignores():
    root = Path(__file__).resolve().parents[2] / "shopify_tool" / "templates"
    for name in ("barcode_label", "qr_label"):
        css = (root / name / "style.css").read_text(encoding="utf-8")
        assert "break-word" not in css
        assert "overflow-wrap: anywhere" in css


@pytest.mark.xfail(strict=True, reason="AUDIT-10-6: expiry '0' logs a warning")
def test_audit_10_6_expiry_zero_means_none_quietly(caplog):
    import logging

    from shopify_tool.analysis import _parse_expiry_date

    with caplog.at_level(logging.WARNING, logger="shopify_tool.analysis"):
        assert _parse_expiry_date("0") is None
    assert caplog.records == []
