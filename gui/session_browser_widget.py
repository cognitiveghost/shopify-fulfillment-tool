"""Session Browser Widget for viewing and opening client sessions.

This widget shows a list of sessions for the currently selected client,
with filtering by status and the ability to open existing sessions.
"""

import logging
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QComboBox,
    QGroupBox,
    QHeaderView,
    QMessageBox,
    QLineEdit,
)
from PySide6.QtCore import Signal, Qt, QEvent

from shopify_tool.session_manager import SessionManager
from gui.wheel_ignore_combobox import WheelIgnoreComboBox
from gui.theme_manager import get_theme_manager
from gui.background_worker import BackgroundWorker


logger = logging.getLogger(__name__)


class SessionLoaderWorker(BackgroundWorker):
    """Background worker for loading session list from file server.

    This worker performs the potentially slow I/O operation of listing
    and parsing session metadata files from the network file server.
    """

    def __init__(self, session_manager, client_id, status_filter=None):
        """Initialize session loader worker.

        Args:
            session_manager: SessionManager instance
            client_id: Client ID to load sessions for
            status_filter: Optional status filter (e.g., "active", "completed")
        """
        super().__init__()
        self.session_manager = session_manager
        self.client_id = client_id
        self.status_filter = status_filter

    def run(self):
        """Execute in background thread - load sessions from file server."""
        try:
            if self._is_cancelled:
                return

            logger.debug(f"Loading sessions for CLIENT_{self.client_id}")

            # This is the potentially slow I/O operation (200-1000ms on slow UNC)
            sessions = self.session_manager.list_client_sessions(
                self.client_id, status_filter=self.status_filter
            )

            if not self._is_cancelled:
                self.finished_with_data.emit(sessions)
                logger.debug(
                    f"Loaded {len(sessions)} sessions for CLIENT_{self.client_id}"
                )

        except Exception as e:
            if not self._is_cancelled:
                logger.error(f"Error loading sessions: {e}", exc_info=True)
                self.error_occurred.emit(str(e))


class SessionBrowserWidget(QWidget):
    """Widget for browsing and opening client sessions.

    Provides:
    - Table showing list of sessions with key info
    - Status filter (all/active/completed)
    - "Refresh" button to reload sessions
    - Double-click or "Open Session" to load a session
    - Multi-select + "Export Combined Stock" for 2+ sessions

    Uses async loading via BackgroundWorker to keep UI responsive during
    slow file server operations.

    Signals:
        session_selected: Emitted when user wants to open a session (session_path: str)
        multi_export_requested: Emitted with list of session_path strings for combined export
    """

    session_selected = Signal(str)  # Emits session_path
    multi_export_requested = Signal(list)  # Emits list of session_path strings

    # Class variable for testing - set to False to disable async loading in tests
    USE_ASYNC = True

    def __init__(self, session_manager: SessionManager, parent=None):
        super().__init__(parent)
        self.session_manager = session_manager
        self.current_client_id = None
        self.sessions_data = []
        self.worker = None  # Track active background worker

        self._init_ui()
        logger.info("SessionBrowserWidget initialized")

    def _init_ui(self):
        """Initialize the UI components."""
        main_layout = QVBoxLayout(self)

        # Create group box
        group = QGroupBox("Existing Sessions")
        group_layout = QVBoxLayout(group)

        # Filter and actions bar
        filter_layout = QHBoxLayout()

        filter_layout.addWidget(QLabel("Status:"))

        self.status_filter = WheelIgnoreComboBox()
        self.status_filter.addItems(
            ["All", "Active", "Completed", "Abandoned", "Archived"]
        )
        self.status_filter.setToolTip("Filter sessions by status")
        self.status_filter.currentTextChanged.connect(self._apply_filter)
        filter_layout.addWidget(self.status_filter)

        filter_layout.addStretch()

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setToolTip("Reload sessions from server")
        self.refresh_btn.clicked.connect(self.refresh_sessions)
        filter_layout.addWidget(self.refresh_btn)

        group_layout.addLayout(filter_layout)

        # Sessions table
        self.sessions_table = QTableWidget()
        self.sessions_table.setColumnCount(7)
        self.sessions_table.setHorizontalHeaderLabels(
            [
                "Session Name",
                "Created",
                "Status",
                "Orders",
                "Items",
                "Packing Lists",
                "Comments",
            ]
        )
        self.sessions_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.sessions_table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.sessions_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.sessions_table.doubleClicked.connect(self._on_session_double_clicked)
        self.sessions_table.setSortingEnabled(True)

        # Set column widths
        header = self.sessions_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(0, 150)  # Session Name
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(1, 150)  # Created
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(2, 100)  # Status
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(3, 80)  # Orders
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(4, 80)  # Items
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(5, 120)  # Packing Lists
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)  # Comments

        group_layout.addWidget(self.sessions_table)

        # Action buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.combined_export_btn = QPushButton("Export Combined Stock")
        self.combined_export_btn.setEnabled(False)
        self.combined_export_btn.setToolTip(
            "Select 2+ sessions to export a combined stock summary"
        )
        self.combined_export_btn.clicked.connect(self._on_combined_export)
        button_layout.addWidget(self.combined_export_btn)

        self.open_btn = QPushButton("Open Selected Session")
        self.open_btn.setToolTip("Load the selected session")
        self.open_btn.clicked.connect(self._on_open_clicked)
        self.open_btn.setEnabled(False)
        button_layout.addWidget(self.open_btn)

        group_layout.addLayout(button_layout)

        main_layout.addWidget(group)

        # Block mouse-move-only events on the viewport so Qt does not change the
        # current/selected row while the user is just hovering (no button pressed).
        # Without this, cell widgets (ComboBox, LineEdit) forward hover events that
        # cause the table to visually jump selection to whichever row the cursor is over.
        self.sessions_table.viewport().installEventFilter(self)

        # Enable open/export buttons on actual click or keyboard navigation.
        self.sessions_table.clicked.connect(lambda _: self._on_selection_changed())
        self.sessions_table.currentItemChanged.connect(self._on_selection_changed)
        self.sessions_table.selectionModel().selectionChanged.connect(
            lambda *_: self._on_selection_changed()
        )

    def set_client(self, client_id: str, auto_refresh: bool = True):
        """Set the client to show sessions for.

        Args:
            client_id: Client ID to load sessions for
            auto_refresh: If False, skip automatic refresh (caller will handle it)
        """
        if client_id != self.current_client_id:
            self.current_client_id = client_id
            if auto_refresh:
                self.refresh_sessions()

    def refresh_sessions(self):
        """Reload sessions from the session manager."""
        if not self.current_client_id:
            self.sessions_table.setRowCount(0)
            logger.debug("No client selected, clearing sessions table")
            return

        # Check if using async mode (can be disabled for tests)
        if not self.USE_ASYNC:
            # Synchronous fallback for tests
            self._do_refresh_sync()
            return

        # === ASYNC MODE ===

        # 1. Cleanup existing worker FIRST (critical to prevent crashes!)
        if self.worker is not None:
            self.worker.cleanup()
            self.worker = None

        # 2. Show loading state immediately
        self.sessions_table.setRowCount(0)  # Clear table
        self.sessions_table.setEnabled(False)
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.setText("Loading...")

        # 3. Get status filter
        status_filter = self.status_filter.currentText().lower()
        if status_filter == "all":
            status_filter = None

        # 4. Create and start new worker
        self.worker = SessionLoaderWorker(
            self.session_manager, self.current_client_id, status_filter
        )

        # 5. Connect signals
        self.worker.finished_with_data.connect(self._on_sessions_loaded)
        self.worker.error_occurred.connect(self._on_load_error)

        # 6. Start background work
        self.worker.start()
        logger.debug("Session loading worker started")

    def _do_refresh_sync(self):
        """Synchronous refresh fallback (for tests).

        This is the old blocking behavior, kept for test compatibility.
        """
        try:
            # Get status filter
            status_filter = self.status_filter.currentText().lower()
            if status_filter == "all":
                status_filter = None

            # Load sessions (blocks UI in sync mode)
            self.sessions_data = self.session_manager.list_client_sessions(
                self.current_client_id, status_filter=status_filter
            )

            # Populate table
            self._populate_table()

            logger.info(f"Loaded {len(self.sessions_data)} sessions (sync mode)")

        except Exception as e:
            logger.error(f"Failed to load sessions: {e}", exc_info=True)
            QMessageBox.warning(self, "Error", f"Failed to load sessions:\n{str(e)}")

    def _on_sessions_loaded(self, sessions_data):
        """Handle loaded data in main thread (safe for UI updates)."""
        # Guard: widget may have been closed while worker was still running
        if not self.isVisible() or self.sessions_table is None:
            logger.debug("Widget closed before sessions loaded — ignoring result")
            return

        logger.debug(f"Received {len(sessions_data)} sessions from worker")
        self.sessions_data = sessions_data
        self._populate_table()

        # Restore UI state
        self.sessions_table.setEnabled(True)
        self.refresh_btn.setEnabled(True)
        self.refresh_btn.setText("Refresh")

    def _on_load_error(self, error_msg):
        """Handle errors in main thread."""
        logger.error(f"Session load error: {error_msg}")

        # Restore UI
        self.sessions_table.setEnabled(True)
        self.refresh_btn.setEnabled(True)
        self.refresh_btn.setText("Refresh")

        # Show error to user
        QMessageBox.warning(
            self, "Error Loading Sessions", f"Failed to load sessions:\n{error_msg}"
        )

    def _populate_table(self):
        """Populate the table with sessions data."""
        self.sessions_table.setSortingEnabled(False)
        self.sessions_table.setRowCount(len(self.sessions_data))

        for row, session_info in enumerate(self.sessions_data):
            session_path = session_info.get("session_path", "")
            stats = session_info.get("statistics", {})

            # Column 0: Session name
            name_item = QTableWidgetItem(session_info.get("session_name", ""))
            self.sessions_table.setItem(row, 0, name_item)

            # Column 1: Created at
            created_at = session_info.get("created_at", "")
            if created_at:
                try:
                    dt = datetime.fromisoformat(created_at)
                    created_str = dt.strftime("%Y-%m-%d %H:%M")
                except (ValueError, TypeError) as e:
                    # Invalid datetime format, use original string
                    created_str = created_at
            else:
                created_str = ""
            created_item = QTableWidgetItem(created_str)
            self.sessions_table.setItem(row, 1, created_item)

            # Column 2: Status (EDITABLE COMBOBOX)
            status = session_info.get("status", "active")
            status_combo = WheelIgnoreComboBox()
            status_combo.addItems(["Active", "Completed", "Abandoned", "Archived"])
            status_combo.setCurrentText(status.capitalize())
            # Color code by status
            if status == "active":
                status_combo.setStyleSheet("QComboBox { color: blue; }")
            elif status == "completed":
                status_combo.setStyleSheet("QComboBox { color: darkgreen; }")
            elif status == "abandoned":
                status_combo.setStyleSheet("QComboBox { color: red; }")
            elif status == "archived":
                theme = get_theme_manager().get_current_theme()
                status_combo.setStyleSheet(
                    f"QComboBox {{ color: {theme.text_secondary}; }}"
                )
            status_combo.currentTextChanged.connect(
                lambda new_status, path=session_path: self._on_status_changed(
                    path, new_status
                )
            )
            self.sessions_table.setCellWidget(row, 2, status_combo)

            # Column 3: Orders (READ-ONLY)
            orders_count = stats.get("total_orders", 0)
            orders_item = QTableWidgetItem(
                str(orders_count) if orders_count > 0 else "N/A"
            )
            orders_item.setTextAlignment(Qt.AlignCenter)
            self.sessions_table.setItem(row, 3, orders_item)

            # Column 4: Items (READ-ONLY)
            items_count = stats.get("total_items", 0)
            items_item = QTableWidgetItem(
                str(items_count) if items_count > 0 else "N/A"
            )
            items_item.setTextAlignment(Qt.AlignCenter)
            self.sessions_table.setItem(row, 4, items_item)

            # Column 5: Packing Lists (READ-ONLY)
            packing_lists_count = stats.get("packing_lists_count", 0)
            packing_lists_item = QTableWidgetItem(str(packing_lists_count))
            packing_lists_item.setTextAlignment(Qt.AlignCenter)
            self.sessions_table.setItem(row, 5, packing_lists_item)

            # Column 6: Comments (EDITABLE LINE EDIT)
            comments = session_info.get("comments", "")
            comments_edit = QLineEdit(comments)
            comments_edit.setPlaceholderText("Add comments...")
            comments_edit.editingFinished.connect(
                lambda path=session_path,
                widget=comments_edit: self._on_comments_changed(path, widget.text())
            )
            self.sessions_table.setCellWidget(row, 6, comments_edit)

            # Build tooltip with full info
            packing_lists_str = ", ".join(stats.get("packing_lists", [])) or "None"
            tooltip = f"""Session: {session_info.get("session_name", "")}
Created: {created_str}
Status: {status.capitalize()}
Orders: {orders_count if orders_count > 0 else "N/A"}
Items: {items_count if items_count > 0 else "N/A"}
Packing Lists ({packing_lists_count}): {packing_lists_str}
Comments: {comments if comments else "None"}"""

            # Apply tooltip to all cells in row
            for col in range(7):
                item = self.sessions_table.item(row, col)
                if item:
                    item.setToolTip(tooltip)

        self.sessions_table.setSortingEnabled(True)
        # Sort by created date descending (newest first)
        self.sessions_table.sortItems(1, Qt.DescendingOrder)

    def _apply_filter(self):
        """Apply the status filter."""
        self.refresh_sessions()

    def _on_selection_changed(self, current=None, previous=None):
        """Handle table selection change (fires on click/keyboard, not hover)."""
        has_selection = self.sessions_table.currentRow() >= 0
        self.open_btn.setEnabled(has_selection)
        selected_count = len(self.sessions_table.selectionModel().selectedRows())
        self.combined_export_btn.setEnabled(selected_count >= 2)

    def _on_combined_export(self):
        """Emit multi_export_requested with session paths for all selected rows."""
        selected_rows = self.sessions_table.selectionModel().selectedRows()
        session_paths = []
        for idx in selected_rows:
            row = idx.row()
            if row < len(self.sessions_data):
                path = self.sessions_data[row].get("session_path")
                if path:
                    session_paths.append(path)
        if len(session_paths) >= 2:
            self.multi_export_requested.emit(session_paths)

    def _on_session_double_clicked(self, index):
        """Handle double-click on session."""
        self._open_selected_session()

    def _on_open_clicked(self):
        """Handle "Open Session" button click."""
        self._open_selected_session()

    def _open_selected_session(self):
        """Open the currently selected session."""
        current_row = self.sessions_table.currentRow()
        if current_row < 0 or current_row >= len(self.sessions_data):
            return

        session_info = self.sessions_data[current_row]
        session_path = session_info.get("session_path")

        if session_path:
            logger.info(f"Opening session: {session_path}")
            self.session_selected.emit(session_path)
        else:
            QMessageBox.warning(self, "Error", "Selected session has no valid path.")

    def get_selected_session_path(self) -> str:
        """Get the path of the currently selected session.

        Returns:
            str: Session path or empty string if none selected
        """
        current_row = self.sessions_table.currentRow()
        if current_row < 0 or current_row >= len(self.sessions_data):
            return ""

        session_info = self.sessions_data[current_row]
        return session_info.get("session_path", "")

    def _on_status_changed(self, session_path: str, new_status: str):
        """Handle status change in table.

        Args:
            session_path: Full path to session directory
            new_status: New status text (capitalized)
        """
        try:
            # Convert to lowercase for storage
            status = new_status.lower()

            # Update session_info.json
            self.session_manager.update_session_status(session_path, status)

            logger.info(f"Updated session status: {session_path} -> {status}")

        except Exception as e:
            logger.error(f"Failed to update status: {e}")
            QMessageBox.critical(self, "Error", f"Failed to update status:\n{str(e)}")
            # Revert to previous value
            self.refresh_sessions()

    def _on_comments_changed(self, session_path: str, comments: str):
        """Handle comments change in table.

        Args:
            session_path: Full path to session directory
            comments: New comments text
        """
        try:
            # Update session_info.json
            self.session_manager.update_session_info(
                session_path, {"comments": comments}
            )

            logger.info(f"Updated session comments: {session_path}")

        except Exception as e:
            logger.error(f"Failed to update comments: {e}")
            # Don't show error dialog for comments (less critical)
            # Just log the error

    def eventFilter(self, watched, event):
        """Block hover-only mouse moves on the table viewport.

        Prevents Qt from changing the selected row when the user moves the mouse
        over sessions without clicking. Only mouseMoveEvent with no button pressed
        is blocked — drag-selection (button held) still works normally.
        """
        if watched is self.sessions_table.viewport():
            if event.type() == QEvent.Type.MouseMove and not event.buttons():
                return True  # consume event — no selection change on hover
        return super().eventFilter(watched, event)

    def showEvent(self, event):
        """Refresh sessions when widget becomes visible.

        Args:
            event: Show event
        """
        super().showEvent(event)
        if self.current_client_id:
            self.refresh_sessions()

    def closeEvent(self, event):
        """Cleanup worker when widget closes.

        CRITICAL: This prevents crashes from worker still running after
        widget destruction (lesson from commit #216).

        Args:
            event: Close event
        """
        if self.worker is not None:
            logger.debug("Cleaning up session browser worker on widget close")
            self.worker.cleanup()
            self.worker = None
        super().closeEvent(event)
