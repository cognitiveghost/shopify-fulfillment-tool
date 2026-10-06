"""Reports generate on a Worker, from the frame as it was at the click (AUDIT-09-O2)."""

import json
import threading
from pathlib import Path

import pandas as pd
from test_stale_session import (  # noqa: F401  main_window is a fixture
    _open_with_state,
    main_window,
)

from shopify_tool import report_jobs, stock_ledger
from shopify_tool.report_jobs import ReportOutcome

PACKING_ALL = {"name": "ALL", "report_type": "packing_lists", "output_filename": "ALL.xlsx", "filters": []}

FRAME = pd.DataFrame(
    {"Order_Number": ["#1001", "#1002"], "SKU": ["A", "B"], "Quantity": [1, 2], "Stock": [5, 5],
     "Order_Fulfillment_Status": ["Fulfillable", "Fulfillable"], "Shipping_Provider": ["DHL", "DHL"],
     "Destination_Country": ["BG", "BG"], "Warehouse_Name": ["W-A", "W-B"], "Product_Name": ["PA", "PB"],
     "Internal_Tags": ["[]", "[]"]}
)


def test_one_failing_report_does_not_stop_the_others(monkeypatch, tmp_path):
    def fake(config, *a, **k):
        if config["name"] == "DPD":
            raise ValueError("no such column")
        return ReportOutcome(config["name"], config["report_type"], output_file="x.xlsx")

    monkeypatch.setattr(report_jobs, "generate_report", fake)
    batch = [{"name": n, "report_type": "packing_lists"} for n in ("DHL", "DPD", "Daily ERP")]
    out = report_jobs.generate_reports(batch, tmp_path, FRAME, {}, "s")
    assert [(o.name, o.failed) for o in out] == [("DHL", False), ("DPD", True), ("Daily ERP", False)]


def test_a_locked_file_is_named_in_the_outcome(monkeypatch, tmp_path):
    def locked(*a, **k):
        raise PermissionError(13, "denied", str(tmp_path / "packing_lists" / "ALL.xlsx"))

    monkeypatch.setattr(report_jobs.packing_lists, "create_packing_list", locked)
    (outcome,) = report_jobs.generate_reports([PACKING_ALL], tmp_path, FRAME, {}, "s")
    assert (outcome.failed, outcome.locked_file) == (True, "ALL.xlsx")


def test_the_packing_json_names_the_session_and_its_orders(tmp_path):
    (outcome,) = report_jobs.generate_reports([PACKING_ALL], tmp_path, FRAME, {}, "2026-10-05_1")
    assert outcome.output_file == str(tmp_path / "packing_lists" / "ALL.xlsx")
    data = json.loads((tmp_path / "packing_lists" / "ALL.json").read_text(encoding="utf-8"))
    assert data["session_id"] == "2026-10-05_1"
    assert (data["total_orders"], data["total_items"]) == (2, 3)


def test_reports_toast_from_the_gui_thread(main_window, qtbot, monkeypatch):  # noqa: F811
    _open_with_state(main_window, FRAME)
    threads = []
    monkeypatch.setattr(main_window.actions_handler, "_results_toast",
                        lambda *a, **k: threads.append(threading.current_thread()))
    main_window.actions_handler._generate_reports([PACKING_ALL], main_window.session_path)
    qtbot.waitUntil(lambda: bool(threads), timeout=10_000)
    assert threads == [threading.main_thread()]
    assert (Path(main_window.session_path) / "packing_lists" / "ALL.xlsx").exists()


def test_a_report_uses_the_frame_as_it_was_at_the_click(main_window, qtbot, monkeypatch):  # noqa: F811
    _open_with_state(main_window, FRAME)
    gate = threading.Event()
    real = report_jobs.generate_reports

    def held(*a, **k):
        gate.wait(5)
        return real(*a, **k)

    monkeypatch.setattr(report_jobs, "generate_reports", held)
    try:
        main_window.actions_handler._generate_reports([PACKING_ALL], main_window.session_path)
        main_window.actions_handler.bulk_change_status(["#1002"], False)  # an edit while it runs
    finally:
        gate.set()
    qtbot.waitUntil(lambda: main_window.actions_handler._reports_worker is None, timeout=10_000)
    data = json.loads((Path(main_window.session_path) / "packing_lists" / "ALL.json").read_text(encoding="utf-8"))
    assert [o["order_number"] for o in data["orders"]] == ["#1001", "#1002"]
    assert stock_ledger.is_fulfillable(main_window.analysis_results_df, "#1002") is False


def test_a_second_batch_waits_for_the_first(main_window, qtbot, monkeypatch):  # noqa: F811
    _open_with_state(main_window, FRAME)
    gate = threading.Event()
    real = report_jobs.generate_reports
    toasts = []

    def held(*a, **k):
        gate.wait(5)
        return real(*a, **k)

    monkeypatch.setattr(report_jobs, "generate_reports", held)
    monkeypatch.setattr(main_window.actions_handler, "_results_toast", lambda text, **k: toasts.append(text))
    try:
        main_window.actions_handler._generate_reports([PACKING_ALL], main_window.session_path)
        main_window.actions_handler._generate_reports([PACKING_ALL], main_window.session_path)
        assert toasts == ["Reports are still being generated"]
    finally:
        gate.set()
    qtbot.waitUntil(lambda: main_window.actions_handler._reports_worker is None, timeout=10_000)
