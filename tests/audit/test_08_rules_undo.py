"""Audit 08: rule engine and undo.

Report: docs/audit/08-rules-undo-review.md. Every AUDIT-08-k test fails
because of the finding it names and is marked xfail(strict=True); the fix
removes the marker. Timing tests use the audit's benchmark frame (5,000
orders x 3 lines) with a generous ceiling, not a tight micro-benchmark.

U3 (untested undo and rule paths) is a coverage finding with no single
failing behaviour; the closing coverage PR (plan step 4) answers it.
"""

import logging
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest
from audit_support import (  # noqa: F401  pytest fixtures, used by name
    benchmark_frame_fixture,
    timed,
)

from gui.actions_handler import ActionsHandler
from gui.selection_helper import SelectionHelper
from shopify_tool.analysis import run_analysis
from shopify_tool.rules import RuleEngine
from shopify_tool.undo_manager import UndoManager

NO_HISTORY = pd.DataFrame({"Order_Number": []})


def _window(df, session_path=None):
    mw = SimpleNamespace(
        analysis_results_df=df,
        analysis_stats=None,
        save_session_state=Mock(),
        log_activity=Mock(),
        _update_all_views=Mock(),
        results_bridge=Mock(),
        ui_manager=Mock(),
        session_path=session_path,
        current_client_id="AUDIT",
        active_profile_config={"settings": {}},
    )
    mw.selection_helper = SelectionHelper(main_window=mw)
    mw.undo_manager = UndoManager(mw)
    return mw


# --------------------------------------------------------------------------
# AUDIT-08-U1: undo survives a re-run of the analysis
# --------------------------------------------------------------------------


@pytest.mark.xfail(strict=True, reason="AUDIT-08-U1: on_analysis_complete keeps the old history")
def test_AUDIT_08_U1_undo_after_a_rerun_does_not_duplicate_an_order(tmp_path):
    orders = pd.DataFrame(
        {"Name": ["#1", "#2", "#3"], "Lineitem sku": ["A", "B", "A"],
         "Lineitem quantity": [1, 1, 1], "Shipping Method": ["DHL"] * 3,
         "Shipping Country": ["BG"] * 3}
    )
    stock = pd.DataFrame({"Артикул": ["A", "B"], "Име": ["a", "b"], "Наличност": [5, 5]})
    mw = _window(run_analysis(stock, orders, NO_HISTORY)[0], session_path=str(tmp_path))
    handler = ActionsHandler(mw)
    handler._record_analysis_stats_async = Mock()  # the server stats file

    # The person removes order #2, recorded as remove_entire_order records it.
    mask = mw.analysis_results_df["Order_Number"] == "#2"
    mw.undo_manager.record_operation(
        "remove_order", "Removed order #2", {"order_number": "#2"},
        mw.analysis_results_df[mask].copy(),
    )
    mw.analysis_results_df = mw.analysis_results_df[~mask].reset_index(drop=True)

    # Then re-runs the analysis on the same orders file, in the same session.
    rerun_df, rerun_stats = run_analysis(stock, orders, NO_HISTORY)
    handler.on_analysis_complete((True, str(tmp_path), rerun_df, rerun_stats))
    if mw.undo_manager.can_undo():
        mw.undo_manager.undo()

    assert int((mw.analysis_results_df["Order_Number"] == "#2").sum()) == 1


# --------------------------------------------------------------------------
# AUDIT-08-R1: order-level rules loop over orders in Python
# --------------------------------------------------------------------------


def _apply(df, rule):
    frame = df.copy()
    seconds, out = timed(lambda: RuleEngine([rule]).apply(frame))
    return seconds, out


@pytest.mark.xfail(strict=True, reason="AUDIT-08-R1: orders x rules x steps in Python")
@pytest.mark.parametrize(
    "condition, tagged",
    [
        ({"field": "item_count", "operator": "is greater than", "value": "1"}, True),
        ({"field": "has_sku", "operator": "equals", "value": "Z"}, False),
    ],
    ids=["every-order-matches", "no-order-matches"],
)
def test_AUDIT_08_R1_an_order_rule_runs_in_well_under_a_second(
    benchmark_frame, condition, tagged
):
    """Audit: 8.0 s and 2.3 s on the benchmark frame."""
    rule = {"name": "o", "level": "order", "conditions": [condition],
            "actions": [{"type": "ADD_TAG", "value": "audit"}]}

    seconds, out = _apply(benchmark_frame[0], rule)

    assert out["Status_Note"].fillna("").str.contains("audit").all() == tagged
    assert seconds < 0.5


# --------------------------------------------------------------------------
# AUDIT-08-R2: date operators parse cell by cell
# --------------------------------------------------------------------------


@pytest.mark.xfail(strict=True, reason="AUDIT-08-R2: six to_datetime calls per cell")
def test_AUDIT_08_R2_a_date_condition_runs_in_well_under_a_second(benchmark_frame):
    """Audit: 3.45 s for one condition on a Shopify `Created at` column."""
    df = benchmark_frame[0].assign(Created_At="2026-10-01 10:00:00 +0200")
    rule = {"name": "d", "level": "article",
            "conditions": [{"field": "Created_At", "operator": "date before", "value": "2026-10-02"}],
            "actions": [{"type": "ADD_TAG", "value": "old"}]}

    seconds, out = _apply(df, rule)

    assert out["Status_Note"].fillna("").str.contains("old").all()
    assert seconds < 0.5


@pytest.mark.xfail(strict=True, reason="AUDIT-08-R2: one WARNING per unparseable cell")
def test_AUDIT_08_R2_a_bad_date_column_logs_one_line(benchmark_frame, caplog):
    df = benchmark_frame[0].head(1000).copy()
    df["Created_At"] = [f"not a date {i}" for i in range(len(df))]
    rule = {"name": "d", "level": "article",
            "conditions": [{"field": "Created_At", "operator": "date before", "value": "2026-10-02"}],
            "actions": [{"type": "ADD_TAG", "value": "old"}]}

    with caplog.at_level(logging.WARNING, logger="shopify_tool.rules"):
        out = RuleEngine([rule]).apply(df)

    assert not out["Status_Note"].fillna("").str.contains("old").any()
    assert len([r for r in caplog.records if r.levelno >= logging.WARNING]) <= 1


# --------------------------------------------------------------------------
# AUDIT-08-U2: undo records store whole rows
# --------------------------------------------------------------------------


@pytest.mark.xfail(strict=True, reason="AUDIT-08-U2: every column of every affected row")
def test_AUDIT_08_U2_one_bulk_status_change_keeps_the_history_small(benchmark_frame, tmp_path):
    """Audit: about 9.9 MB for 6,000 lines x 44 columns, rewritten on every
    edit and undo. Changed columns plus positions fit in well under 2 MB."""
    df = benchmark_frame[0].head(6000).copy()
    for c in range(44 - df.shape[1]):
        df[f"Extra_{c}"] = "some text value"
    assert df.shape == (6000, 44)
    mw = _window(df, session_path=str(tmp_path))

    ActionsHandler(mw).bulk_change_status(df["Order_Number"].unique().tolist(), False)

    history = tmp_path / "analysis" / "operations_history.json"
    assert (mw.analysis_results_df["Order_Fulfillment_Status"] == "Not Fulfillable").all()
    assert mw.undo_manager.can_undo()
    assert history.stat().st_size < 2_000_000
