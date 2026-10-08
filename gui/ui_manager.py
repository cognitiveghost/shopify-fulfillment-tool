import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar

from PySide6.QtCore import QSettings
from PySide6.QtGui import QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from gui.components.commandbar import BarState, CommandBar
from gui.components.error_banner import ErrorBanner, show_error
from gui.components.sidebar import Sidebar
from gui.orders_view import summary_text
from gui.setup_state import FileSlot, MemoryFacts, RunFacts, SessionFacts, setup_state
from gui.shortcuts_dialog import ShortcutsDialog
from shared.icons import icon
from shared.server_connection import ConnectionSettingsDialog
from shared.theme import on_theme_changed
from shopify_tool.profile_manager import PROD_SERVER_PATH

from .web_page import keep_pages_painted, switch_theme

# The sidebar's collapsed state is this PC's, like the theme -- same QSettings
# pair theme_manager and logs_widget use. A function so tests can point it at
# an INI file under tmp_path.
_COLLAPSED_KEY = "shell/sidebar_collapsed"


def _shell_settings() -> QSettings:
    return QSettings("ShopifyFulfillmentTool", "FulfillmentApp")


def age_text(delta) -> str:
    """`19 h`, `45 min`, `3 d` -- the one age format the results screen uses."""
    minutes = max(0, int(delta.total_seconds() // 60))
    if minutes < 60:
        return f"{minutes} min"
    hours = minutes // 60
    if hours < 48:
        return f"{hours} h"
    return f"{hours // 24} d"


def _parse_time(text) -> datetime | None:
    """An ISO timestamp from a JSON file, as a local aware datetime, or None."""
    try:
        moment = datetime.fromisoformat(text or "")
    except (TypeError, ValueError):
        return None
    return moment.astimezone()


class _SessionLabelShim:
    """`mw.session_info_label.setText(...)` forwards to the bar's picker.

    update_session_info_label() in main_window_pyside.py writes through this
    attribute; the write target moved from a QLabel to CommandBar's session
    picker button, so this shim forwards the call rather than editing that
    method's body.
    """

    def __init__(self, bar: CommandBar) -> None:
        self._bar = bar

    def setText(self, text: str) -> None:
        self._bar.set_session_text(text)


class UIManager:
    """Handles the creation, layout, and state of all UI widgets.

    This class is responsible for building the graphical user interface of the
    main window. It creates all the widgets (buttons, labels, tables, etc.),
    arranges them in layouts and group boxes, and provides methods to update
    their state (e.g., enabling/disabling buttons, populating tables).

    It decouples the raw widget creation and layout logic from the main
    application logic in `MainWindow`.

    Attributes:
        mw (MainWindow): A reference to the main window instance.
        log (logging.Logger): A logger for this class.
    """

    # Only long-lived icons need re-theming on a theme toggle. The context
    # menu in main_window_pyside.py is rebuilt on every right-click, so its
    # icons pick up the new colour for free.
    _TAB_ICONS = ("clipboard-list", "table", "folder-open", "info", "wrench")
    # The five former tab titles. Still the pages' own titles; the rail uses
    # _RAIL_LABELS instead -- see below.
    _TAB_LABELS = (
        "Session Setup",
        "Analysis Results",
        "Session Browser",
        "Logs",
        "Tools",
    )
    # 8.6 shipped the rail with _TAB_LABELS verbatim, because guardrail 2 of
    # the parent spec's §6 forbids renaming a destination and moving it in the
    # same release. The move has shipped, so the rename is allowed now -- and
    # needed: at 56px the rail elides five of the six to "Ses...tup" /
    # "Anal...ults" / "Ses...ser", which is worse than no label. The full names
    # survive as the tooltips in _TAB_TOOLTIPS.
    _RAIL_LABELS = ("Setup", "Results", "Browse", "Logs", "Tools")
    _TAB_TOOLTIPS = (
        "Session setup and file loading (Ctrl+1)",
        "View and edit analysis results (Ctrl+2)",
        "Browse past sessions (Ctrl+3)",
        "Activity and execution logs (Ctrl+4)",
        "PDF processing and utilities (Ctrl+5)",
    )
    # No long-lived button icon is re-themed here: the bar re-renders its own.
    _BUTTON_ICONS: ClassVar[dict[str, str]] = {}

    def __init__(self, main_window):
        """Initializes the UIManager.

        Args:
            main_window (MainWindow): The main window instance that this
                manager will build the UI for.
        """
        self.mw = main_window
        self.log = logging.getLogger(__name__)

    def create_widgets(self):
        """Creates and lays out all widgets with new tab-based structure and sidebar.

        This is the main entry point for building the UI. It constructs the
        entire widget hierarchy for the `MainWindow` with a modern tab-based layout
        and collapsible client sidebar.
        """
        self.log.info("Creating UI widgets with new tab-based structure and sidebar.")

        # Create central widget with horizontal layout for sidebar + main content
        central_widget = QWidget()
        self.mw.setCentralWidget(central_widget)
        main_horizontal = QHBoxLayout(central_widget)
        main_horizontal.setSpacing(0)
        main_horizontal.setContentsMargins(0, 0, 0, 0)

        # The sidebar is the outermost chrome, left of everything else. Its
        # NavRail keeps the name nav_rail, so every call site stays as it was.
        self.mw.sidebar = Sidebar(self.mw)
        self.mw.nav_rail = self.mw.sidebar.rail
        main_horizontal.addWidget(self.mw.sidebar)

        right_side = QWidget()
        right_layout = QVBoxLayout(right_side)
        right_layout.setSpacing(0)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # The command bar runs edge to edge; its own border-bottom is the divider.
        right_layout.addWidget(self._create_command_bar())

        # Every page is a web page and paints the sunken plane to its own
        # edges, so the page area has no inset (phase 6 spec section 6.3).
        page_area = QWidget()
        self.mw.page_area = page_area
        page_layout = QVBoxLayout(page_area)
        page_layout.setSpacing(5)
        page_layout.setContentsMargins(0, 0, 0, 0)

        # 9.25: a failure waits here, under the command bar, until dismissed.
        logs_index = self._RAIL_LABELS.index("Logs")
        self.mw.error_banner = ErrorBanner(
            open_logs=lambda: self.mw.main_tabs.setCurrentIndex(logs_index)
        )
        page_layout.addWidget(self.mw.error_banner)

        self._create_tabs()
        page_layout.addWidget(self.mw.main_tabs, 1)

        right_layout.addWidget(page_area, 1)
        main_horizontal.addWidget(right_side, 1)

        self._wire_sidebar()

        # Every widget exists by now, so one pass sets every long-lived icon.
        # on_theme_changed applies immediately, so this is that first pass too.
        on_theme_changed(self.mw, self._on_theme)

        self.mw.connectionChanged.connect(self._on_connection_changed)

        self.log.info(
            "UI widgets created successfully with tab-based structure and sidebar."
        )

    def _wire_sidebar(self) -> None:
        """The footer's three requests, and the collapse this PC remembers."""
        sidebar = self.mw.sidebar
        sidebar.settingsRequested.connect(
            lambda: self.mw.actions_handler.open_settings_window()
        )
        sidebar.themeRequested.connect(switch_theme)
        sidebar.retryRequested.connect(self.mw.recheck_connection)
        sidebar.expandedChanged.connect(
            lambda expanded: _shell_settings().setValue(_COLLAPSED_KEY, not expanded)
        )
        collapsed = _shell_settings().value(_COLLAPSED_KEY, False, type=bool)
        sidebar.set_expanded(not collapsed)

    def _on_theme(self, tokens) -> None:
        self._refresh_icons()
        self.mw.sidebar.set_theme_name(tokens.name)

    def _refresh_nav(self) -> None:
        """The one rule for which destinations the rail offers. Phase 1 spec §5.4.

        Setup and Logs always: Logs is where an operator reads why the server
        is unreachable. Browse and Tools need the share and a client; Results
        needs an analysis. Disabled, never hidden.
        """
        connected = self.mw.is_connected()
        has_client = bool(self.mw.current_client_id)
        analysed = self.mw.analysis_results_df is not None
        offered = (
            True,
            connected and analysed,
            connected and has_client,
            True,
            connected and has_client,
        )
        rail = self.mw.nav_rail
        for index, on in enumerate(offered):
            rail.button(index).setEnabled(on)
        label, tip = self._TAB_LABELS[1], self._TAB_TOOLTIPS[1]
        rail.button(1).setToolTip(
            f"{label} — {tip}"
            if analysed
            else f"{label} — available after Run analysis (Ctrl+2)"
        )
        self.mw.sidebar.set_settings_enabled(connected and has_client)
        if not offered[rail.current_index()]:
            rail.set_current(0)

    def _on_connection_changed(self, connected: bool) -> None:
        """The one signal that drives every control which touches the share.

        The disabling is the guard, not decoration on top of one: no call site
        below carries a None-check, because none of them is reachable while
        this is False. Spec §5.1.
        """
        self._refresh_nav()

        # The selector is not just empty while disconnected, it is disabled:
        # its "New client..." and "Manage groups..." rows are appended by the
        # component itself and would still write to the unreachable share.
        self.mw.command_bar.client_selector.setEnabled(connected)

        self.refresh_setup()
        # With no client the selector is the thing to act on, so it takes focus.
        if connected and not self.mw.current_client_id:
            self.mw.command_bar.client_selector.setFocus()

        self.mw.sidebar.set_connection(
            connected, str(self.mw.profile_manager.base_path)
        )

        if not connected:
            self.mw.command_bar.set_state(BarState.NO_CLIENT)

    def _create_tabs(self):
        """Create the page store and the rail that drives it.

        main_tabs keeps being a QTabWidget with its tab bar hidden. A hidden
        tab bar makes it exactly a QStackedWidget with the API 30 call sites
        already speak -- swapping the class would rewrite all of them and the
        five shortcuts to produce a screen no user can tell apart.
        """
        self.mw.main_tabs = QTabWidget()
        self.mw.main_tabs.setDocumentMode(True)
        self.mw.main_tabs.setTabPosition(QTabWidget.North)
        self.mw.main_tabs.setMovable(False)
        self.mw.main_tabs.tabBar().hide()
        # With the tab bar hidden this is a page stack, and the app sheet's
        # QTabWidget::pane border would frame every page in a 1px strip.
        self.mw.main_tabs.setObjectName("PageStack")
        self.mw.main_tabs.setStyleSheet("#PageStack::pane { border: 0; }")

        pages = (
            self._create_tab1_session_setup(),
            self._create_tab2_analysis_results(),
            self._create_tab3_session_browser(),
            self._create_tab4_logs(),
            self._create_tab5_tools(),
        )
        for page, label, rail_label, icon_name, tip in zip(
            pages,
            self._TAB_LABELS,
            self._RAIL_LABELS,
            self._TAB_ICONS,
            self._TAB_TOOLTIPS,
            strict=True,
        ):
            self.mw.main_tabs.addTab(page, label)
            index = self.mw.nav_rail.add_item(icon(icon_name), rail_label)
            # The rail label is abbreviated, so the tooltip is the only place
            # the destination's full name still appears. _TAB_TOOLTIPS holds
            # descriptions ("Statistics and logs"), not names, so lead with it.
            self.mw.nav_rail.button(index).setToolTip(f"{label} — {tip}")

        # Covered pages keep painting, so a switch never shows a page's old
        # frame (2026-10-08 web tier freshness spec, section 4.1).
        keep_pages_painted(self.mw.main_tabs.findChild(QStackedWidget))

        # Two-way, and the back edge is load-bearing: actions_handler jumps
        # straight to Analysis Results after a run, and without this the rail
        # would keep highlighting the page the user left. It cannot loop --
        # NavRail.set_current returns before emitting when the index is
        # unchanged, and QTabWidget does not re-emit for the index it is on.
        self.mw.nav_rail.currentChanged.connect(self.mw.main_tabs.setCurrentIndex)
        self.mw.main_tabs.currentChanged.connect(self.mw.nav_rail.set_current)

        self._setup_tab_shortcuts()

        # The session chip on every screen but Setup and Tools, whose page
        # heads show it; the analysis age on Results.
        self.mw.main_tabs.currentChanged.connect(
            lambda index: self.mw.command_bar.set_screen(
                chip=index not in (0, 4), meta=index == 1
            )
        )

    def _create_command_bar(self) -> CommandBar:
        """The one-row bar that replaces the two-row global header."""
        bar = CommandBar(self.mw)
        self.mw.command_bar = bar

        # update_session_info_label() still writes through this attribute --
        # the write target moved from a QLabel to the bar's picker button,
        # so the shim forwards .setText() to set_session_text() instead of
        # editing that method's body.
        self.mw.session_info_label = _SessionLabelShim(bar)
        bar.set_session_text("No session")

        bar.newSessionRequested.connect(
            lambda: self.mw.actions_handler.create_new_session()
        )
        self._populate_overflow(bar)
        bar.overflow.aboutToShow.connect(self._refresh_overflow)
        return bar

    def _populate_overflow(self, bar) -> None:
        """The open session's folder, then this PC's server and shortcuts.

        Rebuilt on a client change, because the first section's header is the
        client's name and a stale header points at the wrong profile. New
        session is the bar's own button now (phase 3 spec section 8).
        """
        menu = bar.overflow
        menu.clear()

        menu.add_section(self.mw.current_client_id or "No client")
        self._open_folder_item = menu.add_item(
            "Open session folder", self._open_session_folder
        )
        self._refresh_overflow()

        menu.add_section("THIS PC")
        menu.add_item("Server connection…", self._open_connection_settings)
        menu.add_item("Keyboard shortcuts…", lambda: ShortcutsDialog(self.mw).exec())

    def _refresh_overflow(self) -> None:
        self._open_folder_item.setEnabled(bool(getattr(self.mw, "session_path", None)))

    def _open_connection_settings(self):
        """Open the Server Connection settings dialog.

        Re-checks afterwards: this dialog is the only way back from a
        degraded launch, so the shell has to hear about a success.
        """
        ConnectionSettingsDialog(
            self.mw, "ShopifyTool", "FULFILLMENT_SERVER_PATH", PROD_SERVER_PATH
        ).exec()
        self.mw.recheck_connection()

    def _setup_tab_shortcuts(self):
        """Ctrl+1..5 go to the five destinations, through the same gate the rail uses.

        Bound to the rail rather than straight to main_tabs: a disabled rail
        button that a keystroke walks past is not a guard, and while
        disconnected three of these destinations touch the share.
        """
        for number, index in enumerate(range(5), start=1):
            QShortcut(
                QKeySequence(f"Ctrl+{number}"),
                self.mw,
                lambda index=index: self._go_to_destination(index),
            )

    def _go_to_destination(self, index: int) -> None:
        """Navigate to a rail destination, if the rail is offering it."""
        if self.mw.nav_rail.button(index).isEnabled():
            self.mw.main_tabs.setCurrentIndex(index)

    def _create_tab1_session_setup(self):
        """Setup: one QWebEngineView, no Qt inside (phase 3 spec).

        Everything drawn on this screen is in gui/web/setup.*; what it draws
        is built by refresh_setup(). The two slots are records the file
        handler writes and setup_state reads.
        """
        from gui.setup_bridge import SetupView, mount_setup_page

        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.mw.orders_slot = FileSlot("orders", on_change=self.refresh_setup)
        self.mw.stock_slot = FileSlot("stock", on_change=self.refresh_setup)

        # Never shown. Its enabled state is the guard (refresh_setup sets it),
        # and the page's Run analysis, Ctrl+R and Results' "Run analysis
        # again" all click it.
        self.mw.run_analysis_button = QPushButton("Run analysis", tab)
        self.mw.run_analysis_button.setEnabled(False)
        self.mw.run_analysis_button.hide()

        view = SetupView(tab)
        self.mw.setup_view = view
        self.mw.setup_bridge = mount_setup_page(view)
        layout.addWidget(view, 1)
        return tab

    def refresh_setup(self) -> None:
        """Build the Setup page's state from the window's facts and push it.

        The one place Run analysis is gated (phase 3 spec section 4.3). Never
        touches the share: the session's times are read where
        update_session_chips already reads them.
        """
        mw = self.mw
        if not hasattr(mw, "setup_bridge"):
            return  # asked before the page was mounted
        config = mw.active_profile_config or {}
        memory = config.get("inventory_memory") or {}

        session = None
        if mw.session_path:
            name = Path(mw.session_path).name
            facts = mw.session_facts
            session = (
                facts
                if facts is not None and facts.name == name
                else SessionFacts(name, None, None)
            )

        state = setup_state(
            connected=mw.is_connected(),
            client=mw.current_client_id or "",
            server_path=str(mw.profile_manager.base_path),
            session=session,
            orders=mw.orders_slot,
            stock=mw.stock_slot,
            memory=MemoryFacts(
                on=bool(memory.get("enabled", True)),
                skus=len(memory.get("skus") or {}),
                session=memory.get("session") or "",
                updated=_parse_time(memory.get("last_updated")),
            ),
            strategy=config.get("analysis_mode", "multi_first"),
            run=RunFacts(
                mw._analysis_running, mw._analysis_step, mw._analysis_cancelling
            ),
            now=datetime.now().astimezone(),
        )
        mw.run_analysis_button.setEnabled(state["run"]["enabled"])
        mw.setup_bridge.set_state(state)
        self.refresh_tools()

    def refresh_tools(self) -> None:
        """Let the Tools page follow the window's session.

        Called from refresh_setup(): every client, session and connection
        change already passes through it. ToolsWidget.sync() touches no file.
        """
        tools = getattr(self.mw, "tools_widget", None)
        if tools is not None:
            tools.sync()

    def refresh_recent_sessions(self, client_id: str):
        """Fill the command bar's session picker — call this whenever the
        current client changes (wire into wherever current_client_id is
        set). Bundle 5 deleted the Setup page's own quick-pick strip; this
        method kept its name across three call sites but now writes to the
        bar instead of a QListWidget."""
        if not client_id:
            self.mw.command_bar.set_recent_sessions([])
            return
        sessions = self.mw.session_manager.list_client_sessions(client_id)[:5]
        self.mw.command_bar.set_recent_sessions(
            [
                (info.get("session_name", "?"), info.get("session_path"))
                for info in sessions
            ]
        )

    def _create_tab2_analysis_results(self):
        """Tab 2: the results document -- one QWebEngineView, no Qt inside.

        The page paints `surface` to its own edges (9.13's seam rule), so the
        view takes the whole tab with no margins. Everything drawn on this
        screen is in gui/web/; Bundle 12 spec section 7.
        """
        from PySide6.QtGui import QCursor
        from PySide6.QtWebEngineWidgets import QWebEngineView

        from gui.results_bridge import mount_results_page

        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Never shown. Its enabled state is the guard every existing call
        # site already drives, and the page's Export clicks it via the bridge.
        self.mw.generate_reports_button_tab2 = QPushButton("Generate Reports", tab)
        self.mw.generate_reports_button_tab2.setEnabled(False)
        self.mw.generate_reports_button_tab2.clicked.connect(
            lambda: (
                self.mw.actions_handler.open_generate_reports_dialog()
                if hasattr(self.mw, "actions_handler")
                else None
            )
        )
        self.mw.generate_reports_button_tab2.hide()

        self.mw.results_menu = self._create_results_overflow(tab)

        view = QWebEngineView(tab)
        self.mw.results_view = view
        bridge = mount_results_page(view)
        self.mw.results_bridge = bridge
        bridge.selectionChanged.connect(self.mw.selection_helper.set_selected_orders)
        bridge.exportRequested.connect(self.mw.generate_reports_button_tab2.click)
        # A QMenu is a top-level popup, so it paints above the web view.
        bridge.screenMenuRequested.connect(
            lambda: self.mw.results_menu.popup(QCursor.pos())
        )

        # The detail pane's verbs (Bundle 13 spec §7.1). Resolved at call
        # time: actions_handler is built after this tab.
        def actions():
            return self.mw.actions_handler

        bridge.holdRequested.connect(
            lambda n: actions().set_order_fulfillable(n, False)
        )
        bridge.fulfillRequested.connect(
            lambda n: actions().set_order_fulfillable(n, True)
        )
        bridge.excludeRequested.connect(lambda n: actions().remove_entire_order(n))
        bridge.lineRemovalRequested.connect(
            lambda n, i, s: actions().remove_line(n, i, s)
        )
        bridge.lineQuantityChangeRequested.connect(
            lambda n, i, s, q: actions().change_line_quantity(n, i, s, q)
        )
        bridge.tagAddRequested.connect(lambda n, t: actions().add_internal_tag(n, t))
        bridge.tagRemovalRequested.connect(
            lambda n, t: actions().remove_internal_tag(n, t)
        )
        bridge.columnSettingsChanged.connect(
            lambda s: self.mw.schedule_results_columns_save(s)
        )
        # The KPI strip's hint: straight to the page that maps the price column.
        bridge.columnMappingRequested.connect(
            lambda: actions().open_settings_window(page="Orders mapping")
        )

        # Bundle 14: the selection bar's verbs. The page sends the order list
        # it counted, so the set written is the set the button named -- each
        # handler sets the selection from that list itself, first thing.
        def bulk(name):
            return lambda *args: getattr(actions(), name)(*args)

        bridge.bulkStatusRequested.connect(bulk("bulk_change_status"))
        bridge.bulkTagAddRequested.connect(bulk("bulk_add_tag"))
        bridge.bulkTagRemovalRequested.connect(bulk("bulk_remove_tag"))
        bridge.bulkExcludeRequested.connect(bulk("bulk_delete_orders"))
        bridge.bulkSkuRemovalRequested.connect(bulk("bulk_remove_sku_from_orders"))
        bridge.bulkOrderRemovalRequested.connect(bulk("bulk_remove_orders_with_sku"))
        bridge.bulkExportRequested.connect(bulk("bulk_export_selection"))
        bridge.undoRequested.connect(lambda: self.mw.undo_last_operation())

        layout.addWidget(view, 1)
        return tab

    def set_export_enabled(self, enabled: bool) -> None:
        """The hidden generate-reports button stays the guard; the page mirrors it."""
        self.mw.generate_reports_button_tab2.setEnabled(enabled)
        self.mw.results_bridge.set_export_enabled(enabled)

    def update_session_chips(self) -> None:
        """What the bar and the Setup page say about the open session's times.

        `Analysed 09:33` and `Stock file 19 h old` for the bar; when the
        session was opened and analysed for the page. Stock age is measured at
        analysis time, not now: it qualifies the analysis. The stock copy in
        the session keeps the source file's mtime (shutil.copy2 in core.py).
        """
        bar = self.mw.command_bar
        session_path = getattr(self.mw, "session_path", None)
        info = (
            self.mw.session_manager.get_session_info(session_path)
            if session_path
            else None
        ) or {}
        analysed = _parse_time(info.get("analysis_completed_at"))
        # The one read of session_info.json: refresh_setup never touches the share.
        self.mw.session_facts = (
            SessionFacts(
                Path(session_path).name, _parse_time(info.get("created_at")), analysed
            )
            if session_path
            else None
        )
        try:
            if analysed is None:
                bar.set_status("text_secondary", "")
                bar.set_stock_age("")
                return
            bar.set_status("text_secondary", f"Analysed {analysed.strftime('%H:%M')}")
            stock = (
                Path(self.mw.session_manager.get_input_dir(session_path))
                / "inventory.csv"
            )
            try:
                copied = datetime.fromtimestamp(stock.stat().st_mtime, tz=UTC)
            except OSError:
                bar.set_stock_age("")
                return
            bar.set_stock_age(f"Stock file {age_text(analysed - copied)} old")
        finally:
            self.refresh_setup()

    def _create_tab3_session_browser(self):
        """Browse: one QWebEngineView, no Qt inside (phase 4 spec).

        SessionBrowserWidget hosts the view and does the loading and the
        writes; everything drawn on this screen is in gui/web/browse.*.
        """
        from gui.session_browser_widget import SessionBrowserWidget

        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.mw.session_browser = SessionBrowserWidget(self.mw.session_manager, self.mw)
        layout.addWidget(self.mw.session_browser, 1)
        return tab

    def _create_tab4_logs(self):
        """Logs: one QWebEngineView, no Qt inside (phase 6 spec).

        LogsWidget hosts the view and keeps the entries; everything drawn on
        this screen is in gui/web/logs.*.
        """
        from gui.logs_widget import LogsWidget

        self.mw.logs_widget = LogsWidget(self.mw)
        return self.mw.logs_widget

    def _open_session_folder(self):
        """Open session folder in file explorer."""
        import platform
        import subprocess

        if not self.mw.session_path:
            self.log.warning("_open_session_folder called with no active session")
            return

        try:
            system = platform.system()
            if system == "Windows":
                subprocess.Popen(["explorer", self.mw.session_path])
            elif system == "Darwin":  # macOS
                subprocess.Popen(["open", self.mw.session_path])
            else:  # Linux
                subprocess.Popen(["xdg-open", self.mw.session_path])
        except Exception:
            self.log.exception("Failed to open session folder")
            show_error(
                self.mw, "The session folder wouldn't open", "Details are in Logs."
            )

    def set_ui_busy(self, is_busy):
        """Enables or disables key UI elements based on application state.

        This is used to prevent user interaction while a long-running process
        (like the main analysis) is active. It also enables report buttons
        only when data is loaded.

        Args:
            is_busy (bool): If True, disables interactive widgets. If False,
                enables them based on the current application state.
        """
        self.refresh_setup()

        # FIX: Check that DataFrame is not None before calling .empty
        is_data_loaded = (
            self.mw.analysis_results_df is not None
            and not self.mw.analysis_results_df.empty
        )

        if hasattr(self.mw, "results_bridge"):
            self.set_export_enabled(not is_busy and is_data_loaded)

        self.log.debug(
            f"UI busy state set to: {is_busy}, data_loaded: {is_data_loaded}"
        )

    def _create_results_overflow(self, parent):
        """The screen-level actions that are not the screen's one primary.

        A menu with no button of its own: the page's "⋯" asks for it through
        the bridge. The QActions keep their old attribute names, because every
        caller reaches them through setEnabled / setToolTip / setText.
        Configure Columns returns with the column manager (Bundle 13).
        Run analysis again, Open session folder and Copy summary came from the
        command bar in phase 2.
        """
        from PySide6.QtGui import QAction
        from PySide6.QtWidgets import QMenu

        menu = QMenu(parent)
        # Off by default in Qt, which would silently swallow every setToolTip
        # below -- including the undo tooltip actions_handler recomputes.
        menu.setToolTipsVisible(True)

        def action(label, slot, tooltip, enabled=False):
            item = QAction(label, menu)
            item.setToolTip(tooltip)
            item.setEnabled(enabled)
            item.triggered.connect(slot)
            menu.addAction(item)
            return item

        # What the mockup moves out of the command bar on Results (phase 2
        # spec section 6.2). Their enabled state is read when the menu opens.
        self.mw.rerun_analysis_action = action(
            "Run analysis again",
            lambda: self.mw.run_analysis_button.click(),
            "Run the analysis again on this session's files",
        )
        self.mw.open_folder_action = action(
            "Open session folder",
            self._open_session_folder,
            "Open this session's folder",
        )
        self.mw.copy_summary_action = action(
            "Copy summary",
            self._copy_results_summary,
            "Copy the session's numbers as one line",
        )
        menu.addSeparator()
        menu.aboutToShow.connect(self._refresh_results_menu)

        self.mw.add_product_button_tab2 = action(
            "Add Product to Order",
            lambda: (
                self.mw.actions_handler.show_add_product_dialog()
                if hasattr(self.mw, "actions_handler")
                else None
            ),
            "Manually add a product to an existing order",
        )
        self.mw.undo_button = action(
            "Undo", self.mw.undo_last_operation, "Undo last operation (Ctrl+Z)"
        )
        return menu

    def _refresh_results_menu(self) -> None:
        """Enable what can run now. Called as the menu opens."""
        self.mw.rerun_analysis_action.setEnabled(self.mw.run_analysis_button.isEnabled())
        self.mw.open_folder_action.setEnabled(
            bool(getattr(self.mw, "session_path", None))
        )
        self.mw.copy_summary_action.setEnabled(bool(self.mw.results_bridge.summary))

    def _copy_results_summary(self) -> None:
        text = summary_text(self.mw.results_bridge.summary)
        if not text:
            return
        QGuiApplication.clipboard().setText(text)
        self.mw.results_bridge.raise_toast("Summary copied")

    def _create_tab5_tools(self):
        """Tools: one QWebEngineView, no Qt inside (phase 5 spec).

        ToolsWidget hosts the view and the two tools behind it; everything
        drawn on this screen is in gui/web/tools.*.
        """
        from gui.tools_widget import ToolsWidget

        self.mw.tools_widget = ToolsWidget(self.mw)
        return self.mw.tools_widget

    def _refresh_icons(self):
        """Re-render every long-lived icon in the app's current theme colour.

        A QIcon handed to addTab()/setIcon() is a snapshot -- it does not
        follow a theme toggle, and a dark-grey glyph on the dark theme's
        background is invisible.
        """
        for index, name in enumerate(self._TAB_ICONS):
            self.mw.nav_rail.button(index).setIcon(icon(name))
        for attr, name in self._BUTTON_ICONS.items():
            widget = getattr(self.mw, attr, None)
            if widget is not None:
                widget.setIcon(icon(name))
