import json
import logging
import sys
from typing import ClassVar

import pandas as pd
from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from gui.settings.base import SettingsPage
from gui.settings.fields import (
    ACTION_TYPES,
    CONDITION_FIELDS,
    CONDITION_OPERATORS,
    FILTER_OPERATORS,
    FILTERABLE_COLUMNS,
    ORDER_LEVEL_FIELDS,
)
from gui.settings.general import GeneralPage
from gui.settings.mappings import MappingsPage
from gui.settings.packing_lists import PackingListsPage
from gui.settings.rules import RulesPage
from gui.settings.sets import SetsPage
from gui.settings.stock_exports import StockExportsPage
from gui.settings.weight import WeightPage
from gui.theme_manager import apply_font, font_css
from gui.worker import Worker

logger = logging.getLogger(__name__)


class SettingsWindow(QDialog):
    """A dialog window for viewing and editing all application settings.

    This window provides a tabbed interface for modifying different sections
    of the application's configuration, including:
    - General settings and paths.
    - The rule engine's rule definitions.
    - Pre-configured packing list reports.
    - Pre-configured stock export reports.

    The UI is built dynamically based on the current configuration data that
    is passed in during initialization. It allows for adding, editing, and
    deleting rules, reports, and their constituent parts.

    Attributes:
        config_data (dict): A deep copy of the application's configuration.
        analysis_df (pd.DataFrame): The main analysis DataFrame, used to
            populate dynamic dropdowns for filter values.
    """

    # Constants for builders
    FILTERABLE_COLUMNS: ClassVar[list[str]] = FILTERABLE_COLUMNS
    FILTER_OPERATORS: ClassVar[list[str]] = FILTER_OPERATORS
    ORDER_LEVEL_FIELDS: ClassVar[list[str]] = ORDER_LEVEL_FIELDS
    CONDITION_FIELDS: ClassVar[list[str]] = CONDITION_FIELDS
    CONDITION_OPERATORS: ClassVar[list[str]] = CONDITION_OPERATORS
    ACTION_TYPES: ClassVar[list[str]] = ACTION_TYPES

    # Grouped left-nav replacing the old 10-tab horizontal QTabWidget strip.
    # Group/order chosen to mirror VS Code's own Settings UI grouping.
    SETTINGS_NAV_GROUPS: ClassVar[list[tuple[str, list[str]]]] = [
        ("Data", ["General", "Mappings", "Column Config"]),
        ("Fulfillment Logic", ["Rules", "Sets", "Weight"]),
        ("Output", ["Packing Lists", "Stock Exports", "SKU Labels"]),
        ("Organization", ["Tag Categories"]),
    ]

    def __init__(self, client_id, client_config, profile_manager, analysis_df=None, parent=None):
        """Initializes the SettingsWindow.

        Args:
            client_id (str): The client ID for which settings are being edited.
            client_config (dict): The client's configuration dictionary. A deep
                copy is made to avoid modifying the original until saved.
            profile_manager: The ProfileManager instance for saving settings.
            analysis_df (pd.DataFrame, optional): The current analysis
                DataFrame, used for populating filter value dropdowns.
                Defaults to None.
            parent (QWidget, optional): The parent widget. Defaults to None.
        """
        super().__init__(parent)
        self.client_id = client_id
        self.config_data = json.loads(json.dumps(client_config))
        self.profile_manager = profile_manager
        self.analysis_df = analysis_df if analysis_df is not None else pd.DataFrame()
        self._save_worker = None  # keeps the in-flight save Worker alive
        self._is_saving = False

        # Ensure config structure exists
        if not isinstance(self.config_data.get("column_mappings"), dict):
            self.config_data["column_mappings"] = {
                "orders_required": [],
                "stock_required": []
            }

        if "courier_mappings" not in self.config_data:
            self.config_data["courier_mappings"] = {}

        if "settings" not in self.config_data:
            self.config_data["settings"] = {
                "low_stock_threshold": 5,
                "stock_csv_delimiter": ";"
            }

        if "rules" not in self.config_data:
            self.config_data["rules"] = []

        if "packing_list_configs" not in self.config_data:
            self.config_data["packing_list_configs"] = []

        if "stock_export_configs" not in self.config_data:
            self.config_data["stock_export_configs"] = []

        if "set_decoders" not in self.config_data:
            self.config_data["set_decoders"] = {}

        self.setWindowTitle(f"Settings - CLIENT_{self.client_id}")
        self.setMinimumSize(1100, 600)
        self.setModal(True)
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint)

        main_layout = QVBoxLayout(self)
        content_layout = QHBoxLayout()
        main_layout.addLayout(content_layout)

        self._settings_nav = QListWidget()
        self._settings_nav.setFixedWidth(170)
        self._settings_nav.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        content_layout.addWidget(self._settings_nav)

        self.tab_widget = QStackedWidget()
        content_layout.addWidget(self.tab_widget, 1)

        self._page_index_by_name = {}
        self._pages: list[SettingsPage] = []

        # Create all tabs (unchanged call order/method names)
        self._add_page(GeneralPage(self.config_data.get("settings", {})), "General")
        self._add_page(RulesPage(self.config_data.get("rules", []), self.analysis_df), "Rules")
        self._add_page(
            PackingListsPage(self.config_data.get("packing_list_configs", []), self.analysis_df),
            "Packing Lists",
        )
        self._add_page(
            StockExportsPage(self.config_data.get("stock_export_configs", []), self.analysis_df),
            "Stock Exports",
        )
        self._add_page(
            MappingsPage(
                self.config_data.get("column_mappings", {}),
                self.config_data.get("courier_mappings", {}),
            ),
            "Mappings",
        )
        self._add_page(SetsPage(self.config_data.get("set_decoders", {})), "Sets")
        self._add_page(
            WeightPage(
                self.config_data.get("weight_config", {}),
                self.config_data.get("column_mappings", {}),
                self.config_data.get("settings", {}).get("stock_csv_delimiter", ";"),
            ),
            "Weight",
        )
        self.create_tag_categories_tab()  # Tag Categories tab
        self.create_column_config_tab()  # Column Configuration tab

        self._build_settings_nav()

        button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.save_button = button_box.button(QDialogButtonBox.Save)
        button_box.accepted.connect(self.save_settings)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)

        _screen = parent.screen() if parent else QApplication.primaryScreen()
        _geo = _screen.availableGeometry()
        self.resize(min(1250, _geo.width() - 40), min(820, _geo.height() - 100))

    def _add_settings_page(self, page: QWidget, name: str) -> None:
        """Register a settings page under `name`.

        Replaces the old `self.tab_widget.addTab(page, name)` calls — the
        10-tab horizontal strip is replaced by a grouped left-nav
        (_build_settings_nav) that looks up pages by this same name.
        """
        self.tab_widget.addWidget(page)
        self._page_index_by_name[name] = self.tab_widget.count() - 1

    def _add_page(self, page: SettingsPage, name: str) -> None:
        """Register an extracted SettingsPage. Tracked in _pages so save_settings
        validates and collects from it; _add_settings_page still handles the
        not-yet-extracted create_*_tab pages."""
        self._pages.append(page)
        self._add_settings_page(page, name)

    def _build_settings_nav(self) -> None:
        """Populate the left-nav list from SETTINGS_NAV_GROUPS with
        non-selectable section headers, and wire selection to the stack."""
        for group_name, page_names in self.SETTINGS_NAV_GROUPS:
            header = QListWidgetItem(group_name.upper())
            header.setFlags(Qt.ItemFlag.NoItemFlags)
            apply_font(header, "caption", bold=True)
            self._settings_nav.addItem(header)
            for page_name in page_names:
                if page_name not in self._page_index_by_name:
                    continue
                item = QListWidgetItem(page_name)
                item.setData(Qt.ItemDataRole.UserRole, self._page_index_by_name[page_name])
                self._settings_nav.addItem(item)
        self._settings_nav.currentItemChanged.connect(self._on_settings_nav_changed)
        # Select the first real (non-header) entry
        for row in range(self._settings_nav.count()):
            if self._settings_nav.item(row).flags() & Qt.ItemFlag.ItemIsSelectable:
                self._settings_nav.setCurrentRow(row)
                break

    def _on_settings_nav_changed(self, current, _previous):
        if current is None:
            return
        index = current.data(Qt.ItemDataRole.UserRole)
        if index is not None:
            self.tab_widget.setCurrentIndex(index)

    def reject(self):
        if self._is_saving:
            return
        super().reject()

    def save_settings(self):
        """Saves all settings from the UI back into the config dictionary."""
        try:
            # Extracted pages: validate first, then collect. Pages still
            # living in create_*_tab methods are handled by the inline
            # blocks below until they are moved out.
            for page in self._pages:
                ok, errors = page.validate()
                if not ok:
                    QMessageBox.warning(self, "Invalid Settings", "\n".join(errors))
                    return

            for page in self._pages:
                for key, value in page.collect().items():
                    if isinstance(value, dict) and isinstance(self.config_data.get(key), dict):
                        self.config_data[key].update(value)
                    else:
                        self.config_data[key] = value

            # ========================================
            # Tag Categories Tab
            # ========================================
            if hasattr(self, 'tag_categories_panel'):
                is_valid, errors = self.tag_categories_panel.validate_categories()
                if not is_valid:
                    error_msg = "Tag Categories validation errors:\n\n" + "\n".join(f"- {err}" for err in errors)
                    QMessageBox.warning(self, "Tag Categories Invalid", error_msg)
                    return
                self.config_data["tag_categories"] = self.tag_categories_panel.get_categories()

            # ========================================
            # Save to server via ProfileManager (background -- avoids blocking
            # the GUI thread on the lock-contention retry sleep)
            # ========================================
            self.save_button.setEnabled(False)
            self.save_button.setText("Saving...")
            self._is_saving = True

            worker = Worker(self.profile_manager.save_shopify_config, self.client_id, self.config_data)
            worker.signals.result.connect(self._on_save_settings_result)
            worker.signals.error.connect(self._on_save_settings_error)
            # Keep a strong reference until the worker finishes -- a bare
            # local var is garbage-collected the instant this method returns,
            # which (in this PySide6 build) destroys the QRunnable's
            # unparented signals object before its queued result reaches the
            # main thread. See MainWindow._client_load_worker for the
            # verified repro.
            self._save_worker = worker
            QThreadPool.globalInstance().start(worker)

        except ValueError as e:
            QMessageBox.critical(
                self,
                "Validation Error",
                f"Invalid value entered:\n\n{e!s}\n\nPlease check your inputs."
            )
        except Exception as e:
            import traceback
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to save settings:\n\n{e!s}\n\n{traceback.format_exc()}"
            )

    def _on_save_settings_result(self, success: bool):
        self._is_saving = False
        self.save_button.setEnabled(True)
        self.save_button.setText("Save")
        if success:
            QMessageBox.information(self, "Success", "Settings saved successfully!")
            self.accept()
        else:
            import json
            config_size = len(json.dumps(self.config_data, ensure_ascii=False).encode("utf-8"))
            num_sets = len(self.config_data.get("set_decoders", {}))
            QMessageBox.critical(
                self,
                "Save Error",
                f"Failed to save settings to server.\n\n"
                f"Configuration size: {config_size:,} bytes\n"
                f"Number of sets: {num_sets}\n\n"
                f"Possible causes:\n"
                f"• File is locked by another user\n"
                f"• Network connection issue\n"
                f"• Insufficient permissions\n\n"
                f"Please wait a few seconds and try again."
            )

    def _on_save_settings_error(self, error):
        _exctype, value, tb = error
        logger.error(f"Failed to save settings: {value}\n{tb}")
        self._is_saving = False
        self.save_button.setEnabled(True)
        self.save_button.setText("Save")
        QMessageBox.critical(self, "Error", f"Failed to save settings:\n\n{value!s}")
    # ========================================
    # TAG CATEGORIES TAB
    # ========================================
    def create_tag_categories_tab(self):
        """Create the Tag Categories management tab."""
        from gui.tag_categories_dialog import TagCategoriesPanel

        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(0)

        tag_categories = self.config_data.get("tag_categories", {"version": 2, "categories": {}})
        self.tag_categories_panel = TagCategoriesPanel(tag_categories, parent=tab)
        layout.addWidget(self.tag_categories_panel)

        self._add_settings_page(tab, "Tag Categories")

    # ========================================
    # COLUMN CONFIGURATION TAB
    # ========================================
    def create_column_config_tab(self):
        """Create the Column Configuration tab (embedded ColumnConfigPanel)."""
        from gui.column_config_dialog import ColumnConfigPanel

        main_window = self.parent()
        if main_window is None or not hasattr(main_window, 'table_config_manager'):
            tab = QWidget()
            layout = QVBoxLayout(tab)
            layout.addWidget(QLabel("Column configuration is not available in this context."))
            self._add_settings_page(tab, "Column Config")
            return

        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)

        header_label = QLabel("Column Configuration")
        header_label.setStyleSheet(font_css("heading"))
        layout.addWidget(header_label)

        from gui.theme_manager import get_theme_manager
        theme = get_theme_manager().get_current_theme()
        help_text = QLabel(
            "Configure which columns are visible in the analysis table, their order, and saved views."
        )
        help_text.setWordWrap(True)
        help_text.setStyleSheet(f"color: {theme.text_secondary}; font-style: italic; margin-bottom: 6px;")
        layout.addWidget(help_text)

        self.column_config_panel = ColumnConfigPanel(
            main_window.table_config_manager,
            main_window=main_window,
            parent=tab
        )
        layout.addWidget(self.column_config_panel)

        self._add_settings_page(tab, "Column Config")



if __name__ == "__main__":
    app = QApplication(sys.argv)
    dummy_config = {
        "settings": {"stock_csv_delimiter": ";", "low_stock_threshold": 5},
        "paths": {"templates": "/tmp/fake_templates", "output_dir_stock": "/tmp/fake_output"},
        "rules": [
            {
                "name": "Test Rule",
                "match": "ANY",
                "conditions": [{"field": "SKU", "operator": "contains", "value": "TEST"}],
                "actions": [{"type": "ADD_TAG", "value": "auto_tagged"}],
            }
        ],
        "packing_lists": [
            {
                "name": "Test PL",
                "output_filename": "test.xlsx",
                "filters": [{"field": "Order_Type", "operator": "==", "value": "Single"}],
                "exclude_skus": ["SKU1"],
            }
        ],
        "stock_exports": [
            {
                "name": "Test SE",
                "template": "template.xls",
                "filters": [{"field": "Shipping_Provider", "operator": "==", "value": "DHL"}],
            }
        ],
    }
    dialog = SettingsWindow(None, dummy_config)
    if dialog.exec():
        print("Settings saved:", json.dumps(dialog.config_data, indent=2))
    else:
        print("Cancelled.")
    sys.exit(0)
