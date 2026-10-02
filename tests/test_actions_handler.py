"""Regression test for gui.actions_handler.ActionsHandler.remove_item_from_order.

Root cause: the handler used to match rows by (Order_Number, SKU) alone, so an
order with two lines sharing the same SKU would have both lines deleted when
the user only meant to remove one. The fix threads the clicked row's position
through from the context menu and removes exactly that row.
"""

import time
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest
from PySide6.QtCore import QThreadPool

from gui.actions_handler import ActionsHandler
from gui.selection_helper import SelectionHelper
from shopify_tool import core


@pytest.fixture
def mw():
    df = pd.DataFrame(
        [
            {"Order_Number": "1001", "SKU": "SKU-A", "Lineitem_Quantity": 1},
            {"Order_Number": "1001", "SKU": "SKU-A", "Lineitem_Quantity": 2},
            {"Order_Number": "1001", "SKU": "SKU-B", "Lineitem_Quantity": 1},
        ]
    )
    return SimpleNamespace(
        analysis_results_df=df,
        undo_manager=Mock(),
        undo_last_operation=Mock(),
        save_session_state=Mock(),
        log_activity=Mock(),
        results_bridge=Mock(),
    )


def test_remove_item_removes_only_the_clicked_duplicate_sku_line(mw, monkeypatch):
    monkeypatch.setattr("gui.actions_handler.toast", Mock())
    handler = ActionsHandler(mw)

    handler.remove_item_from_order("1001", "SKU-A", row_position=1)

    remaining = mw.analysis_results_df
    assert len(remaining) == 2
    sku_a_rows = remaining[remaining["SKU"] == "SKU-A"]
    assert len(sku_a_rows) == 1
    assert sku_a_rows.iloc[0]["Lineitem_Quantity"] == 1


def test_remove_item_aborts_if_row_no_longer_matches(mw, monkeypatch):
    monkeypatch.setattr("gui.actions_handler.toast", Mock())
    handler = ActionsHandler(mw)

    # row_position 2 is SKU-B, not SKU-A -- table changed since menu opened
    handler.remove_item_from_order("1001", "SKU-A", row_position=2)

    assert len(mw.analysis_results_df) == 3


def test_remove_item_aborts_if_snapshot_no_longer_matches(mw, monkeypatch):
    """A same-position row can still match (Order_Number, SKU) after the table
    changes if another duplicate-SKU line has taken that slot. The row
    snapshot, captured in full when the menu opened, must catch this even
    when order/SKU alone would pass.
    """
    monkeypatch.setattr("gui.actions_handler.toast", Mock())
    handler = ActionsHandler(mw)

    stale_snapshot = {"Order_Number": "1001", "SKU": "SKU-A", "Lineitem_Quantity": 2}

    # row_position 0 is still Order 1001 / SKU-A, but with Lineitem_Quantity=1
    # now -- a different duplicate-SKU line than the one the snapshot captured.
    handler.remove_item_from_order(
        "1001", "SKU-A", row_position=0, row_snapshot=stale_snapshot
    )

    assert len(mw.analysis_results_df) == 3


@pytest.fixture
def mw_with_tags():
    df = pd.DataFrame(
        [
            {"Order_Number": "1001", "SKU": "A1", "Quantity": 1, "Internal_Tags": "[]"},
            {"Order_Number": "1001", "SKU": "A2", "Quantity": 1, "Internal_Tags": "[]"},
            {
                "Order_Number": "1002",
                "SKU": "B1",
                "Quantity": 1,
                "Internal_Tags": '["URGENT"]',
            },
        ]
    )
    mw = SimpleNamespace(
        analysis_results_df=df,
        undo_manager=Mock(),
        save_session_state=Mock(),
        log_activity=Mock(),
        active_profile_config={"tag_categories": {}},
        _update_all_views=Mock(),
    )
    mw.selection_helper = SelectionHelper(main_window=mw)
    return mw


def test_bulk_add_tag_writes_every_row_of_a_multi_line_order(mw_with_tags):
    handler = ActionsHandler(mw_with_tags)

    # order_numbers names the whole order; every one of its lines is written,
    # not just a line that happened to be checked before this bundle.
    handler.bulk_add_tag(["1001"], "FRAGILE")

    tags = mw_with_tags.analysis_results_df.set_index("SKU")["Internal_Tags"]
    assert '"FRAGILE"' in tags.loc["A1"]
    assert '"FRAGILE"' in tags.loc["A2"]  # order 1001's other line
    assert '"FRAGILE"' not in tags.loc["B1"]  # different order, untouched


def test_bulk_remove_tag_removes_from_every_row_of_a_multi_line_order(mw_with_tags):
    df = mw_with_tags.analysis_results_df
    df.loc[df["Order_Number"] == "1001", "Internal_Tags"] = '["URGENT"]'

    handler = ActionsHandler(mw_with_tags)

    handler.bulk_remove_tag(["1001"], "URGENT")

    tags = mw_with_tags.analysis_results_df.set_index("SKU")["Internal_Tags"]
    assert tags.loc["A1"] == "[]"
    assert tags.loc["A2"] == "[]"  # order 1001's other line, not just the checked one
    assert tags.loc["B1"] == '["URGENT"]'  # different order, untouched


@pytest.mark.parametrize(
    "stats, toasts", [({"history_warning": "History trouble."}, 1), ({}, 0)]
)
def test_on_analysis_complete_toasts_a_history_warning(monkeypatch, tmp_path, stats, toasts):
    monkeypatch.setattr("gui.actions_handler.toast", Mock())
    monkeypatch.setattr("shared.stats_manager.StatsManager.record_analysis", Mock())
    df = pd.DataFrame([{"Order_Number": "1001", "Order_Fulfillment_Status": "Fulfillable"}])
    mw = SimpleNamespace(
        session_path=None,
        current_client_id="M",
        active_profile_config={},
        profile_manager=SimpleNamespace(base_path=tmp_path),
        threadpool=QThreadPool(),
        log_activity=Mock(),
        update_ui_state=Mock(),
        results_bridge=Mock(),
    )
    ActionsHandler(mw).on_analysis_complete((True, "report.csv", df, stats))

    shown = [c.args[0] for c in mw.results_bridge.raise_toast.call_args_list]
    assert shown.count("History trouble.") == toasts
    mw.threadpool.waitForDone(2000)


def test_on_analysis_complete_reads_the_sessions_lots(monkeypatch, tmp_path):
    monkeypatch.setattr("gui.actions_handler.toast", Mock())
    monkeypatch.setattr("shared.stats_manager.StatsManager.record_analysis", Mock())
    lots = {"A": []}
    monkeypatch.setattr("gui.actions_handler.core.session_lot_table", lambda path, _config: lots)
    df = pd.DataFrame([{"Order_Number": "1001", "Order_Fulfillment_Status": "Fulfillable"}])
    mw = SimpleNamespace(
        session_path=None,
        current_client_id="M",
        active_profile_config={},
        profile_manager=SimpleNamespace(base_path=tmp_path),
        threadpool=QThreadPool(),
        log_activity=Mock(),
        update_ui_state=Mock(),
        results_bridge=Mock(),
    )
    ActionsHandler(mw).on_analysis_complete((True, "report.csv", df, {}))
    assert mw.lot_table is lots
    mw.threadpool.waitForDone(2000)


def test_on_analysis_complete_does_not_block_ui_thread_on_stats_recording(
    monkeypatch, tmp_path
):
    """Regression test for the analysis-run freeze (Todoist Track A).

    Root cause: StatsManager.record_analysis() performs blocking network I/O
    (file lock, read/write, fsync) over the UNC file share. on_analysis_complete
    is a Qt result-signal slot, so it always executes on the GUI thread --
    running that I/O inline froze the whole UI on every analysis run,
    regardless of batch size (the network round-trips are a fixed cost, not
    proportional to the data). The fix hands the stats write off to the
    existing background QThreadPool instead of calling it inline.
    """
    df = pd.DataFrame(
        [
            {"Order_Number": "1001", "Order_Fulfillment_Status": "Fulfillable"},
            {"Order_Number": "1002", "Order_Fulfillment_Status": "Fulfillable"},
            {"Order_Number": "1003", "Order_Fulfillment_Status": "Unfulfillable"},
        ]
    )

    calls = []

    def slow_record_analysis(self, **kwargs):
        time.sleep(0.3)  # stand-in for slow/contended UNC network I/O
        calls.append(kwargs)

    monkeypatch.setattr(
        "shared.stats_manager.StatsManager.record_analysis", slow_record_analysis
    )
    monkeypatch.setattr("gui.actions_handler.toast", Mock())

    mw = SimpleNamespace(
        session_path=str(tmp_path / "session_1"),
        current_client_id="M",
        active_profile_config={},
        profile_manager=SimpleNamespace(base_path=tmp_path),
        threadpool=QThreadPool(),
        log_activity=Mock(),
        update_ui_state=Mock(),
    )
    handler = ActionsHandler(mw)

    start = time.perf_counter()
    handler.on_analysis_complete((True, "report.csv", df, {}))
    elapsed = time.perf_counter() - start

    assert elapsed < 0.2, (
        f"on_analysis_complete blocked the calling thread for {elapsed:.3f}s -- "
        "statistics recording must be handed off to a background thread, not "
        "run inline in this Qt result-signal slot"
    )

    assert mw.threadpool.waitForDone(2000), "background stats worker never finished"
    assert len(calls) == 1
    assert calls[0]["client_id"] == "M"
    assert calls[0]["session_id"] == "session_1"
    assert calls[0]["orders_count"] == 3
    assert calls[0]["metadata"]["items_count"] == 3
    assert calls[0]["metadata"]["fulfillable_orders"] == 2


def test_removing_an_item_asks_nothing_and_offers_undo(mw, monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("an undoable removal must not confirm")

    # Patched on the class itself: actions_handler no longer imports it.
    monkeypatch.setattr("shared.components.confirm_dialog.ConfirmDialog.ask", refuse)

    ActionsHandler(mw).remove_item_from_order("1001", "SKU-A", row_position=1)

    # The Results screen's toast lives in the document (ADR 0007), not the
    # Qt-widget toast the rest of the app uses.
    mw.results_bridge.raise_toast.assert_called_once()
    assert "SKU-A" in mw.results_bridge.raise_toast.call_args.args[0]
    assert mw.results_bridge.raise_toast.call_args.kwargs["undoable"] is True


def test_settings_that_save_but_fail_to_reload_say_so(monkeypatch):
    headlines = []
    monkeypatch.setattr(
        "gui.actions_handler.show_error",
        lambda source, headline, what: headlines.append(headline),
    )
    monkeypatch.setattr(
        "gui.actions_handler.SettingsWindow",
        lambda **kwargs: SimpleNamespace(exec=lambda: True, deleteLater=lambda: None),
    )
    profile_manager = Mock()
    profile_manager.load_shopify_config.side_effect = [
        {"settings": {}},
        OSError("gone"),
    ]
    mw = SimpleNamespace(
        current_client_id="M",
        profile_manager=profile_manager,
        analysis_results_df=None,
        orders_file_path=None,
        stock_file_path=None,
    )

    ActionsHandler(mw).open_settings_window()

    assert headlines == ["Settings were saved but didn't reload"]


def test_the_settings_window_is_told_which_files_are_loaded(monkeypatch):
    seen = {}
    deleted = []

    def window(**kwargs):
        seen.update(kwargs)
        return SimpleNamespace(
            exec=lambda: False, deleteLater=lambda: deleted.append(True)
        )

    monkeypatch.setattr("gui.actions_handler.SettingsWindow", window)
    profile_manager = Mock()
    profile_manager.load_shopify_config.return_value = {"settings": {}}
    mw = SimpleNamespace(
        current_client_id="M",
        profile_manager=profile_manager,
        analysis_results_df=None,
        orders_file_path="/data/orders.csv",
        stock_file_path=None,
    )

    ActionsHandler(mw).open_settings_window(page="Orders mapping")

    assert seen["loaded_files"] == {"orders": "/data/orders.csv", "stock": None}
    assert seen["initial_page"] == "Orders mapping"
    # The main window is the dialog's parent: left alone, every open would
    # leave a dialog and its web view alive (ADR 0016).
    assert deleted == [True]


def test_the_writeoff_bypass_is_gone():
    import inspect

    from gui.report_selection_dialog import GenerateReportsDialog

    assert (
        "writeoff_handler"
        not in inspect.signature(GenerateReportsDialog.__init__).parameters
    )
    assert not hasattr(ActionsHandler, "generate_writeoff_report")


def _running_mw():
    return SimpleNamespace(
        _analysis_running=True,
        _analysis_step=1,
        _analysis_cancelling=False,
        command_bar=Mock(),
        ui_manager=Mock(),
        sync_inventory_memory=Mock(),
    )


def test_a_step_the_run_reports_reaches_the_bar_and_the_page():
    mw = _running_mw()
    handler = ActionsHandler(mw)

    handler._report_step(2)

    assert mw._analysis_step == 2
    mw.command_bar.set_step.assert_called_once_with(2, 4, "Allocating stock")
    mw.ui_manager.refresh_setup.assert_called_once()


def test_a_step_that_arrives_after_the_run_ended_is_ignored():
    mw = _running_mw()
    mw._analysis_running = False
    handler = ActionsHandler(mw)

    handler._report_step(3)

    assert mw._analysis_step == 1
    mw.command_bar.set_step.assert_not_called()


def test_cancel_stops_the_run_at_its_next_step():
    mw = _running_mw()
    handler = ActionsHandler(mw)

    handler.cancel_analysis()

    assert mw._analysis_cancelling is True
    mw.ui_manager.refresh_setup.assert_called_once()
    with pytest.raises(core.AnalysisCancelled):
        handler._report_step(2)


def test_cancel_pressed_twice_is_one_cancel():
    mw = _running_mw()
    handler = ActionsHandler(mw)
    handler.cancel_analysis()
    handler.cancel_analysis()
    mw.ui_manager.refresh_setup.assert_called_once()


def test_cancel_with_no_run_going_does_nothing():
    mw = _running_mw()
    mw._analysis_running = False
    handler = ActionsHandler(mw)

    handler.cancel_analysis()

    assert mw._analysis_cancelling is False
    mw.ui_manager.refresh_setup.assert_not_called()
    mw._analysis_running = True
    handler._report_step(0)  # the next run is not cancelled before it starts


def test_cancel_once_saving_has_begun_does_nothing():
    mw = _running_mw()
    mw._analysis_step = 3
    handler = ActionsHandler(mw)

    handler.cancel_analysis()

    assert mw._analysis_cancelling is False


def test_a_finished_run_leaves_no_cancel_behind():
    mw = _running_mw()
    handler = ActionsHandler(mw)
    handler.cancel_analysis()

    handler._on_analysis_finished()

    assert mw._analysis_running is False
    assert mw._analysis_cancelling is False
    mw._analysis_running = True
    handler._report_step(0)  # does not raise: the flag was cleared


def test_a_cancelled_result_is_a_toast_not_an_error(monkeypatch):
    said = Mock()
    failed = Mock()
    monkeypatch.setattr("gui.actions_handler.toast", said)
    monkeypatch.setattr("gui.actions_handler.show_error", failed)
    mw = _running_mw()
    handler = ActionsHandler(mw)

    handler.on_analysis_complete((False, core.CANCELLED, None, None))

    said.assert_called_once_with(mw, "Analysis cancelled")
    failed.assert_not_called()


def test_a_failed_result_is_still_an_error(monkeypatch):
    failed = Mock()
    monkeypatch.setattr("gui.actions_handler.show_error", failed)
    mw = _running_mw()
    handler = ActionsHandler(mw)

    handler.on_analysis_complete((False, "Validation error: no SKU", None, None))

    failed.assert_called_once()


def test_run_analysis_hands_the_run_its_progress_callback(monkeypatch):
    captured = {}

    def fake_worker(fn, *args, **kwargs):
        captured["fn"] = fn
        captured["kwargs"] = kwargs
        return Mock()

    monkeypatch.setattr("gui.actions_handler.Worker", fake_worker)
    mw = SimpleNamespace(
        session_path="/sessions/2026-09-30_1",
        current_client_id="acme",
        _analysis_running=False,
        _analysis_step=3,
        _analysis_cancelling=True,
        active_profile_config={},
        stock_file_path="/d/stock.csv",
        orders_file_path="/d/orders.csv",
        session_manager=Mock(),
        profile_manager=Mock(),
        threadpool=Mock(),
        command_bar=Mock(),
        ui_manager=Mock(),
    )
    handler = ActionsHandler(mw)

    handler.run_analysis()

    assert captured["fn"] is core.run_full_analysis
    assert captured["kwargs"]["progress"] == handler._report_step
    assert mw._analysis_running is True
    assert mw._analysis_step == 0
    assert mw._analysis_cancelling is False
    mw.command_bar.set_step.assert_called_once_with(0, 4, "Reading orders and stock")
    mw.threadpool.start.assert_called_once()
