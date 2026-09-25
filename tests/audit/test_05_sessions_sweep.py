"""Audit 05: session browser, session lifecycle, and the whole-app sweep.

Report: docs/audit/05-sessions-sweep.md. Every AUDIT-05-k test fails because
of the bug it names and is marked xfail(strict=True); the fix removes the
marker. The unmarked tests pin what the audit verified correct. Fixtures are
synthetic and only reproduce the shape of the production data.
"""

from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest
from PySide6.QtWidgets import QApplication

import gui.main_window_pyside as main_window_module
import gui.session_browser_widget as browser_module
from gui.main_window_pyside import MainWindow
from shared.atomic_write import atomic_write_json
from shared.file_lock import FileLockError, locked_file
from shopify_tool import session_lifecycle
from shopify_tool.session_manager import SessionManager, SessionManagerError


class _Profiles:
    """The three ProfileManager calls SessionManager makes."""

    def __init__(self, root):
        self.root = root

    def get_sessions_root(self):
        return self.root

    def client_exists(self, client_id):
        return True

    def invalidate_metadata_cache(self, client_id):
        pass


@pytest.fixture
def sessions(tmp_path):
    return SessionManager(_Profiles(tmp_path / "Sessions"))


def _orders(*statuses):
    """One line per order, numbered 1001 up, with the given statuses."""
    return pd.DataFrame(
        {
            "Order_Number": [f"#{1001 + i}" for i in range(len(statuses))],
            "SKU": [f"SKU-{i}" for i in range(len(statuses))],
            "Quantity": [1] * len(statuses),
            "Order_Fulfillment_Status": list(statuses),
        }
    )


def _pc(session_path, df, session_manager=None):
    """What save_session_state and _load_session_analysis read off a window.

    Both are plain methods over four attributes, so a namespace stands in for
    one PC's MainWindow without building the whole window twice.
    """
    return SimpleNamespace(
        session_path=str(session_path),
        analysis_results_df=None if df is None else df.copy(),
        analysis_stats={"total_orders_completed": 0},
        session_manager=session_manager,
    )


def _open_on_a_pc(session_path):
    """One PC opening the session: the loaded namespace, stamp included."""
    pc = _pc(session_path, None)
    assert MainWindow._load_session_analysis(pc, session_path)
    return pc


def _reopen(session_path):
    return _open_on_a_pc(session_path).analysis_results_df


# --------------------------------------------------------------------------
# AUDIT-05-1: a session-name collision deletes the other PC's session
# --------------------------------------------------------------------------


def test_a_session_name_another_pc_just_took_is_never_deleted(sessions, monkeypatch):
    # PC A created today's session a moment ago and copied its inputs in.
    other = sessions.create_session("M")
    (sessions.get_input_dir(other) / "orders_export.csv").write_text("Name\n#1001\n")
    # PC B's listing of the share is a few seconds old (SMB caches directory
    # listings), so it derives the same name A just used.
    monkeypatch.setattr(
        sessions, "_generate_unique_session_name", lambda _dir: Path(other).name
    )

    try:
        sessions.create_session("M")
    except SessionManagerError:
        pass  # refusing is fine; deleting A's session is not

    assert (Path(other) / "input" / "orders_export.csv").exists()
    assert sessions.get_session_info(other) is not None


def test_a_second_session_the_same_day_takes_the_next_number(sessions):
    first = sessions.create_session("M")
    second = sessions.create_session("M")
    assert first.endswith("_1") and second.endswith("_2")
    assert sessions.get_session_info(first) is not None


# --------------------------------------------------------------------------
# AUDIT-05-2: opening another session keeps the previous session's orders
# --------------------------------------------------------------------------


@pytest.fixture
def main_window(tmp_path, monkeypatch, qapp):
    monkeypatch.setenv("FULFILLMENT_SERVER_PATH", str(tmp_path))
    monkeypatch.setattr(browser_module.SessionBrowserWidget, "USE_ASYNC", False)
    win = MainWindow()
    win.resize(1100, 900)
    win.show()
    QApplication.processEvents()
    win.profile_manager.create_client_profile("acme", "Client Acme")
    win.current_client_id = "acme"
    win.load_client_config("acme")
    yield win
    win.close()


def _session_with_analysis(win, df):
    path = win.session_manager.create_session("acme")
    MainWindow.save_session_state(_pc(path, df))
    return path


def test_opening_a_session_without_analysis_drops_the_previous_orders(main_window):
    first = _session_with_analysis(main_window, _orders("Fulfillable", "Fulfillable"))
    main_window.load_existing_session(first)
    assert main_window.analysis_results_df is not None  # precondition

    second = main_window.session_manager.create_session("acme")
    main_window.load_existing_session(second)

    # Any edit now saves through save_session_state into the second session.
    main_window.save_session_state()
    assert not (main_window.session_manager.get_analysis_dir(second) / "current_state.pkl").exists()
    assert main_window.analysis_results_df is None


def test_a_new_session_starts_without_the_previous_orders(main_window):
    first = _session_with_analysis(main_window, _orders("Fulfillable"))
    main_window.load_existing_session(first)
    assert main_window.analysis_results_df is not None  # precondition

    main_window.actions_handler.create_new_session()

    assert main_window.session_path != first
    assert main_window.analysis_results_df is None


def test_opening_a_session_writes_nothing_into_it(main_window):
    """Production check: 39 sessions opened, none modified by the open itself."""
    path = _session_with_analysis(main_window, _orders("Fulfillable", "Not Fulfillable"))
    root = main_window.session_manager.get_session_path("acme", Path(path).name)
    before = {p: p.stat().st_mtime_ns for p in root.rglob("*") if p.is_file()}

    main_window.load_existing_session(path)

    after = {p: p.stat().st_mtime_ns for p in root.rglob("*") if p.is_file()}
    assert after == before
    assert len(main_window.analysis_results_df) == 2


# --------------------------------------------------------------------------
# AUDIT-05-3: two PCs on one session -- the last save wins, silently
# --------------------------------------------------------------------------


def test_a_hold_made_on_one_pc_survives_a_save_from_another(sessions, monkeypatch):
    told = []
    monkeypatch.setattr(main_window_module, "show_error", lambda *a, **k: told.append(a))
    path = sessions.create_session("M")
    MainWindow.save_session_state(_pc(path, _orders("Fulfillable", "Fulfillable")))

    pc_a = _open_on_a_pc(path)
    pc_b = _open_on_a_pc(path)

    pc_a.analysis_results_df.loc[0, "Order_Fulfillment_Status"] = "Not Fulfillable"
    MainWindow.save_session_state(pc_a)  # PC A holds #1001
    pc_b.analysis_results_df.loc[1, "Order_Fulfillment_Status"] = "Not Fulfillable"
    MainWindow.save_session_state(pc_b)  # PC B holds #1002, unaware of A

    saved = _reopen(path).set_index("Order_Number")["Order_Fulfillment_Status"]
    assert saved["#1001"] == "Not Fulfillable"
    assert told and told[-1][1] == "Another PC changed this session"


def test_one_pc_reopening_its_session_gets_its_last_save(sessions):
    path = sessions.create_session("M")
    pc = _pc(path, _orders("Fulfillable", "Fulfillable"))
    MainWindow.save_session_state(pc)
    pc.analysis_results_df.loc[0, "Order_Fulfillment_Status"] = "Not Fulfillable"
    MainWindow.save_session_state(pc)

    assert _reopen(path)["Order_Fulfillment_Status"].tolist() == [
        "Not Fulfillable",
        "Fulfillable",
    ]


# --------------------------------------------------------------------------
# AUDIT-05-4: session_info.json is rewritten in place
# --------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason="AUDIT-05-4: a failed session_info.json write leaves it torn and the session unreadable",
)
def test_a_failed_session_info_write_keeps_the_old_file(sessions):
    path = sessions.create_session("M")
    # object() stands in for any failure after the first byte is written: a
    # dropped SMB connection, a full disk. json.dump streams, so the file is
    # already truncated when it fails.
    with pytest.raises(SessionManagerError):
        sessions.update_session_info(path, {"comments": object()})

    assert sessions.get_session_info(path) is not None


def test_bulk_status_updates_write_atomically(sessions, monkeypatch):
    """apply_status_updates (the auto-archive pass) already uses atomic_write_json."""
    path = sessions.create_session("M")
    name = Path(path).name

    def fail(*_args, **_kwargs):
        raise OSError("share went away")

    monkeypatch.setattr("shopify_tool.session_manager.atomic_write_json", fail)
    assert sessions.apply_status_updates("M", {name: "archived"}) == 0
    assert sessions.get_session_info(path)["status"] == "active"


def test_packing_tools_lock_excludes_our_session_info_writes(sessions):
    """Packing Tool's update_session_metadata takes locked_file on the same
    sidecar (packing_tool/session_manager.py), so the read-modify-write race
    the apply_status_updates docstring still describes is closed."""
    path = sessions.create_session("M")
    lock = sessions.get_session_path("M", Path(path).name) / "session_info.json.lock"
    with (
        sessions._locked_session_info(lock.parent),
        open(lock, "a+") as handle,
        pytest.raises(FileLockError),
        locked_file(handle, timeout=0.2),
    ):
        pass


# --------------------------------------------------------------------------
# AUDIT-05-5: a failed save of a person's edits is only logged
# --------------------------------------------------------------------------


def test_a_failed_save_of_an_edit_reaches_the_person(sessions, monkeypatch):
    path = sessions.create_session("M")
    told = []
    monkeypatch.setattr(main_window_module, "show_error", lambda *a, **k: told.append(a))
    monkeypatch.setattr(main_window_module, "toast", lambda *a, **k: told.append(a))

    def share_went_away(*_args, **_kwargs):
        raise OSError("The specified network name is no longer available")

    monkeypatch.setattr(pd.DataFrame, "to_pickle", share_went_away)

    try:
        MainWindow.save_session_state(_pc(path, _orders("Not Fulfillable")))
    except Exception:
        told.append("raised")

    assert told


# --------------------------------------------------------------------------
# AUDIT-05-6: the browser's Blocked count never sees a person's edits
# --------------------------------------------------------------------------


def test_blocked_count_follows_edits(sessions):
    path = sessions.create_session("M")
    sessions.update_session_info(
        path, {"total_orders": 2, "fulfillable_orders": 1, "not_fulfillable_orders": 1}
    )
    # A person marks the blocked order fulfillable, which saves the session.
    MainWindow.save_session_state(
        _pc(path, _orders("Fulfillable", "Fulfillable"), session_manager=sessions)
    )

    assert session_lifecycle.blocked_orders(sessions.get_session_info(path)) == 0


def test_status_derivation_matches_the_production_shapes():
    """The four shapes production's 39 sessions take, as the browser shows them."""
    now = datetime(2026, 7, 24, 18, 0).astimezone()
    stamp = (now - timedelta(days=2)).isoformat()
    old = (now - timedelta(days=9)).isoformat()

    def entry(name, lists, progress, created=stamp):
        return {
            "session_name": name,
            "status": "active",
            "created_at": created,
            "statistics": {"packing_lists": lists},
            "packing_progress": progress,
        }

    entries = [
        entry("packed", ["DHL"], {"DHL": {"status": "completed", "updated_at": stamp}}),
        entry("untouched", ["DHL"], {}),
        entry("no-lists", [], {}),
        entry("idle", ["DHL"], {"DHL": {"status": "in_progress", "updated_at": old}}, old),
    ]
    updates = session_lifecycle.derive_status_updates(entries, now)
    for e in entries:
        e["status"] = updates.get(e["session_name"], e["status"])

    assert [session_lifecycle.display_status(e, now) for e in entries] == [
        "completed",
        "not_started",
        "not_started",
        "stale",
    ]
    # Thirty days on, the automation archives all four.
    later = now + timedelta(days=31)
    assert set(session_lifecycle.derive_status_updates(entries, later).values()) == {
        "archived"
    }


# --------------------------------------------------------------------------
# AUDIT-05-7: a comment that fails to save is only logged
# --------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason="AUDIT-05-7: a session comment that fails to save is dropped without telling anyone",
)
def test_a_comment_that_fails_to_save_is_reported(qapp, monkeypatch):
    manager = Mock()
    manager.update_session_info.side_effect = OSError("share went away")
    told = []
    monkeypatch.setattr(browser_module, "show_error", lambda *a, **k: told.append(a))

    widget = browser_module.SessionBrowserWidget(manager)
    widget._on_comments_changed("/share/Sessions/CLIENT_M/2026-07-01_1", "call courier")

    assert told


# --------------------------------------------------------------------------
# AUDIT-05-8 (shared/, packing-tool): atomic_write_json closes its fd twice
# --------------------------------------------------------------------------


def test_atomic_write_reports_the_real_error(tmp_path):
    with pytest.raises(TypeError):
        atomic_write_json(tmp_path / "x.json", {"a": object()}, retries=1)
