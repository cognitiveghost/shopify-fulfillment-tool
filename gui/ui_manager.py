import logging
from typing import ClassVar

import pandas as pd
from PySide6.QtCore import QItemSelection, QItemSelectionModel, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QTableView,
    QTableWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from gui.components.card import Card
from gui.components.commandbar import BarState, CommandBar
from gui.components.state_panel import StatePanel
from shared.icons import icon
from shared.navrail import NavRail
from shared.server_connection import ConnectionSettingsDialog
from shared.theme import StatusChip, on_theme_changed
from shopify_tool.profile_manager import PROD_SERVER_PATH

from .orders_view import HIDDEN_COLUMNS, ORDER_KEY, orders_frame
from .pandas_model import PandasModel
from .tag_categories_dialog import DEFAULT_TAG_COLOR
from .theme_manager import get_theme_manager
from .wheel_ignore_combobox import WheelIgnoreComboBox

# The setup card. 208 is the label gutter W1 specifies; the 840 cap stops a
# three-row form stretching to the page's full 1310, which turns a gutter
# into a horizon.
_SETUP_LABEL_GUTTER = 208
_SETUP_CARD_MAX_WIDTH = 840

# Tab index -> (main_window attribute holding that screen's primary button,
# whether the button lives on this screen and should stop painting itself).
#
# New Session used to be entry 2, borrowed by the Browse screen from Session
# Setup. Under Bundle 4 it is state-owned (BarState.NO_SESSION) and always
# present in the command bar, so the borrow is dead -- new_session_btn is
# hidden unconditionally below instead.
_SCREEN_ACTIONS = {
    0: ("run_analysis_button", True),
    1: ("generate_reports_button_tab2", True),
}


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
        "Information",
        "Tools",
    )
    # 8.6 shipped the rail with _TAB_LABELS verbatim, because guardrail 2 of
    # the parent spec's §6 forbids renaming a destination and moving it in the
    # same release. The move has shipped, so the rename is allowed now -- and
    # needed: at 56px the rail elides five of the six to "Ses...tup" /
    # "Anal...ults" / "Ses...ser", which is worse than no label. The full names
    # survive as the tooltips in _TAB_TOOLTIPS.
    _RAIL_LABELS = ("Setup", "Results", "Browse", "Info", "Tools")
    _TAB_TOOLTIPS = (
        "Session setup and file loading (Ctrl+1)",
        "View and edit analysis results (Ctrl+2)",
        "Browse past sessions (Ctrl+3)",
        "Statistics and logs (Ctrl+4)",
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
            "status_success", "Server connected",
            get_theme_manager().get_current_theme(), parent=self.mw,
        )
        self.mw.statusBar().addPermanentWidget(self.mw.connection_chip)

        self.mw.connectionChanged.connect(self._on_connection_changed)

        self.log.info(
            "UI widgets created successfully with tab-based structure and sidebar."
        )

    _OFFLINE_RAIL_ITEMS = (1, 2, 4)   # Results, Browse, Tools

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
            self._create_tab4_information(),
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
        for attribute, hide_in_page in _SCREEN_ACTIONS.values():
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
        self.mw.command_bar.bind_action(
            None if entry is None else getattr(self.mw, entry[0])
        )

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
        """Session Setup: one card, three rows, above a state-panel page 0.

        Four group boxes, a splitter and a recent-sessions strip became one
        card in Bundle 5. Run Analysis is not a row -- Bundle 4 made it this
        screen's command-bar primary (_SCREEN_ACTIONS[0]), and drawing it
        again here would be the fourth duplicate this screen just deleted.
        """
        from PySide6.QtWidgets import QButtonGroup, QStackedWidget

        from gui.components import Card, FileSlot, FormSection

        self.mw.orders_slot = FileSlot(
            "Orders file", "Drop the Shopify orders export here"
        )
        self.mw.stock_slot = FileSlot("Stock file", "Drop the stock export here")

        tab = QWidget()
        outer = QVBoxLayout(tab)
        outer.setContentsMargins(0, 0, 0, 0)

        card = Card(margins=(16, 16, 16, 16), spacing=8)
        card.setMaximumWidth(_SETUP_CARD_MAX_WIDTH)

        section = FormSection("", label_width=_SETUP_LABEL_GUTTER)

        self.mw.session_name_edit = QLineEdit()
        self.mw.session_name_edit.setPlaceholderText("Tuesday restock")
        section.add_row("Session name", self.mw.session_name_edit)

        section.add_row("Orders file", self.mw.orders_slot)

        stock_row = QWidget()
        stock_row_layout = QVBoxLayout(stock_row)
        stock_row_layout.setContentsMargins(0, 0, 0, 0)
        stock_row_layout.setSpacing(get_theme_manager().get_current_theme().spacing_xs)
        stock_row_layout.addWidget(self.mw.stock_slot)
        # Not a fourth row: the memory toggle only ever matters for the
        # stock file it substitutes for, so it lives in that row's own
        # field column rather than claiming a row of its own (spec's card
        # is three content rows).
        self.mw.inventory_memory_checkbox = QCheckBox("Use Inventory Memory")
        self.mw.inventory_memory_checkbox.setToolTip(
            "When enabled, analysis starts from the final stock of the last "
            "session instead of requiring a new stock file."
        )
        self.mw.inventory_memory_checkbox.setEnabled(False)  # enabled after client load
        stock_row_layout.addWidget(self.mw.inventory_memory_checkbox)
        section.add_row("Stock file", stock_row)

        section.add_row("Allocation", self._create_strategy_picker(QButtonGroup))

        card.add_widget(section)
        outer.addWidget(card)
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
        stack.addWidget(QWidget())    # page 0, replaced by _refresh_setup_panel
        stack.addWidget(tab)          # page 1, the card
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
        """Create Tab 2: Analysis Results

        Contains:
        - Filter controls
        - KPI strip
        - Results table
        - Selection bar (hidden until rows are selected)
        - Footer
        """
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(5)
        layout.setContentsMargins(5, 5, 5, 5)

        # Section 1: Filter controls
        filter_widget = self._create_filter_controls()
        layout.addWidget(filter_widget)

        # Section 2.7: KPI strip
        layout.addWidget(self._create_kpi_strip())

        # Section 3: Results table (MAIN content)
        table_widget = self._create_results_table()
        layout.addWidget(table_widget, 1)  # Stretch factor: 1
        layout.addWidget(self._create_selection_bar())

        # Section 4: Footer
        footer_widget = self._create_footer()
        layout.addWidget(footer_widget)

        return tab

    def _create_selection_bar(self):
        """The actions that only mean something once rows are selected.

        Below the table, as on Session Browser 1e: a bar above it would push
        every row down at the moment the user is pointing at one.
        """
        from PySide6.QtWidgets import QMenu

        from gui.components import ContextualSelectionBar

        handler = self.mw.actions_handler
        bar = ContextualSelectionBar()
        self.mw.selection_bar = bar

        bar.add_action(
            "Set Fulfillable", lambda: handler.bulk_change_status(True)
        )
        bar.add_action(
            "Set Not Fulfillable", lambda: handler.bulk_change_status(False)
        )
        bar.add_action("Add Tag", handler.bulk_add_tag)
        bar.add_action("Remove Tag", handler.bulk_remove_tag)

        delete_btn = bar.add_action("Delete ▾", role="danger")
        delete_menu = QMenu(delete_btn)
        delete_menu.addAction(
            "Remove SKU from Orders", handler.bulk_remove_sku_from_orders
        )
        delete_menu.addAction(
            "Remove Orders with SKU", handler.bulk_remove_orders_with_sku
        )
        delete_menu.addSeparator()
        delete_menu.addAction("Delete Selected Orders", handler.bulk_delete_orders)
        delete_btn.setMenu(delete_menu)

        # One decision, not two buttons.
        export_btn = bar.add_action("Export ▾")
        export_menu = QMenu(export_btn)
        export_menu.addAction("XLSX", lambda: handler.bulk_export_selection("xlsx"))
        export_menu.addAction("CSV", lambda: handler.bulk_export_selection("csv"))
        export_btn.setMenu(export_menu)

        bar.add_action("Clear", self.mw.tableView.clearSelection, role="ghost")
        return bar

    def _create_kpi_strip(self):
        """The four numbers the screen is about, above the table it counts."""
        from gui.components import KpiStrip

        strip = KpiStrip()
        self.mw.kpi_strip = strip
        # Em dash, not zero: an empty warehouse day and an unloaded screen are
        # different facts, and the label this replaces distinguished them.
        self.mw.kpi_cards = {
            key: strip.add("—", label)
            for key, label in (
                ("orders", "Orders"),
                ("fulfillable", "Fulfillable"),
                ("blocked", "Blocked"),
                ("items", "Items"),
            )
        }
        return strip

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

    def _create_tab4_information(self):
        """Create Tab 4: Information

        Contains sub-tabs:
        - Statistics
        - Activity Log
        - Execution Log
        """
        # Create sub-tab widget
        sub_tabs = QTabWidget()
        sub_tabs.setTabPosition(QTabWidget.North)

        # Sub-tab 1: Statistics
        stats_tab = self._create_statistics_subtab()
        sub_tabs.addTab(stats_tab, "Statistics")

        # Sub-tab 2: Activity Log
        activity_tab = self._create_activity_log_subtab()
        sub_tabs.addTab(activity_tab, "Activity Log")

        # Sub-tab 3: Execution Log
        execution_tab = self._create_execution_log_subtab()
        sub_tabs.addTab(execution_tab, "Execution Log")

        return sub_tabs

    def _open_session_folder(self):
        """Open session folder in file explorer."""
        import platform
        import subprocess

        if not self.mw.session_path:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.warning(
                self.mw, "No Session", "No session is currently active."
            )
            return

        try:
            system = platform.system()
            if system == "Windows":
                subprocess.Popen(["explorer", self.mw.session_path])
            elif system == "Darwin":  # macOS
                subprocess.Popen(["open", self.mw.session_path])
            else:  # Linux
                subprocess.Popen(["xdg-open", self.mw.session_path])
        except Exception as e:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.critical(
                self.mw, "Error", f"Failed to open session folder:\n{e!s}"
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

        if hasattr(self.mw, "generate_reports_button_tab2"):
            self.mw.generate_reports_button_tab2.setEnabled(
                not is_busy and is_data_loaded
            )

        self.log.debug(
            f"UI busy state set to: {is_busy}, data_loaded: {is_data_loaded}"
        )

    def update_results_table(self, data_df):
        """Populate the results table -- one row per *order*.

        ``data_df`` is the line-level ``analysis_results_df``; the table shows
        ``orders_frame(data_df)``. The line frame is untouched and stays the
        source of truth for every action, report and export.
        """
        self.log.info("Updating results table with new data.")
        if data_df.empty:
            self.log.warning("Received empty dataframe, clearing tables.")

        # Every tag add, status change and undo re-enters here, and setModel()
        # below throws the selection away. Capture it before the rebuild.
        previously_selected = self._selected_order_numbers()

        orders_df = orders_frame(data_df)
        self.mw.orders_df = orders_df

        # Column configuration is still saved against the line frame's names;
        # the order table applies the order-level half of it. See spec section 4.
        if not self.mw.all_columns:
            self.mw.all_columns = data_df.columns.tolist()
            self.mw.visible_columns = self.mw.all_columns[:]

        source_model = PandasModel(orders_df, self.mw.proxy_model)
        self.mw.proxy_model.setSourceModel(source_model)
        self.mw.tableView.setModel(self.mw.proxy_model)

        # Derived, not data: hidden from the view but still scanned by the
        # filter proxy. apply_config_to_view re-walks the frame, so this runs
        # again after it.
        for name in HIDDEN_COLUMNS:
            if name in orders_df.columns:
                self.mw.tableView.setColumnHidden(
                    orders_df.columns.get_loc(name), True
                )

        # No client selected yet -> no profile config; this runs on every
        # client switch, before one is loaded.
        profile = getattr(self.mw, "active_profile_config", None) or {}
        tag_categories = profile.get("tag_categories", {})
        # toggle_tag_panel() used to do this; the pane is always on screen now,
        # so the dropdown is loaded wherever tag_categories is already read.
        if hasattr(self.mw, "tag_management_panel"):
            self.mw.tag_management_panel.load_predefined_tags(tag_categories)

        if "Internal_Tags" in orders_df.columns:
            from gui.tag_delegate import TagDelegate

            self.mw.tag_delegate = TagDelegate(tag_categories, self.mw)
            self.mw.tableView.setItemDelegateForColumn(
                orders_df.columns.get_loc("Internal_Tags"), self.mw.tag_delegate
            )
            self._populate_tag_filter()

        # Auto-fit only when no saved config exists: resizeColumnsToContents()
        # is O(n*m), and a saved config overwrites the widths straight after.
        has_saved_config = (
            hasattr(self.mw, "table_config_manager")
            and self.mw.table_config_manager.has_saved_column_widths()
        )
        if not has_saved_config:
            self.mw.tableView.resizeColumnsToContents()

        if hasattr(self.mw, "table_config_manager"):
            self.mw.table_config_manager.apply_config_to_view(
                self.mw.tableView, self.results_view_frame()
            )

        # apply_config_to_view walks the frame it is given, so re-hide after it.
        for name in HIDDEN_COLUMNS:
            if name in orders_df.columns:
                self.mw.tableView.setColumnHidden(
                    orders_df.columns.get_loc(name), True
                )

        # setModel() above replaced the selection model, so the connection
        # must be remade every call rather than once at widget-creation time.
        selection_model = self.mw.tableView.selectionModel()
        try:
            selection_model.selectionChanged.disconnect(
                self.mw.on_results_selection_changed
            )
        except (RuntimeError, TypeError):
            pass  # not connected yet -- the first load
        selection_model.selectionChanged.connect(self.mw.on_results_selection_changed)
        self._reselect_orders(previously_selected)
        self.mw.on_results_selection_changed()

        self.update_hidden_columns_indicator()
        self.update_filter_count()

    def _selected_order_numbers(self) -> set:
        """The order numbers currently selected, or an empty set."""
        helper = getattr(self.mw, "selection_helper", None)
        if helper is None or not helper.has_selection():
            return set()
        selected = helper.get_selected_orders_data()
        if selected.empty or ORDER_KEY not in selected.columns:
            return set()
        return set(selected[ORDER_KEY])

    def _reselect_orders(self, order_numbers) -> None:
        """Re-select the rows for ``order_numbers`` after a model rebuild."""
        if not order_numbers:
            return
        orders_df = self.mw.orders_df
        if orders_df is None or orders_df.empty or ORDER_KEY not in orders_df.columns:
            return

        column = orders_df.columns.get_loc(ORDER_KEY)
        proxy = self.mw.proxy_model
        last_col = proxy.columnCount() - 1
        selection = QItemSelection()
        for proxy_row in range(proxy.rowCount()):
            source_row = proxy.mapToSource(proxy.index(proxy_row, 0)).row()
            if orders_df.iat[source_row, column] in order_numbers:
                selection.merge(
                    QItemSelection(
                        proxy.index(proxy_row, 0), proxy.index(proxy_row, last_col)
                    ),
                    QItemSelectionModel.Select,
                )
        if selection.isEmpty():
            return
        selection_model = self.mw.tableView.selectionModel()
        selection_model.select(
            selection, QItemSelectionModel.Select | QItemSelectionModel.Rows
        )
        # select() leaves currentIndex invalid, and the detail pane reads it to
        # decide which of the selected orders to show.
        selection_model.setCurrentIndex(
            selection.indexes()[0], QItemSelectionModel.NoUpdate
        )

    def results_view_frame(self):
        """The frame the results table actually renders.

        Column configuration addresses the view by column *index*, so every
        call that touches ``tableView`` must walk the order frame -- not the
        line-level ``analysis_results_df`` the two frames disagree with.
        HIDDEN_COLUMNS is dropped: both are always last, so no other column
        moves, and carrying them would let "Show All Columns" reveal an
        internal column and write its name into the client's saved config.
        """
        orders_df = getattr(self.mw, "orders_df", None)
        if orders_df is None:
            orders_df = self.mw.analysis_results_df
        if orders_df is None:
            return pd.DataFrame()
        return orders_df.drop(columns=list(HIDDEN_COLUMNS), errors="ignore")

    def _populate_tag_filter(self):
        """Populate the tag filter combo box with tags from current DataFrame.

        Dynamic approach: Only shows tags that actually exist in the current
        analysis_results_df, grouped by category. If DataFrame is empty,
        falls back to showing placeholder message.
        """
        if not hasattr(self.mw, "tag_filter_combo"):
            return

        # Clear existing items
        self.mw.tag_filter_combo.clear()
        self.mw.tag_filter_combo.addItem("All Tags", None)

        # Check if we have data
        if self.mw.analysis_results_df is None or self.mw.analysis_results_df.empty:
            self.mw.tag_filter_combo.addItem("(No data loaded)", None)
            self.mw.tag_filter_combo.setEnabled(False)
            return

        # Check if Internal_Tags column exists
        if "Internal_Tags" not in self.mw.analysis_results_df.columns:
            self.mw.tag_filter_combo.addItem("(No tags in data)", None)
            self.mw.tag_filter_combo.setEnabled(False)
            return

        # Extract unique tags from DataFrame
        unique_tags = self._extract_unique_tags_from_dataframe()

        if not unique_tags:
            self.mw.tag_filter_combo.addItem("(No tags applied)", None)
            self.mw.tag_filter_combo.setEnabled(False)
            return

        # Group tags by category
        tag_categories = self.mw.active_profile_config.get("tag_categories", {})
        grouped_tags = self._group_tags_by_category(unique_tags, tag_categories)

        # Populate combo in sorted order
        for category_label, tags in sorted(grouped_tags.items()):
            for tag in sorted(tags):
                self.mw.tag_filter_combo.addItem(f"{category_label}: {tag}", tag)

        self.mw.tag_filter_combo.setEnabled(True)
        self.log.info(
            f"Tag filter populated with {len(unique_tags)} unique tags from DataFrame"
        )

    def _extract_unique_tags_from_dataframe(self) -> set:
        """Extract all unique tags from analysis_results_df Internal_Tags column.

        Returns:
            set: Set of unique tag strings found in the DataFrame
        """
        from shopify_tool.tag_manager import parse_tags

        unique_tags = set()

        for tags_value in self.mw.analysis_results_df["Internal_Tags"]:
            tags = parse_tags(tags_value)
            unique_tags.update(tags)

        return unique_tags

    def _group_tags_by_category(self, tags: set, tag_categories: dict) -> dict:
        """Group tags by their category.

        Args:
            tags: Set of tag strings to categorize
            tag_categories: Tag categories config

        Returns:
            Dict mapping category_label -> list of tags
            Example: {"Packaging": ["BOX", "BAG"], "Priority": ["URGENT"]}
        """
        from shopify_tool.tag_manager import _normalize_tag_categories, get_tag_category

        categories = _normalize_tag_categories(tag_categories)
        grouped = {}

        for tag in tags:
            category_id = get_tag_category(tag, tag_categories)

            # Get category label
            if category_id in categories:
                category_label = categories[category_id].get("label", category_id)
            else:
                category_label = "Others"  # Custom/unknown tags

            if category_label not in grouped:
                grouped[category_label] = []

            grouped[category_label].append(tag)

        return grouped

    # ========== NEW TAB-SPECIFIC METHODS ==========

    def _create_filter_controls(self):
        """Search, scope, case and tag -- 1e's arrangement, on this screen.

        FilterBar owns the search field and the result count; the other three
        controls sit beside it, not inside it. No filter chips: the two combos
        already draw their own state and a chip would draw it twice.
        """
        from gui.components import FilterBar

        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.mw.filter_bar = FilterBar(widget)
        self.mw.filter_bar.search_field.setPlaceholderText("Search orders")
        # Kept so apply_filter(), Ctrl+F and the 1b tests address it unchanged.
        self.mw.filter_input = self.mw.filter_bar.search_field
        layout.addWidget(self.mw.filter_bar, 1)

        self.mw.filter_column_selector = WheelIgnoreComboBox()
        self.mw.filter_column_selector.addItem("All Columns")
        self.mw.filter_column_selector.setToolTip("Limit the search to one column")
        layout.addWidget(self.mw.filter_column_selector)

        self.mw.case_sensitive_checkbox = QCheckBox("Case Sensitive")
        layout.addWidget(self.mw.case_sensitive_checkbox)

        self.mw.tag_filter_combo = WheelIgnoreComboBox()
        self.mw.tag_filter_combo.addItem("All Tags", None)
        self.mw.tag_filter_combo.setToolTip("Show only orders carrying this tag")
        layout.addWidget(self.mw.tag_filter_combo)

        # The screen's one primary action. _SCREEN_ACTIONS[1] binds it into the
        # CommandBar; it is never shown in the page itself.
        self.mw.generate_reports_button_tab2 = QPushButton("Generate Reports", widget)
        self.mw.generate_reports_button_tab2.setEnabled(False)
        self.mw.generate_reports_button_tab2.setToolTip(
            "Generate packing lists and stock exports based on pre-defined filters"
        )
        self.mw.generate_reports_button_tab2.clicked.connect(
            lambda: self.mw.actions_handler.open_generate_reports_dialog()
            if hasattr(self.mw, "actions_handler")
            else None
        )
        self.mw.generate_reports_button_tab2.hide()

        layout.addWidget(self._create_results_overflow(widget))

        return widget

    def update_filter_count(self):
        """"312 orders", or "48 of 312 orders" while a filter narrows it."""
        bar = getattr(self.mw, "filter_bar", None)
        if bar is None:
            return
        total = self.mw.proxy_model.sourceModel()
        total_rows = total.rowCount() if total is not None else 0
        shown = self.mw.proxy_model.rowCount()
        bar.set_count(
            f"{total_rows} orders" if shown == total_rows
            else f"{shown} of {total_rows} orders"
        )

    def _create_results_overflow(self, parent):
        """The screen-level actions that are not the screen's one primary.

        Generate Reports is the primary (_SCREEN_ACTIONS[1]) and stays a hidden
        QPushButton bound into the CommandBar. These five are QActions under
        their old attribute names: every caller reaches them through
        setEnabled / setToolTip / setText, which QAction has too.
        """
        from PySide6.QtGui import QAction
        from PySide6.QtWidgets import QMenu, QToolButton

        button = QToolButton(parent)
        button.setText("⋯")
        button.setToolTip("More actions for this screen")
        button.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(button)
        # Off by default in Qt, which would silently swallow every setToolTip
        # below -- including the undo tooltip actions_handler recomputes to say
        # what Ctrl+Z would actually undo.
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
            lambda: self.mw.actions_handler.show_add_product_dialog()
            if hasattr(self.mw, "actions_handler")
            else None,
            "Manually add a product to an existing order",
        )
        self.mw.configure_columns_button_tab2 = action(
            "Configure Columns",
            lambda: self.mw.open_column_config_dialog()
            if hasattr(self.mw, "open_column_config_dialog")
            else None,
            "Customize table column visibility and order",
        )
        # Enabled by undo_manager, like the button it replaces. Ctrl+Z is still
        # how this is actually invoked, and the tooltip has always said so.
        self.mw.undo_button = action(
            "Undo", self.mw.undo_last_operation, "Undo last operation (Ctrl+Z)"
        )

        button.setMenu(menu)
        self.mw.results_overflow_button = button
        # build_stylesheet has a QPushButton rule but no QToolButton one, so the
        # global `QWidget { background-color: surface }` leaves this flat text
        # with no border and no hover -- and it is the only way to reach five
        # actions, Settings among them. Styled here rather than in shared/theme.py:
        # that file is one-way synced from packing-tool and must not be hand-edited.
        on_theme_changed(self.mw, lambda _t: self._style_results_overflow())
        return button

    def _style_results_overflow(self):
        """Give the overflow button a border and a hover, in the current theme.

        Re-run on theme_changed: the theme toggle lives *inside* this menu, so a
        one-shot stylesheet here would go stale the moment it is used.
        """
        button = getattr(self.mw, "results_overflow_button", None)
        if button is None:
            return
        theme = get_theme_manager().get_current_theme()
        button.setStyleSheet(
            f"""
            QToolButton {{
                background-color: {theme.surface_raised};
                border: 1px solid {theme.border};
                border-radius: 4px;
                padding: 4px 8px;
                color: {theme.text};
            }}
            QToolButton:hover {{ background-color: {theme.hover}; }}
            QToolButton::menu-indicator {{ image: none; }}
            """
        )

    def _create_results_table(self):
        """Create results table for Tab 2 (Analysis Results) with tag panel."""
        # Create container widget with horizontal layout
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        # Create table view
        self.mw.tableView = QTableView()
        self.mw.tableView.setSelectionBehavior(QTableView.SelectRows)
        self.mw.tableView.setSelectionMode(QTableView.ExtendedSelection)
        self.mw.tableView.setSortingEnabled(True)
        self.mw.tableView.setContextMenuPolicy(Qt.CustomContextMenu)

        # Scroll performance optimizations
        self.mw.tableView.setVerticalScrollMode(QTableView.ScrollPerPixel)
        self.mw.tableView.setHorizontalScrollMode(QTableView.ScrollPerPixel)

        from gui.status_edge_delegate import StatusEdgeDelegate

        # View-wide. setItemDelegateForColumn() wins over this, so TagDelegate
        # keeps the Internal_Tags column and simply never paints an edge there.
        self.mw.tableView.setItemDelegate(StatusEdgeDelegate(self.mw.tableView))

        # Add table to layout
        layout.addWidget(self.mw.tableView, 1)  # Stretch factor: 1

        from gui.order_detail_pane import OrderDetailPane

        self.mw.order_detail_pane = OrderDetailPane(self.mw)
        self.mw.order_detail_pane.setMinimumWidth(320)
        self.mw.order_detail_pane.setMaximumWidth(420)

        # The two existing connections and load_predefined_tags() call sites in
        # main_window_pyside.py speak to tag_management_panel; the pane owns the
        # panel now, so keep the name pointing at it.
        self.mw.tag_management_panel = self.mw.order_detail_pane.tag_panel
        self.mw.tag_management_panel.tag_added.connect(
            self.mw.add_internal_tag_to_order
        )
        self.mw.tag_management_panel.tag_removed.connect(
            self.mw.remove_internal_tag_from_order
        )

        layout.addWidget(self.mw.order_detail_pane)

        # Setup header context menu for column visibility
        self._setup_header_context_menu()

        return container

    def _setup_header_context_menu(self):
        """Setup context menu and signals for table header.

        Sets up:
        - Context menu for column visibility control
        - Signal handlers for column resize (with debounced save)
        - Signal handlers for column move (with Order_Number protection)
        """
        header = self.mw.tableView.horizontalHeader()
        header.setContextMenuPolicy(Qt.CustomContextMenu)
        header.customContextMenuRequested.connect(self._show_header_context_menu)

        # Enable column moving (user can drag-and-drop columns)
        header.setSectionsMovable(True)

        # Connect resize and move signals to TableConfigManager
        if hasattr(self.mw, "table_config_manager"):
            header.sectionResized.connect(
                self.mw.table_config_manager.on_column_resized
            )
            header.sectionMoved.connect(self.mw.table_config_manager.on_column_moved)

    def _show_header_context_menu(self, position):
        """Show context menu for table header.

        Args:
            position: Position where menu was requested
        """
        from PySide6.QtGui import QAction
        from PySide6.QtWidgets import QMenu

        # Only show menu if table config manager is available
        if not hasattr(self.mw, "table_config_manager"):
            return

        # Only show menu if data is loaded
        if self.mw.analysis_results_df is None or self.mw.analysis_results_df.empty:
            return

        header = self.mw.tableView.horizontalHeader()

        # Get logical index at position
        logical_index = header.logicalIndexAt(position)

        if logical_index < 0:
            return

        # Get column name from index
        model = self.mw.tableView.model()
        if model is None:
            return

        # Header sections map straight onto the order frame's columns: the
        # checkbox column that used to offset them is gone.
        col_index = logical_index
        view_df = self.results_view_frame()
        df_columns = view_df.columns.tolist()

        if col_index >= len(df_columns):
            return

        column_name = df_columns[col_index]

        # Check if column is locked
        is_locked = (
            hasattr(self.mw.table_config_manager, "_current_config")
            and self.mw.table_config_manager._current_config
            and column_name
            in self.mw.table_config_manager._current_config.locked_columns
        )

        # Create context menu
        menu = QMenu(self.mw)

        # Get current visibility
        is_visible = self.mw.table_config_manager.get_column_visibility(column_name)

        # Add toggle visibility action
        if is_locked:
            action_text = f"{column_name} (Locked - Always Visible)"
            action = QAction(action_text, self.mw)
            action.setEnabled(False)
            menu.addAction(action)
        else:
            action_text = (
                f"Hide '{column_name}'" if is_visible else f"Show '{column_name}'"
            )
            action = QAction(action_text, self.mw)
            action.triggered.connect(
                lambda: (
                    self.mw.table_config_manager.toggle_column_visibility(
                        self.mw.tableView, column_name, view_df
                    ),
                    self.update_hidden_columns_indicator(),
                )
            )
            menu.addAction(action)

        menu.addSeparator()

        # Add "Show All Columns" action
        show_all_action = QAction("Show All Columns", self.mw)
        show_all_action.triggered.connect(
            lambda: (
                self.mw.table_config_manager.show_all_columns(
                    self.mw.tableView, view_df
                ),
                self.update_hidden_columns_indicator(),
            )
        )
        menu.addAction(show_all_action)

        # Add submenu for showing hidden columns
        hidden_columns = self.mw.table_config_manager.get_hidden_columns(view_df)
        if hidden_columns:
            show_menu = menu.addMenu("Show Column")
            for hidden_col in hidden_columns:
                col_action = QAction(hidden_col, self.mw)
                col_action.triggered.connect(
                    lambda checked=False, col=hidden_col: (
                        self.mw.table_config_manager.set_column_visibility(
                            self.mw.tableView, col, True, view_df
                        ),
                        self.update_hidden_columns_indicator(),
                    )
                )
                show_menu.addAction(col_action)

        menu.addSeparator()

        # Add "Auto-Fit Column Widths" action
        auto_fit_action = QAction("Auto-Fit Column Widths", self.mw)
        auto_fit_action.triggered.connect(
            lambda: self.mw.table_config_manager.auto_fit_column_widths(
                self.mw.tableView, view_df
            )
        )
        menu.addAction(auto_fit_action)

        # Show menu at cursor position
        menu.exec(header.mapToGlobal(position))

    def _create_footer(self):
        """Create the footer bar at the bottom of Tab 2."""
        theme = get_theme_manager().get_current_theme()
        widget = QWidget()
        widget.setMaximumHeight(30)
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(5, 5, 5, 5)

        layout.addStretch()

        # Hidden columns indicator (clickable)
        self.mw.hidden_columns_indicator = QPushButton("")
        self.mw.hidden_columns_indicator.setFlat(True)
        self.mw.hidden_columns_indicator.setStyleSheet(
            f"QPushButton {{ color: {theme.accent_fill}; text-decoration: underline; border: none; padding: 0 5px; }}"
            f"QPushButton:hover {{ color: {theme.accent_fill}; }}"
        )
        self.mw.hidden_columns_indicator.setToolTip(
            "Click to show/restore hidden columns"
        )
        self.mw.hidden_columns_indicator.setVisible(False)
        self.mw.hidden_columns_indicator.clicked.connect(
            self._show_hidden_columns_popup
        )
        layout.addWidget(self.mw.hidden_columns_indicator)

        return widget

    def update_kpi_strip(self):
        """Orders, fulfillable, blocked, items -- from the line frame.

        Quantity is line-level, so the item count cannot come off the order
        frame. Orders are counted by nunique for the same reason.
        """
        cards = getattr(self.mw, "kpi_cards", None)
        if cards is None:
            return

        df = getattr(self.mw, "analysis_results_df", None)
        # The column guard is not paranoia: this runs outside _update_all_views'
        # try/except, so a KeyError here would skip set_ui_busy(False) and leave
        # the whole window stuck busy. Blank the cards instead.
        needed = {"Order_Number", "Order_Fulfillment_Status"}
        if df is None or df.empty or not needed <= set(df.columns):
            for card in cards.values():
                card.set_value("—")
            return

        total_orders = df["Order_Number"].nunique()
        fulfillable = df[df["Order_Fulfillment_Status"] == "Fulfillable"][
            "Order_Number"
        ].nunique()
        items = int(df["Quantity"].sum()) if "Quantity" in df.columns else len(df)

        cards["orders"].set_value(f"{total_orders}")
        cards["fulfillable"].set_value(f"{fulfillable}")
        cards["blocked"].set_value(f"{total_orders - fulfillable}")
        cards["items"].set_value(f"{items}")

    def update_hidden_columns_indicator(self):
        """Update the hidden columns indicator in the filter bar."""
        if not hasattr(self.mw, "hidden_columns_indicator"):
            return

        if (
            not hasattr(self.mw, "table_config_manager")
            or not hasattr(self.mw, "analysis_results_df")
            or self.mw.analysis_results_df is None
        ):
            self.mw.hidden_columns_indicator.setVisible(False)
            return

        hidden = self.mw.table_config_manager.get_hidden_columns(
            self.results_view_frame()
        )
        if hidden:
            self.mw.hidden_columns_indicator.setText(f"{len(hidden)} columns hidden")
            self.mw.hidden_columns_indicator.setVisible(True)
        else:
            self.mw.hidden_columns_indicator.setVisible(False)

    def _show_hidden_columns_popup(self):
        """Show popup menu listing hidden columns with quick-toggle options."""
        from PySide6.QtGui import QAction
        from PySide6.QtWidgets import QMenu

        if (
            not hasattr(self.mw, "table_config_manager")
            or self.mw.analysis_results_df is None
        ):
            return

        hidden = self.mw.table_config_manager.get_hidden_columns(
            self.results_view_frame()
        )
        if not hidden:
            return

        menu = QMenu(self.mw)

        for col in hidden:
            action = QAction(f"Show '{col}'", self.mw)
            action.triggered.connect(
                lambda checked=False, c=col: self._restore_hidden_column(c)
            )
            menu.addAction(action)

        menu.addSeparator()

        show_all_action = QAction("Show All Columns", self.mw)
        show_all_action.triggered.connect(self._restore_all_hidden_columns)
        menu.addAction(show_all_action)

        # Show menu above the indicator button
        pos = self.mw.hidden_columns_indicator.mapToGlobal(
            self.mw.hidden_columns_indicator.rect().topLeft()
        )
        menu.exec(pos)

    def _restore_hidden_column(self, column_name: str):
        """Restore a single hidden column via the indicator popup."""
        if (
            hasattr(self.mw, "table_config_manager")
            and hasattr(self.mw, "tableView")
            and self.mw.analysis_results_df is not None
        ):
            self.mw.table_config_manager.set_column_visibility(
                self.mw.tableView, column_name, True, self.results_view_frame()
            )
            self.update_hidden_columns_indicator()

    def _restore_all_hidden_columns(self):
        """Restore all hidden columns via the indicator popup."""
        if (
            hasattr(self.mw, "table_config_manager")
            and hasattr(self.mw, "tableView")
            and self.mw.analysis_results_df is not None
        ):
            self.mw.table_config_manager.show_all_columns(
                self.mw.tableView, self.results_view_frame()
            )
            self.update_hidden_columns_indicator()

    def _make_stat_card(self, value: str, label: str) -> tuple:
        """Stat card: large value on top, small label below. Returns (widget, value_label)."""
        card = Card()
        value_lbl = card.add_text(value, "display")
        card.add_text(label, "caption", wrap=True)
        return card, value_lbl

    def _make_courier_card(self, courier_id: str, orders: str, repeated: str) -> Card:
        """Courier card: orders count on top, courier name in middle, repeated below."""
        card = Card(min_width=100)
        card.add_text(orders, "display")
        card.add_text(courier_id, "caption")
        card.add_text(f"{repeated} repeated", "caption")
        return card

    def _make_tag_card(self, tag: str, count: str, color: str | None = None) -> Card:
        """Tag card: colored count badge on top, tag name below."""
        if color is None:
            color = DEFAULT_TAG_COLOR
        # Denser than the default on purpose: these sit 60px wide in a
        # horizontal scroll strip.
        card = Card(min_width=60, margins=(6, 4, 6, 4))
        theme = get_theme_manager().get_current_theme()
        card.add_text(
            count,
            "label",
            css=f"color: {theme.on_accent}; background-color: {color}; border-radius: 8px; padding: 2px 6px;",
        )
        card.add_text(tag, "caption", wrap=True)
        return card

    def _create_statistics_subtab(self):
        """Create statistics sub-tab with stat cards."""
        tab = QWidget()
        outer_layout = QVBoxLayout(tab)
        outer_layout.setSpacing(0)
        outer_layout.setContentsMargins(8, 8, 8, 8)

        # Outer vertical scroll wraps all sections
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll_widget = QWidget()
        layout = QVBoxLayout(scroll_widget)
        layout.setSpacing(10)
        layout.setContentsMargins(0, 0, 0, 0)
        scroll.setWidget(scroll_widget)
        outer_layout.addWidget(scroll)

        # ── 1. Session Totals ───────────────────────────────────────────────
        totals_group = QGroupBox("Session Totals")
        totals_row = QHBoxLayout(totals_group)
        totals_row.setSpacing(8)
        totals_row.setContentsMargins(8, 8, 8, 8)

        self.mw.stat_card_labels = {}
        for key, label_text in [
            ("total_orders_completed", "Orders\nCompleted"),
            ("total_orders_not_completed", "Orders Not\nCompleted"),
            ("total_items_to_write_off", "Items to\nWrite Off"),
            ("total_items_not_to_write_off", "Items Not\nWrite Off"),
        ]:
            card, val_lbl = self._make_stat_card("-", label_text)
            self.mw.stat_card_labels[key] = val_lbl
            totals_row.addWidget(card)
        totals_row.addStretch()
        layout.addWidget(totals_group)

        # ── 2. By Courier ──────────────────────────────────────────────────
        courier_group = QGroupBox("By Courier")
        courier_group_layout = QVBoxLayout(courier_group)
        courier_group_layout.setContentsMargins(8, 8, 8, 8)
        courier_group_layout.setSpacing(0)

        courier_hscroll = QScrollArea()
        courier_hscroll.setWidgetResizable(True)
        courier_hscroll.setFrameShape(QFrame.NoFrame)
        courier_hscroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        courier_hscroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        courier_hscroll.setSizeAdjustPolicy(QScrollArea.AdjustToContents)
        courier_hscroll.setMinimumHeight(90)

        courier_container = QWidget()
        self.mw.courier_cards_layout = QHBoxLayout(courier_container)
        self.mw.courier_cards_layout.setSpacing(8)
        self.mw.courier_cards_layout.setContentsMargins(0, 0, 0, 0)
        self.mw.courier_cards_layout.addStretch()
        courier_hscroll.setWidget(courier_container)
        courier_group_layout.addWidget(courier_hscroll)
        layout.addWidget(courier_group)

        # ── 3 & 4. Tags Breakdown (Fulfillable + Not Fulfillable, side by side) ──
        tags_row_widget = QWidget()
        tags_row_layout = QHBoxLayout(tags_row_widget)
        tags_row_layout.setSpacing(8)
        tags_row_layout.setContentsMargins(0, 0, 0, 0)

        tags_f_group = QGroupBox("Fulfillable Tags")
        tags_f_group_layout = QVBoxLayout(tags_f_group)
        tags_f_group_layout.setContentsMargins(8, 8, 8, 8)
        tags_f_group_layout.setSpacing(0)

        tags_f_hscroll = QScrollArea()
        tags_f_hscroll.setWidgetResizable(True)
        tags_f_hscroll.setFrameShape(QFrame.NoFrame)
        tags_f_hscroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        tags_f_hscroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        tags_f_hscroll.setSizeAdjustPolicy(QScrollArea.AdjustToContents)
        tags_f_hscroll.setMinimumHeight(90)

        tags_f_container = QWidget()
        self.mw.tags_fulfillable_layout = QHBoxLayout(tags_f_container)
        self.mw.tags_fulfillable_layout.setSpacing(8)
        self.mw.tags_fulfillable_layout.setContentsMargins(0, 0, 0, 0)
        self.mw.tags_fulfillable_layout.addStretch()
        tags_f_hscroll.setWidget(tags_f_container)
        tags_f_group_layout.addWidget(tags_f_hscroll)
        tags_row_layout.addWidget(tags_f_group)

        tags_nf_group = QGroupBox("Not Fulfillable Tags")
        tags_nf_group_layout = QVBoxLayout(tags_nf_group)
        tags_nf_group_layout.setContentsMargins(8, 8, 8, 8)
        tags_nf_group_layout.setSpacing(0)

        tags_nf_hscroll = QScrollArea()
        tags_nf_hscroll.setWidgetResizable(True)
        tags_nf_hscroll.setFrameShape(QFrame.NoFrame)
        tags_nf_hscroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        tags_nf_hscroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        tags_nf_hscroll.setSizeAdjustPolicy(QScrollArea.AdjustToContents)
        tags_nf_hscroll.setMinimumHeight(90)

        tags_nf_container = QWidget()
        self.mw.tags_not_fulfillable_layout = QHBoxLayout(tags_nf_container)
        self.mw.tags_not_fulfillable_layout.setSpacing(8)
        self.mw.tags_not_fulfillable_layout.setContentsMargins(0, 0, 0, 0)
        self.mw.tags_not_fulfillable_layout.addStretch()
        tags_nf_hscroll.setWidget(tags_nf_container)
        tags_nf_group_layout.addWidget(tags_nf_hscroll)
        tags_row_layout.addWidget(tags_nf_group)

        layout.addWidget(tags_row_widget)

        # ── 5. SKU Summary ─────────────────────────────────────────────────
        sku_group = QGroupBox("SKU Summary")
        sku_layout = QVBoxLayout(sku_group)
        sku_layout.setContentsMargins(8, 8, 8, 8)

        self.mw.sku_search_input = QLineEdit()
        self.mw.sku_search_input.setPlaceholderText("Filter by SKU or product...")
        self.mw.sku_search_input.textChanged.connect(self.mw._on_sku_search_changed)
        sku_layout.addWidget(self.mw.sku_search_input)

        self.mw.sku_table = QTableWidget()
        self.mw.sku_table.setColumnCount(6)
        self.mw.sku_table.setHorizontalHeaderLabels(
            ["#", "SKU", "Product", "Total Qty", "Fulfillable", "Not Fulfillable"]
        )
        self.mw.sku_table.horizontalHeader().setStretchLastSection(False)
        self.mw.sku_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.Stretch
        )
        self.mw.sku_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.mw.sku_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.mw.sku_table.verticalHeader().setVisible(False)
        self.mw.sku_table.setSortingEnabled(True)
        self.mw.sku_table.setMinimumHeight(200)
        sku_layout.addWidget(self.mw.sku_table)
        layout.addWidget(sku_group, 1)

        layout.addStretch()
        return tab

    def _create_activity_log_subtab(self):
        """Create activity log sub-tab for Tab 4."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)

        # Activity table
        self.mw.activity_log_table = QTableWidget()
        self.mw.activity_log_table.setColumnCount(3)
        self.mw.activity_log_table.setHorizontalHeaderLabels(
            ["Time", "Operation", "Description"]
        )
        self.mw.activity_log_table.horizontalHeader().setStretchLastSection(True)
        self.mw.activity_log_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.mw.activity_log_table.setEditTriggers(QTableWidget.NoEditTriggers)

        layout.addWidget(self.mw.activity_log_table)

        return tab

    def _create_execution_log_subtab(self):
        """Create execution log sub-tab for Tab 4."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)

        # Log text widget
        self.mw.execution_log_edit = QPlainTextEdit()
        self.mw.execution_log_edit.setReadOnly(True)
        self.mw.execution_log_edit.setLineWrapMode(QPlainTextEdit.NoWrap)

        layout.addWidget(self.mw.execution_log_edit)

        return tab

    def _create_tab5_tools(self):
        """Create Tab 5: Tools

        Contains sub-tabs:
        - Reference Labels: PDF processing for reference numbers
        - Barcode Generator: Placeholder for future implementation

        Returns:
            QWidget: Tools widget with sub-tabs
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

