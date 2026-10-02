"""The Logs page's rows and buffer: no Qt (phase 6 spec section 4.2)."""

import logging
from datetime import UTC, date, datetime

import pytest

from gui.log_buffer import (
    ACTIVITY,
    CAPACITY,
    EXECUTION,
    LogBuffer,
    band,
    default_filename,
    save_text,
    to_row,
)
from gui.log_entry import LogEntry

STAMP = datetime(2026, 9, 30, 14, 0, 53, 508_900, tzinfo=UTC)
TRACE = (
    "Traceback (most recent call last):\n"
    '  File "gui/tools_widget.py", line 142, in _on_run\n'
    "PermissionError: share is read-only"
)


def entry(
    message="Scanned order #48254",
    level=logging.INFO,
    source="shopify_tool.core",
    trace="",
):
    return LogEntry(STAMP, level, source, message, trace)


@pytest.mark.parametrize(
    ("level", "expected"),
    [
        (logging.DEBUG, "info"),
        (logging.INFO, "info"),
        (25, "info"),
        (logging.WARNING, "warning"),
        (35, "warning"),
        (logging.ERROR, "error"),
        (logging.CRITICAL, "error"),
    ],
)
def test_a_level_falls_in_one_of_three_bands(level, expected):
    assert band(level) == expected


def test_a_row_carries_every_word_the_page_draws():
    row = to_row(
        12, entry("Save failed", logging.ERROR, "gui.tools_widget", TRACE), EXECUTION
    )
    assert row == {
        "id": 12,
        "time": "14:00:53.508",
        "date": "2026-09-30",
        "band": "error",
        "level": "Error",
        "stream": "Execution",
        "source": "gui.tools_widget",
        "short": "tools_widget",
        "message": "Save failed",
        "traceback": TRACE,
    }


@pytest.mark.parametrize(
    ("level", "name"),
    [(logging.DEBUG, "Debug"), (logging.CRITICAL, "Critical"), (25, "Level 25")],
)
def test_the_badge_shows_the_real_level_name(level, name):
    assert to_row(0, entry(level=level), EXECUTION)["level"] == name


@pytest.mark.parametrize(
    ("source", "short"),
    [("Data Edit", "Data Edit"), ("root", "root"), ("a.b.c", "c"), ("odd.", "odd.")],
)
def test_short_is_the_source_after_its_last_dot(source, short):
    assert to_row(0, entry(source=source), ACTIVITY)["short"] == short


def test_milliseconds_are_cut_not_rounded():
    stamp = datetime(2026, 9, 30, 9, 5, 7, 999_999, tzinfo=UTC)
    late = LogEntry(stamp, logging.INFO, "root", "x")
    assert to_row(0, late, EXECUTION)["time"] == "09:05:07.999"


def test_ids_count_up_across_both_streams():
    buffer = LogBuffer()
    ids = [
        buffer.add(entry(), EXECUTION)["id"],
        buffer.add(entry(), ACTIVITY)["id"],
        buffer.add(entry(), EXECUTION)["id"],
    ]
    assert ids == [0, 1, 2]


def test_rows_are_both_streams_oldest_first():
    buffer = LogBuffer()
    buffer.add(entry("a"), EXECUTION)
    buffer.add(entry("b"), ACTIVITY)
    buffer.add(entry("c"), EXECUTION)
    assert [(row["id"], row["stream"], row["message"]) for row in buffer.rows()] == [
        (0, "Execution", "a"),
        (1, "Activity", "b"),
        (2, "Execution", "c"),
    ]


def test_a_full_stream_drops_its_oldest_and_leaves_the_other_alone():
    buffer = LogBuffer(capacity=2)
    buffer.add(entry("kept"), ACTIVITY)
    for message in ("one", "two", "three"):
        buffer.add(entry(message), EXECUTION)
    assert [row["message"] for row in buffer.rows()] == ["kept", "two", "three"]
    # A dropped id is gone for good: the next entry does not take it.
    assert buffer.add(entry("four"), EXECUTION)["id"] == 4


def test_the_default_capacity_is_five_thousand_a_stream():
    assert CAPACITY == 5000
    assert LogBuffer().capacity == 5000


def test_pick_returns_the_named_rows_oldest_first_and_skips_a_dropped_id():
    buffer = LogBuffer(capacity=2)
    for message in ("one", "two", "three"):
        buffer.add(entry(message), EXECUTION)
    assert [row["message"] for row in buffer.pick([2, 0, 1, 99])] == ["two", "three"]
    assert buffer.pick([]) == []


def test_save_text_is_a_line_per_row_with_the_traceback_indented():
    rows = [
        to_row(0, entry("New session created", source="Session"), ACTIVITY),
        to_row(
            1, entry("Save failed", logging.ERROR, "gui.tools_widget", TRACE), EXECUTION
        ),
    ]
    assert save_text(rows) == (
        "2026-09-30 14:00:53.508  INFO      Activity   Session  New session created\n"
        "2026-09-30 14:00:53.508  ERROR     Execution  gui.tools_widget  Save failed\n"
        "    Traceback (most recent call last):\n"
        '      File "gui/tools_widget.py", line 142, in _on_run\n'
        "    PermissionError: share is read-only\n"
    )


def test_save_text_indents_the_later_lines_of_a_message():
    """Only a row starts at the margin, so the file can be read back by row."""
    rows = [to_row(0, entry("line one\nline two", source="a.b"), EXECUTION)]
    assert save_text(rows) == (
        "2026-09-30 14:00:53.508  INFO      Execution  a.b  line one\n"
        "    line two\n"
    )


def test_save_text_of_nothing_is_empty():
    assert save_text([]) == ""


@pytest.mark.parametrize(
    ("client", "name"),
    [
        ("ACME", "logs_ACME_2026-09-30.txt"),
        (None, "logs_2026-09-30.txt"),
        ("", "logs_2026-09-30.txt"),
        ("A/B C", "logs_A_B_C_2026-09-30.txt"),
    ],
)
def test_the_default_file_name_carries_the_client_and_the_day(client, name):
    assert default_filename(client, date(2026, 9, 30)) == name
