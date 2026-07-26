import logging

from PySide6.QtCore import QObject, Signal


class QtLogHandler(logging.Handler, QObject):
    """A custom logging handler that emits a Qt signal for each log record.

    This class inherits from both `logging.Handler` and `QObject` to bridge
    Python's standard logging framework with Qt's signal/slot mechanism.
    When a log record is processed, it is formatted and then emitted via a
    Qt signal. This allows a Qt widget (like a QPlainTextEdit) in the main
    UI thread to receive and display log messages from any thread in a
    thread-safe way.

    Signals:
        log_message_received (str): Emitted with the formatted log message
                                    for each record.
    """

    # Define a signal that will carry the log message
    log_message_received = Signal(str)

    def __init__(self, parent=None):
        """Initializes the QtLogHandler."""
        # Initialize QObject part first
        QObject.__init__(self)
        # Then initialize the logging.Handler part
        logging.Handler.__init__(self)

    def emit(self, record):
        """Formats and emits a log record as a Qt signal.

        This method is called automatically by the Python logging framework
        whenever a log event is dispatched to this handler.

        Args:
            record (logging.LogRecord): The log record to process.
        """
        # Format the log record into a string
        msg = self.format(record)
        # Emit the signal with the formatted message
        self.log_message_received.emit(msg)
