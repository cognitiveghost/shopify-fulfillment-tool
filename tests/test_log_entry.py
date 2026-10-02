import dataclasses
import logging
from datetime import datetime

import pytest

from gui.log_entry import LogEntry


def test_entry_is_frozen():
    entry = LogEntry(
        timestamp=datetime(2026, 9, 7, 12, 0, 0).astimezone(),
        level=logging.INFO,
        source="Session",
        message="New session created",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        entry.level = logging.ERROR


def test_level_name_is_the_logging_name():
    entry = LogEntry(datetime.now().astimezone(), logging.WARNING, "root", "careful")
    assert entry.level_name == "WARNING"


def test_activity_entries_are_info_and_carry_the_op_type_as_source():
    entry = LogEntry.activity("Report", "Generated: picklist")
    assert entry.level == logging.INFO
    assert entry.source == "Report"
    assert entry.message == "Generated: picklist"
    assert isinstance(entry.timestamp, datetime)


def test_an_entry_has_no_traceback_unless_it_is_given_one():
    plain = LogEntry(datetime.now().astimezone(), logging.INFO, "root", "fine")
    assert plain.traceback == ""
    assert LogEntry.activity("Report", "Generated: picklist").traceback == ""
    failed = LogEntry(
        datetime.now().astimezone(), logging.ERROR, "root", "bad", "Traceback (most recent call last):"
    )
    assert failed.traceback == "Traceback (most recent call last):"
