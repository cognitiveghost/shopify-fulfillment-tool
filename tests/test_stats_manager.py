"""Merged StatsManager (shared/ unification) — record_analysis,
record_packing, record_label_print and the reporting/history methods all
live in one canonical file now. Previously packing-tool's copy only had
record_packing; shopify-fulfillment-tool's copy had the full set but
duplicated file-locking and timestamp logic inline instead of reusing
shared.file_lock / shared.metadata_utils. This file exercises the merged
surface end to end.
"""
from datetime import datetime, timedelta

from shared.file_lock import FileLockError as SharedFileLockError
from shared.stats_manager import FileLockError as StatsFileLockError
from shared.stats_manager import StatsManager


def test_default_stats_version_is_the_unified_value(tmp_path):
    manager = StatsManager(str(tmp_path))
    assert manager._get_default_stats()["version"] == "2.0"


def test_file_lock_error_is_the_one_shared_class():
    """Regression: shopify-fulfillment-tool's stats_manager.py used to
    define its own FileLockError(StatsManagerError) — a different class
    from packing-tool's shared.file_lock.FileLockError(Exception), despite
    both being exported from shared/__init__.py under the same name.
    """
    assert StatsFileLockError is SharedFileLockError


def test_record_analysis_updates_global_and_client_counters(tmp_path):
    manager = StatsManager(str(tmp_path))
    manager.record_analysis(
        client_id="M",
        session_id="2026-01-01_1",
        orders_count=150,
        metadata={"fulfillable_orders": 142},
    )

    global_stats = manager.get_global_stats()
    assert global_stats["total_orders_analyzed"] == 150

    client_stats = manager.get_client_stats("M")
    assert client_stats["orders_analyzed"] == 150
    assert client_stats["sessions"] == 0  # only record_packing increments sessions


def test_record_packing_updates_global_and_client_counters(tmp_path):
    manager = StatsManager(str(tmp_path))
    manager.record_packing(
        client_id="M",
        session_id="2026-01-01_1",
        worker_id="worker_001",
        orders_count=142,
        items_count=450,
    )

    global_stats = manager.get_global_stats()
    assert global_stats["total_orders_packed"] == 142
    assert global_stats["total_sessions"] == 1

    client_stats = manager.get_client_stats("M")
    assert client_stats["orders_packed"] == 142
    assert client_stats["sessions"] == 1


def test_record_analysis_and_record_packing_share_one_client_entry(tmp_path):
    """Both apps write the same by_client[client_id] entry in the same
    file — this is the whole point of the unified StatsManager."""
    manager = StatsManager(str(tmp_path))
    manager.record_analysis(client_id="M", session_id="s1", orders_count=150)
    manager.record_packing(
        client_id="M", session_id="s1", worker_id="w1",
        orders_count=142, items_count=450,
    )

    client_stats = manager.get_client_stats("M")
    assert client_stats["orders_analyzed"] == 150
    assert client_stats["orders_packed"] == 142
    assert client_stats["sessions"] == 1


def test_get_all_clients_stats_returns_every_client(tmp_path):
    manager = StatsManager(str(tmp_path))
    manager.record_analysis(client_id="M", session_id="s1", orders_count=10)
    manager.record_analysis(client_id="A", session_id="s2", orders_count=20)

    all_stats = manager.get_all_clients_stats()
    assert set(all_stats.keys()) == {"M", "A"}


def test_get_analysis_history_filters_by_client_and_limit(tmp_path):
    manager = StatsManager(str(tmp_path))
    manager.record_analysis(client_id="M", session_id="s1", orders_count=10)
    manager.record_analysis(client_id="A", session_id="s2", orders_count=20)
    manager.record_analysis(client_id="M", session_id="s3", orders_count=30)

    history = manager.get_analysis_history(client_id="M")
    assert len(history) == 2
    assert all(h["client_id"] == "M" for h in history)

    limited = manager.get_analysis_history(limit=1)
    assert len(limited) == 1


def test_get_packing_history_filters_by_worker(tmp_path):
    manager = StatsManager(str(tmp_path))
    manager.record_packing(client_id="M", session_id="s1", worker_id="w1", orders_count=1, items_count=1)
    manager.record_packing(client_id="M", session_id="s2", worker_id="w2", orders_count=1, items_count=1)

    history = manager.get_packing_history(worker_id="w1")
    assert len(history) == 1
    assert history[0]["worker_id"] == "w1"


def test_record_label_print_updates_counters_and_history(tmp_path):
    manager = StatsManager(str(tmp_path))
    manager.record_label_print(client_id="M", sku="SKU-1", copies=3)
    manager.record_label_print(client_id="M", sku="SKU-2", copies=2)

    stats = manager.get_label_stats(client_id="M")
    assert stats["total_labels_printed"] == 5
    assert stats["unique_skus"] == 2
    assert stats["top_sku"] == "SKU-1"


def test_get_label_print_history_accepts_naive_dates_from_the_gui(tmp_path):
    """Regression: the GUI (client_reports_widget.py) builds start_date/
    end_date from a QDate — a naive datetime, no timezone — while records
    are stored with timezone-aware timestamps (get_current_timestamp()).
    Comparing a naive and an aware datetime raises TypeError; this must
    not happen once every write path in the merged StatsManager produces
    timezone-aware timestamps.
    """
    manager = StatsManager(str(tmp_path))
    manager.record_label_print(client_id="M", sku="SKU-1", copies=1)

    naive_start = datetime.now() - timedelta(days=1)  # noqa: DTZ005 -- naive on purpose, see docstring
    naive_end = datetime.now() + timedelta(days=1)  # noqa: DTZ005 -- naive on purpose, see docstring

    history = manager.get_label_print_history(start_date=naive_start, end_date=naive_end)
    assert len(history) == 1


def test_get_label_print_history_filters_out_of_range_dates(tmp_path):
    manager = StatsManager(str(tmp_path))
    manager.record_label_print(client_id="M", sku="SKU-1", copies=1)

    far_future_start = datetime.now() + timedelta(days=30)  # noqa: DTZ005 -- naive input, same regression coverage as above
    history = manager.get_label_print_history(start_date=far_future_start)
    assert history == []


def test_reset_stats_clears_history_and_counters(tmp_path):
    manager = StatsManager(str(tmp_path))
    manager.record_packing(client_id="M", session_id="s1", worker_id="w1", orders_count=1, items_count=1)

    manager.reset_stats()

    assert manager.get_global_stats()["total_orders_packed"] == 0
    assert manager.get_packing_history() == []
