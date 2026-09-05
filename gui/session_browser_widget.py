"""Session Browser Widget for viewing and opening client sessions.

This widget shows a list of sessions for the currently selected client,
with filtering by status and the ability to open existing sessions.
"""

import logging
from datetime import datetime

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gui.background_worker import BackgroundWorker
from gui.components import ContextualSelectionBar, FilterBar, StatePanel
from gui.selection_ring import SelectionRingDelegate
from gui.session_row_delegates import (
    ROLE_LIVE,
    ROLE_SHAPE,
    ROLE_TOKEN,
    STATE_LABELS,
    STATE_STYLES,
    UNKNOWN_STATE,
    PackingProgressDelegate,
    SessionStatusDelegate,
)
from gui.theme_manager import get_density_profile, get_theme_manager
from gui.wheel_ignore_combobox import WheelIgnoreComboBox
from shared.theme import font_css, on_theme_changed, set_button_role
from shopify_tool.session_lifecycle import (
    age_label,
    blocked_orders,
    derive_status_updates,
    display_status,
    needs_attention,
    packing_completion,
    parse_created_at,
)
from shopify_tool.session_manager import SessionManager

logger = logging.getLogger(__name__)

GROUP_ATTENTION = "Needs attention"
GROUP_REST = "Everything else"


# Columns whose cell text is a rendering, not the value: Age reads "3d"/"2w"
# and Packing reads "10/12", both of which sort wrongly as strings. Each
# carries its real value in UserRole and is compared numerically.
_NUMERIC_SORT_COLUMNS = (1, 6)


class _SessionItem(QTreeWidgetItem):
    """Sorts Age and Packing on the numbers behind their text.

    QTreeWidgetItem compares its DisplayRole, so the plain text form puts
    "10/12" above "2/3" and orders "2w" before "today".
    """

    def __lt__(self, other):
        column = self.treeWidget().sortColumn() if self.treeWidget() else 0
        if column in _NUMERIC_SORT_COLUMNS:
            return (self.data(column, Qt.UserRole) or -1.0) < (
                other.data(column, Qt.UserRole) or -1.0
            )
        return self.text(column) < other.text(column)


class _GroupItem(QTreeWidgetItem):
    """Holds Needs attention above Everything else under every sort.

    Qt sorts top-level items with the same comparator as the rows, so without
    a fixed rank a descending sort on any column swaps the two headings -- and
    spec section 7 puts Needs attention first regardless of what the rows are
    sorted by.
    """

    def __init__(self, rank: int, text: str):
        super().__init__([text])
        self._rank = rank

    def __lt__(self, other):
        tree = self.treeWidget()
        descending = (
            tree is not None
            and tree.header().sortIndicatorOrder() == Qt.DescendingOrder
        )
        # Qt reverses the result of __lt__ under a descending sort, so invert
        # here to land on the same order either way.
        if descending:
            return self._rank > other._rank
        return self._rank < other._rank


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
    - Tree showing sessions in two groups, with key info per row
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
    new_session_requested = Signal()  # The "nothing yet" empty state's action

    # Class variable for testing - set to False to disable async loading in tests
    USE_ASYNC = True

    def __init__(self, session_manager: SessionManager, parent=None):
        super().__init__(parent)
        self.session_manager = session_manager
        self.current_client_id = None
        self.sessions_data = []
        self.worker = None  # Track active background worker
        self.empty_panel = None
        self._show_archived = False
        self._search = ""
        self._is_dirty = True  # forces one load on first show

        self._init_ui()
        logger.info("SessionBrowserWidget initialized")

    def _init_ui(self):
        """Initialize the UI components."""
        self.main_layout = main_layout = QVBoxLayout(self)

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

        main_layout.addLayout(filter_layout)

        # Sessions tree: two groups (Needs attention / Everything else), not a
        # hierarchy -- setRootIsDecorated(False) hides the arrow a real tree
        # would draw for that.
        self.sessions_tree = QTreeWidget()
        self.sessions_tree.setColumnCount(8)
        self.sessions_tree.setHeaderLabels(
            ["Session", "Age", "Status", "Orders", "Items",
             "Blocked", "Packing", "Comment"]
        )
        self.sessions_tree.setSelectionBehavior(QTreeWidget.SelectRows)
        self.sessions_tree.setSelectionMode(QTreeWidget.ExtendedSelection)
        self.sessions_tree.setEditTriggers(QTreeWidget.NoEditTriggers)
        self.sessions_tree.setRootIsDecorated(False)
        self.sessions_tree.setIndentation(0)
        self.sessions_tree.doubleClicked.connect(self._on_session_double_clicked)
        self.sessions_tree.setSortingEnabled(True)
        # setSortingEnabled leaves the indicator on column 0, so the default
        # order has to be stated: newest first, which is what the browser
        # showed before the tree and what spec section 7 keeps.
        self.sessions_tree.sortByColumn(1, Qt.DescendingOrder)

        # A QTreeView has no verticalHeader() to set a pixel row height on, so
        # the density profile arrives per row as a size hint from _build_row;
        # setUniformRowHeights then takes the first row's hint for all of them.
        self.sessions_tree.setUniformRowHeights(True)

        self.sessions_tree.setItemDelegateForColumn(2, SessionStatusDelegate(self))
        self.sessions_tree.setItemDelegateForColumn(6, PackingProgressDelegate(self))
        # Columns 2 and 6 have their own delegates and paint the ring
        # themselves; this closes it on the ones that do not.
        self.sessions_tree.setItemDelegate(SelectionRingDelegate(self))

        header = self.sessions_tree.header()
        for column, width in ((1, 90), (2, 140), (3, 80), (4, 80),
                              (5, 80), (6, 130), (7, 200)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            header.resizeSection(column, width)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

        main_layout.addWidget(self.sessions_tree)

        # Archive is a footer, not a third filter. It reports a fact about
        # what is hidden and offers to unhide it; the two controls above
        # narrow what is shown. Different jobs, different bands of chrome.
        self.archive_line = QWidget(self)
        archive_layout = QHBoxLayout(self.archive_line)
        archive_layout.setContentsMargins(0, 0, 0, 0)
        archive_layout.setSpacing(8)
        self.archive_count = QLabel("")
        self.archive_count.setStyleSheet(font_css("caption"))
        # Spec section 9 sets the line as "12 archived · Show". Its own label,
        # not part of the count, so the count still reads as the bare fact.
        archive_separator = QLabel("·")
        archive_separator.setStyleSheet(font_css("caption"))
        self.archive_toggle = QPushButton("Show")
        set_button_role(self.archive_toggle, "ghost")
        self.archive_toggle.clicked.connect(self._on_show_archived_toggled)
        archive_layout.addWidget(self.archive_count)
        archive_layout.addWidget(archive_separator)
        archive_layout.addWidget(self.archive_toggle)
        archive_layout.addStretch(1)
        self.archive_line.setVisible(False)
        main_layout.addWidget(self.archive_line)

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
        self.sessions_tree.clicked.connect(lambda _: self._on_selection_changed())
        self.sessions_tree.currentItemChanged.connect(self._on_selection_changed)
        self.sessions_tree.itemSelectionChanged.connect(self._on_selection_changed)

        # _build_row bakes three theme values into its items -- the archive
        # warning tint, the blocked tint and the abandoned row's dimming -- and
        # a baked value does not follow a toggle. Per ADR 0003 the fix is to
        # re-run the recipe, so the rows are rebuilt from self.sessions_data,
        # which is already in memory. The same signal carries a density change,
        # which is what refreshes the row-height hint above.
        on_theme_changed(self, lambda _tokens: self._populate_tree())

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
            self.sessions_tree.clear()
            logger.debug("No client selected, clearing sessions tree")
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
        self.sessions_tree.clear()  # Clear tree
        self.sessions_tree.setEnabled(False)
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

            # Populate tree
            self._populate_tree()

            logger.info(f"Loaded {len(self.sessions_data)} sessions (sync mode)")

        except Exception as e:
            logger.exception("Failed to load sessions")
            QMessageBox.warning(self, "Error", f"Failed to load sessions:\n{e!s}")

    def _on_sessions_loaded(self, sessions_data):
        """Handle loaded data in main thread (safe for UI updates)."""
        # Guard: widget may have been closed, or merely hidden (e.g. the user
        # switched tabs while the file-server load was in flight).
        if not self.isVisible() or self.sessions_tree is None:
            logger.debug("Widget not visible when sessions loaded — will retry on next show")
            # refresh_sessions() already cleared _is_dirty when the load started;
            # re-mark it so the next showEvent() retries instead of leaving the
            # table/button stuck in the "Loading..." state forever.
            self._is_dirty = True
            return

        logger.debug(f"Received {len(sessions_data)} sessions from worker")
        self.sessions_data = sessions_data
        self._populate_tree()

        # Restore UI state
        self.sessions_tree.setEnabled(True)
        self.refresh_btn.setEnabled(True)
        self.refresh_btn.setText("Refresh")

    def _on_load_error(self, error_msg):
        """Handle errors in main thread."""
        logger.error(f"Session load error: {error_msg}")

        # Restore UI
        self.sessions_tree.setEnabled(True)
        self.refresh_btn.setEnabled(True)
        self.refresh_btn.setText("Refresh")

        # Show error to user
        QMessageBox.warning(
            self, "Error Loading Sessions", f"Failed to load sessions:\n{error_msg}"
        )

    def _populate_tree(self):
        """Populate the tree with sessions data, grouped by whether they need attention."""
        # Archived sessions are hidden unless asked for. When the user picks
        # "Archived" in the status filter the server-side query already
        # returned only archived rows, so hiding them here would leave an
        # empty tree.
        showing_archived_explicitly = self._archived_filter_active()
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

        now = datetime.now().astimezone()
        header = self.sessions_tree.header()
        sort_column = header.sortIndicatorSection()
        sort_order = header.sortIndicatorOrder()
        self.sessions_tree.setSortingEnabled(False)
        self.sessions_tree.clear()

        attention = _GroupItem(0, GROUP_ATTENTION)
        rest = _GroupItem(1, GROUP_REST)
        for group in (attention, rest):
            group.setFlags(Qt.ItemIsEnabled)      # a group is not selectable
            group.setFirstColumnSpanned(True)

        for session_info in visible_sessions:
            state = display_status(session_info, now)
            blocked = blocked_orders(session_info)
            item = self._build_row(session_info, state, blocked, now)
            parent = attention if needs_attention(state, blocked) else rest
            parent.addChild(item)

        for group in (attention, rest):
            if group.childCount():
                group.setText(0, f"{group.text(0)}  {group.childCount()}")
                self.sessions_tree.addTopLevelItem(group)
                group.setExpanded(True)

        self.sessions_tree.setSortingEnabled(True)
        self.sessions_tree.sortItems(sort_column, sort_order)
        self._update_archive_footer()
        self._update_empty_state()

    def _build_row(self, session_info, state, blocked, now):
        stats = session_info.get("statistics", {})
        comments = session_info.get("comments", "")
        item = _SessionItem()
        theme = get_theme_manager().get_current_theme()
        item.setSizeHint(0, QSize(0, get_density_profile().row_height))

        item.setText(0, session_info.get("session_name", ""))
        item.setData(0, Qt.UserRole, session_info.get("session_path", ""))

        created = parse_created_at(session_info.get("created_at"))
        age_cell, age_tip = age_label(created, now)
        item.setText(1, age_cell)
        # The cell reads "3d"/"2w"; the instant behind it is what Age sorts on.
        item.setData(1, Qt.UserRole, created.timestamp() if created else -1.0)
        if "archives in" in age_cell:
            item.setForeground(1, QColor(theme.status_warning))

        role, live, shape = STATE_STYLES.get(state, UNKNOWN_STATE)
        item.setText(2, STATE_LABELS.get(state, state.replace("_", " ").capitalize()))
        item.setData(2, ROLE_TOKEN, role)
        item.setData(2, ROLE_LIVE, live)
        item.setData(2, ROLE_SHAPE, shape)

        orders = stats.get("total_orders", 0)
        items = stats.get("total_items", 0)
        item.setText(3, str(orders) if orders else "N/A")
        item.setText(4, str(items) if items else "N/A")

        # Blank at zero and at None, so the column reads as a list of
        # exceptions rather than a field of noughts.
        item.setText(5, str(blocked) if blocked else "")
        if blocked:
            item.setForeground(5, QColor(theme.status_warning))

        packed, total = packing_completion(session_info)
        item.setText(6, f"{packed}/{total}" if total else "—")
        item.setData(6, Qt.UserRole, packed / total if total else -1.0)

        item.setText(7, comments)

        for column in (3, 4, 6):
            item.setTextAlignment(column, Qt.AlignCenter)
        # Blocked is right-aligned per spec 6.2: it is read as an exception
        # list down the column, and a ragged left edge is what makes the
        # non-blank rows findable.
        item.setTextAlignment(5, Qt.AlignRight | Qt.AlignVCenter)

        blocked_line = (
            f"{blocked} of {orders} orders cannot be fulfilled"
            if blocked else "No blocked orders"
        )
        tooltip = "\n".join([
            session_info.get("session_name", ""),
            age_tip,
            f"Status: {item.text(2)}",
            f"Orders: {orders if orders else 'N/A'}",
            f"Items: {items if items else 'N/A'}",
            blocked_line,
            f"Packed: {packed}/{total} lists completed in Packing Tool",
            f"Comment: {comments or 'None'}",
        ])
        for column in range(8):
            item.setToolTip(column, tooltip)

        # Abandoned recedes: the system concluded it, it is over. Incomplete
        # stays full strength -- someone can still finish it.
        if state == "abandoned":
            for column in (0, 1, 3, 4, 6, 7):
                item.setForeground(column, QColor(theme.text_secondary))
        return item

    def _archived_filter_active(self) -> bool:
        """True when the status combo is already asking for archived rows.

        The server-side query then returned nothing else, so the footer must
        stand down and _populate_tree must not hide what it fetched.
        """
        return self.status_filter.currentText().lower() == "archived"

    def _update_archive_footer(self):
        archived = sum(
            1 for s in self.sessions_data if s.get("status") == "archived"
        )
        self.archive_line.setVisible(
            bool(archived) and not self._archived_filter_active()
        )
        self.archive_count.setText(f"{archived} archived")
        self.archive_toggle.setText("Hide" if self._show_archived else "Show")

    def _groups(self):
        return [
            self.sessions_tree.topLevelItem(i)
            for i in range(self.sessions_tree.topLevelItemCount())
        ]

    def _empty_reason(self):
        """None, "nothing" or "filtered" -- why the tree has no rows.

        "filtered" is not "nothing": one is a filter the user can widen, the
        other is a client with no sessions on the server. A panel that cannot
        tell them apart is the "No data - Nothing to display" this phase
        deleted.
        """
        if any(g.childCount() for g in self._groups()):
            return None
        return "filtered" if self.sessions_data else "nothing"

    def _update_empty_state(self):
        reason = self._empty_reason()
        if self.empty_panel is not None:
            self.empty_panel.deleteLater()
            self.empty_panel = None
        self.sessions_tree.setVisible(reason is None)
        if reason is None:
            return

        if reason == "nothing":
            panel = StatePanel(
                "No sessions yet",
                f"CLIENT_{self.current_client_id} has no sessions on the file server.",
                action_text="New session",
            )
            panel.button.clicked.connect(self.new_session_requested.emit)
        else:
            panel = StatePanel(
                "No sessions match",
                self._filter_sentence(),
                action_text="Clear filters",
                action_role="secondary",
            )
            panel.button.clicked.connect(self._clear_filters)

        self.empty_panel = panel
        self.main_layout.insertWidget(1, panel, 1)

    def _filter_sentence(self) -> str:
        """Names both live filters, and drops the half that is not set."""
        status = self.status_filter.currentText()
        search = self.filter_bar.search_field.text().strip()
        noun = "session" if status == "All" else f"{status} session"
        if search:
            return f'No {noun} matches "{search}".'
        return f"No {noun} is visible with the current filters."

    def _clear_filters(self):
        # Each setter fires its own handler, and the status one costs a
        # file-server round trip. Clear both quietly, then refresh once.
        for widget in (self.filter_bar.search_field, self.status_filter):
            widget.blockSignals(True)
        self.filter_bar.search_field.clear()
        self.status_filter.setCurrentText("All")
        for widget in (self.filter_bar.search_field, self.status_filter):
            widget.blockSignals(False)
        self._search = ""

        # Putting the archive back away is part of clearing the filters --
        # unless every session this client has is archived, where it would
        # leave the same empty tree and the button would visibly do nothing.
        if any(s.get("status") != "archived" for s in self.sessions_data):
            self._show_archived = False
        self.refresh_sessions()

    def _apply_filter(self):
        """Apply the status filter."""
        self.refresh_sessions()

    def _on_show_archived_toggled(self):
        """Re-filters the already-loaded self.sessions_data -- no new
        file-server call, since the whole index is already in memory."""
        self._show_archived = not self._show_archived
        self._populate_tree()

    def _on_search_changed(self, text: str):
        """Client-side: 42 sessions are already in memory, so searching them
        must not cost a file-server round trip the way the status filter does."""
        self._search = text.strip().lower()
        self._populate_tree()

    def mark_dirty(self):
        """Call this whenever a session is created/updated for the client this
        widget is currently showing, so the next showEvent() actually refreshes
        instead of reusing a stale table."""
        self._is_dirty = True

    def _on_selection_changed(self, current=None, previous=None):
        """Fires on click and keyboard navigation, not hover."""
        selected = len(self._selected_session_paths())
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
        item = self.sessions_tree.currentItem()
        if item is None or item.parent() is None:
            return

        session_path = item.data(0, Qt.UserRole)

        if session_path:
            logger.info(f"Opening session: {session_path}")
            self.session_selected.emit(session_path)
        else:
            QMessageBox.warning(self, "Error", "Selected session has no valid path.")

    def _selected_session_paths(self) -> list[str]:
        """Session paths for every selected row, in tree order.

        Group headings are ItemIsEnabled-only so they never enter a
        selection, but filtering on `parent()` keeps that a property of this
        method rather than of a flag somewhere else.
        """
        return [
            item.data(0, Qt.UserRole)
            for item in self.sessions_tree.selectedItems()
            if item.parent() is not None and item.data(0, Qt.UserRole)
        ]

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
        item = next(i for i in self.sessions_tree.selectedItems() if i.parent() is not None)
        session_name = item.text(0)
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
        item = self.sessions_tree.currentItem()
        if item is None or item.parent() is None:
            return ""
        return item.data(0, Qt.UserRole) or ""

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
