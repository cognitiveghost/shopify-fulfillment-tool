"""The entries the Logs page shows, and every word of a row (phase 6 spec section 4).

Two ring buffers, one per stream, of rows: dicts of strings that
gui/web/logs.js draws as they are. No Qt in this module, so the whole rule
set runs without a QApplication.
"""

import logging
import re
from collections import deque
from datetime import date
from heapq import merge
from operator import itemgetter

from gui.log_entry import LogEntry

CAPACITY = 5000
ACTIVITY = "Activity"
EXECUTION = "Execution"


def band(level: int) -> str:
    """The Level segment an entry counts under: Debug is Info, Critical is Error."""
    if level >= logging.ERROR:
        return "error"
    if level >= logging.WARNING:
        return "warning"
    return "info"


def to_row(entry_id: int, entry: LogEntry, stream: str) -> dict:
    """What the page draws for one entry (spec section 4.2)."""
    stamp = entry.timestamp
    source = str(entry.source)
    return {
        "id": entry_id,
        "time": f"{stamp:%H:%M:%S}.{stamp.microsecond // 1000:03d}",
        "date": f"{stamp:%Y-%m-%d}",
        "band": band(entry.level),
        "level": logging.getLevelName(entry.level).title(),
        "stream": stream,
        "source": source,
        "short": source.rsplit(".", 1)[-1] or source,
        "message": str(entry.message),
        "traceback": entry.traceback,
    }


class LogBuffer:
    """Each stream's last `capacity` rows. An id is never reused."""

    def __init__(self, capacity: int = CAPACITY) -> None:
        self.capacity = capacity
        # One deque per stream: a busy Execution stream cannot push the
        # day's Activity out.
        self._streams: dict[str, deque[dict]] = {
            ACTIVITY: deque(maxlen=capacity),
            EXECUTION: deque(maxlen=capacity),
        }
        self._next_id = 0

    def add(self, entry: LogEntry, stream: str) -> dict:
        """Keep one entry and return its row. A full stream drops its oldest."""
        row = to_row(self._next_id, entry, stream)
        self._next_id += 1
        self._streams[stream].append(row)
        return row

    def rows(self) -> list[dict]:
        """Every row of both streams, oldest first."""
        return list(merge(*self._streams.values(), key=itemgetter("id")))

    def pick(self, ids) -> list[dict]:
        """The rows with these ids, oldest first. A dropped id is skipped."""
        wanted = set(ids)
        return [row for row in self.rows() if row["id"] in wanted]


def save_text(rows) -> str:
    """Save as text: one line per row, then its traceback, indented.

    A message with line breaks keeps its first line on the row; the rest is
    indented with the traceback, so only a row starts at the margin.
    """
    lines = []
    for row in rows:
        first, *rest = row["message"].splitlines() or [""]
        lines.append(
            f"{row['date']} {row['time']}  {row['level'].upper():<8}  "
            f"{row['stream']:<9}  {row['source']}  {first}"
        )
        lines.extend(f"    {line}" for line in rest + row["traceback"].splitlines())
    return "".join(f"{line}\n" for line in lines)


def default_filename(client_id, day: date) -> str:
    """`logs_ACME_2026-09-30.txt`, or `logs_2026-09-30.txt` with no client."""
    client = re.sub(r"[^A-Za-z0-9_-]", "_", str(client_id or ""))
    middle = f"{client}_" if client else ""
    return f"logs_{middle}{day:%Y-%m-%d}.txt"
