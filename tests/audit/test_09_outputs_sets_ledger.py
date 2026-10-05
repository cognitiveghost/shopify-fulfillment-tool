"""Audit 09: set decoding, Packing Tool JSON, stock ledger and exports.

Report: docs/audit/09-outputs-sets-ledger-review.md. Every AUDIT-09-k test
fails because of the finding it names and is marked xfail(strict=True); the
fix removes the marker. Unmarked tests pin what the audit verified correct.
Timing tests use the audit's benchmark frame with a generous ceiling.
"""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest
from audit_support import (  # noqa: F401  pytest fixtures, used by name
    BENCH_ORDERS,
    analysis_run_fixture,
    benchmark_frame_fixture,
    in_place_writes_fixture,
    sessions_fixture,
    timed,
)

from gui.actions_handler import ActionsHandler
from gui.selection_helper import SelectionHelper
from shopify_tool import core, stock_ledger
from shopify_tool.analysis import run_analysis, toggle_order_fulfillment
from shopify_tool.set_decoder import decode_sets_in_orders, import_sets_from_csv
from shopify_tool.undo_manager import UndoManager

NO_HISTORY = pd.DataFrame({"Order_Number": []})


# --------------------------------------------------------------------------
# AUDIT-09-O1: set decoding copies every row in Python
# --------------------------------------------------------------------------


@pytest.mark.xfail(strict=True, reason="AUDIT-09-O1: iterrows and row.copy() over every line")
def test_AUDIT_09_O1_decoding_15000_lines_takes_under_a_second():
    """Audit: 17.7 s. 15,000 lines, 18 columns, a set in a third of them."""
    n = 15000
    df = pd.DataFrame(
        {"Order_Number": [f"#{i // 3}" for i in range(n)], "SKU": ["SET-1", "A", "B"] * (n // 3),
         "Quantity": [1] * n, **{f"c{k}": "x" for k in range(15)}}
    )
    sets = {"SET-1": [{"sku": "A", "quantity": 1}, {"sku": "C", "quantity": 2}]}

    seconds, out = timed(lambda: decode_sets_in_orders(df, sets))

    assert len(out) == 20000
    assert seconds < 1.0


# --------------------------------------------------------------------------
# AUDIT-09-O2: the Packing Tool JSON builder is slow
# --------------------------------------------------------------------------


@pytest.mark.xfail(strict=True, reason="AUDIT-09-O2: is_fulfillable and iterrows per order")
def test_AUDIT_09_O2_the_packing_json_for_5000_orders_builds_in_seconds(benchmark_frame):
    """Audit: 12.7 s, in every run's save step and per packing list on the
    GUI thread."""
    seconds, data = timed(lambda: core._create_analysis_data_for_packing(benchmark_frame[0]))

    assert data["total_orders"] == BENCH_ORDERS
    assert seconds < 2.0


# --------------------------------------------------------------------------
# AUDIT-09-O3: force-fulfil ignores SKUs that aren't in the stock file
# --------------------------------------------------------------------------


@pytest.fixture
def unlisted_sku_order():
    """One order for 3 x X; the stock file lists only A. The run holds it."""
    orders = pd.DataFrame(
        {"Name": ["#1"], "Lineitem sku": ["X"], "Lineitem quantity": [3],
         "Shipping Method": ["DHL"], "Shipping Country": ["BG"]}
    )
    stock = pd.DataFrame({"Артикул": ["A"], "Име": ["a"], "Наличност": [5]})
    df, _ = run_analysis(stock, orders, NO_HISTORY)
    assert df["Order_Fulfillment_Status"].tolist() == ["Not Fulfillable"]
    return df


@pytest.mark.xfail(strict=True, reason="AUDIT-09-O3: _short skips SKUs not in the stock file")
def test_AUDIT_09_O3_force_fulfilling_an_unlisted_sku_is_not_silent(unlisted_sku_order):
    """Holds under either owner rule: refuse (treat unlisted as 0) or allow
    and warn. Both tell the person."""
    ok, message, _df = toggle_order_fulfillment(unlisted_sku_order.copy(), "#1")

    assert not ok or message


@pytest.mark.xfail(strict=True, reason="AUDIT-09-O3: claim covers SKUs not in the stock file")
def test_AUDIT_09_O3_bulk_mark_fulfillable_on_an_unlisted_sku_is_not_silent(unlisted_sku_order):
    mw = SimpleNamespace(
        analysis_results_df=unlisted_sku_order.copy(),
        analysis_stats=None,
        save_session_state=Mock(),
        log_activity=Mock(),
        _update_all_views=Mock(),
        results_bridge=Mock(),
        ui_manager=Mock(),
        session_path=None,
        current_client_id="AUDIT",
        active_profile_config={"settings": {}},
    )
    mw.selection_helper = SelectionHelper(main_window=mw)
    mw.undo_manager = UndoManager(mw)

    ActionsHandler(mw).bulk_change_status(["#1"], True)

    held = mw.analysis_results_df["Order_Fulfillment_Status"].tolist() == ["Not Fulfillable"]
    toasts = " ".join(str(c.args[0]) for c in mw.results_bridge.raise_toast.call_args_list)
    assert held or "stock" in toasts


def test_a_listed_sku_short_of_stock_is_refused(unlisted_sku_order):
    """The listed-SKU path the audit verified: Stock left decides."""
    df = unlisted_sku_order.copy()
    df["SKU"] = "A"
    df["Stock"] = 2
    df["Final_Stock"] = 2
    assert stock_ledger.shortfall(df, "#1") == ["A"]
    assert stock_ledger.claim(df, ["#1"]) == ([], ["#1"])


# --------------------------------------------------------------------------
# AUDIT-09-O4: set import keeps spaces, and the decoder never normalises keys
# --------------------------------------------------------------------------


@pytest.mark.xfail(strict=True, reason="AUDIT-09-O4: Set_SKU and Component_SKU stored as written")
def test_AUDIT_09_O4_an_imported_set_with_spaces_still_expands(tmp_path):
    csv = tmp_path / "sets.csv"
    csv.write_text("Set_SKU,Component_SKU,Component_Quantity\nSET-1 ,A ,2\n", encoding="utf-8")

    sets = import_sets_from_csv(str(csv))
    out = decode_sets_in_orders(
        pd.DataFrame({"Order_Number": ["#1"], "SKU": ["SET-1"], "Quantity": [1]}), sets
    )

    assert out["SKU"].tolist() == ["A"]
    assert out["Quantity"].tolist() == [2]


def test_an_excel_csv_with_a_bom_imports(tmp_path):
    """The report's BOM claim does not reproduce: pandas' C parser strips a
    UTF-8 BOM, so the header is read as Set_SKU."""
    csv = tmp_path / "sets.csv"
    csv.write_text("Set_SKU,Component_SKU,Component_Quantity\nSET-1,A,2\n", encoding="utf-8-sig")
    assert csv.read_bytes().startswith(b"\xef\xbb\xbf")

    assert import_sets_from_csv(str(csv)) == {"SET-1": [{"sku": "A", "quantity": 2}]}


# --------------------------------------------------------------------------
# AUDIT-09-O5: Packing Tool files written in place; a failed build saves an
# empty session
# --------------------------------------------------------------------------


def _packing_list_handler(df):
    mw = Mock()
    mw.analysis_results_df = df
    mw.session_path = None
    return ActionsHandler(mw)


@pytest.mark.xfail(strict=True, reason="AUDIT-09-O5: open(json_path, 'w') next to the XLSX")
def test_AUDIT_09_O5_the_packing_list_json_is_written_atomically(tmp_path, in_place_writes):
    df = pd.DataFrame(
        {"Order_Number": ["#1"], "SKU": ["A"], "Quantity": [1],
         "Order_Fulfillment_Status": ["Fulfillable"], "Shipping_Provider": ["DHL"],
         "Destination_Country": ["BG"], "Warehouse_Name": ["W"], "Product_Name": ["P"],
         "Internal_Tags": ["[]"]}
    )
    in_place = in_place_writes("ALL.json")

    _packing_list_handler(df)._generate_single_report(
        "packing_lists", {"name": "ALL", "output_filename": "ALL.xlsx", "filters": []}, tmp_path
    )

    written = json.loads((tmp_path / "packing_lists" / "ALL.json").read_text(encoding="utf-8"))
    assert [o["order_number"] for o in written["orders"]] == ["#1"]
    assert in_place == []


@pytest.mark.xfail(strict=True, reason="AUDIT-09-O5: a build error is saved as an empty session")
def test_AUDIT_09_O5_a_failed_packing_build_does_not_empty_the_session(
    sessions, analysis_run, monkeypatch
):
    path = sessions.create_session("M")
    ok, msg, _df, _stats = analysis_run(path)
    assert ok, msg
    data_json = Path(path) / "analysis" / "analysis_data.json"
    assert len(json.loads(data_json.read_text(encoding="utf-8"))["orders"]) == 2

    def broken(_order_number, _group):
        raise ValueError("a row Packing Tool's builder cannot read")

    monkeypatch.setattr(core, "build_packing_order_data", broken)
    ok, _msg, _df, stats = analysis_run(path)  # the operator re-runs

    failure_reported = not ok or any(
        k.endswith("_warning") and k != "history_warning" for k in (stats or {})
    )
    assert failure_reported
    assert len(json.loads(data_json.read_text(encoding="utf-8"))["orders"]) == 2
