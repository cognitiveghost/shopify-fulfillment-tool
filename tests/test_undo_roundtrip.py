"""Every undoable edit, made through the app's own handler and undone, gives back the frame it
started from; plus the history file's life cycle (Audit 10, part A)."""

import json
from pathlib import Path

import pandas as pd
import pytest
from test_stale_session import (  # noqa: F401  main_window is a fixture
    _open_with_state,
    main_window,
)

FRAME = pd.DataFrame({
    "Order_Number": ["#1001", "#1001", "#1002", "#1003"],
    "SKU": ["A", "B", "A", "C"], "Product_Name": ["PA", "PB", "PA", "PC"],
    "Quantity": [1, 2, 1, 3], "Stock": [10, 10, 10, 10],
    "Order_Fulfillment_Status": ["Fulfillable"] * 4,
    "Tags": ["", "", "VIP", ""], "Internal_Tags": ["[]", "[]", '["BOX"]', "[]"],
    "Status_Note": ["", "", "", ""],
})

EDITS = [
    ("toggle", lambda h: h.toggle_fulfillment_status_for_order("#1002")),
    ("bulk_status", lambda h: h.bulk_change_status(["#1001", "#1003"], False)),
    ("bulk_add_tag", lambda h: h.bulk_add_tag(["#1001", "#1003"], "BOX")),
    ("bulk_remove_tag", lambda h: h.bulk_remove_tag(["#1002"], "BOX")),
    ("add_internal_tag", lambda h: h.add_internal_tag("#1001", "BOX")),
    ("remove_internal_tag", lambda h: h.remove_internal_tag("#1002", "BOX")),
    ("remove_line", lambda h: h.remove_line("#1001", 1, "B")),
    ("change_quantity", lambda h: h.change_line_quantity("#1003", 0, "C", 1)),
    ("remove_order", lambda h: h.remove_entire_order("#1002")),
    ("bulk_remove_sku", lambda h: h.bulk_remove_sku_from_orders(["#1001", "#1002"], "A")),
    ("bulk_remove_orders_with_sku", lambda h: h.bulk_remove_orders_with_sku(["#1001", "#1002"], "A")),
    ("bulk_delete", lambda h: h.bulk_delete_orders(["#1003"])),
]
COMPARED = ["Order_Number", "SKU", "Quantity", "Order_Fulfillment_Status", "Tags", "Internal_Tags"]


@pytest.mark.parametrize(("name", "edit"), EDITS, ids=[e[0] for e in EDITS])
def test_undo_gives_back_the_frame_before_the_edit(main_window, name, edit):
    _open_with_state(main_window, FRAME)
    before = main_window.analysis_results_df[COMPARED].reset_index(drop=True).copy()
    edit(main_window.actions_handler)
    changed = main_window.analysis_results_df[COMPARED].reset_index(drop=True)
    assert not changed.equals(before), "the edit did nothing"
    ok, _ = main_window.undo_manager.undo()
    assert ok
    after = main_window.analysis_results_df[COMPARED].reset_index(drop=True)
    pd.testing.assert_frame_equal(after, before, check_dtype=False)


def _history_file(win):
    return Path(win.session_path) / "analysis" / f"operations_history_{_pc()}.json"


def _pc():
    from shopify_tool.undo_manager import _pc_name

    return _pc_name()


def _one_edit(win):
    win.actions_handler.bulk_change_status(["#1001"], False)
    assert win.write_queue.flush(timeout=10)


def test_nothing_to_undo_says_so(main_window):
    _open_with_state(main_window, FRAME)
    assert main_window.undo_manager.can_undo() is False
    assert main_window.undo_manager.get_undo_description() is None
    assert main_window.undo_manager.undo() == (False, "Nothing to undo")


def test_the_oldest_step_is_dropped_past_the_limit(main_window):
    _open_with_state(main_window, FRAME)
    um = main_window.undo_manager
    um.max_history = 3
    for n in range(5):
        um.record_operation("toggle_status", f"edit {n}", {"order_number": "#1001"}, FRAME.iloc[:1])
    assert [op["description"] for op in um.operations] == ["edit 2", "edit 3", "edit 4"]
    assert um.current_position == 3
    assert um.get_undo_description() == "edit 4"


def test_a_step_from_another_session_or_client_is_refused(main_window):
    _open_with_state(main_window, FRAME)
    um = main_window.undo_manager
    um.record_operation("toggle_status", "from elsewhere", {"order_number": "#1001"}, FRAME.iloc[:1])
    um.operations[-1]["session_path"] = "/somewhere/else"
    assert um.undo() == (False, "Cannot undo: operation from different session")
    um.operations[-1]["session_path"] = None
    um.operations[-1]["client_id"] = "OTHER"
    assert um.undo() == (False, "Cannot undo: operation from different client")


def test_an_unknown_operation_type_is_reported(main_window):
    _open_with_state(main_window, FRAME)
    um = main_window.undo_manager
    um.record_operation("teleport", "x", {}, FRAME.iloc[:1])
    assert um.undo() == (False, "Unknown operation type: teleport")
    assert um.current_position == 1  # nothing was undone


def test_history_survives_a_reload_of_the_session(main_window):
    _open_with_state(main_window, FRAME)
    _one_edit(main_window)
    assert _history_file(main_window).exists()
    um = main_window.undo_manager
    um.operations, um.current_position = [], 0
    um.reload_session_history()
    assert um.can_undo()
    assert um.get_undo_description().startswith("Bulk Change Status")


def test_a_corrupt_history_file_starts_empty(main_window, caplog):
    path = _open_with_state(main_window, FRAME)
    _history_file(main_window).write_text("{not json", encoding="utf-8")
    um = main_window.undo_manager
    with caplog.at_level("WARNING"):
        um.reload_session_history()
    assert um.operations == [] and um.current_position == 0
    assert any("Corrupted history file" in r.getMessage() for r in caplog.records)
    assert path  # the session itself is untouched


def test_another_pcs_history_is_not_offered_and_a_run_clears_it(main_window):
    path = _open_with_state(main_window, FRAME)
    other = Path(path) / "analysis" / "operations_history_OTHER-PC.json"
    other.parent.mkdir(exist_ok=True)
    other.write_text(json.dumps({"operations": [{"type": "toggle_status"}], "current_position": 1}),
                     encoding="utf-8")
    um = main_window.undo_manager
    um.reload_session_history()
    assert not um.can_undo()  # this PC has no file of its own
    um.clear_history()
    assert main_window.write_queue.flush(timeout=10)
    assert not other.exists()


def test_the_legacy_shared_history_is_read_when_this_pc_has_none(main_window):
    path = _open_with_state(main_window, FRAME)
    legacy = Path(path) / "analysis" / "operations_history.json"
    legacy.parent.mkdir(exist_ok=True)
    legacy.write_text(json.dumps({"operations": [{"type": "toggle_status", "description": "old build",
                                                  "params": {}, "affected_rows_before": []}],
                                  "current_position": 1}), encoding="utf-8")
    um = main_window.undo_manager
    um.reload_session_history()
    assert um.get_undo_description() == "old build"


def _old_build_step(win, op_type, params, rows):
    """A step as an older build wrote it: whole rows and no row_positions."""
    um = win.undo_manager
    um.operations.append({
        "id": len(um.operations) + 1, "timestamp": "2026-09-01T10:00:00+03:00", "type": op_type,
        "description": f"old {op_type}", "params": params,
        "affected_rows_before": rows.to_dict("records"), "stats_before": None,
        "client_id": win.current_client_id, "session_path": str(win.session_path),
    })
    um.current_position = len(um.operations)
    return um


def _statuses(win):
    df = win.analysis_results_df
    return dict(zip(df["Order_Number"] + "/" + df["SKU"], df["Order_Fulfillment_Status"], strict=True))


def test_an_older_toggle_step_restores_the_orders_status_by_order_number(main_window):
    _open_with_state(main_window, FRAME)
    main_window.analysis_results_df.loc[main_window.analysis_results_df["Order_Number"] == "#1001",
                                        "Order_Fulfillment_Status"] = "Not Fulfillable"
    um = _old_build_step(main_window, "toggle_status", {"order_number": "#1001"}, FRAME.iloc[:2])
    ok, message = um.undo()
    assert ok and message == "Undone: old toggle_status"
    assert set(_statuses(main_window).values()) == {"Fulfillable"}


def test_a_toggle_step_for_an_order_that_is_gone_fails_cleanly(main_window):
    _open_with_state(main_window, FRAME)
    um = _old_build_step(main_window, "toggle_status", {"order_number": "#9999"}, FRAME.iloc[:1])
    ok, message = um.undo()
    assert not ok and message == "Failed to undo: old toggle_status"
    assert um.current_position == 1


def test_an_older_bulk_status_step_restores_each_orders_status(main_window):
    _open_with_state(main_window, FRAME)
    df = main_window.analysis_results_df
    df["Order_Fulfillment_Status"] = "Not Fulfillable"
    um = _old_build_step(main_window, "bulk_change_status", {}, FRAME.iloc[[0, 3]])
    ok, _ = um.undo()
    assert ok
    statuses = _statuses(main_window)
    assert statuses["#1001/A"] == statuses["#1001/B"] == statuses["#1003/C"] == "Fulfillable"
    assert statuses["#1002/A"] == "Not Fulfillable"


def test_a_bulk_step_with_nothing_recorded_is_refused(main_window):
    _open_with_state(main_window, FRAME)
    um = _old_build_step(main_window, "bulk_change_status", {}, FRAME.iloc[:0])
    assert um.undo() == (False, "Failed to undo: old bulk_change_status")


@pytest.mark.parametrize("op_type", ["add_tag", "add_internal_tag", "remove_internal_tag"])
def test_an_older_tag_step_puts_the_orders_tags_back(main_window, op_type):
    _open_with_state(main_window, FRAME)
    column = "Status_Note" if op_type == "add_tag" else "Internal_Tags"
    main_window.analysis_results_df.loc[main_window.analysis_results_df["Order_Number"] == "#1001",
                                        column] = "CHANGED"
    um = _old_build_step(main_window, op_type, {"order_number": "#1001"}, FRAME.iloc[:2])
    ok, _ = um.undo()
    assert ok
    rows = main_window.analysis_results_df
    assert list(rows.loc[rows["Order_Number"] == "#1001", column]) == list(FRAME.iloc[:2][column])


@pytest.mark.parametrize("op_type", ["bulk_add_tag", "bulk_remove_tag"])
def test_an_older_bulk_tag_step_puts_each_orders_tags_back(main_window, op_type):
    _open_with_state(main_window, FRAME)
    main_window.analysis_results_df["Internal_Tags"] = '["X"]'
    um = _old_build_step(main_window, op_type, {}, FRAME)
    ok, _ = um.undo()
    assert ok
    assert list(main_window.analysis_results_df["Internal_Tags"]) == list(FRAME["Internal_Tags"])


@pytest.mark.parametrize(
    ("op_type", "params"),
    [("remove_item", {"order_number": "#1001", "sku": "B"}), ("remove_order", {"order_number": "#1001"}),
     ("bulk_remove_sku", {"sku": "A"}), ("bulk_remove_orders_with_sku", {"sku": "A"}),
     ("bulk_delete_orders", {})],
)
def test_an_older_removal_step_appends_the_rows_it_cannot_place(main_window, op_type, params):
    _open_with_state(main_window, FRAME)
    kept = main_window.analysis_results_df.iloc[2:].reset_index(drop=True)
    main_window.analysis_results_df = kept
    um = _old_build_step(main_window, op_type, params, FRAME.iloc[:2])
    ok, _ = um.undo()
    assert ok
    assert list(main_window.analysis_results_df["Order_Number"]) == ["#1002", "#1003", "#1001", "#1001"]


def test_a_change_quantity_step_it_cannot_place_fails(main_window):
    _open_with_state(main_window, FRAME)
    um = _old_build_step(main_window, "change_quantity", {"order_number": "#1003"}, FRAME.iloc[[3]])
    assert um.undo() == (False, "Failed to undo: old change_quantity")


def test_undo_restores_the_statistics_it_recorded(main_window):
    _open_with_state(main_window, FRAME)
    um = main_window.undo_manager
    main_window.analysis_stats = {"total_orders_analyzed": 3}
    main_window.actions_handler.bulk_change_status(["#1001"], False)
    main_window.analysis_stats = {"total_orders_analyzed": 99}
    ok, _ = um.undo()
    assert ok and main_window.analysis_stats == {"total_orders_analyzed": 3}
