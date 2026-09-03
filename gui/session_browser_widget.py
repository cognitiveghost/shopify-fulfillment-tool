"""Session Browser Widget for viewing and opening client sessions.

This widget shows a list of sessions for the currently selected client,
with filtering by status and the ability to open existing sessions.
"""

import logging
from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QMenu,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gui.background_worker import BackgroundWorker
from gui.components import ContextualSelectionBar, FilterBar
from gui.session_row_delegates import (
    ROLE_MANUAL,
    ROLE_TOKEN,
    STATUS_ROLES,
    PackingProgressDelegate,
    SessionStatusDelegate,
)
from gui.theme_manager import get_density_profile
from gui.wheel_ignore_combobox import WheelIgnoreComboBox
from shared.icons import icon
from shared.theme import on_theme_changed
from shopify_tool.session_lifecycle import derive_status_updates, packing_completion
from shopify_tool.session_manager import SessionManager

logger = logging.getLogger(__name__)


class _RatioSortItem(QTableWidgetItem):
    """Displays "packed/total" but sorts on the ratio behind it.

    QTableWidgetItem compares its DisplayRole, so the plain text form puts
    "10/12" above "2/3".
    """

    def __lt__(self, other):
        return self.data(Qt.UserRole) < other.data(Qt.UserRole)


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

            if self._is_cancelled:
                return

            sessions = self._sync_statuses(sessions)

            self.finished_with_data.emit(sessions)
            logger.debug(
                f"Loaded {len(sessions)} sessions for CLIENT_{self.client_id}"
            )

        except Exception as e:
            if not self._is_cancelled:
                logger.exception("Error loading sessions")
                self.error_occurred.emit(str(e))

    def _sync_statuses(self, sessions):
        """Apply automatic status changes, then reflect them into `sessions`.

        File I/O only -- this runs on a background thread and must never
        touch a widget. Failures are swallowed: a stale status is survivable,
        a session list that will not load is not.
        """
        # ponytail: the first refresh after this shipped clears the whole
        # backlog in one pass -- 41 of 42 sessions on the data this was built
        # against. It is one-time (the derive returns empty forever after) and
        # runs off the UI thread, so no progress UI or first-run prompt is
        # built. If it drags on the production share, bound the pass to the N
        # oldest sessions per refresh.
        try:
            updates = derive_status_updates(sessions, datetime.now().astimezone())
            if not updates:
                return sessions
            self.session_manager.apply_status_updates(self.client_id, updates)
            for session in sessions:
                new_status = updates.get(session.get("session_name"))
                if new_status:
                    session["status"] = new_status
        except Exception:
            logger.exception("Automatic session status sync failed; showing stored statuses")
        return sessions


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
        self._show_archived = False
        self._search = ""
        self._is_dirty = True  # forces one load on first show

        self._init_ui()
        logger.info("SessionBrowserWidget initialized")

    def _init_ui(self):
        """Initialize the UI components."""
        main_layout = QVBoxLayout(self)

        # No group box: regions separate by elevation and space (Phase 8 fault
        # #1). The NavRail destination already names this screen.
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(8)

        filter_layout = QHBoxLayout()

        self.filter_bar = FilterBar(self)
        self.filter_bar.search_field.setPlaceholderText("Search sessions")
        self.filter_bar.searchChanged.connect(self._on_search_changed)
        filter_layout.addWidget(self.filter_bar, 1)

        # Status is a server-side query -- it triggers a real refresh -- so it
        # is not the same kind of control as the search box and stays outside
        # it. Skipped: a dismissible filter chip; with one filter dimension it
        # would draw the same state twice. Add chips at a second dimension.
        self.status_filter = WheelIgnoreComboBox()
        self.status_filter.addItems(
            ["All", "Active", "Completed", "Abandoned", "Archived"]
        )
        self.status_filter.setToolTip("Filter sessions by status")
        self.status_filter.currentTextChanged.connect(self._apply_filter)
        filter_layout.addWidget(self.status_filter)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setToolTip("Reload sessions from server")
        self.refresh_btn.clicked.connect(self.refresh_sessions)
        filter_layout.addWidget(self.refresh_btn)

        self.show_archived_btn = QPushButton("Show Archived")
        self.show_archived_btn.setCheckable(True)
        self.show_archived_btn.setToolTip(
            "Show archived sessions (sessions are archived automatically after 30 days)"
        )
        self.show_archived_btn.toggled.connect(self._on_show_archived_toggled)
        filter_layout.addWidget(self.show_archived_btn)

        main_layout.addLayout(filter_layout)

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
                "Packing",
            ]
        )
        self.sessions_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.sessions_table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.sessions_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.sessions_table.doubleClicked.connect(self._on_session_double_clicked)
        self.sessions_table.setSortingEnabled(True)

        vertical = self.sessions_table.verticalHeader()
        # ponytail: read once. theme_manager has no density_changed signal, so a
        # desk<->floor switch lands on this table at next restart. Wire a signal
        # if a second painted table needs it.
        vertical.setDefaultSectionSize(get_density_profile().row_height)
        vertical.setVisible(False)

        self.sessions_table.setItemDelegateForColumn(2, SessionStatusDelegate(self))
        self.sessions_table.setItemDelegateForColumn(6, PackingProgressDelegate(self))

        header = self.sessions_table.horizontalHeader()
        for column, width in ((1, 150), (2, 130), (3, 80), (4, 80), (5, 120), (6, 130)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            header.resizeSection(column, width)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

        main_layout.addWidget(self.sessions_table)

        self.selection_bar = ContextualSelectionBar(self)

        self.status_btn = self.selection_bar.add_action("Status ▾")
        status_menu = QMenu(self.status_btn)
        for label in ("Active", "Completed", "Abandoned", "Archived"):
            status_menu.addAction(
                label,
                lambda _checked=False, value=label: self._apply_status_to_selection(value),
            )
        self.status_btn.setMenu(status_menu)
        self.status_btn.setToolTip("Set the status of every selected session")

        self.comment_btn = self.selection_bar.add_action(
            "Comment…", self._edit_comment_for_selection
        )
        self.comment_btn.setToolTip("Edit this session's comment")

        self.combined_export_btn = self.selection_bar.add_action(
            "Export Combined Stock", self._on_combined_export
        )
        self.combined_export_btn.setToolTip(
            "Select 2+ sessions to export a combined stock summary"
        )
        self.open_btn = self.selection_bar.add_action(
            "Open", self._on_open_clicked, role="primary"
        )
        self.open_btn.setToolTip("Load the selected session")

        main_layout.addWidget(self.selection_bar)

        # Enable open/export buttons on actual click or keyboard navigation.
        self.sessions_table.clicked.connect(lambda _: self._on_selection_changed())
        self.sessions_table.currentItemChanged.connect(self._on_selection_changed)
        self.sessions_table.selectionModel().selectionChanged.connect(
            lambda *_: self._on_selection_changed()
        )

        # A comment icon is a QIcon snapshot handed to a QTableWidgetItem, not
        # a live style -- it does not follow a toggle on its own. Re-running
        # the whole population pass is one connection for the widget's life,
        # rather than one per icon per refresh (which _populate_table() calls
        # on every keystroke in the search box).
        on_theme_changed(self, lambda _t: self._populate_table())

    def set_client(self, client_id: str, auto_refresh: bool = True):
        """Set the client to show sessions for.

        Args:
            client_id: Client ID to load sessions for
            auto_refresh: If False, skip the immediate refresh and let the next
                showEvent() pick up the dirty flag instead -- unless the widget
                is already visible right now, in which case there's no future
                showEvent to rescue it (the tab isn't changing), so it must
                refresh immediately or the table is left showing the previous
                client's sessions indefinitely.
        """
        if client_id != self.current_client_id:
            self.current_client_id = client_id
            self._is_dirty = True
            if auto_refresh or self.isVisible():
                self.refresh_sessions()

    def refresh_sessions(self):
        """Reload sessions from the session manager."""
        self._is_dirty = False
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
        Note it does NOT run SessionLoaderWorker._sync_statuses, so a test
        written against sync mode does not exercise automatic status
        derivation at all -- test that against the worker directly.
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
            logger.exception("Failed to load sessions")
            QMessageBox.warning(self, "Error", f"Failed to load sessions:\n{e!s}")

    def _on_sessions_loaded(self, sessions_data):
        """Handle loaded data in main thread (safe for UI updates)."""
        # Guard: widget may have been closed, or merely hidden (e.g. the user
        # switched tabs while the file-server load was in flight).
        if not self.isVisible() or self.sessions_table is None:
            logger.debug("Widget not visible when sessions loaded — will retry on next show")
            # refresh_sessions() already cleared _is_dirty when the load started;
            # re-mark it so the next showEvent() retries instead of leaving the
            # table/button stuck in the "Loading..." state forever.
            self._is_dirty = True
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
        # Archived sessions are hidden unless asked for. When the user picks
        # "Archived" in the status filter the server-side query already
        # returned only archived rows, so hiding them here would leave an
        # empty table.
        showing_archived_explicitly = self.status_filter.currentText().lower() == "archived"
        if self._show_archived or showing_archived_explicitly:
            visible_sessions = list(self.sessions_data)
        else:
            visible_sessions = [
                s for s in self.sessions_data if s.get("status") != "archived"
            ]
        if self._search:
            visible_sessions = [
                s
                for s in visible_sessions
                if self._search in s.get("session_name", "").lower()
            ]
        total = len(self.sessions_data)
        shown = len(visible_sessions)
        self.filter_bar.set_count(
            f"{shown} sessions" if shown == total else f"{shown} of {total} sessions"
        )
        header = self.sessions_table.horizontalHeader()
        sort_column = header.sortIndicatorSection()
        sort_order = header.sortIndicatorOrder()
        self.sessions_table.setSortingEnabled(False)
        self.sessions_table.setRowCount(len(visible_sessions))

        for row, session_info in enumerate(visible_sessions):
            session_path = session_info.get("session_path", "")
            stats = session_info.get("statistics", {})
            comments = session_info.get("comments", "")

            # Column 0: Session name
            name_item = QTableWidgetItem(session_info.get("session_name", ""))
            name_item.setData(Qt.UserRole, session_path)
            if comments:
                name_item.setIcon(icon("message-square"))
            self.sessions_table.setItem(row, 0, name_item)

            # Column 1: Created at
            created_at = session_info.get("created_at", "")
            if created_at:
                try:
                    dt = datetime.fromisoformat(created_at)
                    created_str = dt.strftime("%Y-%m-%d %H:%M")
                except (ValueError, TypeError):
                    # Invalid datetime format, use original string
                    created_str = created_at
            else:
                created_str = ""
            created_item = QTableWidgetItem(created_str)
            self.sessions_table.setItem(row, 1, created_item)

            # Column 2: Status -- painted by SessionStatusDelegate. The role and
            # the authorship flag ride on the item; the delegate owns the paint.
            status = session_info.get("status", "active")
            status_item = QTableWidgetItem(status.capitalize())
            status_item.setData(ROLE_TOKEN, STATUS_ROLES.get(status, "text_secondary"))
            status_item.setData(
                ROLE_MANUAL, bool(session_info.get("status_manually_set", False))
            )
            self.sessions_table.setItem(row, 2, status_item)

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

            # Column 6: Packing progress from Packing Tool (READ-ONLY)
            packed, total = packing_completion(session_info)
            packing_item = _RatioSortItem(f"{packed}/{total}" if total else "—")
            packing_item.setData(Qt.UserRole, packed / total if total else -1.0)
            packing_item.setTextAlignment(Qt.AlignCenter)
            self.sessions_table.setItem(row, 6, packing_item)

            # Build tooltip with full info
            packing_lists_str = ", ".join(stats.get("packing_lists", [])) or "None"
            tooltip = f"""Session: {session_info.get("session_name", "")}
Created: {created_str}
Status: {status.capitalize()}
Orders: {orders_count if orders_count > 0 else "N/A"}
Items: {items_count if items_count > 0 else "N/A"}
Packing Lists ({packing_lists_count}): {packing_lists_str}
Packed: {packed}/{total} lists completed in Packing Tool
Comments: {comments if comments else "None"}"""

            # Apply tooltip to all cells in row
            for col in range(self.sessions_table.columnCount()):
                self.sessions_table.item(row, col).setToolTip(tooltip)

        self.sessions_table.setSortingEnabled(True)
        # Created descending is the default, but this method now runs on every
        # search keystroke -- hardcoding the sort here would snap the table back
        # to column 1 mid-word after the user sorted by something else.
        if sort_column < 0:
            sort_column, sort_order = 1, Qt.DescendingOrder
        self.sessions_table.sortItems(sort_column, sort_order)

    def _apply_filter(self):
        """Apply the status filter."""
        self.refresh_sessions()

    def _on_show_archived_toggled(self, checked: bool):
        """Toggling this only re-filters the already-loaded self.sessions_data --
        no new file-server call, since the whole index is already in memory."""
        self._show_archived = checked
        self._populate_table()

    def _on_search_changed(self, text: str):
        """Client-side: 42 sessions are already in memory, so searching them
        must not cost a file-server round trip the way the status filter does."""
        self._search = text.strip().lower()
        self._populate_table()

    def mark_dirty(self):
        """Call this whenever a session is created/updated for the client this
        widget is currently showing, so the next showEvent() actually refreshes
        instead of reusing a stale table."""
        self._is_dirty = True

    def _on_selection_changed(self, current=None, previous=None):
        """Fires on click and keyboard navigation, not hover."""
        selected = len(self.sessions_table.selectionModel().selectedRows())
        self.open_btn.setEnabled(selected == 1)
        self.comment_btn.setEnabled(selected == 1)
        self.status_btn.setEnabled(selected >= 1)
        self.combined_export_btn.setEnabled(selected >= 2)
        noun = "session" if selected == 1 else "sessions"
        self.selection_bar.set_selection(f"{selected} {noun} selected" if selected else "")

    def _on_combined_export(self):
        """Emit multi_export_requested with session paths for all selected rows."""
        session_paths = self._selected_session_paths()
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
        if current_row < 0:
            return

        item = self.sessions_table.item(current_row, 0)
        session_path = item.data(Qt.UserRole) if item else None

        if session_path:
            logger.info(f"Opening session: {session_path}")
            self.session_selected.emit(session_path)
        else:
            QMessageBox.warning(self, "Error", "Selected session has no valid path.")

    def _selected_session_paths(self) -> list[str]:
        """Session paths for every selected row, in table order."""
        paths = []
        for index in self.sessions_table.selectionModel().selectedRows():
            item = self.sessions_table.item(index.row(), 0)
            path = item.data(Qt.UserRole) if item else None
            if path:
                paths.append(path)
        return paths

    def _apply_status_to_selection(self, status: str):
        """Bulk status write -- the capability the per-row combobox never had.

        Each write goes through _on_status_changed, so manual=True and the
        error handling stay in one place. One refresh at the end, not one per
        row: on the production file server that is the difference between one
        round trip and six.
        """
        paths = self._selected_session_paths()
        if not paths:
            return
        failed = [
            p for p in paths if not self._on_status_changed(p, status, quiet=True)
        ]
        if failed:
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to update status on {len(failed)} of {len(paths)} sessions.\n"
                "See the log for details.",
            )
        self.refresh_sessions()

    def _edit_comment_for_selection(self):
        """Comments left the grid in 1e; this is where editing them lives now."""
        paths = self._selected_session_paths()
        if len(paths) != 1:
            return
        row = self.sessions_table.selectionModel().selectedRows()[0].row()
        session_name = self.sessions_table.item(row, 0).text()
        current = next(
            (
                s.get("comments", "")
                for s in self.sessions_data
                if s.get("session_path") == paths[0]
            ),
            "",
        )
        text, accepted = QInputDialog.getMultiLineText(
            self, "Session comment", session_name, current
        )
        if not accepted:
            return
        self._on_comments_changed(paths[0], text)
        self.refresh_sessions()

    def get_selected_session_path(self) -> str:
        """Get the path of the currently selected session.

        Returns:
            str: Session path or empty string if none selected
        """
        current_row = self.sessions_table.currentRow()
        if current_row < 0:
            return ""

        item = self.sessions_table.item(current_row, 0)
        return item.data(Qt.UserRole) if item else ""

    def _on_status_changed(
        self, session_path: str, new_status: str, *, quiet: bool = False
    ) -> bool:
        """Handle status change in table. Returns True on success.

        Args:
            session_path: Full path to session directory
            new_status: New status text (capitalized)
            quiet: report failure by return value only -- a bulk write shows one
                dialog for the whole selection, not one per row.
        """
        try:
            # Convert to lowercase for storage
            status = new_status.lower()

            # Update session_info.json
            # manual=True stops session_lifecycle from ever managing this
            # session's status again -- otherwise un-archiving an old session
            # would just re-archive it on the next refresh.
            self.session_manager.update_session_status(session_path, status, manual=True)

            logger.info(f"Updated session status: {session_path} -> {status}")
            return True

        except Exception as e:
            logger.exception("Failed to update status")
            if quiet:
                return False
            QMessageBox.critical(self, "Error", f"Failed to update status:\n{e!s}")
            # Revert to previous value
            self.refresh_sessions()
            return False

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

        except Exception:
            logger.exception("Failed to update comments")
            # Don't show error dialog for comments (less critical)
            # Just log the error

    def showEvent(self, event):
        """Refresh only if something changed since the last load -- avoids
        re-fetching from the file server every time this widget becomes
        visible with nothing new to show.
        """
        super().showEvent(event)
        if self._is_dirty and self.current_client_id:
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
