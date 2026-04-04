import logging
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout, QPushButton, QLabel,
    QTabWidget, QGroupBox, QTableView, QPlainTextEdit, QTableWidget, QTableWidgetItem,
    QLineEdit, QComboBox, QCheckBox, QRadioButton, QListWidget, QListWidgetItem,
    QFrame, QStyle, QScrollArea, QSplitter, QHeaderView
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from .pandas_model import PandasModel
from .wheel_ignore_combobox import WheelIgnoreComboBox
from .tag_management_panel import TagManagementPanel
from .bulk_operations_toolbar import BulkOperationsToolbar
from .selection_helper import SelectionHelper
from .theme_manager import get_theme_manager


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

        # Create sidebar
        from gui.client_sidebar import ClientSidebar
        self.mw.client_sidebar = ClientSidebar(
            profile_manager=self.mw.profile_manager,
            groups_manager=self.mw.groups_manager,
            parent=self.mw
        )
        main_horizontal.addWidget(self.mw.client_sidebar)

        # Create right side container (header + tabs)
        right_side = QWidget()
        right_layout = QVBoxLayout(right_side)
        right_layout.setSpacing(5)
        right_layout.setContentsMargins(5, 5, 5, 5)

        # Step 1: Create global header (always visible)
        header_widget = self._create_global_header()
        right_layout.addWidget(header_widget)

        # Step 2: Create main tab widget with 5 tabs
        self._create_tabs()
        right_layout.addWidget(self.mw.main_tabs, 1)  # Stretch factor: 1

        # Add right side to horizontal layout
        main_horizontal.addWidget(right_side, 1)  # Stretch tabs

        # Setup status bar
        self.mw.statusBar().showMessage("Ready")

        self.log.info("UI widgets created successfully with tab-based structure and sidebar.")

    def _create_tabs(self):
        """Create main tab widget with 5 tabs."""
        self.mw.main_tabs = QTabWidget()
        self.mw.main_tabs.setDocumentMode(True)  # Cleaner look
        self.mw.main_tabs.setTabPosition(QTabWidget.North)
        self.mw.main_tabs.setMovable(False)  # Prevent accidental reorder

        # Create the 5 main tabs
        tab1 = self._create_tab1_session_setup()
        tab2 = self._create_tab2_analysis_results()
        tab3 = self._create_tab3_session_browser()
        tab4 = self._create_tab4_information()
        tab5 = self._create_tab5_tools()

        # Add tabs with icons (using QStyle built-in icons)
        file_icon = self.mw.style().standardIcon(QStyle.SP_FileIcon)
        table_icon = self.mw.style().standardIcon(QStyle.SP_FileDialogDetailedView)
        folder_icon = self.mw.style().standardIcon(QStyle.SP_DirIcon)
        info_icon = self.mw.style().standardIcon(QStyle.SP_MessageBoxInformation)
        tools_icon = self.mw.style().standardIcon(QStyle.SP_FileDialogContentsView)

        self.mw.main_tabs.addTab(tab1, file_icon, "Session Setup")
        self.mw.main_tabs.addTab(tab2, table_icon, "Analysis Results")
        self.mw.main_tabs.addTab(tab3, folder_icon, "Session Browser")
        self.mw.information_tab = tab4
        self.mw.main_tabs.addTab(tab4, info_icon, "Information")
        self.mw.main_tabs.addTab(tab5, tools_icon, "Tools")

        # Add keyboard shortcuts for tab switching
        self._setup_tab_shortcuts()

    def _create_global_header(self):
        """Create global header with sidebar toggle, current client, and session info.

        Always visible above tabs.
        """
        header = QWidget()
        header.setMaximumHeight(80)
        layout = QVBoxLayout(header)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        # Row 1: Sidebar toggle + current client label
        toggle_row = QHBoxLayout()

        self.mw.sidebar_toggle_btn = QPushButton("☰")
        self.mw.sidebar_toggle_btn.setMaximumWidth(40)
        self.mw.sidebar_toggle_btn.setToolTip("Toggle client sidebar")
        self.mw.sidebar_toggle_btn.clicked.connect(
            lambda: self.mw.client_sidebar.toggle_expanded()
        )
        toggle_row.addWidget(self.mw.sidebar_toggle_btn)

        self.mw.current_client_label = QLabel("No client selected")
        self.mw.current_client_label.setStyleSheet("font-weight: bold; font-size: 11pt;")
        toggle_row.addWidget(self.mw.current_client_label)

        toggle_row.addStretch()

        layout.addLayout(toggle_row)

        # Row 2: Session info
        session_row = QHBoxLayout()

        folder_icon = self.mw.style().standardIcon(QStyle.SP_DirIcon)
        session_icon_label = QLabel()
        session_icon_label.setPixmap(folder_icon.pixmap(16, 16))
        session_row.addWidget(session_icon_label)

        session_row.addWidget(QLabel("Session:"))

        self.mw.session_info_label = QLabel("No session")
        self.mw.session_info_label.setStyleSheet("font-weight: bold;")
        session_row.addWidget(self.mw.session_info_label)

        session_row.addStretch()

        layout.addLayout(session_row)

        # Separator line
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line)

        return header

    def _setup_tab_shortcuts(self):
        """Setup keyboard shortcuts for tab switching."""
        # Tab switching shortcuts
        QShortcut(QKeySequence("Ctrl+1"), self.mw,
                  lambda: self.mw.main_tabs.setCurrentIndex(0))
        QShortcut(QKeySequence("Ctrl+2"), self.mw,
                  lambda: self.mw.main_tabs.setCurrentIndex(1))
        QShortcut(QKeySequence("Ctrl+3"), self.mw,
                  lambda: self.mw.main_tabs.setCurrentIndex(2))
        QShortcut(QKeySequence("Ctrl+4"), self.mw,
                  lambda: self.mw.main_tabs.setCurrentIndex(3))
        QShortcut(QKeySequence("Ctrl+5"), self.mw,
                  lambda: self.mw.main_tabs.setCurrentIndex(4))

        # Set tooltips on tabs
        self.mw.main_tabs.setTabToolTip(0, "Session setup and file loading (Ctrl+1)")
        self.mw.main_tabs.setTabToolTip(1, "View and edit analysis results (Ctrl+2)")
        self.mw.main_tabs.setTabToolTip(2, "Browse past sessions (Ctrl+3)")
        self.mw.main_tabs.setTabToolTip(3, "Statistics and logs (Ctrl+4)")
        self.mw.main_tabs.setTabToolTip(4, "PDF processing and utilities (Ctrl+5)")

    def _create_tab1_session_setup(self):
        """Create Tab 1: Session Setup with split layout.

        Contains:
        - Left panel (60%): Session management, File loading, Actions, Reports
        - Right panel (40%): Session Browser for quick session switching
        """
        tab = QWidget()
        main_layout = QHBoxLayout(tab)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Create horizontal splitter
        splitter = QSplitter(Qt.Horizontal)

        # Left panel (60%) - Session Setup content
        left_panel = self._create_session_setup_panel()
        splitter.addWidget(left_panel)

        # Right panel (40%) - Session Browser
        right_panel = self._create_session_browser_panel()
        splitter.addWidget(right_panel)

        # Set initial sizes (60:40 proportion)
        splitter.setSizes([600, 400])
        splitter.setStretchFactor(0, 6)
        splitter.setStretchFactor(1, 4)

        main_layout.addWidget(splitter)
        return tab

    def _create_session_setup_panel(self):
        """Create left panel with Session Setup content."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        # Existing sections (no changes to logic)
        layout.addWidget(self._create_session_management_section())
        layout.addWidget(self._create_files_group())
        layout.addWidget(self._create_main_actions_group())
        layout.addWidget(self._create_reports_group())
        layout.addStretch()

        return panel

    def _create_session_browser_panel(self):
        """Create right panel with Session Browser."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setSpacing(5)
        layout.setContentsMargins(10, 10, 10, 10)

        # Title
        title = QLabel("Session Browser")
        title.setStyleSheet("font-size: 11pt; font-weight: bold;")
        layout.addWidget(title)

        # Integrate existing SessionBrowserWidget
        from gui.session_browser_widget import SessionBrowserWidget
        self.mw.session_browser_widget = SessionBrowserWidget(
            self.mw.session_manager,
            parent=panel
        )

        # Connect signal to main window's method
        self.mw.session_browser_widget.session_selected.connect(
            self.mw.on_session_selected
        )

        layout.addWidget(self.mw.session_browser_widget, 1)

        return panel

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

        # Section 3: Results table (MAIN content)
        table_widget = self._create_results_table()
        layout.addWidget(table_widget, 1)  # Stretch factor: 1

        # Section 4: Summary bar
        summary_widget = self._create_summary_bar()
        layout.addWidget(summary_widget)

        return tab

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
        self.mw.session_browser = SessionBrowserWidget(
            self.mw.session_manager,
            self.mw
        )

        layout.addWidget(self.mw.session_browser, 1)  # Full stretch

        self.mw.session_browser_tab = tab
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
        self.mw.client_selector = ClientSelectorWidget(
            self.mw.profile_manager,
            self.mw
        )
        layout.addWidget(self.mw.client_selector)
        layout.addStretch()

        return group

    def _create_session_management_group(self):
        """Creates the 'Session Management' QGroupBox."""
        from gui.session_browser_widget import SessionBrowserWidget

        group = QGroupBox("Session Management")
        layout = QVBoxLayout()
        group.setLayout(layout)

        # Create new session row
        session_row = QHBoxLayout()
        self.mw.new_session_btn = QPushButton("Create New Session")
        self.mw.new_session_btn.setToolTip("Creates a new session for the current client.")
        self.mw.new_session_btn.setEnabled(False)  # Enabled when client is selected
        self.mw.session_path_label = QLabel("No client/session selected.")

        session_row.addWidget(self.mw.new_session_btn)
        session_row.addWidget(self.mw.session_path_label, 1)

        layout.addLayout(session_row)

        # Add session browser
        self.mw.session_browser = SessionBrowserWidget(
            self.mw.session_manager,
            self.mw
        )
        layout.addWidget(self.mw.session_browser)

        return group

    def _create_files_group(self):
        """Creates the 'Load Data' QGroupBox with folder support."""
        group = QGroupBox("Load Data")
        layout = QHBoxLayout()
        group.setLayout(layout)

        # Orders section
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
        self.mw.load_orders_btn.setToolTip("Select the orders_export.csv file from Shopify.")
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

    def _create_actions_layout(self):
        """Creates the QHBoxLayout containing the 'Reports' and 'Actions' groups."""
        layout = QHBoxLayout()
        layout.addWidget(self._create_reports_group(), 1)
        layout.addWidget(self._create_main_actions_group(), 3)
        return layout

    def _create_reports_group(self):
        """Creates the 'Reports' QGroupBox."""
        group = QGroupBox("Reports")
        layout = QVBoxLayout()
        group.setLayout(layout)

        self.mw.packing_list_button = QPushButton("Create Packing List")
        self.mw.packing_list_button.setToolTip("Generate packing lists based on pre-defined filters.")
        self.mw.stock_export_button = QPushButton("Create Stock Export")
        self.mw.stock_export_button.setToolTip("Generate stock export files for couriers.")
        self.mw.packing_list_button.setEnabled(False)
        self.mw.stock_export_button.setEnabled(False)

        layout.addWidget(self.mw.packing_list_button)
        layout.addWidget(self.mw.stock_export_button)

        # Add "Open Session Folder" button
        self.mw.open_session_folder_button = QPushButton("Open Session Folder")
        self.mw.open_session_folder_button.setIcon(
            self.mw.style().standardIcon(QStyle.SP_DirOpenIcon)
        )
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
        import subprocess
        import platform

        if not self.mw.session_path:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self.mw,
                "No Session",
                "No session is currently active."
            )
            return

        try:
            system = platform.system()
            if system == "Windows":
                subprocess.Popen(['explorer', self.mw.session_path])
            elif system == "Darwin":  # macOS
                subprocess.Popen(["open", self.mw.session_path])
            else:  # Linux
                subprocess.Popen(["xdg-open", self.mw.session_path])
        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(
                self.mw,
                "Error",
                f"Failed to open session folder:\n{str(e)}"
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
        self.mw.run_analysis_button.setStyleSheet("""
            QPushButton {
                font-size: 11pt;
                font-weight: bold;
            }
        """)
        primary_layout.addWidget(self.mw.run_analysis_button, 2)

        # Add Product to Order
        self.mw.add_product_button = QPushButton("+ Add Product to Order")
        self.mw.add_product_button.setMinimumHeight(70)
        self.mw.add_product_button.setEnabled(False)
        self.mw.add_product_button.setToolTip("Manually add a product to an existing order")
        primary_layout.addWidget(self.mw.add_product_button, 1)

        main_layout.addLayout(primary_layout)

        # === Row 2: Settings ===
        settings_layout = QHBoxLayout()

        # Client Settings
        self.mw.settings_button = QPushButton("Client Settings")
        self.mw.settings_button.setToolTip("Open the settings window")
        self.mw.settings_button.setEnabled(False)
        settings_layout.addWidget(self.mw.settings_button)

        # (Tag Categories and Configure Columns moved to Settings window tabs)

        main_layout.addLayout(settings_layout)

        return group

    def _create_tab_view(self):
        """Creates the main QTabWidget for displaying data and logs."""
        tab_view = QTabWidget()
        self.mw.execution_log_edit = QPlainTextEdit()
        self.mw.execution_log_edit.setReadOnly(True)
        tab_view.addTab(self.mw.execution_log_edit, "Execution Log")

        self.mw.activity_log_tab = self._create_activity_log_tab()
        tab_view.addTab(self.mw.activity_log_tab, "Activity Log")

        self.mw.data_view_tab = self._create_data_view_tab()
        tab_view.addTab(self.mw.data_view_tab, "Analysis Data")

        self.mw.stats_tab = QWidget()
        self.create_statistics_tab(self.mw.stats_tab)
        tab_view.addTab(self.mw.stats_tab, "Statistics")

        return tab_view

    def _create_activity_log_tab(self):
        """Creates the 'Activity Log' tab with its QTableWidget."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self.mw.activity_log_table = QTableWidget()
        self.mw.activity_log_table.setColumnCount(3)
        self.mw.activity_log_table.setHorizontalHeaderLabels(["Time", "Operation", "Description"])
        self.mw.activity_log_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.mw.activity_log_table)
        return tab

    def _create_data_view_tab(self):
        """Creates the 'Analysis Data' tab, including the filter controls and table view."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # --- Advanced Filter Controls ---
        filter_layout = QHBoxLayout()
        self.mw.filter_column_selector = WheelIgnoreComboBox()
        self.mw.filter_input = QLineEdit()
        self.mw.filter_input.setPlaceholderText("Enter filter text...")
        self.mw.case_sensitive_checkbox = QCheckBox("Case Sensitive")
        self.mw.clear_filter_button = QPushButton("Clear")

        filter_layout.addWidget(QLabel("Filter by:"))
        filter_layout.addWidget(self.mw.filter_column_selector)
        filter_layout.addWidget(self.mw.filter_input, 1) # Allow stretching
        filter_layout.addWidget(self.mw.case_sensitive_checkbox)
        filter_layout.addWidget(self.mw.clear_filter_button)
        layout.addLayout(filter_layout)


        # --- Table View ---
        self.mw.tableView = QTableView()
        self.mw.tableView.setSortingEnabled(True)
        self.mw.tableView.setContextMenuPolicy(Qt.CustomContextMenu)
        layout.addWidget(self.mw.tableView)
        return tab

    def create_statistics_tab(self, tab_widget):
        """Creates and lays out the UI elements for the 'Statistics' tab.

        Args:
            tab_widget (QWidget): The parent widget (the tab) to populate.
        """
        layout = QGridLayout(tab_widget)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.mw.stats_labels = {}
        stat_keys = {
            "total_orders_completed": "Total Orders Completed:",
            "total_orders_not_completed": "Total Orders Not Completed:",
            "total_items_to_write_off": "Total Items to Write Off:",
            "total_items_not_to_write_off": "Total Items Not to Write Off:",
        }
        row_counter = 0
        for key, text in stat_keys.items():
            label = QLabel(text)
            value_label = QLabel("-")
            self.mw.stats_labels[key] = value_label
            layout.addWidget(label, row_counter, 0)
            layout.addWidget(value_label, row_counter, 1)
            row_counter += 1

        courier_header = QLabel("Couriers Stats:")
        courier_header.setStyleSheet("font-weight: bold; margin-top: 15px;")
        layout.addWidget(courier_header, row_counter, 0, 1, 2)
        row_counter += 1
        self.mw.courier_stats_layout = QGridLayout()
        layout.addLayout(self.mw.courier_stats_layout, row_counter, 0, 1, 2)
        self.log.info("Statistics tab created.")

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

        self.mw.packing_list_button.setEnabled(not is_busy and is_data_loaded)
        self.mw.stock_export_button.setEnabled(not is_busy and is_data_loaded)

        # Enable "Add Product" button after analysis
        if hasattr(self.mw, 'add_product_button'):
            self.mw.add_product_button.setEnabled(not is_busy and is_data_loaded)

        # Enable "Bulk Operations" button after analysis
        if hasattr(self.mw, 'toggle_bulk_mode_btn'):
            self.mw.toggle_bulk_mode_btn.setEnabled(not is_busy and is_data_loaded)

        self.log.debug(f"UI busy state set to: {is_busy}, data_loaded: {is_data_loaded}")

    def update_results_table(self, data_df):
        """Populates the main results table with new data from a DataFrame.

        It sets up a `PandasModel` and a `QSortFilterProxyModel` to efficiently
        display and filter the potentially large dataset of analysis results.

        Args:
            data_df (pd.DataFrame): The DataFrame containing the analysis
                results to display.
        """
        self.log.info("Updating results table with new data.")
        if data_df.empty:
            self.log.warning("Received empty dataframe, clearing tables.")

        # Reset columns if this is the first data load
        if not self.mw.all_columns:
            self.mw.all_columns = data_df.columns.tolist()
            self.mw.visible_columns = self.mw.all_columns[:]

        # Use all columns from the dataframe, visibility is handled by the view
        main_df = data_df.copy()

        # Check if bulk mode is active
        bulk_mode_enabled = (hasattr(self.mw, 'toggle_bulk_mode_btn') and
                            self.mw.toggle_bulk_mode_btn.isChecked())

        # Create model with checkbox support if bulk mode is active
        source_model = PandasModel(main_df, enable_checkboxes=bulk_mode_enabled)
        self.mw.proxy_model.setSourceModel(source_model)
        self.mw.tableView.setModel(self.mw.proxy_model)

        # Set order group delegate for visual borders between orders
        from gui.order_group_delegate import OrderGroupDelegate
        if not hasattr(self.mw, 'order_group_delegate') or self.mw.order_group_delegate is None:
            self.mw.order_group_delegate = OrderGroupDelegate(self.mw)
        self.mw.tableView.setItemDelegate(self.mw.order_group_delegate)

        # Set checkbox delegate for first column if bulk mode is active
        if bulk_mode_enabled:
            from gui.checkbox_delegate import CheckboxDelegate
            checkbox_delegate = CheckboxDelegate(self.mw.selection_helper)
            self.mw.tableView.setItemDelegateForColumn(0, checkbox_delegate)
            # Set checkbox column width
            self.mw.tableView.setColumnWidth(0, 30)
        else:
            # Reset column 0 delegate to default (order group delegate) when bulk mode is off
            self.mw.tableView.setItemDelegateForColumn(0, self.mw.order_group_delegate)

        # Set tag delegate for Internal_Tags column if it exists
        # This overrides the order group delegate for this specific column
        if "Internal_Tags" in main_df.columns:
            from gui.tag_delegate import TagDelegate

            tag_categories = self.mw.active_profile_config.get("tag_categories", {})
            self.mw.tag_delegate = TagDelegate(tag_categories, self.mw)

            # Adjust column index for checkbox column if enabled
            col_index = main_df.columns.get_loc("Internal_Tags")
            if bulk_mode_enabled:
                col_index += 1  # Account for checkbox column
            self.mw.tableView.setItemDelegateForColumn(col_index, self.mw.tag_delegate)

            # Populate tag filter combo box
            self._populate_tag_filter()

        # Auto-fit columns to content only when no saved config exists.
        # resizeColumnsToContents() is O(n*m) — expensive on large DataFrames.
        # If the config manager has saved widths it will apply them right after,
        # so we skip the full scan when saved widths are available.
        has_saved_config = (
            hasattr(self.mw, 'table_config_manager')
            and self.mw.table_config_manager.has_saved_column_widths()
        )
        if not has_saved_config:
            self.mw.tableView.resizeColumnsToContents()

        # Apply table configuration (column visibility, order, widths)
        if hasattr(self.mw, 'table_config_manager'):
            self.mw.table_config_manager.apply_config_to_view(
                self.mw.tableView,
                data_df
            )

        # Update hidden columns indicator
        self.update_hidden_columns_indicator()

    def _populate_tag_filter(self):
        """Populate the tag filter combo box with tags from current DataFrame.

        Dynamic approach: Only shows tags that actually exist in the current
        analysis_results_df, grouped by category. If DataFrame is empty,
        falls back to showing placeholder message.
        """
        if not hasattr(self.mw, 'tag_filter_combo'):
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
        self.log.info(f"Tag filter populated with {len(unique_tags)} unique tags from DataFrame")

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
        from shopify_tool.tag_manager import get_tag_category, _normalize_tag_categories

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
        self.mw.new_session_btn.setIcon(
            self.mw.style().standardIcon(QStyle.SP_FileDialogNewFolder)
        )
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
        self.mw.clear_filter_button.setIcon(
            self.mw.style().standardIcon(QStyle.SP_DialogResetButton)
        )
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
        self.mw.undo_button = QPushButton("↶ Undo")
        self.mw.undo_button.setToolTip("Undo last operation (Ctrl+Z)")
        self.mw.undo_button.setEnabled(False)  # Enabled by undo_manager
        self.mw.undo_button.clicked.connect(self.mw.undo_last_operation)
        layout.addWidget(self.mw.undo_button)

        # Add separator
        layout.addSpacing(20)

        # Add Product button (Tab 2 version - keep reference for signal connection)
        self.mw.add_product_button_tab2 = QPushButton("+ Add Product to Order")
        self.mw.add_product_button_tab2.setEnabled(False)
        self.mw.add_product_button_tab2.setToolTip(
            "Manually add a product to an existing order"
        )
        # Connect to same handler as Tab 1 button
        self.mw.add_product_button_tab2.clicked.connect(
            lambda: self.mw.actions_handler.show_add_product_dialog()
            if hasattr(self.mw, 'actions_handler') else None
        )
        layout.addWidget(self.mw.add_product_button_tab2)

        # Packing List button (Tab 2 version)
        self.mw.packing_list_button_tab2 = QPushButton("Packing List")
        self.mw.packing_list_button_tab2.setEnabled(False)
        self.mw.packing_list_button_tab2.setToolTip(
            "Generate packing lists based on pre-defined filters"
        )
        self.mw.packing_list_button_tab2.clicked.connect(
            lambda: self.mw.actions_handler.open_report_selection_dialog("packing_lists")
            if hasattr(self.mw, 'actions_handler') else None
        )
        layout.addWidget(self.mw.packing_list_button_tab2)

        # Stock Export button (Tab 2 version)
        self.mw.stock_export_button_tab2 = QPushButton("Stock Export")
        self.mw.stock_export_button_tab2.setEnabled(False)
        self.mw.stock_export_button_tab2.setToolTip(
            "Generate stock export files for couriers"
        )
        self.mw.stock_export_button_tab2.clicked.connect(
            lambda: self.mw.actions_handler.open_report_selection_dialog("stock_exports")
            if hasattr(self.mw, 'actions_handler') else None
        )
        layout.addWidget(self.mw.stock_export_button_tab2)

        # Settings button (Tab 2 version)
        self.mw.settings_button_tab2 = QPushButton("Client Settings")
        self.mw.settings_button_tab2.setEnabled(False)
        self.mw.settings_button_tab2.setToolTip(
            "Open the settings window for the active client"
        )
        self.mw.settings_button_tab2.clicked.connect(
            lambda: self.mw.actions_handler.open_settings_window()
            if hasattr(self.mw, 'actions_handler') else None
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
            if hasattr(self.mw, 'open_column_config_dialog') else None
        )
        layout.addWidget(self.mw.configure_columns_button_tab2)

        # Add separator
        layout.addSpacing(20)

        # Tag Management Panel toggle button
        self.mw.toggle_tags_panel_btn = QPushButton("Tags Manager")
        self.mw.toggle_tags_panel_btn.setCheckable(True)
        self.mw.toggle_tags_panel_btn.setEnabled(False)
        self.mw.toggle_tags_panel_btn.setToolTip("Show/hide Internal Tags management panel")
        self.mw.toggle_tags_panel_btn.clicked.connect(self.mw.toggle_tag_panel)
        layout.addWidget(self.mw.toggle_tags_panel_btn)

        # Add separator
        layout.addSpacing(20)

        # Bulk Operations toggle button (NEW)
        self.mw.toggle_bulk_mode_btn = QPushButton("Bulk Operations")
        self.mw.toggle_bulk_mode_btn.setCheckable(True)
        self.mw.toggle_bulk_mode_btn.setEnabled(False)
        self.mw.toggle_bulk_mode_btn.setToolTip("Enable bulk selection and operations on multiple orders")
        self.mw.toggle_bulk_mode_btn.clicked.connect(self.mw.toggle_bulk_mode)
        layout.addWidget(self.mw.toggle_bulk_mode_btn)

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

        # Add table to layout
        layout.addWidget(self.mw.tableView, 1)  # Stretch factor: 1

        # Create tag management panel
        self.mw.tag_management_panel = TagManagementPanel(self.mw)
        self.mw.tag_management_panel.setMaximumWidth(300)
        self.mw.tag_management_panel.hide()  # Hidden by default

        # Connect tag panel signals
        self.mw.tag_management_panel.tag_added.connect(self.mw.add_internal_tag_to_order)
        self.mw.tag_management_panel.tag_removed.connect(self.mw.remove_internal_tag_from_order)

        # Add tag panel to layout
        layout.addWidget(self.mw.tag_management_panel)

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
        if hasattr(self.mw, 'table_config_manager'):
            header.sectionResized.connect(self.mw.table_config_manager.on_column_resized)
            header.sectionMoved.connect(self.mw.table_config_manager.on_column_moved)

    def _show_header_context_menu(self, position):
        """Show context menu for table header.

        Args:
            position: Position where menu was requested
        """
        from PySide6.QtWidgets import QMenu
        from PySide6.QtGui import QAction

        # Only show menu if table config manager is available
        if not hasattr(self.mw, 'table_config_manager'):
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

        # Get source model (unwrap proxy if present)
        source_model = model
        if hasattr(model, 'sourceModel') and model.sourceModel() is not None:
            source_model = model.sourceModel()

        # Adjust index if checkbox column exists
        col_index = logical_index
        if hasattr(source_model, 'enable_checkboxes') and source_model.enable_checkboxes:
            if col_index == 0:
                # Checkbox column, no menu
                return
            col_index -= 1  # Adjust for checkbox column

        # Get DataFrame columns
        df_columns = self.mw.analysis_results_df.columns.tolist()

        if col_index >= len(df_columns):
            return

        column_name = df_columns[col_index]

        # Check if column is locked
        is_locked = (hasattr(self.mw.table_config_manager, '_current_config') and
                     self.mw.table_config_manager._current_config and
                     column_name in self.mw.table_config_manager._current_config.locked_columns)

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
            action_text = f"Hide '{column_name}'" if is_visible else f"Show '{column_name}'"
            action = QAction(action_text, self.mw)
            action.triggered.connect(
                lambda: (
                    self.mw.table_config_manager.toggle_column_visibility(
                        self.mw.tableView, column_name, self.mw.analysis_results_df
                    ),
                    self.update_hidden_columns_indicator()
                )
            )
            menu.addAction(action)

        menu.addSeparator()

        # Add "Show All Columns" action
        show_all_action = QAction("Show All Columns", self.mw)
        show_all_action.triggered.connect(
            lambda: (
                self.mw.table_config_manager.show_all_columns(
                    self.mw.tableView, self.mw.analysis_results_df
                ),
                self.update_hidden_columns_indicator()
            )
        )
        menu.addAction(show_all_action)

        # Add submenu for showing hidden columns
        hidden_columns = self.mw.table_config_manager.get_hidden_columns(self.mw.analysis_results_df)
        if hidden_columns:
            show_menu = menu.addMenu("Show Column")
            for hidden_col in hidden_columns:
                col_action = QAction(hidden_col, self.mw)
                col_action.triggered.connect(
                    lambda checked=False, col=hidden_col: (
                        self.mw.table_config_manager.set_column_visibility(
                            self.mw.tableView, col, True, self.mw.analysis_results_df
                        ),
                        self.update_hidden_columns_indicator()
                    )
                )
                show_menu.addAction(col_action)

        menu.addSeparator()

        # Add "Auto-Fit Column Widths" action
        auto_fit_action = QAction("Auto-Fit Column Widths", self.mw)
        auto_fit_action.triggered.connect(
            lambda: self.mw.table_config_manager.auto_fit_column_widths(
                self.mw.tableView, self.mw.analysis_results_df
            )
        )
        menu.addAction(auto_fit_action)

        # Show menu at cursor position
        menu.exec(header.mapToGlobal(position))

    def _create_summary_bar(self):
        """Create summary bar at bottom of Tab 2."""
        widget = QWidget()
        widget.setMaximumHeight(30)
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(5, 5, 5, 5)

        self.mw.summary_label = QLabel("No analysis data")
        self.mw.summary_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.mw.summary_label)

        layout.addStretch()

        # Hidden columns indicator (clickable)
        self.mw.hidden_columns_indicator = QPushButton("")
        self.mw.hidden_columns_indicator.setFlat(True)
        self.mw.hidden_columns_indicator.setStyleSheet(
            "QPushButton { color: #4A90D9; text-decoration: underline; border: none; padding: 0 5px; }"
            "QPushButton:hover { color: #2A70B9; }"
        )
        self.mw.hidden_columns_indicator.setToolTip("Click to show/restore hidden columns")
        self.mw.hidden_columns_indicator.setVisible(False)
        self.mw.hidden_columns_indicator.clicked.connect(self._show_hidden_columns_popup)
        layout.addWidget(self.mw.hidden_columns_indicator)

        return widget

    def update_summary_bar(self):
        """Update summary bar with current analysis stats."""
        if not hasattr(self.mw, 'analysis_results_df') or self.mw.analysis_results_df is None:
            self.mw.summary_label.setText("No analysis data")
            return

        df = self.mw.analysis_results_df

        # Get unique order counts
        total_orders = df['Order_Number'].nunique()
        fulfillable_orders = df[df['Order_Fulfillment_Status'] == 'Fulfillable']['Order_Number'].nunique()

        # Get item quantity sums (not row counts)
        total_items = int(df['Quantity'].sum()) if 'Quantity' in df.columns else len(df)
        fulfillable_items = int(df[df['Order_Fulfillment_Status'] == 'Fulfillable']['Quantity'].sum()) if 'Quantity' in df.columns else 0

        # Display format: total (fulfillable)
        self.mw.summary_label.setText(
            f"{total_orders} orders ({fulfillable_orders} fulfillable) | "
            f"{total_items} items ({fulfillable_items} fulfillable)"
        )

    def update_hidden_columns_indicator(self):
        """Update the hidden columns indicator in the summary bar."""
        if not hasattr(self.mw, 'hidden_columns_indicator'):
            return

        if not hasattr(self.mw, 'table_config_manager') or \
           not hasattr(self.mw, 'analysis_results_df') or \
           self.mw.analysis_results_df is None:
            self.mw.hidden_columns_indicator.setVisible(False)
            return

        hidden = self.mw.table_config_manager.get_hidden_columns(self.mw.analysis_results_df)
        if hidden:
            self.mw.hidden_columns_indicator.setText(f"{len(hidden)} columns hidden")
            self.mw.hidden_columns_indicator.setVisible(True)
        else:
            self.mw.hidden_columns_indicator.setVisible(False)

    def _show_hidden_columns_popup(self):
        """Show popup menu listing hidden columns with quick-toggle options."""
        from PySide6.QtWidgets import QMenu
        from PySide6.QtGui import QAction

        if not hasattr(self.mw, 'table_config_manager') or \
           self.mw.analysis_results_df is None:
            return

        hidden = self.mw.table_config_manager.get_hidden_columns(self.mw.analysis_results_df)
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
        if hasattr(self.mw, 'table_config_manager') and \
           hasattr(self.mw, 'tableView') and \
           self.mw.analysis_results_df is not None:
            self.mw.table_config_manager.set_column_visibility(
                self.mw.tableView, column_name, True, self.mw.analysis_results_df
            )
            self.update_hidden_columns_indicator()

    def _restore_all_hidden_columns(self):
        """Restore all hidden columns via the indicator popup."""
        if hasattr(self.mw, 'table_config_manager') and \
           hasattr(self.mw, 'tableView') and \
           self.mw.analysis_results_df is not None:
            self.mw.table_config_manager.show_all_columns(
                self.mw.tableView, self.mw.analysis_results_df
            )
            self.update_hidden_columns_indicator()

    def _make_stat_card(self, value: str, label: str) -> tuple:
        """Stat card: large value on top, small label below. Returns (widget, value_label)."""
        card = QFrame()
        card.setFrameShape(QFrame.StyledPanel)
        card.setFrameShadow(QFrame.Raised)
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(2)
        card_layout.setContentsMargins(12, 8, 12, 8)

        value_lbl = QLabel(value)
        value_lbl.setAlignment(Qt.AlignCenter)
        value_lbl.setStyleSheet("font-size: 20px; font-weight: bold;")

        text_lbl = QLabel(label)
        text_lbl.setAlignment(Qt.AlignCenter)
        text_lbl.setWordWrap(True)
        text_lbl.setStyleSheet("font-size: 10px;")

        card_layout.addWidget(value_lbl)
        card_layout.addWidget(text_lbl)
        return card, value_lbl

    def _make_courier_card(self, courier_id: str, orders: str, repeated: str) -> QFrame:
        """Courier card: orders count on top, courier name in middle, repeated below."""
        card = QFrame()
        card.setFrameShape(QFrame.StyledPanel)
        card.setFrameShadow(QFrame.Raised)
        card.setMinimumWidth(100)
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(1)
        card_layout.setContentsMargins(12, 8, 12, 8)

        orders_lbl = QLabel(orders)
        orders_lbl.setAlignment(Qt.AlignCenter)
        orders_lbl.setStyleSheet("font-size: 20px; font-weight: bold;")

        name_lbl = QLabel(courier_id)
        name_lbl.setAlignment(Qt.AlignCenter)
        name_lbl.setStyleSheet("font-size: 11px;")

        repeated_lbl = QLabel(f"{repeated} repeated")
        repeated_lbl.setAlignment(Qt.AlignCenter)
        repeated_lbl.setStyleSheet("font-size: 10px;")

        card_layout.addWidget(orders_lbl)
        card_layout.addWidget(name_lbl)
        card_layout.addWidget(repeated_lbl)
        return card

    def _make_tag_card(self, tag: str, count: str, color: str = "#9E9E9E") -> QFrame:
        """Tag card: colored count badge on top, tag name below."""
        card = QFrame()
        card.setFrameShape(QFrame.StyledPanel)
        card.setFrameShadow(QFrame.Raised)
        card.setMinimumWidth(60)
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(2)
        card_layout.setContentsMargins(6, 4, 6, 4)

        count_lbl = QLabel(count)
        count_lbl.setAlignment(Qt.AlignCenter)
        count_lbl.setStyleSheet(
            f"font-size: 14px; font-weight: bold; color: white; "
            f"background-color: {color}; border-radius: 8px; padding: 2px 6px;"
        )

        tag_lbl = QLabel(tag)
        tag_lbl.setAlignment(Qt.AlignCenter)
        tag_lbl.setWordWrap(True)
        tag_lbl.setStyleSheet("font-size: 10px;")

        card_layout.addWidget(count_lbl)
        card_layout.addWidget(tag_lbl)
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

        # ── 0. Global Statistics (all-time, from global_stats.json) ────────
        global_group = QGroupBox("Global Statistics (all sessions, all clients)")
        global_row = QHBoxLayout(global_group)
        global_row.setSpacing(8)
        global_row.setContentsMargins(8, 8, 8, 8)

        self.mw.global_stat_labels = {}
        for key, label_text in [
            ("total_orders_analyzed", "Orders\nAnalyzed"),
            ("total_orders_packed",   "Orders\nPacked"),
            ("total_sessions",        "Sessions\nRun"),
        ]:
            card, val_lbl = self._make_stat_card("-", label_text)
            self.mw.global_stat_labels[key] = val_lbl
            global_row.addWidget(card)

        self.mw.global_stats_updated_lbl = QLabel("")
        theme = get_theme_manager().get_current_theme()
        self.mw.global_stats_updated_lbl.setStyleSheet(
            f"font-size: 10px; color: {theme.text_secondary};"
        )
        global_row.addStretch()
        global_row.addWidget(self.mw.global_stats_updated_lbl)
        layout.addWidget(global_group)

        # ── 1. Session Totals ───────────────────────────────────────────────
        totals_group = QGroupBox("Session Totals")
        totals_row = QHBoxLayout(totals_group)
        totals_row.setSpacing(8)
        totals_row.setContentsMargins(8, 8, 8, 8)

        self.mw.stat_card_labels = {}
        for key, label_text in [
            ("total_orders_completed",       "Orders\nCompleted"),
            ("total_orders_not_completed",   "Orders Not\nCompleted"),
            ("total_items_to_write_off",     "Items to\nWrite Off"),
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

        self.mw.sku_table = QTableWidget()
        self.mw.sku_table.setColumnCount(6)
        self.mw.sku_table.setHorizontalHeaderLabels(
            ["#", "SKU", "Product", "Total Qty", "Fulfillable", "Not Fulfillable"]
        )
        self.mw.sku_table.horizontalHeader().setStretchLastSection(False)
        self.mw.sku_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.mw.sku_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.mw.sku_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.mw.sku_table.setAlternatingRowColors(True)
        self.mw.sku_table.verticalHeader().setVisible(False)
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

    def _update_theme_button_text(self):
        """Update theme toggle button text based on current theme."""
        theme_manager = get_theme_manager()
        if theme_manager.is_dark_theme():
            # Currently dark, button shows "switch to light"
            self.mw.theme_toggle_btn.setText("Light Mode")
        else:
            # Currently light, button shows "switch to dark"
            self.mw.theme_toggle_btn.setText("Dark Mode")

    def _on_theme_toggle_clicked(self):
        """Handle theme toggle button click."""
        theme_manager = get_theme_manager()
        theme_manager.toggle_theme()
