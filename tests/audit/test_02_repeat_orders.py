"""Audit 02: repeat orders, inventory memory, packed-order check.

Report: docs/audit/02-repeat-orders.md. Every AUDIT-02-k test fails because
of the bug it names and is marked xfail(strict=True); the fix removes the
marker. The unmarked tests pin what the audit verified correct.

Runs go through core.run_full_analysis in legacy mode (no session manager),
so the real history read, repeat detection and history write all run. The
Packing Tool signal is injected by replacing core.load_packed_orders, whose
own reader is covered by tests/test_packed_orders.py. Fixtures are synthetic.
"""

import datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest

from gui.actions_handler import ActionsHandler
from gui.selection_helper import SelectionHelper
from shopify_tool import core
from shopify_tool.packing_lists import create_packing_list
from shopify_tool.sku_writeoff import calculate_writeoff_quantities
from shopify_tool.stock_export import create_stock_export
from shopify_tool.undo_manager import UndoManager

MAPPINGS = {
    "orders": {
        "Name": "Order_Number",
        "Lineitem sku": "SKU",
        "Lineitem quantity": "Quantity",
        "Shipping Method": "Shipping_Method",
    },
    "stock": {"Артикул": "SKU", "Име": "Product_Name", "Наличност": "Stock"},
}

# The local date, as core writes it into history.
TODAY = datetime.datetime.now().astimezone().date()
YESTERDAY = (TODAY - datetime.timedelta(days=1)).isoformat()


def packed(*orders, day=YESTERDAY):
    """What load_packed_orders returns: orders Packing Tool completed."""
    return pd.DataFrame(
        {"Order_Number": list(orders), "Execution_Date": [day] * len(orders)}
    )


class Shop:
    """One client's files on disk: history, and a run that reads and writes it."""

    def __init__(self, tmp_path, monkeypatch):
        self.dir = tmp_path
        self.history = tmp_path / "fulfillment_history.csv"
        self.packed = packed()
        monkeypatch.setattr(core, "get_persistent_data_path", lambda _n: self.history)
        monkeypatch.setattr(core, "load_packed_orders", lambda _pm, _cid: self.packed)
        self._n = 0

    def write_history(self, rows):
        pd.DataFrame(rows, columns=["Order_Number", "Execution_Date"]).to_csv(
            self.history, index=False
        )

    def history_rows(self):
        return dict(pd.read_csv(self.history, dtype=str).values.tolist())

    def age_history(self, days=1):
        """Move every history date back, as if the next working day has come."""
        h = pd.read_csv(self.history, dtype=str)
        h["Execution_Date"] = (
            pd.to_datetime(h["Execution_Date"]) - pd.Timedelta(days=days)
        ).dt.strftime("%Y-%m-%d")
        h.to_csv(self.history, index=False)

    def run(self, order_rows, stock_rows, window=1, **kw):
        """order_rows: (name, sku, qty); stock_rows: (sku, qty) or None for memory mode."""
        self._n += 1
        orders_csv = self.dir / f"orders{self._n}.csv"
        pd.DataFrame(
            [
                {
                    "Name": n,
                    "Lineitem sku": s,
                    "Lineitem quantity": q,
                    "Shipping Method": "DHL",
                }
                for n, s, q in order_rows
            ]
        ).to_csv(orders_csv, index=False)
        stock_csv = None
        if stock_rows is not None:
            stock_csv = self.dir / f"stock{self._n}.csv"
            pd.DataFrame(
                [
                    {"Артикул": s, "Име": f"{s} name", "Наличност": q}
                    for s, q in stock_rows
                ]
            ).to_csv(stock_csv, index=False)
        ok, msg, final_df, _ = core.run_full_analysis(
            str(stock_csv) if stock_csv else None,
            str(orders_csv),
            str(self.dir / "out"),
            ",",
            ",",
            {
                "settings": {"repeat_detection_days": window},
                "column_mappings": MAPPINGS,
            },
            **kw,
        )
        assert ok, msg
        return final_df


def repeat(df, order):
    notes = df.loc[df["Order_Number"].astype(str) == str(order), "System_note"]
    return any("Repeat" in str(n) for n in notes)


def window(df):
    mw = SimpleNamespace(
        analysis_results_df=df,
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
    return mw


class MemoryProfile:
    """The four ProfileManager calls a run makes, with memory enabled."""

    def __init__(self, client_dir, skus):
        self.client_dir = client_dir
        self.memory = {"enabled": True, "skus": dict(skus), "names": {}}

    def get_inventory_memory(self, _cid):
        return self.memory

    def load_shopify_config(self, _cid):
        return {"inventory_memory": self.memory}

    def load_client_config(self, _cid):
        return {}

    def get_client_directory(self, _cid):
        return self.client_dir

    def save_inventory_memory(self, _cid, stock_dict, config=None, names_dict=None):
        self.memory["skus"] = dict(stock_dict)
        return True


@pytest.fixture
def shop(tmp_path, monkeypatch):
    return Shop(tmp_path, monkeypatch)


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason="AUDIT-02-1: an order packed earlier today in another session is not flagged Repeat",
)
def test_order_packed_earlier_today_in_another_session_is_flagged(shop):
    # Morning session packed #1. The afternoon export still lists it, because
    # Shopify has not been marked fulfilled yet.
    shop.packed = packed("#1", day=TODAY.isoformat())
    df = shop.run([("#1", "A", 1)], [("A", 5)])
    assert repeat(df, "#1")


@pytest.mark.xfail(
    strict=True,
    reason="AUDIT-02-2: raising the repeat window hides recent repeats instead of widening detection",
)
def test_raising_the_repeat_window_still_flags_yesterdays_order(shop):
    shop.write_history([("#1", YESTERDAY)])
    df = shop.run([("#1", "A", 1)], [("A", 5)], window=7)
    assert repeat(df, "#1")


@pytest.mark.xfail(
    strict=True,
    reason="AUDIT-02-3: an order a person marks fulfillable never reaches fulfillment history",
)
def test_order_marked_fulfillable_by_a_person_is_flagged_next_day(shop):
    # Stock covers one of the two. A person swaps them: hold #1, ship #2.
    lines = [("#1", "A", 3), ("#2", "A", 3)]
    df = shop.run(lines, [("A", 3)])
    handler = ActionsHandler(mw := window(df))
    handler.toggle_fulfillment_status_for_order("#1")
    handler.toggle_fulfillment_status_for_order("#2")
    after = mw.analysis_results_df.groupby("Order_Number")[
        "Order_Fulfillment_Status"
    ].first()
    assert after.to_dict() == {"#1": "Not Fulfillable", "#2": "Fulfillable"}
    # If the fix writes history from save_session_state (a Mock here), call
    # the real writer at this point.
    shop.age_history()
    # #2 shipped without Packing Tool, so the packed signal stays empty.
    df2 = shop.run(lines, [("A", 3)])
    assert repeat(df2, "#2")


@pytest.mark.xfail(
    strict=True,
    reason="AUDIT-02-4: an order analysed fulfillable but held and never shipped is flagged Repeat",
)
def test_order_held_after_analysis_is_not_a_repeat_next_day(shop):
    df = shop.run([("#1", "A", 1)], [("A", 5)])
    mw = window(df)
    ActionsHandler(mw).toggle_fulfillment_status_for_order("#1")
    assert set(mw.analysis_results_df["Order_Fulfillment_Status"]) == {
        "Not Fulfillable"
    }
    shop.age_history()
    df2 = shop.run([("#1", "A", 1)], [("A", 5)])
    assert not repeat(df2, "#1")


@pytest.mark.xfail(
    strict=True,
    reason="AUDIT-02-5: numeric order numbers never match the Packing Tool signal (int vs str)",
)
def test_numeric_order_number_packed_yesterday_is_flagged(shop):
    # Packing Tool records str(order_number) from the packing-list JSON.
    shop.packed = packed("12345")
    df = shop.run([(12345, "A", 1)], [("A", 5)])
    assert repeat(df, 12345)


@pytest.mark.xfail(
    strict=True,
    reason="AUDIT-02-6: an unreadable history file is replaced by this run's orders alone",
)
def test_unreadable_history_is_not_overwritten(shop):
    shop.history.write_text(
        "Order_Number,Execution_Date\n"
        "#OLD1,2026-01-05\n"
        "#OLD2,2026-01-05,stray field\n",  # one bad row -> ParserError on read
        encoding="utf-8",
    )
    shop.run([("#NEW", "A", 1)], [("A", 5)])
    text = shop.history.read_text(encoding="utf-8")
    assert "#OLD1" in text and "#OLD2" in text


@pytest.mark.xfail(
    strict=True,
    reason="AUDIT-02-7: two PCs analysing one client at once lose one side's history rows",
)
def test_concurrent_runs_keep_both_sides_history(shop, monkeypatch):
    original = core._run_analysis_and_rules

    def pc_a_between_read_and_write(*args, **kwargs):
        # PC B runs a whole analysis while PC A holds the history it read.
        monkeypatch.setattr(core, "_run_analysis_and_rules", original)
        shop.run([("#B", "A", 1)], [("A", 5)])
        return original(*args, **kwargs)

    monkeypatch.setattr(core, "_run_analysis_and_rules", pc_a_between_read_and_write)
    shop.run([("#A", "A", 1)], [("A", 5)])
    assert {"#A", "#B"} <= set(shop.history_rows())


@pytest.mark.xfail(
    strict=True,
    reason="AUDIT-02-8: a Repeat order reaches the printed packing list with no mark",
)
def test_packing_list_marks_a_repeat_order(shop, tmp_path):
    shop.write_history([("#1", YESTERDAY)])
    df = shop.run([("#1", "A", 1), ("#2", "A", 1)], [("A", 5)])
    assert repeat(df, "#1")
    out = tmp_path / "list.xlsx"
    create_packing_list(df, str(out))
    sheet = pd.read_excel(out, header=None, dtype=str).fillna("")
    rows_for_1 = sheet[
        sheet.apply(lambda r: r.str.contains("#1", regex=False).any(), axis=1)
    ]
    assert rows_for_1.apply(lambda r: r.str.contains("Repeat").any(), axis=1).any()


@pytest.mark.xfail(
    strict=True,
    reason="AUDIT-02-9: a run without a stock file (inventory memory) ignores fulfillment history",
)
def test_memory_mode_run_reads_history(shop):
    shop.write_history([("#1", YESTERDAY)])
    pm = MemoryProfile(shop.dir, {"A": 10.0})
    shop.history = shop.dir / "fulfillment_history.csv"  # client dir == tmp_path
    df = shop.run([("#1", "A", 2)], None, client_id="AUDIT", profile_manager=pm)
    assert repeat(df, "#1")


@pytest.mark.xfail(
    strict=True,
    reason="AUDIT-02-9: a run without a stock file never saves memory or history",
)
def test_memory_mode_run_writes_memory_and_history(shop):
    pm = MemoryProfile(shop.dir, {"A": 10.0})
    df = shop.run([("#1", "A", 2)], None, client_id="AUDIT", profile_manager=pm)
    assert set(df["Order_Fulfillment_Status"]) == {"Fulfillable"}
    assert pm.memory["skus"] == {"A": 8.0}
    assert "#1" in shop.history_rows()


def test_memory_seed_sums_a_sku_listed_on_several_rows():
    stock_df = pd.DataFrame({"SKU": ["A", "A", "B"], "Stock": [3, 4, 1]})
    final_df = pd.DataFrame({"SKU": ["B"], "Final_Stock": [0]})
    assert core.build_inventory_snapshot(final_df, stock_df) == {"A": 7.0, "B": 0.0}
    assert core.inventory_total_units(stock_df) == 8.0


# ---------------------------------------------------------------------------
# Verified correct
# ---------------------------------------------------------------------------


def test_order_packed_on_an_earlier_day_is_flagged_even_without_history(shop):
    """The Packing Tool signal alone flags it: covers orders a person marked
    fulfillable, which history never records (AUDIT-02-3)."""
    shop.packed = packed("#1")
    df = shop.run([("#1", "A", 1), ("#2", "A", 1)], [("A", 5)])
    assert repeat(df, "#1") and not repeat(df, "#2")


def test_order_in_history_from_an_earlier_day_is_flagged(shop):
    shop.write_history([("#1", "2026-01-05")])
    df = shop.run([("#1", "A", 1), ("#2", "A", 1)], [("A", 5)])
    assert repeat(df, "#1") and not repeat(df, "#2")


def test_rerunning_the_same_export_today_does_not_flag_its_own_orders(shop):
    """What the same-day rule exists for. The AUDIT-02-1 fix must keep it."""
    shop.run([("#1", "A", 1)], [("A", 5)])
    df = shop.run([("#1", "A", 1)], [("A", 5)])
    assert not repeat(df, "#1")


def test_rerun_keeps_the_earliest_history_date(shop):
    shop.write_history([("#1", "2026-01-05")])
    shop.run([("#1", "A", 1)], [("A", 5)])
    assert shop.history_rows()["#1"] == "2026-01-05"


def test_packaging_writeoff_counts_each_tag_once_per_order():
    df = pd.DataFrame(
        {
            "Order_Number": ["#1", "#1", "#1", "#2"],
            "Order_Fulfillment_Status": ["Fulfillable"] * 3 + ["Not Fulfillable"],
            "Internal_Tags": ['["BOX"]'] * 4,
        }
    )
    config = {
        "version": 2,
        "categories": {
            "packaging": {
                "tags": ["BOX"],
                "sku_writeoff": {
                    "enabled": True,
                    "mappings": {"BOX": [{"sku": "PKG", "quantity": 1.0}]},
                },
            }
        },
    }
    out = calculate_writeoff_quantities(df, config)
    assert out.set_index("SKU")["Writeoff_Quantity"].to_dict() == {"PKG": 1.0}


def test_stock_export_writes_a_repeated_sku_off_once_after_reopen(tmp_path):
    """Lot path: two lines of one SKU share one allocation. The export dedupes
    it by object identity, which must survive the session's pickle."""
    stock_df = pd.DataFrame(
        {
            "Артикул": ["A", "A"],
            "Име": ["a", "a"],
            "Наличност": [2, 5],
            "Годност": ["2027-01-01", "2028-01-01"],
            "Партида": ["L1", "L2"],
        }
    )
    orders_df = pd.DataFrame(
        {
            "Name": ["#1", "#1"],
            "Lineitem sku": ["A", "A"],
            "Lineitem quantity": [2, 1],
            "Shipping Method": ["DHL", "DHL"],
        }
    )
    from shopify_tool.analysis import run_analysis

    df, *_ = run_analysis(stock_df, orders_df, pd.DataFrame({"Order_Number": []}))
    pkl = tmp_path / "current_state.pkl"
    df.to_pickle(pkl)
    out = tmp_path / "export.xls"
    create_stock_export(pd.read_pickle(pkl), str(out))
    export = pd.read_excel(out, dtype=str)
    assert export["Брой"].astype(int).sum() == 3
    assert dict(zip(export["Партида"], export["Брой"].astype(int))) == {
        "L1": 2,
        "L2": 1,
    }
