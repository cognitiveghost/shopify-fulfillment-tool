"""
Unified logging for Shopify Tool and Packing Tool.

Canonical version. This module lives in packing-tool/shared/ and is copied
into shopify-fulfillment-tool/shared/ by
shopify-fulfillment-tool/scripts/sync_shared.py - the two copies must stay
byte-identical. See shared/README.md.

Each process writes its own log file (Logs/<tool_name>/<tool_name>_
<hostname>_<pid>.log), so multiple PCs/processes sharing one network file
server never contend for the same file - no locking needed, since a given
filename only ever has exactly one writer for its whole lifetime. Contrast
with shared.stats_manager, where every process genuinely shares one file
and needs shared.file_lock.
"""
import json
import logging
import os
import socket
import sys
import time
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

_STANDARD_RECORD_ATTRS = frozenset(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()
) | {"message", "asctime"}

# Handlers this module added to the root logger, so a second setup_logging()
# call in the same process (e.g. a Server Connection recovery retry
# reconstructing ProfileManager after the user fixes an unreachable path)
# replaces them instead of stacking duplicates that would each re-emit
# every subsequent log line.
_active_handlers: list = []


class UnifiedJSONFormatter(logging.Formatter):
    """JSON formatter shared by both tools.

    Any attribute a log call sets via extra={...} that isn't one of the
    standard LogRecord attributes is captured under log_data["extra"] -
    generic, not a hardcoded field-name allowlist. This is what packing-
    tool's old StructuredJSONFormatter got wrong: it looked for a single
    record.extra_data attribute that logging never actually sets (each
    extra= key becomes its own attribute directly on the record).
    """

    def __init__(self, tool_name: str):
        super().__init__()
        self.tool_name = tool_name

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "tool": self.tool_name,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "message": record.getMessage(),
        }

        if record.exc_info:
            log_data["exc_info"] = self.formatException(record.exc_info)

        extra = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _STANDARD_RECORD_ATTRS
        }
        if extra:
            log_data["extra"] = extra

        return json.dumps(log_data, ensure_ascii=False, default=str)


def _sweep_old_logs(log_dir: Path, retention_days: int) -> None:
    """Best-effort delete of files in log_dir older than retention_days.

    Per-process log files have no single long-lived owner left to prune
    their own old rotations once their process exits -
    TimedRotatingFileHandler's backupCount only prunes rotations created
    by that same handler instance. A file that can't be deleted (e.g.
    still open by another live process - Windows refuses to remove it)
    is silently skipped and retried on the next startup.
    """
    cutoff = time.time() - retention_days * 86400
    try:
        entries = list(log_dir.iterdir())
    except OSError:
        return
    for entry in entries:
        try:
            if entry.is_file() and entry.stat().st_mtime < cutoff:
                entry.unlink()
        except OSError:
            continue


def setup_logging(
    tool_name: str,
    base_path: str,
    level: int = logging.INFO,
    retention_days: int = 30,
) -> None:
    """Configure the root logger for `tool_name`.

    Every existing logging.getLogger(__name__) /
    logging.getLogger("ShopifyToolLogger") call in either app keeps
    working unchanged - this only configures handlers on the root logger.

    Call once base_path is known (from ProfileManager.base_path), not at
    import time with an unresolved path.

    Safe to call again later in the same process - previously-added
    handlers are closed and removed first, so retries never stack
    duplicate handlers.
    """
    global _active_handlers

    root_logger = logging.getLogger()
    for handler in _active_handlers:
        root_logger.removeHandler(handler)
        handler.close()
    _active_handlers = []

    log_dir = Path(base_path) / "Logs" / tool_name
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        log_dir = Path.home() / f".{tool_name.lower()}" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        print(f"Warning: could not access server logs directory. Using local: {log_dir}. Error: {e}")

    log_file = log_dir / f"{tool_name}_{socket.gethostname()}_{os.getpid()}.log"

    file_handler = TimedRotatingFileHandler(
        log_file, when="midnight", backupCount=retention_days, encoding="utf-8"
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(UnifiedJSONFormatter(tool_name))
    root_logger.addHandler(file_handler)
    _active_handlers.append(file_handler)

    if sys.stderr is not None:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(logging.Formatter(
            fmt="%(asctime)s | %(name)s | %(levelname)s | %(funcName)s:%(lineno)d | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        root_logger.addHandler(console_handler)
        _active_handlers.append(console_handler)

    root_logger.setLevel(level)

    _sweep_old_logs(log_dir, retention_days)

    startup_logger = logging.getLogger(tool_name)
    startup_logger.info("=" * 80)
    startup_logger.info(f"{tool_name} started")
    startup_logger.info(f"Log level: {logging.getLevelName(level)}")
    startup_logger.info(f"Log file: {log_file}")
    startup_logger.info("=" * 80)


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        setup_logging("SelfCheckTool", tmp, level=logging.DEBUG)
        logging.getLogger(__name__).info("hello", extra={"client_id": "M"})

        log_dir = Path(tmp) / "Logs" / "SelfCheckTool"
        files = list(log_dir.glob("SelfCheckTool_*.log"))
        assert len(files) == 1, f"expected 1 log file, found {files}"

        lines = [line for line in files[0].read_text(encoding="utf-8").splitlines() if '"hello"' in line]
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["extra"]["client_id"] == "M"

        handlers_before = len(_active_handlers)
        setup_logging("SelfCheckTool", tmp, level=logging.DEBUG)
        assert len(_active_handlers) == handlers_before, "setup_logging() must not stack duplicate handlers"

        old_file = log_dir / "old.log"
        old_file.write_text("stale")
        old_time = time.time() - 40 * 86400
        os.utime(old_file, (old_time, old_time))
        _sweep_old_logs(log_dir, retention_days=30)
        assert not old_file.exists(), "sweep should delete files older than retention_days"

    print("shared/logger.py self-check OK")
