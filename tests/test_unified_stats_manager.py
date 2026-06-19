"""Unit tests for the Unified StatsManager — PostgreSQL backend."""

import time
import tempfile
from pathlib import Path

import pytest

from shared.stats_manager import StatsManager, StatsManagerError, FileLockError
from shopify_tool.db_manager import get_db


_STAT_TEST_CLIENTS = ["M", "A", "NEW_CLIENT", "ERR_TEST"]


@pytest.fixture(autouse=True)
def clean_event_tables():
    """Ensure test client rows exist and event tables are empty before each test."""
    _purge()
    db = get_db()
    for cid in _STAT_TEST_CLIENTS:
        db.execute(
            "INSERT INTO clients (client_id, client_name) VALUES (%s,%s) "
            "ON CONFLICT (client_id) DO NOTHING",
            (cid, cid),
        )
    yield
    _purge()
    for cid in _STAT_TEST_CLIENTS:
        db.execute("DELETE FROM clients WHERE client_id = %s", (cid,))


def _purge():
    db = get_db()
    db.execute("DELETE FROM analysis_events")
    db.execute("DELETE FROM packing_events")
    db.execute("DELETE FROM label_print_events")


@pytest.fixture
def stats_manager(tmp_path):
    return StatsManager(base_path=str(tmp_path))


# ── Imports ────────────────────────────────────────────────────────────────

class TestImports:
    def test_fileLockError_is_importable(self):
        assert FileLockError is StatsManagerError


# ── Initialization ─────────────────────────────────────────────────────────

class TestStatsManagerInitialization:
    def test_get_global_stats_returns_zeros_on_empty_db(self, stats_manager):
        stats = stats_manager.get_global_stats()
        assert stats["total_orders_analyzed"] == 0
        assert stats["total_orders_packed"] == 0
        assert stats["total_sessions"] == 0
        assert stats["total_labels_printed"] == 0

    def test_global_stats_has_required_keys(self, stats_manager):
        stats = stats_manager.get_global_stats()
        for key in ("total_orders_analyzed", "total_orders_packed",
                    "total_sessions", "last_updated"):
            assert key in stats


# ── Record analysis ────────────────────────────────────────────────────────

class TestRecordAnalysis:
    def test_record_analysis_basic(self, stats_manager):
        stats_manager.record_analysis("M", "2025-11-05_1", 150)

        stats = stats_manager.get_global_stats()
        assert stats["total_orders_analyzed"] == 150
        assert stats["total_orders_packed"] == 0

    def test_record_analysis_with_metadata(self, stats_manager):
        meta = {"fulfillable_orders": 142, "courier_breakdown": {"DHL": 80}}
        stats_manager.record_analysis("M", "2025-11-05_1", 150, metadata=meta)

        history = stats_manager.get_analysis_history(limit=1)
        assert len(history) == 1
        assert history[0]["metadata"] == meta

    def test_record_analysis_multiple_clients(self, stats_manager):
        stats_manager.record_analysis("M", "s1", 100)
        stats_manager.record_analysis("A", "s2", 50)
        stats_manager.record_analysis("M", "s3", 75)

        assert stats_manager.get_global_stats()["total_orders_analyzed"] == 225
        assert stats_manager.get_client_stats("M")["orders_analyzed"] == 175
        assert stats_manager.get_client_stats("A")["orders_analyzed"] == 50

    def test_record_analysis_creates_client_entry(self, stats_manager):
        stats_manager.record_analysis("NEW_CLIENT", "s1", 100)

        client = stats_manager.get_client_stats("NEW_CLIENT")
        assert client["orders_analyzed"] == 100
        assert client["orders_packed"] == 0
        assert client["sessions"] == 0


# ── Record packing ─────────────────────────────────────────────────────────

class TestRecordPacking:
    def test_record_packing_basic(self, stats_manager):
        stats_manager.record_packing("M", "2025-11-05_1", "001", 142, 450)

        stats = stats_manager.get_global_stats()
        assert stats["total_orders_packed"] == 142
        assert stats["total_orders_analyzed"] == 0
        assert stats["total_sessions"] == 1

    def test_record_packing_with_metadata(self, stats_manager):
        meta = {"start_time": "2025-11-05T10:00:00", "duration_seconds": 9000}
        stats_manager.record_packing("M", "s1", "001", 142, 450, metadata=meta)

        history = stats_manager.get_packing_history(limit=1)
        assert len(history) == 1
        assert history[0]["metadata"] == meta
        assert history[0]["worker_id"] == "001"

    def test_record_packing_no_worker(self, stats_manager):
        stats_manager.record_packing("M", "s1", None, 100, 300)

        history = stats_manager.get_packing_history(limit=1)
        assert history[0]["worker_id"] is None

    def test_record_packing_increments_sessions(self, stats_manager):
        stats_manager.record_packing("M", "s1", "001", 10, 30)
        stats_manager.record_packing("M", "s2", "001", 20, 60)
        stats_manager.record_packing("A", "s3", "002", 15, 45)

        assert stats_manager.get_global_stats()["total_sessions"] == 3
        assert stats_manager.get_client_stats("M")["sessions"] == 2


# ── Integrated workflow ────────────────────────────────────────────────────

class TestIntegratedWorkflow:
    def test_complete_workflow(self, stats_manager):
        stats_manager.record_analysis("M", "2025-11-05_1", 150)
        stats_manager.record_packing("M", "2025-11-05_1", "001", 142, 450)

        gs = stats_manager.get_global_stats()
        assert gs["total_orders_analyzed"] == 150
        assert gs["total_orders_packed"] == 142
        assert gs["total_sessions"] == 1

        cs = stats_manager.get_client_stats("M")
        assert cs["orders_analyzed"] == 150
        assert cs["orders_packed"] == 142
        assert cs["sessions"] == 1

    def test_multiple_sessions_same_client(self, stats_manager):
        stats_manager.record_analysis("M", "2025-11-05_1", 100)
        stats_manager.record_packing("M", "2025-11-05_1", "001", 95, 300)
        stats_manager.record_analysis("M", "2025-11-05_2", 120)
        stats_manager.record_packing("M", "2025-11-05_2", "002", 118, 350)

        cs = stats_manager.get_client_stats("M")
        assert cs["orders_analyzed"] == 220
        assert cs["orders_packed"] == 213
        assert cs["sessions"] == 2


# ── History retrieval ──────────────────────────────────────────────────────

class TestHistoryRetrieval:
    def test_get_analysis_history_all(self, stats_manager):
        stats_manager.record_analysis("M", "s1", 100)
        stats_manager.record_analysis("A", "s2", 50)
        stats_manager.record_analysis("M", "s3", 75)

        assert len(stats_manager.get_analysis_history()) == 3

    def test_get_analysis_history_by_client(self, stats_manager):
        stats_manager.record_analysis("M", "s1", 100)
        stats_manager.record_analysis("A", "s2", 50)
        stats_manager.record_analysis("M", "s3", 75)

        history = stats_manager.get_analysis_history(client_id="M")
        assert len(history) == 2
        assert all(h["client_id"] == "M" for h in history)

    def test_get_analysis_history_with_limit(self, stats_manager):
        for i in range(10):
            stats_manager.record_analysis("M", f"s{i}", 10)

        assert len(stats_manager.get_analysis_history(limit=5)) == 5

    def test_get_packing_history_by_worker(self, stats_manager):
        stats_manager.record_packing("M", "s1", "001", 10, 30)
        stats_manager.record_packing("M", "s2", "002", 20, 60)
        stats_manager.record_packing("M", "s3", "001", 15, 45)

        history = stats_manager.get_packing_history(worker_id="001")
        assert len(history) == 2
        assert all(h["worker_id"] == "001" for h in history)

    def test_history_sorted_newest_first(self, stats_manager):
        stats_manager.record_analysis("M", "s1", 10)
        time.sleep(0.05)
        stats_manager.record_analysis("M", "s2", 20)
        time.sleep(0.05)
        stats_manager.record_analysis("M", "s3", 30)

        history = stats_manager.get_analysis_history()
        assert history[0]["session_id"] == "s3"
        assert history[1]["session_id"] == "s2"
        assert history[2]["session_id"] == "s1"


# ── Client stats ───────────────────────────────────────────────────────────

class TestClientStats:
    def test_get_client_stats_nonexistent(self, stats_manager):
        stats = stats_manager.get_client_stats("NONEXISTENT")
        assert stats["orders_analyzed"] == 0
        assert stats["orders_packed"] == 0
        assert stats["sessions"] == 0

    def test_get_all_clients_stats(self, stats_manager):
        stats_manager.record_analysis("M", "s1", 100)
        stats_manager.record_packing("M", "s1", "001", 95, 300)
        stats_manager.record_analysis("A", "s2", 50)
        stats_manager.record_packing("A", "s2", "002", 48, 150)

        all_stats = stats_manager.get_all_clients_stats()
        assert "M" in all_stats
        assert "A" in all_stats
        assert all_stats["M"]["orders_analyzed"] == 100
        assert all_stats["A"]["orders_analyzed"] == 50

    def test_get_all_clients_stats_empty(self, stats_manager):
        all_stats = stats_manager.get_all_clients_stats()
        assert isinstance(all_stats, dict)
        assert len(all_stats) == 0


# ── Persistence (DB naturally persists across instances) ───────────────────

class TestPersistence:
    def test_data_persists_across_instances(self, tmp_path):
        manager1 = StatsManager(base_path=str(tmp_path))
        manager1.record_analysis("M", "s1", 100)
        manager1.record_packing("M", "s1", "001", 95, 300)

        manager2 = StatsManager(base_path=str(tmp_path))
        stats = manager2.get_global_stats()
        assert stats["total_orders_analyzed"] == 100
        assert stats["total_orders_packed"] == 95
        assert stats["total_sessions"] == 1


# ── Reset ──────────────────────────────────────────────────────────────────

class TestResetStats:
    def test_reset_stats(self, stats_manager):
        stats_manager.record_analysis("M", "s1", 100)
        stats_manager.record_packing("M", "s1", "001", 95, 300)

        stats_manager.reset_stats()

        stats = stats_manager.get_global_stats()
        assert stats["total_orders_analyzed"] == 0
        assert stats["total_orders_packed"] == 0
        assert stats["total_sessions"] == 0
        assert len(stats_manager.get_all_clients_stats()) == 0


# ── Error handling ─────────────────────────────────────────────────────────

class TestErrorHandling:
    def test_base_path_stored_but_not_required(self):
        """StatsManager stores base_path for API compat but DB does not need it."""
        manager = StatsManager(base_path="/some/nonexistent/path")
        manager.record_analysis("ERR_TEST", "s1", 5)
        assert manager.get_client_stats("ERR_TEST")["orders_analyzed"] == 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
