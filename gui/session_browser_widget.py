"""Session Browser Widget for viewing and opening client sessions.

This widget shows a list of sessions for the currently selected client,
with filtering by status and the ability to open existing sessions.

Cross-app integration: reads the Packer Tool's registry_index.json to show
packing status and worker info alongside analysis sessions. A QFileSystemWatcher
(with 30-second polling fallback for unreliable UNC paths) triggers automatic
refreshes when the Packer Tool updates the registry.
"""

import logging
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QPushButton, QComboBox, QGroupBox, QHeaderView, QMessageBox, QLineEdit
)
from PySide6.QtCore import Signal, Qt, QEvent, QFileSystemWatcher, QTimer
from PySide6.QtGui import QColor, QBrush

from shopify_tool.session_manager import SessionManager
from gui.wheel_ignore_combobox import WheelIgnoreComboBox
from gui.theme_manager import get_theme_manager
from gui.background_worker import BackgroundWorker


logger = logging.getLogger(__name__)


class SessionLoaderWorker(BackgroundWorker):
    """Background worker for loading session list and packing registry from file server."""

    def __init__(self, session_manager, client_id, status_filter=None):
        super().__init__()
        self.session_manager = session_manager
        self.client_id = client_id
        self.status_filter = status_filter

    def run(self):
        """Load sessions + packing registry in background thread."""
        try:
            if self._is_cancelled:
                return

            logger.debug(f"Loading sessions for CLIENT_{self.client_id}")
            sessions = self.session_manager.list_client_sessions(
                self.client_id,
                status_filter=self.status_filter
            )

            if self._is_cancelled:
                return

            # Attach packing summaries from Packer Tool registry (cached, fast)
            for session_info in sessions:
                session_name = session_info.get("session_name", "")
                if session_name:
                    session_info["packing_summary"] = (
                        self.session_manager.get_session_packing_summary(
                            self.client_id, session_name
                        )
                    )

            if not self._is_cancelled:
                self.finished_with_data.emit(sessions)
                logger.debug(f"Loaded {len(sessions)} sessions for CLIENT_{self.client_id}")

        except Exception as e:
            if not self._is_cancelled:
                logger.error(f"Error loading sessions: {e}", exc_info=True)
                self.error_occurred.emit(str(e))


class RegistryRefreshWorker(BackgroundWorker):
    """Lightweight background worker that only re-reads the packing registry.

    Used for the auto-refresh path when only registry_index.json changes —
    avoids a full session list reload and preserves scroll/selection state.
    """

    def __init__(self, session_manager, client_id, session_names):
        super().__init__()
        self.session_manager = session_manager
        self.client_id = client_id
        self.session_names = session_names  # list of session names currently in table

    def run(self):
        try:
            if self._is_cancelled:
                return
            summaries = {}
            for name in self.session_names:
                if self._is_cancelled:
                    return
                summaries[name] = self.session_manager.get_session_packing_summary(
                    self.client_id, name
                )
            if not self._is_cancelled:
                self.finished_with_data.emit(summaries)
        except Exception as e:
            if not self._is_cancelled:
                logger.debug(f"Registry refresh error: {e}")
                self.error_occurred.emit(str(e))


class SessionBrowserWidget(QWidget):
    """Widget for browsing and opening client sessions.

    Provides:
    - Table showing list of sessions with key info (including packing status from Packer Tool)
    - Status filter (all/active/completed)
    - "Refresh" button to reload sessions
    - Double-click or "Open Session" to load a session
    - Auto-refresh via QFileSystemWatcher when Packer Tool updates registry_index.json

    Uses async loading via BackgroundWorker to keep UI responsive during
    slow file server operations.

    Signals:
        session_selected: Emitted when user wants to open a session (session_path: str)
    """

    session_selected = Signal(str)  # Emits session_path

    # Class variable for testing - set to False to disable async loading in tests
    USE_ASYNC = True

    # Polling interval (ms) — fallback when QFileSystemWatcher misses UNC events
    _POLL_INTERVAL_MS = 30_000

    def __init__(self, session_manager: SessionManager, parent=None):
        super().__init__(parent)
        self.session_manager = session_manager
        self.current_client_id = None
        self.sessions_data = []
        self.worker = None          # session loader worker
        self.registry_worker = None  # lightweight registry refresh worker

        # File watching
        self._file_watcher = QFileSystemWatcher(self)
        self._file_watcher.fileChanged.connect(self._on_file_changed)
        self._file_watcher.directoryChanged.connect(self._on_directory_changed)

        # Debounce timer — coalesce rapid watcher events
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(2000)
        self._debounce_timer.timeout.connect(self._on_watch_debounced)
        self._registry_changed = False
        self._sessions_dir_changed = False

        # Polling fallback — fires every 30s regardless of watcher
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(self._POLL_INTERVAL_MS)
        self._poll_timer.timeout.connect(self._on_poll_tick)

        self._init_ui()
        logger.info("SessionBrowserWidget initialized")

    def _init_ui(self):
        """Initialize the UI components."""
        main_layout = QVBoxLayout(self)

        group = QGroupBox("Existing Sessions")
        group_layout = QVBoxLayout(group)

        # Filter and actions bar
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Status:"))

        self.status_filter = WheelIgnoreComboBox()
        self.status_filter.addItems(["All", "Active", "Completed", "Abandoned", "Archived"])
        self.status_filter.setToolTip("Filter sessions by status")
        self.status_filter.currentTextChanged.connect(self._apply_filter)
        filter_layout.addWidget(self.status_filter)

        filter_layout.addStretch()

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setToolTip("Reload sessions from server")
        self.refresh_btn.clicked.connect(self.refresh_sessions)
        filter_layout.addWidget(self.refresh_btn)

        group_layout.addLayout(filter_layout)

        # Sessions table — 9 columns
        self.sessions_table = QTableWidget()
        self.sessions_table.setColumnCount(9)
        self.sessions_table.setHorizontalHeaderLabels([
            "Session Name",  # 0
            "Created",       # 1
            "Status",        # 2
            "Orders",        # 3
            "Items",         # 4
            "Packing Lists", # 5
            "Packed",        # 6  ← Packer Tool data
            "Packer",        # 7  ← Packer Tool data
            "Comments",      # 8
        ])
        self.sessions_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.sessions_table.setSelectionMode(QTableWidget.SingleSelection)
        self.sessions_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.sessions_table.doubleClicked.connect(self._on_session_double_clicked)
        self.sessions_table.setSortingEnabled(True)

        header = self.sessions_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(0, 150)  # Session Name
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(1, 150)  # Created
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(2, 100)  # Status
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(3, 70)   # Orders
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(4, 70)   # Items
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(5, 100)  # Packing Lists
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(6, 90)   # Packed
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(7, 100)  # Packer
        header.setSectionResizeMode(8, QHeaderView.ResizeMode.Stretch)  # Comments

        group_layout.addWidget(self.sessions_table)

        # Action buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.open_btn = QPushButton("Open Selected Session")
        self.open_btn.setToolTip("Load the selected session")
        self.open_btn.clicked.connect(self._on_open_clicked)
        self.open_btn.setEnabled(False)
        button_layout.addWidget(self.open_btn)

        group_layout.addLayout(button_layout)
        main_layout.addWidget(group)

        self.sessions_table.viewport().installEventFilter(self)
        self.sessions_table.clicked.connect(lambda _: self._on_selection_changed())
        self.sessions_table.currentItemChanged.connect(self._on_selection_changed)

    # ------------------------------------------------------------------
    # Client selection + file watching
    # ------------------------------------------------------------------

    def set_client(self, client_id: str, auto_refresh: bool = True):
        """Set the client to show sessions for."""
        if client_id != self.current_client_id:
            self.current_client_id = client_id
            self._update_watchers(client_id)
            if auto_refresh:
                self.refresh_sessions()

    def _update_watchers(self, client_id: str):
        """Update QFileSystemWatcher paths for the new client.

        Only watches registry_index.json (Packer Tool file). The sessions
        directory is intentionally NOT watched — our own index writes would
        trigger directoryChanged and cause an infinite refresh loop.
        New sessions from other PCs are picked up by the 30-second poll timer.
        """
        # Remove old watched paths
        watched_files = self._file_watcher.files()
        watched_dirs = self._file_watcher.directories()
        if watched_files:
            self._file_watcher.removePaths(watched_files)
        if watched_dirs:
            self._file_watcher.removePaths(watched_dirs)

        if not client_id:
            self._poll_timer.stop()
            return

        sm = self.session_manager
        registry_path = str(sm._get_registry_path(client_id))

        # Only watch the Packer Tool registry file (watcher silently ignores
        # paths that don't exist yet — that's fine, poll timer is the fallback)
        self._file_watcher.addPath(registry_path)

        self._poll_timer.start()
        logger.debug(f"File watcher updated for CLIENT_{client_id}")

    def _on_file_changed(self, path: str):
        """Called when a watched file changes."""
        sm = self.session_manager
        if self.current_client_id:
            registry_path = str(sm._get_registry_path(self.current_client_id))
            if path == registry_path:
                # Re-add the path — some editors/writers remove and recreate the file
                self._file_watcher.addPath(path)
                self._registry_changed = True
                self._debounce_timer.start()

    def _on_directory_changed(self, path: str):
        """Called when a watched directory changes. Not currently used — sessions
        directory is not watched to avoid an index-write → refresh feedback loop."""

    def _on_watch_debounced(self):
        """Fires after debounce — lightweight packing-columns refresh."""
        self._registry_changed = False
        self._sessions_dir_changed = False
        if self.sessions_data:
            logger.debug("Registry changed — refreshing packing columns")
            self._refresh_packing_columns()

    def _on_poll_tick(self):
        """30-second polling fallback — only triggers a registry refresh if the
        debounce timer is not already running (watcher already handled it)."""
        if not self._debounce_timer.isActive() and self.current_client_id and self.sessions_data:
            self._registry_changed = True
            self._debounce_timer.start()

    def _refresh_packing_columns(self):
        """Lightweight refresh: re-read packing registry and update columns 6-7 only."""
        if not self.current_client_id or not self.sessions_data:
            return

        if self.registry_worker is not None:
            self.registry_worker.cleanup()
            self.registry_worker = None

        session_names = [s.get("session_name", "") for s in self.sessions_data]
        self.registry_worker = RegistryRefreshWorker(
            self.session_manager, self.current_client_id, session_names
        )
        self.registry_worker.finished_with_data.connect(self._on_registry_refreshed)
        self.registry_worker.start()

    def _on_registry_refreshed(self, summaries: dict):
        """Update packing columns in-place without rebuilding the full table."""
        if self.sessions_table is None:
            return
        self.sessions_table.setSortingEnabled(False)
        for row, session_info in enumerate(self.sessions_data):
            name = session_info.get("session_name", "")
            summary = summaries.get(name)
            if summary:
                session_info["packing_summary"] = summary
                self._update_packing_cells(row, summary)
        self.sessions_table.setSortingEnabled(True)

    # ------------------------------------------------------------------
    # Session loading (full)
    # ------------------------------------------------------------------

    def refresh_sessions(self):
        """Reload sessions from the session manager."""
        if not self.current_client_id:
            self.sessions_table.setRowCount(0)
            return

        if not self.USE_ASYNC:
            self._do_refresh_sync()
            return

        if self.worker is not None:
            self.worker.cleanup()
            self.worker = None

        self.sessions_table.setRowCount(0)
        self.sessions_table.setEnabled(False)
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.setText("Loading...")

        status_filter = self.status_filter.currentText().lower()
        if status_filter == "all":
            status_filter = None

        self.worker = SessionLoaderWorker(
            self.session_manager,
            self.current_client_id,
            status_filter
        )
        self.worker.finished_with_data.connect(self._on_sessions_loaded)
        self.worker.error_occurred.connect(self._on_load_error)
        self.worker.start()
        logger.debug("Session loading worker started")

    def _do_refresh_sync(self):
        """Synchronous refresh fallback (for tests)."""
        try:
            status_filter = self.status_filter.currentText().lower()
            if status_filter == "all":
                status_filter = None

            sessions = self.session_manager.list_client_sessions(
                self.current_client_id,
                status_filter=status_filter
            )
            for session_info in sessions:
                name = session_info.get("session_name", "")
                if name:
                    session_info["packing_summary"] = (
                        self.session_manager.get_session_packing_summary(
                            self.current_client_id, name
                        )
                    )
            self.sessions_data = sessions
            self._populate_table()
            logger.info(f"Loaded {len(self.sessions_data)} sessions (sync mode)")
        except Exception as e:
            logger.error(f"Failed to load sessions: {e}", exc_info=True)
            QMessageBox.warning(self, "Error", f"Failed to load sessions:\n{str(e)}")

    def _on_sessions_loaded(self, sessions_data):
        """Handle loaded data in main thread (safe for UI updates)."""
        if self.sessions_table is None:
            return

        logger.debug(f"Received {len(sessions_data)} sessions from worker")
        self.sessions_data = sessions_data
        self._populate_table()

        self.sessions_table.setEnabled(True)
        self.refresh_btn.setEnabled(True)
        self.refresh_btn.setText("Refresh")

    def _on_load_error(self, error_msg):
        """Handle errors in main thread."""
        logger.error(f"Session load error: {error_msg}")
        self.sessions_table.setEnabled(True)
        self.refresh_btn.setEnabled(True)
        self.refresh_btn.setText("Refresh")
        QMessageBox.warning(
            self,
            "Error Loading Sessions",
            f"Failed to load sessions:\n{error_msg}"
        )

    # ------------------------------------------------------------------
    # Table rendering
    # ------------------------------------------------------------------

    def _populate_table(self):
        """Populate the table with sessions data."""
        self.sessions_table.setSortingEnabled(False)
        self.sessions_table.setRowCount(len(self.sessions_data))

        for row, session_info in enumerate(self.sessions_data):
            session_path = session_info.get("session_path", "")
            stats = session_info.get("statistics", {})

            # Col 0: Session name (stores session_path in UserRole for safe row lookup)
            name_item = QTableWidgetItem(session_info.get("session_name", ""))
            name_item.setData(Qt.UserRole, session_path)
            self.sessions_table.setItem(row, 0, name_item)

            # Col 1: Created at
            created_at = session_info.get("created_at", "")
            if created_at:
                try:
                    dt = datetime.fromisoformat(created_at)
                    created_str = dt.strftime("%Y-%m-%d %H:%M")
                except (ValueError, TypeError):
                    created_str = created_at
            else:
                created_str = ""
            created_item = QTableWidgetItem(created_str)
            self.sessions_table.setItem(row, 1, created_item)

            # Col 2: Status (editable combobox)
            status = session_info.get("status", "active")
            status_combo = WheelIgnoreComboBox()
            status_combo.addItems(["Active", "Completed", "Abandoned", "Archived"])
            status_combo.setCurrentText(status.capitalize())
            if status == "active":
                status_combo.setStyleSheet("QComboBox { color: blue; }")
            elif status == "completed":
                status_combo.setStyleSheet("QComboBox { color: darkgreen; }")
            elif status == "abandoned":
                status_combo.setStyleSheet("QComboBox { color: red; }")
            elif status == "archived":
                theme = get_theme_manager().get_current_theme()
                status_combo.setStyleSheet(f"QComboBox {{ color: {theme.text_secondary}; }}")
            status_combo.currentTextChanged.connect(
                lambda new_status, path=session_path: self._on_status_changed(path, new_status)
            )
            self.sessions_table.setCellWidget(row, 2, status_combo)

            # Col 3: Orders
            orders_count = stats.get("total_orders", 0)
            orders_item = QTableWidgetItem(str(orders_count) if orders_count > 0 else "N/A")
            orders_item.setTextAlignment(Qt.AlignCenter)
            self.sessions_table.setItem(row, 3, orders_item)

            # Col 4: Items
            items_count = stats.get("total_items", 0)
            items_item = QTableWidgetItem(str(items_count) if items_count > 0 else "N/A")
            items_item.setTextAlignment(Qt.AlignCenter)
            self.sessions_table.setItem(row, 4, items_item)

            # Col 5: Packing Lists
            packing_lists_count = stats.get("packing_lists_count", 0)
            packing_lists_item = QTableWidgetItem(str(packing_lists_count))
            packing_lists_item.setTextAlignment(Qt.AlignCenter)
            self.sessions_table.setItem(row, 5, packing_lists_item)

            # Cols 6-7: Packing data from Packer Tool registry
            summary = session_info.get("packing_summary")
            self._update_packing_cells(row, summary)

            # Col 8: Comments (editable)
            comments = session_info.get("comments", "")
            comments_edit = QLineEdit(comments)
            comments_edit.setPlaceholderText("Add comments...")
            comments_edit.editingFinished.connect(
                lambda path=session_path, widget=comments_edit: self._on_comments_changed(path, widget.text())
            )
            self.sessions_table.setCellWidget(row, 8, comments_edit)

            # Tooltip
            packing_lists_str = ", ".join(stats.get("packing_lists", [])) or "None"
            pack_info = ""
            if summary and summary.get("pack_status") != "not_started":
                pack_info = (
                    f"\nPacked: {summary['packed_orders']}/{summary['total_orders']} orders"
                    f"\nPackers: {', '.join(summary.get('worker_names', [])) or '—'}"
                )
            tooltip = (
                f"Session: {session_info.get('session_name', '')}\n"
                f"Created: {created_str}\n"
                f"Status: {status.capitalize()}\n"
                f"Orders: {orders_count if orders_count > 0 else 'N/A'}\n"
                f"Items: {items_count if items_count > 0 else 'N/A'}\n"
                f"Packing Lists ({packing_lists_count}): {packing_lists_str}"
                f"{pack_info}\n"
                f"Comments: {comments if comments else 'None'}"
            )
            for col in range(9):
                item = self.sessions_table.item(row, col)
                if item:
                    item.setToolTip(tooltip)

        self.sessions_table.setSortingEnabled(True)
        self.sessions_table.sortItems(1, Qt.DescendingOrder)

    def _update_packing_cells(self, row: int, summary: dict):
        """Update columns 6 (Packed) and 7 (Packer) for a single row."""
        theme = get_theme_manager().get_current_theme()

        if not summary or summary.get("pack_status") == "not_started":
            packed_item = QTableWidgetItem("-")
            packer_item = QTableWidgetItem("-")
        else:
            packed = summary.get("packed_orders", 0)
            total = summary.get("total_orders", 0)
            pack_status = summary.get("pack_status", "not_started")
            workers = summary.get("worker_names", [])

            packed_text = f"{packed}/{total}" if total > 0 else "-"
            packed_item = QTableWidgetItem(packed_text)
            packed_item.setTextAlignment(Qt.AlignCenter)

            if pack_status == "completed":
                packed_item.setForeground(QBrush(QColor(theme.accent_green)))
            elif pack_status == "in_progress":
                packed_item.setForeground(QBrush(QColor(theme.accent_blue)))
            elif pack_status in ("partial", "available"):
                packed_item.setForeground(QBrush(QColor(theme.accent_orange)))

            packer_item = QTableWidgetItem(", ".join(workers) if workers else "-")

        packed_item.setTextAlignment(Qt.AlignCenter)
        packer_item.setTextAlignment(Qt.AlignCenter)
        self.sessions_table.setItem(row, 6, packed_item)
        self.sessions_table.setItem(row, 7, packer_item)

    # ------------------------------------------------------------------
    # Interaction
    # ------------------------------------------------------------------

    def _apply_filter(self):
        self.refresh_sessions()

    def _on_selection_changed(self, current=None, previous=None):
        has_selection = self.sessions_table.currentRow() >= 0
        self.open_btn.setEnabled(has_selection)

    def _on_session_double_clicked(self, index):
        self._open_selected_session()

    def _on_open_clicked(self):
        self._open_selected_session()

    def _open_selected_session(self):
        """Open the currently selected session.

        Uses UserRole data from the name cell (col 0) for the session path,
        so sorting does not break the row→session mapping.
        """
        current_row = self.sessions_table.currentRow()
        if current_row < 0:
            return
        name_item = self.sessions_table.item(current_row, 0)
        session_path = name_item.data(Qt.UserRole) if name_item else ""
        if session_path:
            logger.info(f"Opening session: {session_path}")
            self.session_selected.emit(session_path)
        else:
            QMessageBox.warning(self, "Error", "Selected session has no valid path.")

    def get_selected_session_path(self) -> str:
        """Get the path of the currently selected session."""
        current_row = self.sessions_table.currentRow()
        if current_row < 0:
            return ""
        name_item = self.sessions_table.item(current_row, 0)
        return name_item.data(Qt.UserRole) if name_item else ""

    def _on_status_changed(self, session_path: str, new_status: str):
        try:
            self.session_manager.update_session_status(session_path, new_status.lower())
            logger.info(f"Updated session status: {session_path} -> {new_status.lower()}")
        except Exception as e:
            logger.error(f"Failed to update status: {e}")
            QMessageBox.critical(self, "Error", f"Failed to update status:\n{str(e)}")
            self.refresh_sessions()

    def _on_comments_changed(self, session_path: str, comments: str):
        try:
            self.session_manager.update_session_info(session_path, {"comments": comments})
            logger.info(f"Updated session comments: {session_path}")
        except Exception as e:
            logger.error(f"Failed to update comments: {e}")

    def eventFilter(self, watched, event):
        """Block hover-only mouse moves on the table viewport."""
        if watched is self.sessions_table.viewport():
            if event.type() == QEvent.Type.MouseMove and not event.buttons():
                return True
        return super().eventFilter(watched, event)

    def closeEvent(self, event):
        """Cleanup workers and timers on close."""
        self._poll_timer.stop()
        self._debounce_timer.stop()
        if self.worker is not None:
            self.worker.cleanup()
            self.worker = None
        if self.registry_worker is not None:
            self.registry_worker.cleanup()
            self.registry_worker = None
        super().closeEvent(event)
