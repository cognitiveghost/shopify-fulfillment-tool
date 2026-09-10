import logging

from gui.log_entry import LogEntry
from gui.log_handler import QtLogHandler


def _record(
    level=logging.WARNING, name="ShopifyToolLogger", msg="careful %s", args=("now",)
):
    return logging.LogRecord(
        name=name,
        level=level,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=args,
        exc_info=None,
    )


def test_emit_sends_a_log_entry(qapp):
    handler = QtLogHandler()
    received = []
    handler.entry_received.connect(received.append)

    handler.emit(_record())

    assert len(received) == 1
    assert isinstance(received[0], LogEntry)


def test_the_entry_carries_level_logger_name_and_rendered_message(qapp):
    handler = QtLogHandler()
    received = []
    handler.entry_received.connect(received.append)

    handler.emit(
        _record(
            level=logging.ERROR,
            name="shopify_tool.core",
            msg="failed on %s",
            args=("order 42",),
        )
    )

    entry = received[0]
    assert entry.level == logging.ERROR
    assert entry.source == "shopify_tool.core"
    # Rendered, not the raw template -- args must be interpolated.
    assert entry.message == "failed on order 42"


def test_the_old_string_signal_is_gone(qapp):
    assert not hasattr(QtLogHandler, "log_message_received")


def test_an_exception_summary_rides_on_the_message(qapp):
    import sys

    handler = QtLogHandler()
    received = []
    handler.entry_received.connect(received.append)
    try:
        raise PermissionError("share is read-only")
    except PermissionError:
        record = logging.LogRecord(
            name="gui.actions_handler",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="Save failed",
            args=(),
            exc_info=sys.exc_info(),
        )

    handler.emit(record)

    assert received[0].message == "Save failed — PermissionError: share is read-only"


def test_a_record_without_an_exception_keeps_its_message(qapp):
    handler = QtLogHandler()
    received = []
    handler.entry_received.connect(received.append)

    handler.emit(_record())

    assert received[0].message == "careful now"
