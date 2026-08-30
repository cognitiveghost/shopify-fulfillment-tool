import logging
from typing import ClassVar

import pandas as pd
from PySide6.QtCore import QItemSelection, QItemSelectionModel, Qt
from PySide6.QtGui import QFontMetrics, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSplitter,
    QTableView,
    QTableWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from gui.components.card import Card
from gui.components.commandbar import CommandBar
from shared.navrail import NavRail
from shared.server_connection import ConnectionSettingsDialog
from shopify_tool.profile_manager import PROD_SERVER_PATH

from .bulk_operations_toolbar import BulkOperationsToolbar
from .icons import icon
from .orders_view import HIDDEN_COLUMNS, ORDER_KEY, orders_frame
from .pandas_model import PandasModel
from .tag_categories_dialog import DEFAULT_TAG_COLOR
from .theme_manager import font_css, get_theme_manager
from .wheel_ignore_combobox import WheelIgnoreComboBox

# Tab 1 layout. The setup column is inside a QScrollArea, which is always
# willing to scroll rather than ask the splitter for room -- so it must declare
# the width its content needs, or action buttons get hidden. See
# docs/superpowers/specs/2026-08-23-session-setup-layout-design.md.
# Frame + vertical scrollbar. Measured: frame 0 (the scroll area is NoFrame)
# and a 12px scrollbar from the theme -- 24 is deliberate slack over that.
_SETUP_COLUMN_SLACK = 24
_RECENT_PANEL_MAX_WIDTH = 320
_RECENT_SESSIONS_ROWS = 5

# Tab index -> (main_window attribute holding that screen's primary button,
# whether the button lives on this screen and should stop painting itself).
#
# Screen 2 is the exception: SessionBrowserWidget has no New Session control of
# its own, so it borrows Session Setup's -- which must keep rendering there,
# where Run Analysis is the primary and this is not. Hence an explicit flag
# rather than inferring hiding from the mapping.
_SCREEN_ACTIONS = {
    0: ("run_analysis_button", True),
    1: ("generate_reports_button_tab2", True),
    2: ("new_session_btn", False),
}


def _recent_list_height(widget: QListWidget) -> int:
    """Height of exactly _RECENT_SESSIONS_ROWS rows.

    Prefers sizeHintForRow(), Qt's own measurement of an actual row -- it
    returns -1 while the list is empty, which it is when the panel is first
    built, so that case falls back to a font-metrics estimate. The +4 on the
    fallback is the transparent 2px top/bottom border every QListWidget::item
    carries so selecting one does not shift its text (shared/theme.py);
    without it the fifth row clips. The trailing +4 is slack for the frame.

    Font-metric estimates drift a pixel from the real row height across
    Qt/font builds (it did between the dev machine and CI), so
    refresh_recent_sessions() re-calls this once real items exist to correct
    the fixed height to the true measurement.
    """
    row = widget.sizeHintForRow(0)
    if row < 0:
        row = QFontMetrics(widget.font()).height() + 4
    return row * _RECENT_SESSIONS_ROWS + 2 * widget.frameWidth() + 4


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
    _BUTTON_ICONS: ClassVar[dict[str, str]] = {
        "open_session_folder_button": "folder-open",
        "new_session_btn": "folder-plus",
        "clear_filter_button": "funnel-x",
        "connection_btn": "settings",
    }

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
        self._refresh_icons()
        get_theme_manager().theme_changed.connect(self._refresh_icons)

        # Setup status bar
        self.mw.statusBar().showMessage("Ready")

        self.log.info(
            "UI widgets created successfully with tab-based structure and sidebar."
        )

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

        # Server Connection is an app setting, not a destination -- footer.
        self.mw.connection_btn = self.mw.nav_rail.add_footer_item(
            icon("settings"), "Server"
        )
        self.mw.connection_btn.setToolTip("Server Connection settings")
        self.mw.connection_btn.clicked.connect(self._open_connection_settings)

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

        # Same name the header's label had, so update_session_info_label()
        # keeps working unchanged.
        self.mw.session_info_label = bar.session_label
        bar.set_session("No session")
        return bar

    def _bind_screen_action(self, index: int) -> None:
        """Point the command bar's one primary at this screen's primary button."""
        entry = _SCREEN_ACTIONS.get(index)
        self.mw.command_bar.bind_action(
            None if entry is None else getattr(self.mw, entry[0])
        )

    def _open_connection_settings(self):
        """Open the Server Connection settings dialog."""
        ConnectionSettingsDialog(
            self.mw, "ShopifyTool", "FULFILLMENT_SERVER_PATH", PROD_SERVER_PATH
        ).exec()

    def _setup_tab_shortcuts(self):
        """Setup keyboard shortcuts for tab switching."""
        # Tab switching shortcuts
        QShortcut(
            QKeySequence("Ctrl+1"),
            self.mw,
            lambda: self.mw.main_tabs.setCurrentIndex(0),
        )
        QShortcut(
            QKeySequence("Ctrl+2"),
            self.mw,
            lambda: self.mw.main_tabs.setCurrentIndex(1),
        )
        QShortcut(
            QKeySequence("Ctrl+3"),
            self.mw,
            lambda: self.mw.main_tabs.setCurrentIndex(2),
        )
        QShortcut(
            QKeySequence("Ctrl+4"),
            self.mw,
            lambda: self.mw.main_tabs.setCurrentIndex(3),
        )
        QShortcut(
            QKeySequence("Ctrl+5"),
            self.mw,
            lambda: self.mw.main_tabs.setCurrentIndex(4),
        )

    def _create_tab1_session_setup(self):
        """Create Tab 1: Session Setup with split layout.

        Contains:
        - Left panel: Session management, File loading, Actions, Reports. Takes
          all width the quick-pick does not need, and never less than its
          content requires.
        - Right panel: Recent Sessions quick-pick, capped at
          _RECENT_PANEL_MAX_WIDTH (full browser is on Tab 3).
        """
        tab = QWidget()
        main_layout = QHBoxLayout(tab)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Create horizontal splitter
        splitter = QSplitter(Qt.Horizontal)

        # Left panel - Session Setup content
        left_panel = self._create_session_setup_panel()
        splitter.addWidget(left_panel)

        # Right panel - Session Browser
        right_panel = self._create_session_browser_panel()
        splitter.addWidget(right_panel)

        # All extra width goes to the setup content, not the quick-pick card --
        # a 6:4 stretch re-inflates the card to 642px on a wide monitor for a
        # five-row list.
        splitter.setSizes([1100, _RECENT_PANEL_MAX_WIDTH])
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)

        main_layout.addWidget(splitter)
        return tab

    def _create_session_setup_panel(self):
        """Create left panel with Session Setup content.

        Wrapped in a QScrollArea (same pattern as _create_statistics_subtab)
        because switching Orders/Stock 'Load Mode' to Folder reveals extra
        widgets that were previously hidden. Without a scroll area to absorb
        that growth, the panel's minimum height jumps and forces the whole
        top-level window to resize/reflow instead of just this panel.
        """
        panel = QWidget()
        outer_layout = QVBoxLayout(panel)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        scroll_widget = QWidget()
        layout = QVBoxLayout(scroll_widget)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        # Existing sections (no changes to logic)
        layout.addWidget(self._create_session_management_section())
        layout.addWidget(self._create_files_group())
        layout.addWidget(self._create_main_actions_group())
        layout.addWidget(self._create_reports_group())
        layout.addStretch()

        scroll.setWidget(scroll_widget)
        outer_layout.addWidget(scroll)

        # A QScrollArea's own minimum is tiny -- it would rather scroll than ask
        # for room, which let the splitter squeeze this column below the 706px
        # its content needs and hide action buttons behind a horizontal
        # scrollbar. Pin the minimum to what the content actually reports; the
        # hint is already correct here, before show().
        panel.setMinimumWidth(
            scroll_widget.minimumSizeHint().width() + _SETUP_COLUMN_SLACK
        )

        return panel

    def _create_session_browser_panel(self):
        """Create right panel with a compact 'Recent Sessions' quick-pick.

        The full SessionBrowserWidget lives exclusively on Tab 3 ("Session
        Browser") — this panel used to embed a second full copy of it squeezed
        into 40% width, which was too narrow to be useful. See
        2026-07-26-unified-ui-design-system-design.md.
        """
        panel = QWidget()
        # The stretch factors already size the card; this cap is what stops the
        # user dragging the splitter and re-inflating it.
        panel.setMaximumWidth(_RECENT_PANEL_MAX_WIDTH)
        layout = QVBoxLayout(panel)
        layout.setSpacing(5)
        layout.setContentsMargins(10, 10, 10, 10)

        title = QLabel("Recent Sessions")
        title.setStyleSheet(font_css("label"))
        layout.addWidget(title)

        self.mw.recent_sessions_list = QListWidget()
        self.mw.recent_sessions_list.itemDoubleClicked.connect(self._on_recent_session_double_clicked)
        self.mw.recent_sessions_list.setFixedHeight(
            _recent_list_height(self.mw.recent_sessions_list)
        )
        layout.addWidget(self.mw.recent_sessions_list)

        open_full_link = QPushButton("Open full Session Browser →")
        open_full_link.setFlat(True)
        open_full_link.clicked.connect(lambda: self.mw.main_tabs.setCurrentIndex(2))
        layout.addWidget(open_full_link)
        layout.addStretch()  # keep the list and its link together at the top

        return panel

    def _on_recent_session_double_clicked(self, item):
        session_path = item.data(Qt.ItemDataRole.UserRole)
        if session_path:
            self.mw.on_session_selected(session_path)

    def refresh_recent_sessions(self, client_id: str):
        """Populate the Tab 1 quick-pick list — call this whenever the current
        client changes (wire into wherever current_client_id is set)."""
        self.mw.recent_sessions_list.clear()
        if not client_id:
            return
        sessions = self.mw.session_manager.list_client_sessions(client_id)[
            :_RECENT_SESSIONS_ROWS
        ]
        for info in sessions:
            label = f"{info.get('session_name', '?')} — {info.get('status', '?')}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, info.get("session_path"))
            self.mw.recent_sessions_list.addItem(item)
        self.mw.recent_sessions_list.setFixedHeight(
            _recent_list_height(self.mw.recent_sessions_list)
        )

    def _create_tab2_analysis_results(self):
        """Create Tab 2: Analysis Results

        Contains:
        - Filter controls
        - Action buttons
        - Bulk operations toolbar (hidden by default)
        - Results table
        - Summary bar
        """
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(5)
        layout.setContentsMargins(5, 5, 5, 5)

        # Section 1: Filter controls
        filter_widget = self._create_filter_controls()
        layout.addWidget(filter_widget)

        # Section 2: Action buttons
        actions_widget = self._create_results_actions()
        layout.addWidget(actions_widget)

        # Section 2.5: Bulk Operations Toolbar (NEW - hidden by default)
        self.mw.bulk_toolbar = BulkOperationsToolbar()
        self.mw.bulk_toolbar.setVisible(False)
        layout.addWidget(self.mw.bulk_toolbar)

        # Section 2.7: KPI strip
        layout.addWidget(self._create_kpi_strip())

        # Section 3: Results table (MAIN content)
        table_widget = self._create_results_table()
        layout.addWidget(table_widget, 1)  # Stretch factor: 1

        # Section 4: Footer
        footer_widget = self._create_footer()
        layout.addWidget(footer_widget)

        return tab

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

    def _create_client_selector_group(self):
        """Creates the 'Client Selection' QGroupBox with ClientSelectorWidget."""
        from gui.client_settings_dialog import ClientSelectorWidget

        group = QGroupBox("Client Selection")
        layout = QHBoxLayout()
        group.setLayout(layout)

        # Add client selector widget
        self.mw.client_selector = ClientSelectorWidget(self.mw.profile_manager, self.mw)
        layout.addWidget(self.mw.client_selector)
        layout.addStretch()

        return group

    def _create_files_group(self):
        """Creates the 'Load Data' QGroupBox with folder support."""
        group = QGroupBox("Load Data")
        layout = QHBoxLayout()
        group.setLayout(layout)

        # Orders section
        # ponytail: Orders and Stock side by side set this page's 706px floor,
        # so the setup column stops shrinking at 730px. That is inert today --
        # the window cannot go below 1221px anyway, a floor Tab 2 sets, not this
        # one. No responsive stacking is built; if Tab 2's floor ever drops,
        # stack these two vertically below a width threshold.
        layout.addWidget(self._create_orders_file_section())

        # Stock section
        layout.addWidget(self._create_stock_file_section())

        return group

    def _create_orders_file_section(self):
        """Creates Orders file selection with folder support."""
        group_box = QGroupBox("Orders File")
        layout = QVBoxLayout()

        # Mode selector (Radio buttons)
        mode_layout = QHBoxLayout()
        mode_label = QLabel("Load Mode:")

        self.mw.orders_single_radio = QRadioButton("Single File")
        self.mw.orders_folder_radio = QRadioButton("Folder (Multiple Files)")
        self.mw.orders_single_radio.setChecked(True)  # Default

        mode_layout.addWidget(mode_label)
        mode_layout.addWidget(self.mw.orders_single_radio)
        mode_layout.addWidget(self.mw.orders_folder_radio)
        mode_layout.addStretch()

        layout.addLayout(mode_layout)

        # Select button (text changes based on mode)
        self.mw.load_orders_btn = QPushButton("Load Orders File (.csv)")
        self.mw.load_orders_btn.setToolTip(
            "Select the orders_export.csv file from Shopify."
        )
        self.mw.load_orders_btn.setEnabled(False)
        layout.addWidget(self.mw.load_orders_btn)

        # File path label (shows filename or "X files merged")
        path_layout = QHBoxLayout()
        path_layout.addWidget(QLabel("Selected:"))
        self.mw.orders_file_path_label = QLabel("Orders file not selected")
        self.mw.orders_file_status_label = QLabel("")
        path_layout.addWidget(self.mw.orders_file_path_label)
        path_layout.addWidget(self.mw.orders_file_status_label)
        path_layout.addStretch()

        layout.addLayout(path_layout)

        # File list preview (only visible in folder mode)
        self.mw.orders_file_list_widget = QListWidget()
        self.mw.orders_file_list_widget.setMaximumHeight(120)
        self.mw.orders_file_list_widget.setVisible(False)
        layout.addWidget(self.mw.orders_file_list_widget)

        # File count label
        self.mw.orders_file_count_label = QLabel("")
        self.mw.orders_file_count_label.setVisible(False)
        layout.addWidget(self.mw.orders_file_count_label)

        # Options (only visible in folder mode)
        self.mw.orders_options_widget = QWidget()
        options_layout = QVBoxLayout()

        self.mw.orders_recursive_checkbox = QCheckBox("Include subfolders")
        self.mw.orders_remove_duplicates_checkbox = QCheckBox("Remove duplicate orders")
        self.mw.orders_remove_duplicates_checkbox.setChecked(True)
        self.mw.orders_remove_duplicates_checkbox.setToolTip(
            "Remove orders with same Order Number + SKU (keeps first occurrence)"
        )

        options_layout.addWidget(self.mw.orders_recursive_checkbox)
        options_layout.addWidget(self.mw.orders_remove_duplicates_checkbox)
        self.mw.orders_options_widget.setLayout(options_layout)
        self.mw.orders_options_widget.setVisible(False)

        layout.addWidget(self.mw.orders_options_widget)

        group_box.setLayout(layout)
        return group_box

    def _create_stock_file_section(self):
        """Creates Stock file selection with folder support."""
        group_box = QGroupBox("Stock File")
        layout = QVBoxLayout()

        # Mode selector (Radio buttons)
        mode_layout = QHBoxLayout()
        mode_label = QLabel("Load Mode:")

        self.mw.stock_single_radio = QRadioButton("Single File")
        self.mw.stock_folder_radio = QRadioButton("Folder (Multiple Files)")
        self.mw.stock_single_radio.setChecked(True)  # Default

        mode_layout.addWidget(mode_label)
        mode_layout.addWidget(self.mw.stock_single_radio)
        mode_layout.addWidget(self.mw.stock_folder_radio)
        mode_layout.addStretch()

        layout.addLayout(mode_layout)

        # Select button (text changes based on mode)
        self.mw.load_stock_btn = QPushButton("Load Stock File (.csv)")
        self.mw.load_stock_btn.setToolTip("Select the inventory/stock CSV file.")
        self.mw.load_stock_btn.setEnabled(False)
        layout.addWidget(self.mw.load_stock_btn)

        # File path label (shows filename or "X files merged")
        path_layout = QHBoxLayout()
        path_layout.addWidget(QLabel("Selected:"))
        self.mw.stock_file_path_label = QLabel("Stock file not selected")
        self.mw.stock_file_status_label = QLabel("")
        path_layout.addWidget(self.mw.stock_file_path_label)
        path_layout.addWidget(self.mw.stock_file_status_label)
        path_layout.addStretch()

        layout.addLayout(path_layout)

        # Inventory memory toggle
        self.mw.inventory_memory_checkbox = QCheckBox("Use Inventory Memory")
        self.mw.inventory_memory_checkbox.setToolTip(
            "When enabled, analysis starts from the final stock of the last session "
            "instead of requiring a new stock file."
        )
        self.mw.inventory_memory_checkbox.setEnabled(False)  # enabled after client load
        layout.addWidget(self.mw.inventory_memory_checkbox)

        # File list preview (only visible in folder mode)
        self.mw.stock_file_list_widget = QListWidget()
        self.mw.stock_file_list_widget.setMaximumHeight(120)
        self.mw.stock_file_list_widget.setVisible(False)
        layout.addWidget(self.mw.stock_file_list_widget)

        # File count label
        self.mw.stock_file_count_label = QLabel("")
        self.mw.stock_file_count_label.setVisible(False)
        layout.addWidget(self.mw.stock_file_count_label)

        # Options (only visible in folder mode)
        self.mw.stock_options_widget = QWidget()
        options_layout = QVBoxLayout()

        self.mw.stock_recursive_checkbox = QCheckBox("Include subfolders")
        self.mw.stock_remove_duplicates_checkbox = QCheckBox("Remove duplicate items")
        self.mw.stock_remove_duplicates_checkbox.setChecked(True)
        self.mw.stock_remove_duplicates_checkbox.setToolTip(
            "Remove items with same SKU (keeps first occurrence)"
        )

        options_layout.addWidget(self.mw.stock_recursive_checkbox)
        options_layout.addWidget(self.mw.stock_remove_duplicates_checkbox)
        self.mw.stock_options_widget.setLayout(options_layout)
        self.mw.stock_options_widget.setVisible(False)

        layout.addWidget(self.mw.stock_options_widget)

        group_box.setLayout(layout)
        return group_box

    def on_orders_mode_changed(self, checked):
        """Handle mode change between Single and Folder for Orders."""
        is_folder_mode = self.mw.orders_folder_radio.isChecked()

        # Update button text
        if is_folder_mode:
            self.mw.load_orders_btn.setText("Select Orders Folder...")
        else:
            self.mw.load_orders_btn.setText("Load Orders File (.csv)")

        # Show/hide folder-specific widgets
        self.mw.orders_file_list_widget.setVisible(is_folder_mode)
        self.mw.orders_file_count_label.setVisible(is_folder_mode)
        self.mw.orders_options_widget.setVisible(is_folder_mode)

        # Clear selection when switching modes
        self.mw.orders_file_path = None
        self.mw.orders_file_path_label.setText("Orders file not selected")
        self.mw.orders_file_status_label.setText("")
        self.mw.orders_file_list_widget.clear()

    def on_stock_mode_changed(self, checked):
        """Handle mode change between Single and Folder for Stock."""
        is_folder_mode = self.mw.stock_folder_radio.isChecked()

        # Update button text
        if is_folder_mode:
            self.mw.load_stock_btn.setText("Select Stock Folder...")
        else:
            self.mw.load_stock_btn.setText("Load Stock File (.csv)")

        # Show/hide folder-specific widgets
        self.mw.stock_file_list_widget.setVisible(is_folder_mode)
        self.mw.stock_file_count_label.setVisible(is_folder_mode)
        self.mw.stock_options_widget.setVisible(is_folder_mode)

        # Clear selection when switching modes
        self.mw.stock_file_path = None
        self.mw.stock_file_path_label.setText("Stock file not selected")
        self.mw.stock_file_status_label.setText("")
        self.mw.stock_file_list_widget.clear()

    def _create_reports_group(self):
        """Creates the 'Reports' QGroupBox."""
        group = QGroupBox("Reports")
        layout = QVBoxLayout()
        group.setLayout(layout)

        self.mw.generate_reports_button = QPushButton("Generate Reports")
        self.mw.generate_reports_button.setToolTip(
            "Generate packing lists and stock exports based on pre-defined filters."
        )
        self.mw.generate_reports_button.setEnabled(False)

        layout.addWidget(self.mw.generate_reports_button)

        # Add "Open Session Folder" button
        self.mw.open_session_folder_button = QPushButton("Open Session Folder")
        self.mw.open_session_folder_button.setEnabled(False)
        self.mw.open_session_folder_button.setToolTip(
            "Open the current session folder in file explorer"
        )
        self.mw.open_session_folder_button.clicked.connect(self._open_session_folder)
        layout.addWidget(self.mw.open_session_folder_button)

        layout.addStretch()
        return group

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

    def _create_main_actions_group(self):
        """Create Actions section with logical button grouping."""
        group = QGroupBox("Actions")
        main_layout = QVBoxLayout(group)

        # === Row 1: Primary Actions ===
        primary_layout = QHBoxLayout()

        # Run Analysis - largest button
        self.mw.run_analysis_button = QPushButton("▶ Run Analysis")
        self.mw.run_analysis_button.setMinimumHeight(70)
        self.mw.run_analysis_button.setMinimumWidth(180)
        self.mw.run_analysis_button.setEnabled(False)
        self.mw.run_analysis_button.setToolTip("Start the fulfillment analysis")
        self.mw.run_analysis_button.setStyleSheet(f"""
            QPushButton {{
                {font_css('label')}
            }}
        """)
        primary_layout.addWidget(self.mw.run_analysis_button, 2)

        # Add Product to Order
        self.mw.add_product_button = QPushButton("Add Product to Order")
        self.mw.add_product_button.setMinimumHeight(70)
        self.mw.add_product_button.setEnabled(False)
        self.mw.add_product_button.setToolTip(
            "Manually add a product to an existing order"
        )
        primary_layout.addWidget(self.mw.add_product_button, 1)

        main_layout.addLayout(primary_layout)

        # === Row 2: Analysis mode ===
        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel("Analysis mode:"))
        self.mw.analysis_mode_combo = WheelIgnoreComboBox()
        self.mw.analysis_mode_combo.addItems(
            ["Multi-item first", "FIFO (oldest first)"]
        )
        self.mw.analysis_mode_combo.setToolTip(
            "Multi-item first: maximizes complete orders fulfilled.\n"
            "FIFO: processes strictly oldest orders first, regardless of item count."
        )
        mode_layout.addWidget(self.mw.analysis_mode_combo)
        mode_layout.addStretch()
        main_layout.addLayout(mode_layout)

        # === Row 3: Settings ===
        settings_layout = QHBoxLayout()

        # Client Settings
        self.mw.settings_button = QPushButton("Settings")
        self.mw.settings_button.setToolTip("Open settings for the active client")
        self.mw.settings_button.setEnabled(False)
        settings_layout.addWidget(self.mw.settings_button)

        # (Tag Categories and Configure Columns moved to Settings window tabs)

        main_layout.addLayout(settings_layout)

        return group

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

        self.mw.generate_reports_button.setEnabled(not is_busy and is_data_loaded)

        # Enable "Add Product" button after analysis
        if hasattr(self.mw, "add_product_button"):
            self.mw.add_product_button.setEnabled(not is_busy and is_data_loaded)

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

        source_model = PandasModel(orders_df)
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

    def _create_session_management_section(self):
        """Create session management UI for Tab 1."""
        group = QGroupBox("Session Management")
        layout = QHBoxLayout(group)

        # Create new session button
        self.mw.new_session_btn = QPushButton("Create New Session")
        self.mw.new_session_btn.setToolTip(
            "Create a new analysis session for the selected client"
        )
        self.mw.new_session_btn.setEnabled(False)
        layout.addWidget(self.mw.new_session_btn)

        # Session path label
        layout.addWidget(QLabel("Current:"))
        self.mw.session_path_label = QLabel("No session")
        layout.addWidget(self.mw.session_path_label)

        layout.addStretch()

        return group

    def _create_filter_controls(self):
        """Create filter controls for Tab 2 (Analysis Results)."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(QLabel("Filter by:"))

        # Column selector
        self.mw.filter_column_selector = WheelIgnoreComboBox()
        self.mw.filter_column_selector.addItem("All Columns")
        layout.addWidget(self.mw.filter_column_selector)

        # Filter input
        self.mw.filter_input = QLineEdit()
        self.mw.filter_input.setPlaceholderText("Enter filter text...")
        self.mw.filter_input.setClearButtonEnabled(True)  # Built-in clear button!
        layout.addWidget(self.mw.filter_input, 1)

        # Case sensitive checkbox
        self.mw.case_sensitive_checkbox = QCheckBox("Case Sensitive")
        layout.addWidget(self.mw.case_sensitive_checkbox)

        # Clear button
        self.mw.clear_filter_button = QPushButton("Clear")
        layout.addWidget(self.mw.clear_filter_button)

        # Separator
        layout.addWidget(QLabel(" | "))

        # Tag filter
        layout.addWidget(QLabel("Tag:"))
        self.mw.tag_filter_combo = WheelIgnoreComboBox()
        self.mw.tag_filter_combo.addItem("All Tags", None)
        layout.addWidget(self.mw.tag_filter_combo)

        return widget

    def _create_results_actions(self):
        """Create action buttons for Tab 2 (Analysis Results)."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # Undo button (left side)
        self.mw.undo_button = QPushButton("Undo")
        self.mw.undo_button.setToolTip("Undo last operation (Ctrl+Z)")
        self.mw.undo_button.setEnabled(False)  # Enabled by undo_manager
        self.mw.undo_button.clicked.connect(self.mw.undo_last_operation)
        layout.addWidget(self.mw.undo_button)

        # Add separator
        layout.addSpacing(20)

        # Add Product button (Tab 2 version - keep reference for signal connection)
        self.mw.add_product_button_tab2 = QPushButton("Add Product to Order")
        self.mw.add_product_button_tab2.setEnabled(False)
        self.mw.add_product_button_tab2.setToolTip(
            "Manually add a product to an existing order"
        )
        # Connect to same handler as Tab 1 button
        self.mw.add_product_button_tab2.clicked.connect(
            lambda: self.mw.actions_handler.show_add_product_dialog()
            if hasattr(self.mw, "actions_handler")
            else None
        )
        layout.addWidget(self.mw.add_product_button_tab2)

        # Generate Reports button (Tab 2 version)
        self.mw.generate_reports_button_tab2 = QPushButton("Generate Reports")
        self.mw.generate_reports_button_tab2.setEnabled(False)
        self.mw.generate_reports_button_tab2.setToolTip(
            "Generate packing lists and stock exports based on pre-defined filters"
        )
        self.mw.generate_reports_button_tab2.clicked.connect(
            lambda: self.mw.actions_handler.open_generate_reports_dialog()
            if hasattr(self.mw, "actions_handler")
            else None
        )
        layout.addWidget(self.mw.generate_reports_button_tab2)

        # Settings button (Tab 2 version)
        self.mw.settings_button_tab2 = QPushButton("Settings")
        self.mw.settings_button_tab2.setEnabled(False)
        self.mw.settings_button_tab2.setToolTip(
            "Open settings for the active client"
        )
        self.mw.settings_button_tab2.clicked.connect(
            lambda: self.mw.actions_handler.open_settings_window()
            if hasattr(self.mw, "actions_handler")
            else None
        )
        layout.addWidget(self.mw.settings_button_tab2)

        # Configure Columns button (Tab 2 version)
        self.mw.configure_columns_button_tab2 = QPushButton("Configure Columns")
        self.mw.configure_columns_button_tab2.setEnabled(False)
        self.mw.configure_columns_button_tab2.setToolTip(
            "Customize table column visibility and order"
        )
        self.mw.configure_columns_button_tab2.clicked.connect(
            lambda: self.mw.open_column_config_dialog()
            if hasattr(self.mw, "open_column_config_dialog")
            else None
        )
        layout.addWidget(self.mw.configure_columns_button_tab2)

        # Add separator
        layout.addSpacing(20)

        # Theme toggle button
        theme_manager = get_theme_manager()
        self.mw.theme_toggle_btn = QPushButton()
        self._update_theme_button_text()  # Set initial text based on current theme
        self.mw.theme_toggle_btn.setToolTip("Toggle between light and dark theme")
        self.mw.theme_toggle_btn.clicked.connect(self._on_theme_toggle_clicked)
        layout.addWidget(self.mw.theme_toggle_btn)

        # Connect to theme_changed signal to update button text
        theme_manager.theme_changed.connect(self._update_theme_button_text)

        layout.addStretch()

        return widget

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
        self.mw.tableView.setAlternatingRowColors(True)
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
        if df is None or df.empty:
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
        """Update the hidden columns indicator in the summary bar."""
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
        self.mw.sku_table.setAlternatingRowColors(True)
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
        self.mw.activity_log_table.setAlternatingRowColors(True)

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

    def _update_theme_button_text(self):
        """Update theme toggle button text based on current theme."""
        theme_manager = get_theme_manager()
        if theme_manager.is_dark_theme():
            # Currently dark, button shows "switch to light"
            self.mw.theme_toggle_btn.setText("☀️ Light Mode")
        else:
            # Currently light, button shows "switch to dark"
            self.mw.theme_toggle_btn.setText("🌙 Dark Mode")

    def _on_theme_toggle_clicked(self):
        """Handle theme toggle button click."""
        theme_manager = get_theme_manager()
        theme_manager.toggle_theme()
