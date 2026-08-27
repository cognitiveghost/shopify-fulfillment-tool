import logging
import time
import tkinter as tk
from collections import deque
from tkinter import ttk

import customtkinter as ctk

from gui.theme_manager import get_theme_manager


class TreeViewLogHandler(logging.Handler):
    """A custom logging handler that sends records to a deque.

    This handler is designed to be used with the `LogViewer` widget. Instead
    of writing to a file or console, it simply places each `LogRecord` it
    receives onto a thread-safe deque (double-ended queue). The `LogViewer`
    can then process this queue in the main UI thread.

    Attributes:
        queue (deque): The queue where log records are placed.
    """

    def __init__(self, queue):
        """Initializes the TreeViewLogHandler.

        Args:
            queue (deque): The deque instance to use for storing log records.
        """
        super().__init__()
        self.queue = queue

    def emit(self, record):
        """Adds the log record to the queue.

        Args:
            record (logging.LogRecord): The log record to handle.
        """
        # Add the actual record object to the queue
        self.queue.append(record)


class LogViewer(ctk.CTkFrame):
    """A widget for displaying and filtering logs from the Python logging module.

    Note: This widget appears to be from a previous implementation using
    CustomTkinter and is likely not used in the current PySide6-based
    application.

    This widget provides a table-like view of log messages with capabilities
    for filtering by log level and searching by message content. It uses a
    custom `TreeViewLogHandler` to capture log records in a thread-safe manner.

    Attributes:
        all_logs (deque): A master list of all received log records.
        log_queue (deque): A queue for incoming log records from the handler.
        log_handler (TreeViewLogHandler): The custom logging handler instance.
    """

    def __init__(self, master, **kwargs):
        """Initializes the LogViewer widget.

        Args:
            master: The parent widget.
            **kwargs: Additional keyword arguments for the ctk.CTkFrame.
        """
        super().__init__(master, **kwargs)

        self.all_logs = deque(maxlen=1000)  # Master list of all log records
        self.log_queue = deque(maxlen=1000)
        self.log_handler = TreeViewLogHandler(self.log_queue)

        # Configure the logger to use our handler
        logger = logging.getLogger("ShopifyToolLogger")
        logger.addHandler(self.log_handler)

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._create_widgets()
        self._process_log_queue()

    def _create_widgets(self):
        """Creates and lays out all the sub-widgets for the log viewer."""
        theme = get_theme_manager().get_current_theme()
        # --- Controls Frame ---
        controls_frame = ctk.CTkFrame(self, fg_color="transparent")
        controls_frame.grid(row=0, column=0, padx=5, pady=5, sticky="ew")
        controls_frame.grid_columnconfigure(2, weight=1)

        ctk.CTkLabel(controls_frame, text="Filter by Level:").grid(row=0, column=0, padx=(0, 5))
        self.level_filter_var = tk.StringVar(value="ALL")
        self.level_filter_menu = ctk.CTkOptionMenu(
            controls_frame,
            variable=self.level_filter_var,
            values=["ALL", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
            command=self._apply_filters,
        )
        self.level_filter_menu.grid(row=0, column=1, padx=5)

        ctk.CTkLabel(controls_frame, text="Search:").grid(row=0, column=2, padx=(10, 5), sticky="e")
        self.search_var = tk.StringVar()
        self.search_entry = ctk.CTkEntry(controls_frame, textvariable=self.search_var)
        self.search_entry.grid(row=0, column=3, padx=5, sticky="ew")
        self.search_var.trace_add("write", self._apply_filters)

        # --- Treeview for Logs ---
        self.tree = ttk.Treeview(self, columns=("Time", "Level", "Message"), show="headings")
        self.tree.grid(row=1, column=0, sticky="nsew")

        self.tree.heading("Time", text="Time")
        self.tree.heading("Level", text="Level")
        self.tree.heading("Message", text="Message")

        self.tree.column("Time", width=160, anchor="w", stretch=tk.NO)
        self.tree.column("Level", width=80, anchor="w", stretch=tk.NO)
        self.tree.column("Message", width=600, anchor="w")

        # --- Scrollbar ---
        vsb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        vsb.grid(row=1, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=vsb.set)

        # --- Tags for color-coding ---
        self.tree.tag_configure("DEBUG", foreground="gray")
        self.tree.tag_configure("INFO", foreground="white")
        self.tree.tag_configure("WARNING", foreground=theme.status_warning)
        self.tree.tag_configure("ERROR", foreground=theme.status_danger)
        self.tree.tag_configure("CRITICAL", background=theme.status_danger, foreground="white")

    def _process_log_queue(self):
        """Periodically checks the queue for new log messages.

        This method runs on a timer in the UI thread. It moves records from
        the `log_queue` to the `all_logs` master list and adds them to the
        view if they match the current filters. This ensures thread-safe
        updates to the UI.
        """
        while self.log_queue:
            record = self.log_queue.popleft()
            self.all_logs.append(record)
            # Live update: add new logs that match current filter
            self._add_log_entry_if_match(record)

        self.after(100, self._process_log_queue)

    def _add_log_entry_if_match(self, record):
        """Adds a single log entry to the treeview if it matches current filters.

        Args:
            record (logging.LogRecord): The log record to check and add.
        """
        level_filter = self.level_filter_var.get()
        search_term = self.search_var.get().lower()
        level = record.levelname
        message = record.getMessage().lower()

        level_match = (level_filter == "ALL") or (level == level_filter)
        search_match = (search_term == "") or (search_term in message)

        if level_match and search_match:
            log_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(record.created))
            self.tree.insert("", 0, values=(log_time, level, record.getMessage()), tags=(level,))

    def _apply_filters(self, *args):
        """Clears and repopulates the log view based on the current filter settings.

        This is called whenever a filter control (level dropdown, search box)
        is changed. It iterates through the `all_logs` master list and re-adds
        only the records that match the new filter criteria.
        """
        # Clear the tree view
        for item in self.tree.get_children():
            self.tree.delete(item)

        # Repopulate with logs from the master list that match the filters
        for record in self.all_logs:
            self._add_log_entry_if_match(record)
