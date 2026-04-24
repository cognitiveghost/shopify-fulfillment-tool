import logging
import os
import json
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging."""

    def __init__(self, tool_name: str = "shopify_tool"):
        super().__init__()
        self.tool_name = tool_name

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON with structured fields.

        Args:
            record: The log record to format

        Returns:
            JSON-formatted log entry as string
        """
        log_data = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "tool": self.tool_name,
            "client_id": getattr(record, "client_id", None),
            "session_id": getattr(record, "session_id", None),
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data, ensure_ascii=False)


def setup_logging(
    server_base_path: Optional[str] = None,
    client_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> logging.Logger:
    """Configures and initializes centralized logging for the application.

    This function sets up a centralized logger named 'ShopifyToolLogger'.
    It configures two handlers:
    1.  **RotatingFileHandler**: Writes log messages of level INFO and above to
        a centralized server location with date-based file names in JSON format.
        The log file is rotated when it reaches 10MB, and up to 30 backup files
        are kept. This is for persistent historical logging.
    2.  **StreamHandler**: Writes log messages of level INFO and above to the
        console (stderr) in human-readable format. This is useful for immediate
        feedback during development or for headless execution.

    The function ensures that handlers are not duplicated if it is called
    multiple times. A specific handler for the GUI is expected to be added
    separately by the UI code.

    Args:
        server_base_path: Base path to the server (e.g., r"\\\\192.168.88.101\\_Fulfilment_\\0UFulfilment")
                         If None, uses local "logs" directory for development/testing
        client_id: Current client ID for structured logging (optional)
        session_id: Current session ID for structured logging (optional)

    Returns:
        logging.Logger: The configured logger instance for the application.
    """
    # Determine log directory
    if server_base_path:
        # Centralized server logging
        log_dir = Path(server_base_path) / "Logs" / "shopify_tool"
    else:
        # Local logging for development/testing
        log_dir = Path("logs")

    # Create log directory if it doesn't exist
    log_dir.mkdir(parents=True, exist_ok=True)

    # Create date-based log file name
    log_file = log_dir / f"{datetime.now().strftime('%Y-%m-%d')}.log"

    # Get the root logger used by the application
    logger = logging.getLogger("ShopifyToolLogger")
    logger.setLevel(logging.INFO)  # Set the lowest level to capture all messages

    # Prevent adding handlers multiple times
    if logger.hasHandlers():
        logger.handlers.clear()

    # Create a handler for writing to a file with JSON formatting
    file_handler = RotatingFileHandler(
        log_file, maxBytes=10 * 1024 * 1024, backupCount=30, encoding="utf-8"
    )
    file_handler.setLevel(logging.INFO)  # Log everything to the file
    file_formatter = JSONFormatter(tool_name="shopify_tool")
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    # The UI handler will be added separately in the GUI code
    # We add a basic StreamHandler for non-GUI execution or debugging
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO)
    stream_formatter = logging.Formatter("%(levelname)s: %(message)s")
    stream_handler.setFormatter(stream_formatter)
    logger.addHandler(stream_handler)

    # Store context for structured logging
    if client_id:
        logger.client_id = client_id
    if session_id:
        logger.session_id = session_id

    return logger


def log_with_context(
    logger: logging.Logger,
    level: int,
    message: str,
    client_id: Optional[str] = None,
    session_id: Optional[str] = None,
    **kwargs,
) -> None:
    """Log a message with structured context fields.

    Args:
        logger: The logger instance to use
        level: Log level (logging.INFO, logging.WARNING, etc.)
        message: The log message
        client_id: Client ID for this log entry
        session_id: Session ID for this log entry
        **kwargs: Additional context to include in the log
    """
    extra = {}
    if client_id or hasattr(logger, "client_id"):
        extra["client_id"] = client_id or getattr(logger, "client_id", None)
    if session_id or hasattr(logger, "session_id"):
        extra["session_id"] = session_id or getattr(logger, "session_id", None)

    # Add any additional context
    extra.update(kwargs)

    logger.log(level, message, extra=extra)
