"""Session browser's 30-day default view filter (no Qt needed — pure data)."""
from datetime import datetime, timedelta

from gui.session_browser_widget import filter_sessions_by_age


def _session(days_old: int) -> dict:
    created = (datetime.now().astimezone() - timedelta(days=days_old)).isoformat()
    return {"session_name": f"session_{days_old}d", "created_at": created}


class TestFilterSessionsByAge:
    def test_keeps_sessions_within_cutoff(self):
        sessions = [_session(5), _session(10)]
        result = filter_sessions_by_age(sessions, cutoff_days=30, now=datetime.now().astimezone())
        assert len(result) == 2

    def test_drops_sessions_older_than_cutoff(self):
        sessions = [_session(5), _session(45)]
        result = filter_sessions_by_age(sessions, cutoff_days=30, now=datetime.now().astimezone())
        assert len(result) == 1
        assert result[0]["session_name"] == "session_5d"

    def test_missing_created_at_is_kept_not_dropped(self):
        # Never hide a session just because its date couldn't be parsed --
        # that would silently disappear real data from the default view.
        sessions = [{"session_name": "no_date"}]
        result = filter_sessions_by_age(sessions, cutoff_days=30, now=datetime.now().astimezone())
        assert len(result) == 1

    def test_cutoff_none_returns_all_sessions(self):
        sessions = [_session(5), _session(400)]
        result = filter_sessions_by_age(sessions, cutoff_days=None, now=datetime.now().astimezone())
        assert len(result) == 2
