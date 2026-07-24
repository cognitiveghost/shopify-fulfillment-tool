"""Session lifecycle & session_info.json accuracy (part of priority 6: app config)."""
from pathlib import Path

import pytest

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
