"""An unhandled exception reaches the log.

A frozen Windows GUI build has no console, so anything Python writes to stderr
is discarded. Without a hook, a crash leaves nothing behind at all -- which is
exactly what the owner saw after the Bundle 5 merge.
"""

import logging
import sys
import threading

import pytest

from shared.logger import install_crash_logging


@pytest.mark.qt_no_exception_capture
def test_an_unhandled_exception_is_logged_with_its_traceback(caplog):
    previous = sys.excepthook
    try:
        install_crash_logging()
        with caplog.at_level(logging.CRITICAL):
            try:
                raise ValueError("the thing that went wrong")
            except ValueError:
                sys.excepthook(*sys.exc_info())
    finally:
        sys.excepthook = previous

    assert "the thing that went wrong" in caplog.text
    assert "ValueError" in caplog.text
    assert "Traceback" in caplog.text


def test_the_previous_hook_still_runs(caplog):
    previous = sys.excepthook
    seen = []
    sys.excepthook = lambda *args: seen.append(args[0])
    try:
        install_crash_logging()
        try:
            raise ValueError("chained")
        except ValueError:
            sys.excepthook(*sys.exc_info())
    finally:
        sys.excepthook = previous

    assert seen == [ValueError], "the hook that was there before must still run"


@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
def test_a_thread_crash_is_logged_too(caplog):
    previous = threading.excepthook
    try:
        install_crash_logging()
        with caplog.at_level(logging.CRITICAL):

            def boom():
                raise RuntimeError("in a worker thread")

            thread = threading.Thread(target=boom)
            thread.start()
            thread.join()
    finally:
        threading.excepthook = previous

    assert "in a worker thread" in caplog.text


@pytest.mark.qt_no_exception_capture
def test_a_keyboard_interrupt_is_not_logged_as_a_crash(caplog):
    previous = sys.excepthook
    try:
        install_crash_logging()
        with caplog.at_level(logging.CRITICAL):
            try:
                raise KeyboardInterrupt()
            except KeyboardInterrupt:
                sys.excepthook(*sys.exc_info())
    finally:
        sys.excepthook = previous

    assert caplog.text == "", "Ctrl-C is a person leaving, not a crash"
