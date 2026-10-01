"""The Browse screen: the sessions of the selected client (phase 4 spec section 6).

A widget that hosts one web view. It loads the session list off the GUI
thread, hands the page one state map (gui/browse_state.py), and carries out
what the page asks for through BrowseBridge: open, set a status, comment,
export combined stock, Undo.
"""

import logging
from datetime import datetime

from PySide6.QtCore import Signal
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QVBoxLayout, QWidget

from gui.background_worker import BackgroundWorker
from gui.browse_bridge import mount_browse_page
from gui.browse_state import browse_state
from gui.components import show_error
from shopify_tool.session_lifecycle import derive_status_updates
from shopify_tool.session_manager import SessionManager

logger = logging.getLogger(__name__)

# What a status or a comment change can alter in session_info.json, and so
# what Undo puts back. A key the session did not have is restored as absent.
_UNDO_KEYS = (
    "status",
    "status_manually_set",
    "status_updated_at",
    "comments",
    "last_updated",
)


def _what(entries: list[dict]) -> str:
    """How a toast names what it changed: the session, or how many."""
    if len(entries) == 1:
        return entries[0]["session_name"]
    return f"{len(entries)} sessions"


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
            logger.debug(f"Loaded {len(sessions)} sessions for CLIENT_{self.client_id}")

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
            logger.exception(
                "Automatic session status sync failed; showing stored statuses"
            )
        return sessions


class SessionBrowserWidget(QWidget):
    """The Browse screen's widget: one web view and the code behind it.

    Signals:
        session_selected: the operator opened a session (session_path: str)
        multi_export_requested: combined stock export for these session paths
        new_session_requested: the "No sessions yet" panel's button
    """

    session_selected = Signal(str)
    multi_export_requested = Signal(list)
    new_session_requested = Signal()

    # Class variable for testing - set to False to load in line, with no thread.
    USE_ASYNC = True

    def __init__(self, session_manager: SessionManager, parent=None):
        super().__init__(parent)
        self.session_manager = session_manager
        self.current_client_id = None
        self.sessions_data = []
        self.worker = None  # the load in flight, if any
        self._is_dirty = True  # forces one load on first show
        self._loading = False
        self._failed = False
        self._undo = {}  # session_path -> the fields the last change replaced

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.view = QWebEngineView(self)
        self.bridge = mount_browse_page(self.view)
        layout.addWidget(self.view, 1)

        self.bridge.refreshRequested.connect(lambda: self.refresh_sessions())
        self.bridge.openRequested.connect(self._open)
        self.bridge.newSessionRequested.connect(self.new_session_requested)
        self.bridge.exportRequested.connect(self._export)
        self.bridge.statusRequested.connect(self._set_status)
        self.bridge.commentRequested.connect(self._set_comment)
        self.bridge.undoRequested.connect(self._undo_last)
        self._push()
        logger.info("SessionBrowserWidget initialized")

    def _push(self) -> None:
        """Build the page's state from what this widget holds and send it."""
        self.bridge.set_state(
            browse_state(
                client=self.current_client_id or "",
                loading=self._loading,
                failed=self._failed,
                sessions=self.sessions_data,
                now=datetime.now().astimezone(),
            )
        )

    # --- loading -------------------------------------------------------------

    def set_client(self, client_id: str, auto_refresh: bool = True):
        """Set the client to show sessions for.

        Args:
            client_id: Client ID to load sessions for
            auto_refresh: If False, skip the immediate refresh and let the next
                showEvent() pick up the dirty flag instead -- unless the widget
                is already visible right now, in which case there's no future
                showEvent to rescue it (the tab isn't changing), so it must
                refresh immediately or the page is left on its skeleton.
        """
        if client_id == self.current_client_id:
            return
        self.current_client_id = client_id
        # The previous client's rows never show under the new client's name.
        self.sessions_data = []
        self._undo = {}
        self._failed = False
        self._loading = bool(client_id)
        self._is_dirty = True
        self._push()
        if auto_refresh or self.isVisible():
            self.refresh_sessions()

    def refresh_sessions(self, quiet: bool = False):
        """Reload the sessions from the server.

        A loud refresh shows the skeleton first. A quiet one, after a write,
        leaves the rows on screen until the new ones arrive.
        """
        self._is_dirty = False
        if not self.current_client_id:
            self.sessions_data = []
            self._loading = self._failed = False
            self._push()
            return

        if not quiet:
            self._loading, self._failed = True, False
            self._push()

        if not self.USE_ASYNC:
            # In line, for tests. It does NOT run SessionLoaderWorker's
            # automatic status sync: test that against the worker directly.
            try:
                sessions = self.session_manager.list_client_sessions(
                    self.current_client_id
                )
            except Exception as error:
                logger.exception("Failed to load sessions")
                self._on_load_error(str(error))
                return
            self._show(sessions)
            return

        # Clean up the previous worker FIRST (critical to prevent crashes).
        if self.worker is not None:
            self.worker.cleanup()
            self.worker = None
        # Every status: the tabs filter in the page.
        self.worker = SessionLoaderWorker(self.session_manager, self.current_client_id)
        self.worker.finished_with_data.connect(self._on_sessions_loaded)
        self.worker.error_occurred.connect(self._on_load_error)
        self.worker.start()
        logger.debug("Session loading worker started")

    def _on_sessions_loaded(self, sessions):
        """A background load finished (main thread)."""
        # The widget may have been hidden while the file-server load was in
        # flight (the user switched tabs). refresh_sessions() already cleared
        # _is_dirty when the load started; re-mark it so the next showEvent()
        # loads again instead of leaving the page on its skeleton forever.
        if not self.isVisible():
            logger.debug("Widget not visible when sessions loaded; will retry on next show")
            self._is_dirty = True
            return
        self._show(sessions)

    def _show(self, sessions) -> None:
        logger.debug(f"Showing {len(sessions)} sessions")
        self.sessions_data = sessions
        self._loading = self._failed = False
        self._push()

    def _on_load_error(self, error_msg):
        """A load failed (main thread). The page shows the failed panel."""
        logger.error(f"Session load error: {error_msg}")
        self.sessions_data = []
        self._loading, self._failed = False, True
        self._push()

    def mark_dirty(self):
        """Call this whenever a session is created/updated for the client this
        widget is currently showing, so the next showEvent() actually refreshes
        instead of reusing a stale list."""
        self._is_dirty = True

    # --- what the page asks for ----------------------------------------------

    def _entries(self, names) -> list[dict]:
        """The loaded sessions with these names, in list order.

        The page sends names only. A name this widget did not load is dropped,
        so nothing from the page is ever used as a path.
        """
        wanted = set(names)
        return [
            entry
            for entry in self.sessions_data
            if isinstance(entry, dict)
            and isinstance(entry.get("session_name"), str)
            and entry["session_name"] in wanted
            and entry.get("session_path")
        ]

    def _open(self, name: str) -> None:
        for entry in self._entries([name]):
            logger.info(f"Opening session: {entry['session_path']}")
            self.session_selected.emit(entry["session_path"])

    def _export(self, names) -> None:
        paths = [entry["session_path"] for entry in self._entries(names)]
        if len(paths) >= 2:
            self.multi_export_requested.emit(paths)

    def _set_status(self, names, status: str) -> None:
        # manual=True stops session_lifecycle from ever managing this session's
        # status again -- otherwise un-archiving an old session would just
        # re-archive it on the next refresh.
        self._write(
            names,
            lambda path: self.session_manager.update_session_status(
                path, status, manual=True
            ),
            done=f"Set {{what}} to {status.capitalize()}",
            one_failed="The status wasn't updated",
        )

    def _set_comment(self, names, text: str) -> None:
        self._write(
            names,
            lambda path: self.session_manager.update_session_info(
                path, {"comments": text}
            ),
            done="Comment saved on {what}" if text else "Comment cleared on {what}",
            one_failed="The comment wasn't saved",
        )

    def _write(self, names, write, *, done: str, one_failed: str) -> None:
        """Apply one change to every named session, then say so once.

        One banner for the sessions that failed, one toast with Undo for the
        ones that were written, and one quiet reload at the end: on the
        production file server that is one round trip, not one per session.
        """
        entries = self._entries(names)
        if not entries:
            return
        written = []
        for entry in entries:
            try:
                write(entry["session_path"])
            except Exception:
                logger.exception(f"Failed to update {entry['session_name']}")
            else:
                written.append(entry)

        failed = len(entries) - len(written)
        if failed:
            show_error(
                self,
                one_failed
                if len(entries) == 1
                else f"{failed} of {len(entries)} sessions weren't updated",
                "Details are in Logs.",
            )
        if written:
            self._undo = {
                entry["session_path"]: {key: entry.get(key) for key in _UNDO_KEYS}
                for entry in written
            }
            self.bridge.raise_toast(done.format(what=_what(written)), True)
        self.refresh_sessions(quiet=True)

    def _undo_last(self) -> None:
        """Put back what the last status or comment change replaced."""
        undo, self._undo = self._undo, {}
        if not undo:
            return
        failed = 0
        for path, fields in undo.items():
            try:
                self.session_manager.restore_session_fields(path, fields)
            except Exception:
                logger.exception(f"Failed to restore {path}")
                failed += 1
        if failed:
            show_error(
                self,
                "The change wasn't undone"
                if len(undo) == 1
                else f"{failed} of {len(undo)} sessions weren't restored",
                "Details are in Logs.",
            )
        self.refresh_sessions(quiet=True)

    # --- widget events -------------------------------------------------------

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
        """
        if self.worker is not None:
            logger.debug("Cleaning up session browser worker on widget close")
            self.worker.cleanup()
            self.worker = None
        super().closeEvent(event)
