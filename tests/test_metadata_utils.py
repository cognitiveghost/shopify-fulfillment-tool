"""Timestamp/duration edge cases (target #5) underpinning every duration
metric, timing report, and lock-staleness check in the app.
"""
import json
from datetime import datetime

import pytest

from shared.metadata_utils import (
    calculate_duration,
    get_current_timestamp,
    load_session_summary,
    parse_timestamp,
)


def test_get_current_timestamp_is_timezone_aware():
    ts = get_current_timestamp()
    parsed = datetime.fromisoformat(ts)
    assert parsed.tzinfo is not None


def test_calculate_duration_same_offset():
    assert calculate_duration("2026-01-01T10:00:00+02:00", "2026-01-01T12:30:00+02:00") == 9000


def test_calculate_duration_across_differing_utc_offsets_is_still_correct():
    """Same instant expressed with two different UTC offsets must be a 0s duration."""
    assert calculate_duration("2026-01-01T12:00:00+02:00", "2026-01-01T10:00:00+00:00") == 0


def test_calculate_duration_malformed_input_returns_zero():
    assert calculate_duration("not-a-timestamp", "2026-01-01T12:00:00+00:00") == 0
    assert calculate_duration("", "") == 0
    assert calculate_duration(None, None) == 0


def test_parse_timestamp_naive_string_is_assumed_utc():
    """Documents an edge case: a naive (no-offset) timestamp is assumed UTC.
    If it actually represents local time in a non-UTC timezone, any duration
    computed against it will be off by exactly the local UTC offset.
    """
    naive = "2026-01-01T10:00:00"        # assumed to mean 10:00 UTC
    aware_same_wall_clock = "2026-01-01T10:00:00+02:00"  # actually means 08:00 UTC

    duration = calculate_duration(naive, aware_same_wall_clock)
    assert duration == -7200, (
        "a naive timestamp is silently treated as UTC — if it actually came from "
        "a local (e.g. +02:00) clock, every duration computed against it is off "
        "by the local UTC offset"
    )


def test_parse_timestamp_handles_z_suffix():
    dt = parse_timestamp("2026-01-01T10:00:00Z")
    assert dt is not None
    assert dt.utcoffset().total_seconds() == 0


def test_parse_timestamp_none_and_empty_return_none():
    assert parse_timestamp(None) is None
    assert parse_timestamp("") is None


def test_parse_timestamp_garbage_returns_none():
    assert parse_timestamp("not a timestamp") is None


# ---------------------------------------------------------------------------
# load_session_summary
# ---------------------------------------------------------------------------

def test_load_session_summary_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_session_summary(tmp_path / "nope.json")


def test_load_session_summary_wrong_version_raises(tmp_path):
    path = tmp_path / "session_summary.json"
    path.write_text(json.dumps({"version": "0.9.0"}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_session_summary(path)


def test_load_session_summary_fills_missing_fields_with_defaults(tmp_path):
    path = tmp_path / "session_summary.json"
    path.write_text(json.dumps({"version": "1.3.0", "session_id": "s1"}), encoding="utf-8")
    summary = load_session_summary(path)
    assert summary["metrics"]["avg_time_per_order"] == 0
    assert summary["worker_name"] == "Unknown"
    assert summary["orders"] == []


def test_load_session_summary_corrupted_json_raises_decode_error(tmp_path):
    path = tmp_path / "session_summary.json"
    path.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        load_session_summary(path)
