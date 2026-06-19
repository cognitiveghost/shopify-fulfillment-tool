"""Unit tests for SessionManager — PostgreSQL backend.

Tests cover:
- Session creation with unique naming
- Session directory structure
- Session metadata management
- Session listing and filtering
- Session status updates
- Session info updates
- Session subdirectory access
- Error handling
"""

import shutil
import tempfile
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from shopify_tool.db_manager import get_db
from shopify_tool.profile_manager import ProfileManager
from shopify_tool.session_manager import SessionManager, SessionManagerError


# ── DB isolation helpers ────────────────────────────────────────────────────

_TEST_CLIENTS = ["M", "A", "B", "TESTONLY"]


def _delete_test_clients():
    db = get_db()
    for cid in _TEST_CLIENTS:
        try:
            db.execute("DELETE FROM sessions WHERE client_id = %s", (cid,))
            db.execute("DELETE FROM clients WHERE client_id = %s", (cid,))
        except Exception:
            pass


@pytest.fixture(autouse=True)
def clean_db():
    """Remove test client data from DB before and after each test."""
    _delete_test_clients()
    yield
    _delete_test_clients()


# ── Common fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def temp_base_path():
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def profile_manager(temp_base_path):
    return ProfileManager(str(temp_base_path))


@pytest.fixture
def session_manager(profile_manager):
    return SessionManager(profile_manager)


@pytest.fixture
def client_with_profile(profile_manager):
    profile_manager.create_client_profile("M", "M Cosmetics")
    return "M"


# ── Session creation ────────────────────────────────────────────────────────


class TestSessionCreation:
    def test_create_session_success(self, session_manager, client_with_profile):
        session_path = session_manager.create_session(client_with_profile)

        assert session_path is not None
        p = Path(session_path)
        assert p.exists()
        assert (p / "input").exists()
        assert (p / "analysis").exists()
        assert (p / "packing_lists").exists()
        assert (p / "stock_exports").exists()

    def test_create_session_nonexistent_client(self, session_manager):
        with pytest.raises(SessionManagerError) as exc_info:
            session_manager.create_session("NONEXISTENT")
        assert "does not exist" in str(exc_info.value)

    def test_session_name_format(self, session_manager, client_with_profile):
        session_path = session_manager.create_session(client_with_profile)
        session_name = Path(session_path).name
        parts = session_name.split("_")

        assert len(parts) == 2
        assert parts[1].isdigit()
        datetime.strptime(parts[0], "%Y-%m-%d")  # raises ValueError if wrong

    def test_multiple_sessions_same_day(self, session_manager, client_with_profile):
        s1 = session_manager.create_session(client_with_profile)
        s2 = session_manager.create_session(client_with_profile)
        s3 = session_manager.create_session(client_with_profile)

        today = datetime.now().strftime("%Y-%m-%d")
        n1 = Path(s1).name
        n2 = Path(s2).name
        n3 = Path(s3).name

        assert n1.startswith(today)
        assert n2.startswith(today)
        assert n3.startswith(today)
        assert n1.endswith("_1")
        assert n2.endswith("_2")
        assert n3.endswith("_3")

    def test_session_info_content(self, session_manager, client_with_profile):
        session_path = session_manager.create_session(client_with_profile)
        info = session_manager.get_session_info(session_path)

        assert info is not None
        assert info["created_by_tool"] == "shopify"
        assert info["client_id"] == client_with_profile
        assert info["status"] == "active"
        assert "created_at" in info
        assert "session_name" in info
        assert info["analysis_completed"] is False
        assert info["packing_lists_generated"] == []

    def test_create_session_case_insensitive(self, session_manager, client_with_profile):
        session_path = session_manager.create_session("m")  # lowercase
        assert Path(session_path).exists()
        assert "CLIENT_M" in str(session_path)


# ── Session listing ─────────────────────────────────────────────────────────


class TestSessionListing:
    def test_list_client_sessions_empty(self, session_manager, client_with_profile):
        assert session_manager.list_client_sessions(client_with_profile) == []

    def test_list_client_sessions(self, session_manager, client_with_profile):
        session_manager.create_session(client_with_profile)
        time.sleep(0.05)
        session_manager.create_session(client_with_profile)
        time.sleep(0.05)
        session_manager.create_session(client_with_profile)

        sessions = session_manager.list_client_sessions(client_with_profile)
        assert len(sessions) == 3

        for i in range(len(sessions) - 1):
            t1 = datetime.fromisoformat(sessions[i]["created_at"])
            t2 = datetime.fromisoformat(sessions[i + 1]["created_at"])
            assert t1 >= t2

    def test_list_sessions_with_status_filter(self, session_manager, client_with_profile):
        s1 = session_manager.create_session(client_with_profile)
        s2 = session_manager.create_session(client_with_profile)
        s3 = session_manager.create_session(client_with_profile)

        session_manager.update_session_status(s1, "completed")
        session_manager.update_session_status(s2, "completed")

        completed = session_manager.list_client_sessions(client_with_profile, "completed")
        active = session_manager.list_client_sessions(client_with_profile, "active")

        assert len(completed) == 2
        assert len(active) == 1

    def test_list_nonexistent_client(self, session_manager):
        assert session_manager.list_client_sessions("NONEXISTENT") == []


# ── Session info ────────────────────────────────────────────────────────────


class TestSessionInfo:
    def test_get_session_info(self, session_manager, client_with_profile):
        session_path = session_manager.create_session(client_with_profile)
        info = session_manager.get_session_info(session_path)

        assert info is not None
        assert "client_id" in info
        assert "status" in info
        assert "created_at" in info
        assert "session_path" in info

    def test_get_session_info_nonexistent(self, session_manager, temp_base_path):
        fake_path = temp_base_path / "fake_session"
        assert session_manager.get_session_info(str(fake_path)) is None

    def test_update_session_info(self, session_manager, client_with_profile):
        session_path = session_manager.create_session(client_with_profile)

        updates = {
            "orders_file": "orders_export.csv",
            "stock_file": "inventory.csv",
            "analysis_completed": True,
        }
        result = session_manager.update_session_info(session_path, updates)
        assert result is True

        info = session_manager.get_session_info(session_path)
        assert info["orders_file"] == "orders_export.csv"
        assert info["stock_file"] == "inventory.csv"
        assert info["analysis_completed"] is True
        assert info["last_modified"] is not None

    def test_update_session_info_invalid_path(self, session_manager, temp_base_path):
        fake_path = temp_base_path / "CLIENT_M" / "fake_session"
        with pytest.raises(SessionManagerError):
            session_manager.update_session_info(str(fake_path), {"analysis_completed": True})


# ── Session status ──────────────────────────────────────────────────────────


class TestSessionStatus:
    def test_update_session_status_valid(self, session_manager, client_with_profile):
        session_path = session_manager.create_session(client_with_profile)

        for status in ["active", "completed", "abandoned"]:
            result = session_manager.update_session_status(session_path, status)
            assert result is True
            info = session_manager.get_session_info(session_path)
            assert info["status"] == status
            assert info["status_updated_at"] is not None

    def test_update_session_status_invalid(self, session_manager, client_with_profile):
        session_path = session_manager.create_session(client_with_profile)

        with pytest.raises(SessionManagerError) as exc_info:
            session_manager.update_session_status(session_path, "invalid_status")
        assert "Invalid status" in str(exc_info.value)

    def test_update_status_nonexistent_session(self, session_manager, temp_base_path):
        fake_path = temp_base_path / "CLIENT_M" / "fake_session"
        with pytest.raises(SessionManagerError):
            session_manager.update_session_status(str(fake_path), "completed")


# ── Session subdirectories ──────────────────────────────────────────────────


class TestSessionSubdirectories:
    def test_get_session_subdirectory_valid(self, session_manager, client_with_profile):
        session_path = session_manager.create_session(client_with_profile)

        for subdir_name in ["input", "analysis", "packing_lists", "stock_exports"]:
            subdir = session_manager.get_session_subdirectory(session_path, subdir_name)
            assert subdir is not None
            assert subdir.exists()
            assert subdir.is_dir()
            assert subdir.name == subdir_name

    def test_get_session_subdirectory_invalid(self, session_manager, client_with_profile):
        session_path = session_manager.create_session(client_with_profile)

        with pytest.raises(SessionManagerError) as exc_info:
            session_manager.get_session_subdirectory(session_path, "invalid_subdir")
        assert "Invalid subdirectory" in str(exc_info.value)

    def test_get_input_dir(self, session_manager, client_with_profile):
        session_path = session_manager.create_session(client_with_profile)
        d = session_manager.get_input_dir(session_path)
        assert d.exists() and d.name == "input"

    def test_get_analysis_dir(self, session_manager, client_with_profile):
        session_path = session_manager.create_session(client_with_profile)
        d = session_manager.get_analysis_dir(session_path)
        assert d.exists() and d.name == "analysis"

    def test_get_packing_lists_dir(self, session_manager, client_with_profile):
        session_path = session_manager.create_session(client_with_profile)
        d = session_manager.get_packing_lists_dir(session_path)
        assert d.exists() and d.name == "packing_lists"

    def test_get_stock_exports_dir(self, session_manager, client_with_profile):
        session_path = session_manager.create_session(client_with_profile)
        d = session_manager.get_stock_exports_dir(session_path)
        assert d.exists() and d.name == "stock_exports"


# ── Session paths ───────────────────────────────────────────────────────────


class TestSessionPaths:
    def test_get_session_path(self, session_manager, client_with_profile):
        session_path = session_manager.create_session(client_with_profile)
        session_name = Path(session_path).name

        retrieved = session_manager.get_session_path(client_with_profile, session_name)
        assert str(retrieved) == session_path

    def test_session_exists(self, session_manager, client_with_profile):
        session_path = session_manager.create_session(client_with_profile)
        session_name = Path(session_path).name

        assert session_manager.session_exists(client_with_profile, session_name)
        assert not session_manager.session_exists(client_with_profile, "2020-01-01_1")
        assert not session_manager.session_exists("NONEXISTENT", "2020-01-01_1")


# ── Session deletion ────────────────────────────────────────────────────────


class TestSessionDeletion:
    def test_delete_session_success(self, session_manager, client_with_profile):
        session_path = session_manager.create_session(client_with_profile)
        assert Path(session_path).exists()

        result = session_manager.delete_session(session_path)
        assert result is True
        assert not Path(session_path).exists()

    def test_delete_nonexistent_session(self, session_manager, temp_base_path):
        fake_path = temp_base_path / "CLIENT_M" / "fake_session"
        result = session_manager.delete_session(str(fake_path))
        assert result is False


# ── Multiple clients ────────────────────────────────────────────────────────


class TestMultipleClients:
    def test_sessions_isolated_per_client(self, profile_manager, session_manager):
        profile_manager.create_client_profile("M", "M Cosmetics")
        profile_manager.create_client_profile("A", "A Company")

        sm1 = session_manager.create_session("M")
        sm2 = session_manager.create_session("M")
        sa1 = session_manager.create_session("A")

        assert len(session_manager.list_client_sessions("M")) == 2
        assert len(session_manager.list_client_sessions("A")) == 1

        assert "CLIENT_M" in sm1
        assert "CLIENT_M" in sm2
        assert "CLIENT_A" in sa1


# ── Error handling ──────────────────────────────────────────────────────────


class TestErrorHandling:
    def test_missing_subdirectory(self, session_manager, client_with_profile):
        session_path = session_manager.create_session(client_with_profile)
        shutil.rmtree(Path(session_path) / "input")

        with pytest.raises(SessionManagerError):
            session_manager.get_input_dir(session_path)

    def test_session_creation_failure_cleanup(self, session_manager, client_with_profile):
        original_mkdir = Path.mkdir

        def failing_mkdir(self, *args, **kwargs):
            if "packing_lists" in str(self):
                raise PermissionError("Mocked failure")
            return original_mkdir(self, *args, **kwargs)

        with patch.object(Path, "mkdir", failing_mkdir):
            with pytest.raises(SessionManagerError):
                session_manager.create_session(client_with_profile)


# ── Timestamp / name generation ─────────────────────────────────────────────


class TestTimestampGeneration:
    def test_unique_name_generation_with_gaps(
        self, session_manager, profile_manager, temp_base_path
    ):
        """Session numbering uses MAX(n)+1 so gaps are skipped correctly."""
        profile_manager.create_client_profile("M", "M Cosmetics")
        client_sessions_dir = (
            temp_base_path / "Sessions" / "CLIENT_M"
        )
        client_sessions_dir.mkdir(parents=True, exist_ok=True)

        today = datetime.now().strftime("%Y-%m-%d")
        # Insert sessions with gaps directly into DB
        db = get_db()
        for n in (1, 3, 5):
            db.execute(
                "INSERT INTO sessions (client_id, session_name, status, pc_name, "
                "analysis_completed) VALUES (%s,%s,'active','test',false)",
                ("M", f"{today}_{n}"),
            )
            (client_sessions_dir / f"{today}_{n}").mkdir(exist_ok=True)

        new_name = session_manager._generate_unique_session_name("M")
        assert new_name == f"{today}_6"

    def test_unique_name_generation_no_existing(
        self, session_manager, profile_manager
    ):
        profile_manager.create_client_profile("M", "M Cosmetics")

        name = session_manager._generate_unique_session_name("M")
        today = datetime.now().strftime("%Y-%m-%d")
        assert name == f"{today}_1"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
