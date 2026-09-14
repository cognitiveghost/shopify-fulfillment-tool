import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import ClassVar

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from gui.components.commandbar import BarState, CommandBar
from gui.components.error_banner import ErrorBanner, show_error
from gui.components.state_panel import StatePanel
from shared.icons import icon
from shared.navrail import NavRail
from shared.server_connection import ConnectionSettingsDialog
from shared.theme import StatusChip, on_theme_changed
from shopify_tool.profile_manager import PROD_SERVER_PATH

from .theme_manager import get_theme_manager

# The setup card. 208 is the label gutter W1 specifies; the 840 cap stops a
# three-row form stretching to the page's full 1310, which turns a gutter
# into a horizon.
_SETUP_LABEL_GUTTER = 208
_SETUP_CARD_MAX_WIDTH = 840

# Tab index -> (main_window attribute holding that screen's command-bar action,
# whether that button lives on a screen and must stop painting itself, and the
# role the bar's slot takes). Results re-runs the analysis as a *secondary*
# action: its one primary, Export, is inside the results document (W3).
#
# New Session used to be entry 2, borrowed by the Browse screen from Session
# Setup. Under Bundle 4 it is state-owned (BarState.NO_SESSION) and always
# present in the command bar, so the borrow is dead -- new_session_btn is
# hidden unconditionally below instead.
_SCREEN_ACTIONS = {
    0: ("run_analysis_button", True, "primary"),
    1: ("run_analysis_button", True, "secondary"),
}


def age_text(delta) -> str:
    """`19 h`, `45 min`, `3 d` -- the one age format the results screen uses."""
    minutes = max(0, int(delta.total_seconds() // 60))
    if minutes < 60:
        return f"{minutes} min"
    hours = minutes // 60
    if hours < 48:
        return f"{hours} h"
    return f"{hours // 24} d"


class _SetupPage(QWidget):
    """Slides the setup card's label gutter with window width.

    Spec §8's ladder: 208px above 1024, 96 down to the card's own 840px cap,
    0 (labels above fields) below that. Production never resizes below its
    1366px floor, but this page also runs in tests and in dev at whatever
    width Linux gives it, so the ladder has a trigger there even without one
    on Windows.
    """

    def __init__(self, section) -> None:
        super().__init__()
        self._section = section

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        width = self.width()
        if width >= 1024:
            gutter = _SETUP_LABEL_GUTTER
        elif width >= _SETUP_CARD_MAX_WIDTH:
            gutter = 96
        else:
            gutter = 0
        self._section.set_label_width(gutter)


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
    # Both former entries (open_session_folder_button, new_session_btn) were
    # duplicates of shell controls Bundle 5 deleted; the command bar's own
    # open_folder_button re-renders its icon directly (commandbar.py).
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

        # The rail is the outermost chrome, left of everything else.
        self.mw.nav_rail = NavRail(self.mw)
        main_horizontal.addWidget(self.mw.nav_rail)

        # Create right side container (header + tabs)
        right_side = QWidget()
        right_layout = QVBoxLayout(right_side)
        right_layout.setSpacing(5)
        right_layout.setContentsMargins(5, 5, 5, 5)

        # Step 1: The command bar — client selector, session, status, actions.
        # Replaces the two-row header: its own border-bottom is the separator.
        right_layout.addWidget(self._create_command_bar())

        # 9.25: a failure waits here, under the command bar, until dismissed.
        logs_index = self._RAIL_LABELS.index("Logs")
        self.mw.error_banner = ErrorBanner(
            open_logs=lambda: self.mw.main_tabs.setCurrentIndex(logs_index)
        )
        right_layout.addWidget(self.mw.error_banner)

        # Step 2: Create main tab widget with 5 tabs
        self._create_tabs()
        right_layout.addWidget(self.mw.main_tabs, 1)  # Stretch factor: 1

        # Add right side to horizontal layout
        main_horizontal.addWidget(right_side, 1)  # Stretch tabs

        # Every widget exists by now, so one pass sets every long-lived icon.
        # on_theme_changed applies immediately, so this is that first pass too.
        on_theme_changed(self.mw, lambda _t: self._refresh_icons())

        # Status bar: a fixed-height chip reporting connection state, in
        # place of the free-text "Ready" message it replaces.
        self.mw.statusBar().setFixedHeight(28)
        self.mw.connection_chip = StatusChip(
            "status_success",
            "Server connected",
            get_theme_manager().get_current_theme(),
            parent=self.mw,
        )
        self.mw.statusBar().addPermanentWidget(self.mw.connection_chip)

        self.mw.connectionChanged.connect(self._on_connection_changed)

        self.log.info(
            "UI widgets created successfully with tab-based structure and sidebar."
        )

    _OFFLINE_RAIL_ITEMS = (1, 2, 4)  # Results, Browse, Tools

    def _on_connection_changed(self, connected: bool) -> None:
        """The one signal that drives every control which touches the share.

        The disabling is the guard, not decoration on top of one: no call site
        below carries a None-check, because none of them is reachable while
        this is False. Spec §5.1.
        """
        for index in self._OFFLINE_RAIL_ITEMS:
            self.mw.nav_rail.button(index).setEnabled(connected)
        if not connected:
            self.mw.nav_rail.set_current(0)

        # The selector is not just empty while disconnected, it is disabled:
        # its "New client..." and "Manage groups..." rows are appended by the
        # component itself and would still write to the unreachable share.
        self.mw.command_bar.client_selector.setEnabled(connected)

        self._refresh_setup_panel()
        self.mw.setup_stack.setCurrentIndex(
            1 if connected and self.mw.current_client_id else 0
        )

        # Resting when connected -- nothing to act on. Live when not.
        # Hollow either way: the system derived it, no person set it.
        self.mw.connection_chip.set_status(
            "status_success" if connected else "status_danger",
            "Server connected" if connected else "Server unreachable",
            get_theme_manager().get_current_theme(),
            live=not connected,
            manual=False,
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

        # Two-way, and the back edge is load-bearing: actions_handler jumps
        # straight to Analysis Results after a run, and without this the rail
        # would keep highlighting the page the user left. It cannot loop --
        # NavRail.set_current returns before emitting when the index is
        # unchanged, and QTabWidget does not re-emit for the index it is on.
        self.mw.nav_rail.currentChanged.connect(self.mw.main_tabs.setCurrentIndex)
        self.mw.main_tabs.currentChanged.connect(self.mw.nav_rail.set_current)

        self._setup_tab_shortcuts()

        # The screen's primary action moves into the command bar's one slot.
        for attribute, hide_in_page, _role in _SCREEN_ACTIONS.values():
            if hide_in_page:
                getattr(self.mw, attribute).hide()
        self.mw.main_tabs.currentChanged.connect(self._bind_screen_action)
        self._bind_screen_action(self.mw.main_tabs.currentIndex())

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
        bar.openFolderRequested.connect(self._open_session_folder)
        self._populate_overflow(bar)
        return bar

    def _populate_overflow(self, bar) -> None:
        """The client's own scope, then this PC. Spec §4.1.

        Rebuilt on a client change, because the first section's header is the
        client's name and a stale header points at the wrong profile.
        """
        menu = bar.overflow
        menu.clear()

        client = self.mw.current_client_id or "No client"
        menu.add_section(client)
        # The bar's own New Session button is state-owned (BarState.NO_SESSION
        # only) -- with a session already open, the overflow was the only
        # scope-appropriate place left to reach it without switching clients.
        item = menu.add_item(
            "New session…",
            lambda: self.mw.actions_handler.create_new_session(),
        )
        item.setEnabled(bool(self.mw.current_client_id))
        item = menu.add_item(
            "Client settings…",
            lambda: self.mw.actions_handler.open_settings_window(),
        )
        item.setEnabled(bool(self.mw.current_client_id))

        menu.add_section("THIS PC")
        menu.add_item("Server connection…", self._open_connection_settings)

        current = "Dark" if get_theme_manager().is_dark_theme() else "Light"
        menu.add_choice_group(
            ["Light", "Dark"],
            current,
            lambda name: get_theme_manager().set_theme(name.lower()),
        )

    def _bind_screen_action(self, index: int) -> None:
        """Point the command bar's one primary at this screen's primary button."""
        entry = _SCREEN_ACTIONS.get(index)
        if entry is None:
            self.mw.command_bar.bind_action(None)
            return
        attribute, _hide_in_page, role = entry
        self.mw.command_bar.bind_action(getattr(self.mw, attribute), role)

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
        """Session Setup: one card, above a state-panel page 0.

        Four group boxes, a splitter and a recent-sessions strip became one
        card in Bundle 5. Run Analysis is not a row -- Bundle 4 made it this
        screen's command-bar primary (_SCREEN_ACTIONS[0]), and drawing it
        again here would be the fourth duplicate this screen just deleted.

        No Session name row: the field was inert (nothing read it -- see the
        PR body's design call) and PR #317 review picked dropping it over
        wiring it up sight unseen.
        """
        from PySide6.QtWidgets import QButtonGroup, QStackedWidget

        from gui.components import Card, FileSlot, FormSection

        self.mw.orders_slot = FileSlot(
            "Orders file", "Drop the Shopify orders export here"
        )
        self.mw.stock_slot = FileSlot("Stock file", "Drop the stock export here")

        section = FormSection("", label_width=_SETUP_LABEL_GUTTER)

        tab = _SetupPage(section)
        outer = QVBoxLayout(tab)
        outer.setContentsMargins(0, 0, 0, 0)

        card = Card(margins=(16, 16, 16, 16), spacing=8)
        # Fixed, not maximum: a QVBoxLayout fills its cross-axis by default,
        # which is how the card reached 840px before -- but centring it
        # needs an alignment flag on addWidget, and that switches sizing
        # from "fill the cross-axis" to "use sizeHint", which without a
        # fixed width would shrink the card to its unexpanded content size.
        card.setFixedWidth(_SETUP_CARD_MAX_WIDTH)

        section.add_row("Orders file", self.mw.orders_slot)
        section.add_row("Stock file", self.mw.stock_slot)

        # Its own row, not folded into the stock row's field column: PR #317
        # review flagged the card as showing a control the three-row mockup
        # doesn't, and the fix is to let it be the option it actually is.
        self.mw.inventory_memory_checkbox = QCheckBox("Use Inventory Memory")
        self.mw.inventory_memory_checkbox.setToolTip(
            "When enabled, analysis starts from the final stock of the last "
            "session instead of requiring a new stock file."
        )
        self.mw.inventory_memory_checkbox.setEnabled(False)  # enabled after client load
        section.add_row("Inventory memory", self.mw.inventory_memory_checkbox)

        section.add_row("Allocation", self._create_strategy_picker(QButtonGroup))

        card.add_widget(section)
        # Centred, not pinned to the page's top-left corner -- the page is
        # 1310px wide and an 840px card left-aligned in it reads as stranded.
        outer.addWidget(card, alignment=Qt.AlignHCenter)
        outer.addStretch()

        # The screen's primary, bound into the command bar by _SCREEN_ACTIONS.
        # Never rendered here -- Bundle 4 hides it.
        self.mw.run_analysis_button = QPushButton("Run analysis", tab)
        self.mw.run_analysis_button.setEnabled(False)
        self.mw.run_analysis_button.hide()

        # Written by update_session_info_label() for compatibility; never
        # shown -- the command bar's session picker is the visible
        # presentation now.
        self.mw.session_path_label = QLabel("No session", tab)
        self.mw.session_path_label.hide()

        self.mw.strategy_multi_item.toggled.connect(
            lambda checked: self.mw._on_analysis_mode_changed(0) if checked else None
        )
        self.mw.strategy_fifo.toggled.connect(
            lambda checked: self.mw._on_analysis_mode_changed(1) if checked else None
        )

        stack = QStackedWidget()
        # Page 0 starts empty -- _refresh_setup_panel fills it, and is the
        # only place either of its two forms is built.
        stack.addWidget(QWidget())  # page 0, replaced by _refresh_setup_panel
        stack.addWidget(tab)  # page 1, the card
        self.mw.setup_stack = stack
        self._refresh_setup_panel()
        return stack

    def _create_strategy_picker(self, QButtonGroup):
        """The two allocation strategies, each stating its consequence."""
        from gui.components import RadioCard

        holder = QWidget()
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(0, 0, 0, 0)

        self.mw.strategy_multi_item = RadioCard(
            "Multi-item first",
            "Fills orders that can go out whole before partial ones. A few "
            "old orders wait longer for stock instead.",
        )
        self.mw.strategy_fifo = RadioCard(
            "Oldest first",
            "Fills strictly by order date, whatever it contains. No order "
            "waits behind a newer one; more leave part-filled.",
        )
        self.mw.strategy_multi_item.setChecked(True)

        # QFormLayout's field-growth negotiation, once nested this deep
        # (Card > FormSection > QFormLayout > holder > RadioCard), does not
        # reliably re-query RadioCard's own (correct) heightForWidth after
        # the first layout pass -- a known QFormLayout limitation, not a
        # RadioCard bug (heightForWidth() is right when called directly; see
        # docs/superpowers/plans/2026-09-04-phase9-bundle5-session-setup-plan.md
        # Task 6 notes). A hard floor at the height each card itself knows it
        # needs sidesteps the stale negotiation instead of fighting it.
        for card in (self.mw.strategy_multi_item, self.mw.strategy_fifo):
            card.setMinimumHeight(card.heightForWidth(card.sizeHint().width()))

        group = QButtonGroup(holder)
        group.addButton(self.mw.strategy_multi_item)
        group.addButton(self.mw.strategy_fifo)
        self.mw.strategy_group = group

        layout.addWidget(self.mw.strategy_multi_item)
        layout.addWidget(self.mw.strategy_fifo)
        return holder

    def _refresh_setup_panel(self) -> None:
        """Page 0's two forms. Connection first, then client. No third one.

        A new panel each time rather than mutating one: StatePanel's four
        constructors differ in whether they have a button at all, and a
        widget that grows and loses a button is two widgets wearing one name.
        """
        if not self.mw.is_connected():
            panel = StatePanel.failed(
                "This PC can't reach the fulfilment server",
                "Clients, stock files and past sessions all live on the "
                "server. Until this PC reaches it, there is nothing to set up.",
                str(self.mw.profile_manager.base_path),
                "Server connection…",
            )
            panel.button.clicked.connect(self._open_connection_settings)
        else:
            panel = StatePanel.nothing_loaded(
                "Choose a client to begin",
                "Pick a client in the bar above. Sessions, stock and reports "
                "all belong to one client.",
                "",
            )
            # This form's action is the selector, so it takes focus -- but
            # only while it is still the thing to act on. Once a client is
            # chosen the stack moves to page 1 and stealing focus back would
            # yank it out of whatever the user just clicked.
            if not self.mw.current_client_id:
                self.mw.command_bar.client_selector.setFocus()

        old = self.mw.setup_stack.widget(0)
        self.mw.setup_stack.insertWidget(0, panel)
        self.mw.setup_stack.removeWidget(old)
        old.deleteLater()
        self.mw.setup_state_panel = panel

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
        bridge.tagAddRequested.connect(lambda n, t: actions().add_internal_tag(n, t))
        bridge.tagRemovalRequested.connect(
            lambda n, t: actions().remove_internal_tag(n, t)
        )
        bridge.columnSettingsChanged.connect(
            lambda s: self.mw.schedule_results_columns_save(s)
        )

        layout.addWidget(view, 1)
        return tab

    def set_export_enabled(self, enabled: bool) -> None:
        """The hidden generate-reports button stays the guard; the page mirrors it."""
        self.mw.generate_reports_button_tab2.setEnabled(enabled)
        self.mw.results_bridge.set_export_enabled(enabled)

    def update_session_chips(self) -> None:
        """`Analysed 09:33` and `Stock file 19 h old` (W3's two command-bar chips).

        Stock age is measured at analysis time, not now: it qualifies the
        analysis. The stock copy in the session keeps the source file's mtime
        (shutil.copy2 in core.py).
        """
        bar = self.mw.command_bar
        session_path = getattr(self.mw, "session_path", None)
        info = (
            self.mw.session_manager.get_session_info(session_path)
            if session_path
            else None
        )
        try:
            analysed = datetime.fromisoformat(
                (info or {}).get("analysis_completed_at") or ""
            )
        except ValueError:
            analysed = None
        if analysed is None:
            bar.set_status("text_secondary", "")
            bar.set_stock_age("")
            return
        if analysed.tzinfo is None:
            analysed = analysed.astimezone()
        bar.set_status(
            "text_secondary", f"Analysed {analysed.astimezone().strftime('%H:%M')}"
        )
        stock = (
            Path(self.mw.session_manager.get_input_dir(session_path)) / "inventory.csv"
        )
        try:
            copied = datetime.fromtimestamp(stock.stat().st_mtime, tz=timezone.utc)
        except OSError:
            bar.set_stock_age("")
            return
        bar.set_stock_age(f"Stock file {age_text(analysed - copied)} old")

    def _create_tab3_session_browser(self):
        """Create Tab 3: Session Browser

        Reuses existing SessionBrowserWidget.
        """
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(5)
        layout.setContentsMargins(5, 5, 5, 5)

        # REUSE existing SessionBrowserWidget
        from gui.session_browser_widget import SessionBrowserWidget

        self.mw.session_browser = SessionBrowserWidget(self.mw.session_manager, self.mw)

        layout.addWidget(self.mw.session_browser, 1)  # Full stretch

        return tab

    def _create_tab4_logs(self):
        """Create Tab 4: Logs -- one viewer, two sources, no sub-tabs.

        Statistics is deleted (9.20) and the two log widgets are one widget
        (9.21), so there is nothing left to tab between.
        """
        from gui.log_viewer import LogViewer

        self.mw.log_viewer = LogViewer(self.mw)
        return self.mw.log_viewer

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
        self.mw.run_analysis_button.setEnabled(not is_busy)

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

    def _create_tab5_tools(self):
        """Create Tab 5: Tools

        Reference labels and Barcode labels as two cards, side by side, that
        stack when the page is narrow. See gui/tools_widget.py.

        Returns:
            QWidget: the Tools page
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
