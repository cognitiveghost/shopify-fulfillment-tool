"""The session loader applies automatic status updates before emitting."""
from unittest.mock import Mock

from gui.session_browser_widget import SessionLoaderWorker


def _old_session(name):
    return {
        "session_name": name,
        "status": "active",
        "created_at": "2026-07-01T09:00:00",
        "statistics": {"packing_lists": []},
    }


def test_applies_derived_updates_and_emits_the_new_status():
    manager = Mock()
    manager.list_client_sessions.return_value = [_old_session("2026-07-01_1")]
    worker = SessionLoaderWorker(manager, "M")
    emitted = []
    worker.finished_with_data.connect(emitted.append)

    worker.run()

    manager.apply_status_updates.assert_called_once_with("M", {"2026-07-01_1": "archived"})
    assert emitted[0][0]["status"] == "archived"


def test_no_changes_means_no_write():
    manager = Mock()
    manager.list_client_sessions.return_value = [
        {"session_name": "s", "status": "active", "created_at": "", "statistics": {"packing_lists": []}}
    ]
    worker = SessionLoaderWorker(manager, "M")

    worker.run()

    manager.apply_status_updates.assert_not_called()


def test_a_failing_write_still_emits_the_session_list():
    # A stale status is survivable; a session list that will not load is not.
    manager = Mock()
    manager.list_client_sessions.return_value = [_old_session("2026-07-01_1")]
    manager.apply_status_updates.side_effect = OSError("share unreachable")
    worker = SessionLoaderWorker(manager, "M")
    emitted = []
    worker.finished_with_data.connect(emitted.append)

    worker.run()

    assert len(emitted) == 1
    assert emitted[0][0]["session_name"] == "2026-07-01_1"


def test_cancelled_worker_does_not_write():
    manager = Mock()
    manager.list_client_sessions.return_value = [_old_session("2026-07-01_1")]
    worker = SessionLoaderWorker(manager, "M")
    worker._is_cancelled = True

    worker.run()

    manager.apply_status_updates.assert_not_called()
