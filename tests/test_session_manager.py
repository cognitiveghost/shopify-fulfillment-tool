"""Session lifecycle & session_info.json accuracy (part of priority 6: app config)."""
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from shared.atomic_write import atomic_write_json
from shopify_tool.session_lifecycle import derive_status_updates
from shopify_tool.session_manager import SessionManager, SessionManagerError


@pytest.fixture
def session_manager(profile_manager):
    profile_manager.create_client_profile("M", "Test Client")
    return SessionManager(profile_manager)


class TestSessionCreation:
    def test_create_session_builds_expected_subdirs(self, session_manager):
        session_path = Path(session_manager.create_session("M"))
        for subdir in SessionManager.SESSION_SUBDIRS:
            assert (session_path / subdir).is_dir()
        assert (session_path / "session_info.json").exists()

    def test_create_session_for_unknown_client_raises(self, session_manager):
        with pytest.raises(SessionManagerError):
            session_manager.create_session("GHOST")

    def test_second_session_same_day_increments_suffix(self, session_manager):
        first = Path(session_manager.create_session("M"))
        second = Path(session_manager.create_session("M"))
        assert first != second
        n1 = int(first.name.rsplit("_", 1)[1])
        n2 = int(second.name.rsplit("_", 1)[1])
        assert n2 == n1 + 1

    def test_session_info_initial_status_is_active(self, session_manager):
        session_path = session_manager.create_session("M")
        info = session_manager.get_session_info(session_path)
        assert info["status"] == "active"
        assert info["client_id"] == "M"
        assert info["analysis_completed"] is False


class TestSessionInfoUpdates:
    def test_update_session_info_merges_fields(self, session_manager):
        session_path = session_manager.create_session("M")
        session_manager.update_session_info(session_path, {"comments": "hello"})
        info = session_manager.get_session_info(session_path)
        assert info["comments"] == "hello"
        assert info["status"] == "active"  # untouched fields survive

    def test_update_session_status_validates_status(self, session_manager):
        session_path = session_manager.create_session("M")
        assert session_manager.update_session_status(session_path, "completed") is True
        info = session_manager.get_session_info(session_path)
        assert info["status"] == "completed"

    def test_get_session_info_missing_file_returns_none(self, session_manager, tmp_path):
        empty_dir = tmp_path / "not_a_real_session"
        empty_dir.mkdir()
        assert session_manager.get_session_info(str(empty_dir)) is None


class TestDirectoryGetters:
    def test_subdirectory_getters_point_inside_session(self, session_manager):
        session_path = session_manager.create_session("M")
        assert session_manager.get_input_dir(session_path) == Path(session_path) / "input"
        assert session_manager.get_analysis_dir(session_path) == Path(session_path) / "analysis"
        assert session_manager.get_packing_lists_dir(session_path) == Path(session_path) / "packing_lists"
        assert session_manager.get_stock_exports_dir(session_path) == Path(session_path) / "stock_exports"


class TestAppendToSessionList:
    """append_to_session_list closes a race that survives update_session_info's
    own lock: two callers each reading a stale list via get_session_info and
    appending locally would still clobber each other on write."""

    def test_appends_new_value(self, session_manager):
        session_path = session_manager.create_session("M")
        assert session_manager.append_to_session_list(session_path, "packing_lists_generated", "a.xlsx") is True
        info = session_manager.get_session_info(session_path)
        assert info["packing_lists_generated"] == ["a.xlsx"]

    def test_duplicate_value_is_a_noop(self, session_manager):
        session_path = session_manager.create_session("M")
        session_manager.append_to_session_list(session_path, "packing_lists_generated", "a.xlsx")
        assert session_manager.append_to_session_list(session_path, "packing_lists_generated", "a.xlsx") is False
        info = session_manager.get_session_info(session_path)
        assert info["packing_lists_generated"] == ["a.xlsx"]

    def test_concurrent_appends_to_same_field_are_not_lost(self, session_manager):
        import threading

        session_path = session_manager.create_session("M")
        barrier = threading.Barrier(2)

        def _append(value):
            barrier.wait()
            session_manager.append_to_session_list(session_path, "packing_lists_generated", value)

        t1 = threading.Thread(target=_append, args=("a.xlsx",))
        t2 = threading.Thread(target=_append, args=("b.xlsx",))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        info = session_manager.get_session_info(session_path)
        assert set(info["packing_lists_generated"]) == {"a.xlsx", "b.xlsx"}


class TestConfirmedBugs:
    def test_two_interleaved_updates_do_not_lose_either_field(self, session_manager):
        import threading
        import time

        session_path = session_manager.create_session("M")

        # update_session_info() reads session_info.json, mutates in memory, then
        # writes it back -- with no lock spanning that read-modify-write. Widen
        # the window deterministically so two concurrent single-field updates
        # (exactly the pattern core.py uses for packing_lists_generated /
        # stock_exports_generated) actually interleave instead of serializing
        # by accident.
        original_get_info = session_manager.get_session_info

        def slow_get_info(path):
            info = original_get_info(path)
            time.sleep(0.05)
            return info

        barrier = threading.Barrier(2)

        def _update(field, value):
            session_manager.get_session_info = slow_get_info
            barrier.wait()
            session_manager.update_session_info(session_path, {field: value})

        t1 = threading.Thread(target=_update, args=("packing_lists_generated", ["dhl.xlsx"]))
        t2 = threading.Thread(target=_update, args=("stock_exports_generated", ["export.xls"]))
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        session_manager.get_session_info = original_get_info

        final = session_manager.get_session_info(session_path)
        assert final["packing_lists_generated"] == ["dhl.xlsx"]
        assert final["stock_exports_generated"] == ["export.xls"]

    def test_delete_session_refuses_path_outside_sessions_root(self, session_manager, tmp_path):
        outside_dir = tmp_path / "not_a_session"
        outside_dir.mkdir()
        (outside_dir / "important.txt").write_text("do not delete me")

        with pytest.raises(SessionManagerError):
            session_manager.delete_session(str(outside_dir))
        assert outside_dir.exists()


class TestSessionIndex:
    def test_create_session_adds_index_entry(self, session_manager):
        session_path = Path(session_manager.create_session("M"))
        index_path = session_path.parent / SessionManager.INDEX_FILENAME
        assert index_path.exists()
        entries = json.loads(index_path.read_text())
        assert len(entries) == 1
        assert entries[0]["session_name"] == session_path.name
        assert entries[0]["status"] == "active"
        assert "session_path" not in entries[0]

    def test_update_session_status_updates_index_entry(self, session_manager):
        session_path = session_manager.create_session("M")
        session_manager.update_session_status(session_path, "completed")
        index_path = Path(session_path).parent / SessionManager.INDEX_FILENAME
        entries = json.loads(index_path.read_text())
        assert entries[0]["status"] == "completed"

    def test_update_session_info_updates_index_entry(self, session_manager):
        session_path = session_manager.create_session("M")
        session_manager.update_session_info(session_path, {"comments": "hi"})
        index_path = Path(session_path).parent / SessionManager.INDEX_FILENAME
        entries = json.loads(index_path.read_text())
        assert entries[0]["comments"] == "hi"

    def test_append_to_session_list_updates_index_entry(self, session_manager):
        session_path = session_manager.create_session("M")
        session_manager.append_to_session_list(session_path, "packing_lists_generated", "a.xlsx")
        index_path = Path(session_path).parent / SessionManager.INDEX_FILENAME
        entries = json.loads(index_path.read_text())
        assert entries[0]["packing_lists_generated"] == ["a.xlsx"]

    def test_second_session_appends_not_replaces_index(self, session_manager):
        session_manager.create_session("M")
        second_path = Path(session_manager.create_session("M"))
        index_path = second_path.parent / SessionManager.INDEX_FILENAME
        entries = json.loads(index_path.read_text())
        assert len(entries) == 2

    def test_another_tools_write_to_a_session_is_picked_up(self, session_manager):
        """Packing Tool writes session_info.json and nothing else. The count
        is unchanged, so a count-only staleness check served the stale entry
        forever -- silently."""
        session_path = Path(session_manager.create_session("M"))
        client_sessions_dir = session_path.parent

        info = json.loads((session_path / "session_info.json").read_text())
        info["packing_progress"] = {"ALL": {"completed_orders": ["#A"]}}
        atomic_write_json(session_path / "session_info.json", info)
        # The index was written before that; pin the ordering so the test
        # doesn't depend on filesystem timestamp granularity.
        index_path = client_sessions_dir / SessionManager.INDEX_FILENAME
        stamp = session_path.stat().st_mtime - 10
        os.utime(index_path, (stamp, stamp))

        sessions = session_manager.list_client_sessions("M")
        assert sessions[0]["packing_progress"] == {"ALL": {"completed_orders": ["#A"]}}

    def test_own_writes_do_not_trigger_a_rebuild(self, session_manager):
        """The whole point of the index is that the UI doesn't walk the
        session tree. Every writer here updates the index *after* the
        session_info.json write it mirrors, so the index stays newer than
        the directory and the mtime check must stay quiet."""
        session_manager.create_session("M")
        session_path = session_manager.create_session("M")
        session_manager.update_session_status(session_path, "completed")
        session_manager.update_session_info(session_path, {"comments": "hi"})

        scans = []
        original_scan = session_manager._scan_sessions
        session_manager._scan_sessions = lambda d: scans.append(d) or original_scan(d)

        for _ in range(3):
            session_manager.list_client_sessions("M")

        assert scans == []

    def test_rebuild_index_scans_directory_and_writes_index(self, session_manager):
        session_path = Path(session_manager.create_session("M"))
        index_path = session_path.parent / SessionManager.INDEX_FILENAME
        index_path.unlink()  # simulate pre-existing sessions with no index yet
        entries = session_manager._rebuild_index(session_path.parent)
        assert len(entries) == 1
        assert entries[0]["session_name"] == session_path.name
        assert index_path.exists()

    def test_rebuild_holds_index_lock_across_scan_and_write(self, session_manager):
        """A rebuild that only locks the write (not the scan) can capture a
        stale snapshot and then overwrite a concurrent _upsert_index_entry()
        write with it once the lock is finally taken -- and the loser's data
        is gone until something else marks the index stale again. Proven
        directly: while the scan is in flight, a second lock attempt on the
        same file must not succeed.
        """
        import fcntl
        import threading

        session_path = Path(session_manager.create_session("M"))
        client_sessions_dir = session_path.parent
        index_path = client_sessions_dir / SessionManager.INDEX_FILENAME
        index_path.unlink()  # force list_client_sessions() to rebuild

        scan_started = threading.Event()
        release_scan = threading.Event()
        original_scan = session_manager._scan_sessions

        def blocking_scan(dir_path):
            entries = original_scan(dir_path)
            scan_started.set()
            release_scan.wait(timeout=2)
            return entries

        session_manager._scan_sessions = blocking_scan

        t1 = threading.Thread(target=lambda: session_manager.list_client_sessions("M"))
        t1.start()
        assert scan_started.wait(timeout=2), "rebuild's scan never started"

        lock_path = session_manager._index_lock_path(client_sessions_dir)
        with open(lock_path, "a+") as probe:
            with pytest.raises(BlockingIOError):
                fcntl.flock(probe.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(probe.fileno(), fcntl.LOCK_UN)

        release_scan.set()
        t1.join()
        session_manager._scan_sessions = original_scan

    def test_read_index_returns_none_when_missing(self, session_manager, tmp_path):
        empty_dir = tmp_path / "CLIENT_NOINDEX"
        empty_dir.mkdir()
        assert session_manager._read_index(empty_dir) is None

    def test_index_write_failure_does_not_break_session_update(self, session_manager, monkeypatch):
        session_path = session_manager.create_session("M")
        monkeypatch.setattr(
            session_manager, "_upsert_index_entry",
            lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")),
        )
        # The primary session_info.json write must still succeed even if the
        # index-cache update fails.
        assert session_manager.update_session_status(session_path, "completed") is True
        info = session_manager.get_session_info(session_path)
        assert info["status"] == "completed"


class TestListClientSessionsUsesIndex:
    def test_list_matches_previous_full_scan_output(self, session_manager):
        p1 = Path(session_manager.create_session("M"))
        session_manager.update_session_status(p1, "completed")
        p2 = session_manager.create_session("M")
        sessions = session_manager.list_client_sessions("M")
        assert len(sessions) == 2
        names = {s["session_name"] for s in sessions}
        assert names == {p1.name, Path(p2).name}
        # sorted newest first
        assert sessions[0]["created_at"] >= sessions[1]["created_at"]

    def test_status_filter_still_works(self, session_manager):
        p1 = Path(session_manager.create_session("M"))
        session_manager.update_session_status(p1, "completed")
        session_manager.create_session("M")
        active_only = session_manager.list_client_sessions("M", status_filter="active")
        assert len(active_only) == 1

    def test_missing_index_is_built_transparently(self, session_manager):
        session_path = Path(session_manager.create_session("M"))
        index_path = session_path.parent / SessionManager.INDEX_FILENAME
        index_path.unlink()  # simulate a client dir from before this feature
        sessions = session_manager.list_client_sessions("M")
        assert len(sessions) == 1
        assert index_path.exists()  # self-healed

    def test_manually_added_session_folder_triggers_rebuild(self, session_manager):
        session_path = Path(session_manager.create_session("M"))
        # Simulate a session folder restored/copied in without going through
        # create_session (index has no entry for it).
        extra = session_path.parent / "2020-01-01_1"
        extra.mkdir()
        for subdir in SessionManager.SESSION_SUBDIRS:
            (extra / subdir).mkdir()
        (extra / "session_info.json").write_text(json.dumps({
            "session_name": "2020-01-01_1", "status": "active",
            "created_at": "2020-01-01T00:00:00", "client_id": "M",
        }))
        sessions = session_manager.list_client_sessions("M")
        assert len(sessions) == 2  # count mismatch caught it, rebuilt

    def test_no_sessions_dir_returns_empty_list(self, session_manager):
        assert session_manager.list_client_sessions("M") == []


class TestBatchStatusUpdates:
    def test_applies_every_update_to_session_info(self, session_manager):
        first = Path(session_manager.create_session("M"))
        second = Path(session_manager.create_session("M"))

        applied = session_manager.apply_status_updates(
            "M", {first.name: "archived", second.name: "completed"}
        )

        assert applied == 2
        assert session_manager.get_session_info(str(first))["status"] == "archived"
        assert session_manager.get_session_info(str(second))["status"] == "completed"

    def test_rewrites_the_index_exactly_once(self, session_manager, monkeypatch):
        # The whole point of the batch path. A test that only checks the
        # resulting statuses passes just as happily with the per-session
        # implementation, which rewrites the entire index once per session.
        names = [Path(session_manager.create_session("M")).name for _ in range(3)]

        calls = []
        original = SessionManager._write_index
        def counting(self, client_sessions_dir, entries):
            calls.append(client_sessions_dir)
            return original(self, client_sessions_dir, entries)
        monkeypatch.setattr(SessionManager, "_write_index", counting)

        session_manager.apply_status_updates("M", dict.fromkeys(names, "archived"))

        assert len(calls) == 1

    def test_index_reflects_the_new_statuses(self, session_manager):
        session_path = Path(session_manager.create_session("M"))

        session_manager.apply_status_updates("M", {session_path.name: "archived"})

        sessions = session_manager.list_client_sessions("M")
        assert [s["status"] for s in sessions] == ["archived"]

    def test_one_bad_session_does_not_stop_the_others(self, session_manager):
        good = Path(session_manager.create_session("M"))

        applied = session_manager.apply_status_updates(
            "M", {"does_not_exist": "archived", good.name: "archived"}
        )

        assert applied == 1
        assert session_manager.get_session_info(str(good))["status"] == "archived"

    def test_empty_updates_writes_nothing(self, session_manager, monkeypatch):
        session_manager.create_session("M")
        monkeypatch.setattr(
            SessionManager, "_write_index",
            lambda *a, **k: pytest.fail("must not touch the index for an empty update set"),
        )
        assert session_manager.apply_status_updates("M", {}) == 0

    def test_invalid_status_is_skipped_not_raised(self, session_manager):
        session_path = Path(session_manager.create_session("M"))
        assert session_manager.apply_status_updates("M", {session_path.name: "bogus"}) == 0
        assert session_manager.get_session_info(str(session_path))["status"] == "active"

    def test_manual_flag_survives_a_batch_update(self, session_manager):
        session_path = Path(session_manager.create_session("M"))
        session_manager.update_session_status(str(session_path), "active", manual=True)

        session_manager.apply_status_updates("M", {session_path.name: "archived"})

        info = session_manager.get_session_info(str(session_path))
        assert info["status"] == "archived"
        assert info["status_manually_set"] is True

    def test_a_failed_index_rewrite_drops_the_index(self, session_manager, monkeypatch):
        # The write pass is only self-limiting while the index reflects it.
        # If the rewrite fails and the stale index survives, every refresh
        # re-derives and rewrites the same sessions forever.
        session_path = Path(session_manager.create_session("M"))
        index_path = session_path.parent / SessionManager.INDEX_FILENAME
        session_manager.list_client_sessions("M")
        assert index_path.exists()

        monkeypatch.setattr(
            SessionManager, "_write_index",
            lambda *a, **k: (_ for _ in ()).throw(OSError("share went away")),
        )
        session_manager.apply_status_updates("M", {session_path.name: "archived"})

        assert not index_path.exists()

    def test_derive_apply_reread_derive_is_a_fixed_point(self, session_manager):
        # The end-to-end idempotency the design relies on: after one pass
        # clears the backlog, later refreshes must derive nothing at all.
        session_path = Path(session_manager.create_session("M"))
        old = (datetime.now().astimezone() - timedelta(days=90)).isoformat()
        session_manager.update_session_info(str(session_path), {"created_at": old})

        now = datetime.now().astimezone()
        first = derive_status_updates(session_manager.list_client_sessions("M"), now)
        assert first == {session_path.name: "archived"}

        session_manager.apply_status_updates("M", first)

        assert derive_status_updates(session_manager.list_client_sessions("M"), now) == {}


class TestManualStatusFlag:
    def test_manual_update_records_the_flag(self, session_manager):
        session_path = session_manager.create_session("M")
        session_manager.update_session_status(session_path, "active", manual=True)
        assert session_manager.get_session_info(session_path)["status_manually_set"] is True

    def test_automatic_update_does_not_set_the_flag(self, session_manager):
        session_path = session_manager.create_session("M")
        session_manager.update_session_status(session_path, "completed")
        assert "status_manually_set" not in session_manager.get_session_info(session_path)
