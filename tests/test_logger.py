"""Unified logger (shared/logger.py) - per-process log files (no locking:
each filename has exactly one writer for its whole lifetime), a JSON
formatter that generically captures extra= fields, a console handler
gated on sys.stderr being available, and a best-effort mtime-based
retention sweep (per-process files have no long-lived owner left to
prune their own old rotations, unlike a TimedRotatingFileHandler
rotating a single long-lived shared file)."""
import json
import logging
import os
import time

import pytest

from shared.logger import _active_handlers, _sweep_old_logs, setup_logging


@pytest.fixture(autouse=True)
def _reset_root_logger():
    """Hermetic tests: each test's setup_logging() call configures the
    real root logger (there is only one). Handlers and level must not
    leak between tests, or a later test's assertions about handler count
    would depend on test execution order."""
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    yield
    for handler in root.handlers[:]:
        if handler not in original_handlers:
            root.removeHandler(handler)
            handler.close()
    root.setLevel(original_level)
    _active_handlers.clear()


def _read_json_lines(log_file):
    return [json.loads(line) for line in log_file.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_setup_logging_creates_one_file_per_process(tmp_path):
    setup_logging("TestTool", str(tmp_path), level=logging.DEBUG)

    log_dir = tmp_path / "Logs" / "TestTool"
    files = list(log_dir.glob("TestTool_*.log"))
    assert len(files) == 1
    assert f"_{os.getpid()}.log" in files[0].name


def test_log_message_is_captured_as_json(tmp_path):
    setup_logging("TestTool", str(tmp_path), level=logging.DEBUG)
    logging.getLogger("test_module").info("hello world")

    log_file = next((tmp_path / "Logs" / "TestTool").glob("TestTool_*.log"))
    records = _read_json_lines(log_file)
    assert any(r["message"] == "hello world" and r["level"] == "INFO" for r in records)


def test_extra_fields_are_captured_generically(tmp_path):
    """Regression: packing-tool's old StructuredJSONFormatter looked for a
    record.extra_data attribute that logging never actually sets - each
    extra={...} key becomes its own attribute directly on the record, so
    session_lock_manager.py's extra={"client_id": ...} calls were
    silently dropped from the JSON output. UnifiedJSONFormatter must not
    repeat that bug."""
    setup_logging("TestTool", str(tmp_path), level=logging.DEBUG)
    logging.getLogger("test_module").warning(
        "lock conflict", extra={"client_id": "M", "session_dir": "S1"}
    )

    log_file = next((tmp_path / "Logs" / "TestTool").glob("TestTool_*.log"))
    records = _read_json_lines(log_file)
    match = next(r for r in records if r["message"] == "lock conflict")
    assert match["extra"] == {"client_id": "M", "session_dir": "S1"}


def test_setup_logging_is_idempotent(tmp_path):
    """Regression: the Server Connection recovery-retry flow can
    reconstruct ProfileManager (and therefore call setup_logging again)
    within the same process. A second call must replace, not stack, its
    handlers - otherwise every subsequent log line gets emitted once per
    accumulated handler."""
    setup_logging("TestTool", str(tmp_path), level=logging.DEBUG)
    handler_count_after_first = len(_active_handlers)

    setup_logging("TestTool", str(tmp_path), level=logging.DEBUG)
    assert len(_active_handlers) == handler_count_after_first

    logging.getLogger("test_module").info("only once")
    log_file = next((tmp_path / "Logs" / "TestTool").glob("TestTool_*.log"))
    records = _read_json_lines(log_file)
    assert sum(1 for r in records if r["message"] == "only once") == 1


def test_console_handler_skipped_when_stderr_is_none(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.stderr", None)
    setup_logging("TestTool", str(tmp_path), level=logging.DEBUG)

    assert not any(isinstance(h, logging.StreamHandler) for h in _active_handlers)


def test_sweep_deletes_old_files_but_keeps_recent(tmp_path):
    log_dir = tmp_path / "Logs" / "TestTool"
    log_dir.mkdir(parents=True)

    old_file = log_dir / "old.log"
    old_file.write_text("stale")
    old_time = time.time() - 40 * 86400
    os.utime(old_file, (old_time, old_time))

    recent_file = log_dir / "recent.log"
    recent_file.write_text("fresh")

    _sweep_old_logs(log_dir, retention_days=30)

    assert not old_file.exists()
    assert recent_file.exists()
