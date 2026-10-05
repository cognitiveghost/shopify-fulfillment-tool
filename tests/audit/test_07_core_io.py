"""Audit 07: core path, multi-PC correctness and share I/O.

Report: docs/audit/07-core-io-review.md. Every AUDIT-07-k test fails because
of the finding it names and is marked xfail(strict=True); the fix removes the
marker. Unmarked tests pin what the audit verified correct. Fixtures are
synthetic (see conftest.py); no production data lives here.
"""

import copy
import json
import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest
from audit_support import (  # noqa: F401  pytest fixtures, used by name
    MAPPINGS,
    analysis_run_fixture,
    benchmark_frame_fixture,
    in_place_writes_fixture,
    sessions_fixture,
    timed,
)

import gui.main_window_pyside as main_window_module
import shopify_tool.profile_manager as profile_manager_module
from gui.main_window_pyside import MainWindow
from gui.session_write_queue import SessionWriteQueue
from shared.atomic_write import atomic_write_json
from shopify_tool import core, fulfillment_history, session_state
from shopify_tool.analysis import lot_table, run_analysis
from shopify_tool.profile_manager import ProfileManager

NO_HISTORY = pd.DataFrame({"Order_Number": []})


def _save_failure_reported(ok, stats):
    """The run failed, or it carries a save warning beside history_warning."""
    return not ok or any(
        key.endswith("_warning") and key != "history_warning" for key in (stats or {})
    )


@pytest.fixture
def profiles(tmp_path):
    ProfileManager._config_cache.clear()  # class-level; one test's PCs only
    pm = ProfileManager(base_path=str(tmp_path / "server"))
    pm.create_client_profile("X", "Client X")
    yield pm
    ProfileManager._config_cache.clear()


# --------------------------------------------------------------------------
# AUDIT-07-H1: a Setup toggle reverts other PCs' Settings changes
# --------------------------------------------------------------------------


def _pc_opening_client(pm):
    """One PC's MainWindow after it opened client X: the config as loaded then."""
    pc = SimpleNamespace(
        current_client_id="X",
        profile_manager=pm,
        active_profile_config=pm.load_shopify_config("X"),
        ui_manager=Mock(),
    )
    pc.sync_inventory_memory = lambda: MainWindow.sync_inventory_memory(pc)
    return pc


def _another_pc_adds_a_rule(base_path):
    pm_b = ProfileManager(base_path=base_path)
    config = pm_b.load_shopify_config("X")
    config.setdefault("rules", []).append({"name": "added on PC-B"})
    pm_b.save_shopify_config("X", config)


_SETUP_TOGGLES = [
    (lambda pc: MainWindow._on_inventory_memory_toggled(pc, True),
     lambda cfg: cfg["inventory_memory"]["enabled"] is True),
    (lambda pc: MainWindow._on_analysis_mode_changed(pc, "fifo"),
     lambda cfg: cfg["analysis_mode"] == "fifo"),
]
_SETUP_TOGGLE_IDS = ["inventory-memory-switch", "analysis-mode"]


@pytest.mark.parametrize("toggle, applied", _SETUP_TOGGLES, ids=_SETUP_TOGGLE_IDS)
def test_AUDIT_07_H1_a_setup_toggle_keeps_another_pcs_settings(profiles, toggle, applied):
    pc_a = _pc_opening_client(profiles)  # 08:00
    _another_pc_adds_a_rule(str(profiles.base_path))  # 10:00, PC-B

    toggle(pc_a)  # 11:00, PC-A

    on_disk = ProfileManager(base_path=str(profiles.base_path)).load_shopify_config("X")
    assert applied(on_disk)
    assert {"name": "added on PC-B"} in on_disk.get("rules", [])


@pytest.mark.parametrize("toggle, applied", _SETUP_TOGGLES, ids=_SETUP_TOGGLE_IDS)
def test_a_setup_toggle_refreshes_this_pcs_config(profiles, toggle, applied):
    """PC-A's own copy holds PC-B's rule too, so its next save keeps it."""
    pc_a = _pc_opening_client(profiles)
    _another_pc_adds_a_rule(str(profiles.base_path))

    toggle(pc_a)

    assert applied(pc_a.active_profile_config)
    assert {"name": "added on PC-B"} in pc_a.active_profile_config.get("rules", [])


@pytest.mark.parametrize("toggle, applied", _SETUP_TOGGLES, ids=_SETUP_TOGGLE_IDS)
def test_a_failed_toggle_leaves_this_pcs_config_alone(profiles, monkeypatch, toggle, applied):
    """The Setup page redraws from this copy: it must show what is on disk."""
    pc_a = _pc_opening_client(profiles)

    def locked_by_another_pc(path, *_args, **_kwargs):
        raise PermissionError(13, "being used by another process", str(path))

    monkeypatch.setattr(profile_manager_module, "atomic_write_json", locked_by_another_pc)
    monkeypatch.setattr(main_window_module, "toast", Mock())

    toggle(pc_a)

    assert not applied(pc_a.active_profile_config)
    main_window_module.toast.assert_called_once()


# --------------------------------------------------------------------------
# AUDIT-07-H2: each edit does six groups of share I/O on the GUI thread
# --------------------------------------------------------------------------


def test_AUDIT_07_H2_an_edit_returns_to_the_person_quickly(benchmark_frame, tmp_path, sessions, qapp):
    """Measured on local disk at 2.7-3.3 s per edit for the benchmark frame,
    before any share latency. Only current_state.pkl needs to be on the
    click (the report's fix direction; the owner decides the rest)."""
    df, stats = benchmark_frame
    pc = SimpleNamespace(
        session_path=sessions.create_session("M"),
        analysis_results_df=df.copy(),
        analysis_stats=dict(stats),
        session_manager=sessions,
        profile_manager=sessions.profile_manager,
        current_client_id="M",
        active_profile_config={},
        write_queue=SessionWriteQueue(),
    )
    MainWindow.save_session_state(pc)  # the run's own save; not timed
    pc.analysis_results_df.loc[0, "Order_Fulfillment_Status"] = "Not Fulfillable"

    seconds, _ = timed(lambda: MainWindow.save_session_state(pc))

    assert seconds < 1.0
    assert pc.write_queue.flush(timeout=30)
    history = fulfillment_history.load(fulfillment_history.history_path(pc.profile_manager, "M"))
    assert (history["Session"] == Path(pc.session_path).name).any()
    info = json.loads((Path(pc.session_path) / "session_info.json").read_text(encoding="utf-8"))
    assert session_state.order_counts(pc.analysis_results_df).items() <= info.items()


def test_a_run_drops_history_rows_of_deleted_sessions(sessions, analysis_run):
    """AUDIT-07-L1: only the run prunes, and only folders that are gone."""
    kept = Path(sessions.create_session("M"))
    path = sessions.create_session("M")
    history = fulfillment_history.history_path(sessions.profile_manager, "M")
    pd.DataFrame({"Order_Number": ["#8", "#9", "#7"], "Execution_Date": ["2026-01-01"] * 3,
                  "Session": ["gone", kept.name, ""]}).to_csv(history, index=False)
    ok, msg, _df, _stats = analysis_run(path)
    assert ok, msg
    rows = fulfillment_history.load(history)
    assert set(rows["Session"]) == {kept.name, "", Path(path).name}


def test_the_session_names_the_report_it_wrote(sessions, analysis_run):
    """AUDIT-07-L2."""
    path = sessions.create_session("M")
    assert analysis_run(path)[0]
    info = json.loads((Path(path) / "session_info.json").read_text(encoding="utf-8"))
    assert (Path(path) / info["analysis_report_path"]).exists()


def test_a_run_writes_no_excel_mirror(sessions, analysis_run):
    path = sessions.create_session("M")
    ok, msg, _df, _stats = analysis_run(path)
    assert ok, msg
    assert not (Path(path) / "analysis" / "current_state.xlsx").exists()


# --------------------------------------------------------------------------
# AUDIT-07-H3 / H4: the session index rescans the whole client tree
# --------------------------------------------------------------------------


def _client_with_sessions(sessions, n=3):
    for _ in range(n):
        sessions.create_session("A")
    return sessions.sessions_root / "CLIENT_A"


def _count_calls(monkeypatch, obj, name):
    calls = []
    real = getattr(obj, name)

    def counting(*args, **kwargs):
        calls.append(args)
        return real(*args, **kwargs)

    monkeypatch.setattr(obj, name, counting)
    return calls


def test_AUDIT_07_H3_a_stray_folder_does_not_force_rescans(sessions, monkeypatch):
    client_dir = _client_with_sessions(sessions)
    (client_dir / "stray_folder").mkdir()  # half-deleted session, manual archive
    scans = _count_calls(monkeypatch, sessions, "_scan_sessions")

    for _ in range(5):
        listed = sessions.list_client_sessions("A")

    assert len(listed) == 3
    assert len(scans) <= 1


def test_without_a_stray_folder_the_index_is_scanned_once(sessions, monkeypatch):
    _client_with_sessions(sessions)
    scans = _count_calls(monkeypatch, sessions, "_scan_sessions")
    for _ in range(5):
        sessions.list_client_sessions("A")
    assert len(scans) <= 1


def test_AUDIT_07_H4_a_packing_tool_write_refreshes_one_entry(sessions, monkeypatch):
    client_dir = _client_with_sessions(sessions)
    sessions.list_client_sessions("A")  # builds the index
    index_mtime = (client_dir / sessions.INDEX_FILENAME).stat().st_mtime

    # Packing Tool writes completed_orders into one session as temp + rename.
    packed = min(p for p in client_dir.iterdir() if p.is_dir())
    info = json.loads((packed / "session_info.json").read_text(encoding="utf-8"))
    info["completed_orders"] = ["#1001"]
    atomic_write_json(packed / "session_info.json", info)
    os.utime(packed, (index_mtime + 5, index_mtime + 5))

    reads = _count_calls(monkeypatch, sessions, "get_session_info")
    listed = sessions.list_client_sessions("A")

    by_name = {s["session_name"]: s for s in listed}
    assert by_name[packed.name].get("completed_orders") == ["#1001"]
    assert len(reads) <= 1


# --------------------------------------------------------------------------
# AUDIT-07-M1: lot (FIFO) allocation ignores negative stock rows
# --------------------------------------------------------------------------


def test_AUDIT_07_M1_a_lot_column_does_not_change_the_answer():
    """Either owner rule (net negatives against the oldest lots, or cap lot
    availability at the SKU total) gives both paths the same answer."""
    orders = pd.DataFrame(
        {"Name": ["#1001"], "Lineitem sku": ["A"], "Lineitem quantity": [9],
         "Shipping Method": ["DHL"], "Shipping Country": ["BG"]}
    )
    no_lots = pd.DataFrame({"Артикул": ["A", "A"], "Име": ["x", "x"], "Наличност": [10, -3]})
    lots = no_lots.assign(Годност=["2027-01-01", "2027-02-01"])

    def outcome(stock):
        row = run_analysis(stock, orders.copy(), NO_HISTORY)[0].iloc[0]
        return row["Order_Fulfillment_Status"], float(row["Stock"]), float(row["Final_Stock"])

    assert outcome(no_lots) == ("Not Fulfillable", 7.0, 7.0)
    assert outcome(lots) == outcome(no_lots)

    table = lot_table(pd.DataFrame({"SKU": ["A", "A"], "Stock": [10, -3],
                                    "Expiry_Date": ["2027-01-01", "2027-02-01"]}))
    assert [(lot["expiry"], lot["qty"]) for lot in table["A"]] == [("2027-01-01", 7.0)]


# --------------------------------------------------------------------------
# AUDIT-07-M2: the run's state files are written in place
# --------------------------------------------------------------------------


@pytest.mark.xfail(strict=True, reason="AUDIT-07-M2: to_pickle and open('w') on the share")
def test_AUDIT_07_M2_the_run_writes_its_state_files_atomically(
    sessions, analysis_run, in_place_writes
):
    path = sessions.create_session("M")
    in_place = in_place_writes("current_state.pkl", "analysis_data.json", "analysis_stats.json")

    ok, msg, _df, _stats = analysis_run(path)

    assert ok, msg
    assert in_place == []


# --------------------------------------------------------------------------
# AUDIT-07-M3: a failed state save still reports success
# --------------------------------------------------------------------------


@pytest.mark.xfail(strict=True, reason="AUDIT-07-M3: the save failure is logged and swallowed")
def test_AUDIT_07_M3_a_failed_state_save_is_reported(sessions, analysis_run):
    path = sessions.create_session("M")
    # A directory where the pickle goes: the write fails for real.
    (Path(path) / "analysis" / "current_state.pkl").mkdir(parents=True)

    ok, _msg, _df, stats = analysis_run(path)

    assert _save_failure_reported(ok, stats)


# --------------------------------------------------------------------------
# AUDIT-07-M4: the replace-retry window is shorter than a slow read
# --------------------------------------------------------------------------


@pytest.fixture
def held_by_a_reader(monkeypatch):
    """os.replace refuses for `seconds`, as Windows does while another PC
    reads the target without FILE_SHARE_DELETE, then succeeds."""

    def hold(seconds):
        real = os.replace
        until = time.monotonic() + seconds

        def replace(src, dst, *args, **kwargs):
            if time.monotonic() < until:
                raise PermissionError(13, "being used by another process", str(dst))
            return real(src, dst, *args, **kwargs)

        monkeypatch.setattr(os, "replace", replace)

    return hold


def _write_json(tmp_path):
    atomic_write_json(tmp_path / "x.json", {"a": 1})
    return json.loads((tmp_path / "x.json").read_text(encoding="utf-8")) == {"a": 1}


def _write_state(tmp_path):
    df = pd.DataFrame({"Order_Number": ["#1"]})
    session_state.save_state(tmp_path, df, session_state.state_stamp(tmp_path))
    return pd.read_pickle(tmp_path / "analysis" / "current_state.pkl").equals(df)


def _write_history(tmp_path):
    df = pd.DataFrame({"Order_Number": ["#1"], "Execution_Date": ["2026-10-05"], "Session": ["S"]})
    fulfillment_history._write_atomic(tmp_path / "h.csv", df)
    return pd.read_csv(tmp_path / "h.csv", dtype=str).equals(df)


@pytest.mark.xfail(strict=True, reason="AUDIT-07-M4: 3 x 0.15 s gives up before the reader is done")
@pytest.mark.parametrize(
    "write", [_write_json, _write_state, _write_history],
    ids=["atomic_write_json", "session_state.save_state", "fulfillment_history"],
)
def test_AUDIT_07_M4_a_write_outlasts_a_one_second_read(tmp_path, held_by_a_reader, write):
    held_by_a_reader(1.0)
    assert write(tmp_path)


# --------------------------------------------------------------------------
# AUDIT-07-M5: config backups rotate out after about 10 edits
# --------------------------------------------------------------------------


class _TickingClock(datetime):
    """One second passes per now(), so every backup gets its own name."""

    current = datetime(2026, 10, 5, 8, 0, 0, tzinfo=UTC)

    @classmethod
    def now(cls, tz=None):
        cls.current += timedelta(seconds=1)
        return cls.current if tz is None else cls.current.astimezone(tz)


def test_AUDIT_07_M5_a_settings_backup_survives_a_day_of_edits(profiles, monkeypatch):
    monkeypatch.setattr(profile_manager_module, "datetime", _TickingClock)
    config = profiles.load_shopify_config("X")
    config["rules"] = [{"name": "good"}]
    profiles.save_shopify_config("X", config)
    config = profiles.load_shopify_config("X")
    config["rules"] = [{"name": "bad"}]  # the Settings change to undo later
    profiles.save_shopify_config("X", config)

    for units in range(12):  # inventory memory follows each edit
        profiles.save_inventory_memory("X", {"A": units + 1}, session="S")

    backups = (profiles.clients_dir / "CLIENT_X" / "backups").glob("shopify_config_*.json")
    rules = [json.loads(b.read_text(encoding="utf-8")).get("rules") for b in backups]
    assert [{"name": "good"}] in rules


# --------------------------------------------------------------------------
# AUDIT-07-M6: the run mutates the GUI's column_mappings
# --------------------------------------------------------------------------


def test_AUDIT_07_M6_a_run_leaves_the_callers_column_mappings_alone(tmp_path):
    mappings = copy.deepcopy(MAPPINGS)
    config = {
        "column_mappings": mappings,
        "set_decoders": {"SET-1": [{"sku": "A", "quantity": 1}]},
        "test_stock_df": pd.DataFrame({"Артикул": ["A"], "Име": ["a"], "Наличност": [5]}),
        "test_orders_df": pd.DataFrame(
            {"Name": ["#1"], "Lineitem sku": ["SET-1"], "Lineitem quantity": [1],
             "Shipping Method": ["DHL"]}
        ),
    }

    ok, msg, _df, _stats = core.run_full_analysis(
        None, None, str(tmp_path), ",", ",", config
    )

    assert ok, msg
    assert config["column_mappings"] == MAPPINGS


# --------------------------------------------------------------------------
# AUDIT-07-M7: a failed migration save hides a readable config
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "file_name, dropped_key, load",
    [
        ("shopify_config.json", "inventory_memory", ProfileManager.load_shopify_config),
        ("client_config.json", "ui_settings", ProfileManager.load_client_config),
    ],
    ids=["shopify_config", "client_config"],
)
def test_AUDIT_07_M7_a_migration_that_cannot_save_still_returns_the_config(
    profiles, monkeypatch, file_name, dropped_key, load
):
    path = profiles.clients_dir / "CLIENT_X" / file_name
    data = json.loads(path.read_text(encoding="utf-8"))
    data.pop(dropped_key, None)  # an older file: its migration needs a save
    path.write_text(json.dumps(data), encoding="utf-8")
    ProfileManager._config_cache.clear()

    def locked_by_another_pc(*_args, **_kwargs):
        raise PermissionError(13, "being used by another process", str(path))

    monkeypatch.setattr(profile_manager_module, "atomic_write_json", locked_by_another_pc)

    config = load(profiles, "X")

    assert config is not None
    assert dropped_key in config  # migrated in memory

