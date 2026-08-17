import json
import logging
from typing import ClassVar

import pandas as pd
from PySide6.QtCore import QSettings, Qt, QThreadPool
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
)

from gui.components.form_section import FormSection
from gui.settings.base import SettingsPage
from gui.settings.general import GeneralPage
from gui.settings.mappings import OrdersMappingPage, StockMappingPage
from gui.settings.reports import ReportsPage
from gui.settings.rules import RulesPage
from gui.settings.sets import SetsPage
from gui.settings.weight import WeightPage
from gui.theme_manager import apply_font, set_button_role
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

    # Grouped left-nav replacing the old 10-tab horizontal QTabWidget strip.
    # Group/order chosen to mirror VS Code's own Settings UI grouping.
    SETTINGS_NAV_GROUPS: ClassVar[list[tuple[str, list[str]]]] = [
        ("Data", ["General", "Orders Mapping", "Stock Mapping", "Column Config"]),
        ("Fulfillment Logic", ["Rules", "Sets", "Weight"]),
        ("Output", ["Packing Lists", "Stock Exports", "SKU Labels"]),
        ("Organization", ["Tag Categories"]),
    ]

    # Stored by *name*, not row index: the nav groups have gained entries
    # twice already and an index would silently point at a different page.
    NAV_SETTINGS_KEY = "settings_hub/last_page"

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
        self._settings_nav.setObjectName("settingsNav")
        self._settings_nav.setFixedWidth(170)
        self._settings_nav.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        content_layout.addWidget(self._settings_nav)

        self.tab_widget = QStackedWidget()
        content_layout.addWidget(self.tab_widget, 1)

        self._page_index_by_name = {}
        self._pages: list[SettingsPage] = []

        # Create all tabs (unchanged call order/method names)
        self._add_page(GeneralPage(self.config_data.get("settings", {})), "General")
        self._add_page(
            RulesPage(
                self.config_data.get("rules", []),
                self.analysis_df,
                tag_categories=self.config_data.get("tag_categories", {}),
            ),
            "Rules",
        )
        self._add_page(
            ReportsPage(
                self.config_data.get("packing_list_configs", []),
                self.config_data.get("stock_export_configs", []),
                self.analysis_df,
            ),
            "Reports",
        )
        self._add_page(
            OrdersMappingPage(
                self.config_data.get("column_mappings", {}),
                self.config_data.get("courier_mappings", {}),
            ),
            "Orders Mapping",
        )
        self._add_page(
            StockMappingPage(self.config_data.get("column_mappings", {})),
            "Stock Mapping",
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
        self._add_page(
            _TagCategoriesPage(self.config_data.get("tag_categories", {"version": 2, "categories": {}})),
            "Tag Categories",
        )
        self._add_page(_ColumnConfigPage(self.parent()), "Column Config")

        self._build_settings_nav()

        button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.save_button = button_box.button(QDialogButtonBox.Save)
        set_button_role(self.save_button, "primary")
        set_button_role(button_box.button(QDialogButtonBox.Cancel), "secondary")
        button_box.accepted.connect(self.save_settings)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)

        _screen = parent.screen() if parent else QApplication.primaryScreen()
        _geo = _screen.availableGeometry()
        self.resize(min(1250, _geo.width() - 40), min(820, _geo.height() - 100))

    def _add_page(self, page: SettingsPage, name: str) -> None:
        """Register a settings page under `name`. Tracked in _pages so
        save_settings validates and collects from it.

        Replaces the old `self.tab_widget.addTab(page, name)` calls — the
        10-tab horizontal strip is replaced by a grouped left-nav
        (_build_settings_nav) that looks up pages by this same name.
        """
        self._pages.append(page)
        self.tab_widget.addWidget(page)
        self._page_index_by_name[name] = self.tab_widget.count() - 1

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
        self._restore_nav_selection()

    def _first_selectable_row(self) -> int:
        for row in range(self._settings_nav.count()):
            if self._settings_nav.item(row).flags() & Qt.ItemFlag.ItemIsSelectable:
                return row
        return -1

    def _restore_nav_selection(self) -> None:
        """Select the last-viewed page, or the first entry if it is gone."""
        wanted = QSettings("ShopifyFulfillmentTool", "FulfillmentApp").value(
            self.NAV_SETTINGS_KEY
        )
        for row in range(self._settings_nav.count()):
            item = self._settings_nav.item(row)
            if item.text() == wanted and item.flags() & Qt.ItemFlag.ItemIsSelectable:
                self._settings_nav.setCurrentRow(row)
                return
        row = self._first_selectable_row()
        if row >= 0:
            self._settings_nav.setCurrentRow(row)

    def _on_settings_nav_changed(self, current, _previous):
        if current is None:
            return
        index = current.data(Qt.ItemDataRole.UserRole)
        if index is not None:
            self.tab_widget.setCurrentIndex(index)
            QSettings("ShopifyFulfillmentTool", "FulfillmentApp").setValue(
                self.NAV_SETTINGS_KEY, current.text()
            )

    def reject(self):
        if self._is_saving:
            return
        super().reject()

    def save_settings(self):
        """Saves all settings from the UI back into the config dictionary."""
        try:
            for page in self._pages:
                ok, errors = page.validate()
                if not ok:
                    QMessageBox.warning(self, "Invalid Settings", "\n".join(errors))
                    return

            for page in self._pages:
                for key, value in page.collect().items():
                    self.config_data[key] = value

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


class _TagCategoriesPage(SettingsPage):
    """Adapter: TagCategoriesPanel already has the right shape under
    different method names, and is used standalone elsewhere -- so wrap it
    rather than rename its public API."""

    def __init__(self, tag_categories: dict, parent=None):
        super().__init__(parent)
        from gui.tag_categories_dialog import TagCategoriesPanel

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(0)
        self.panel = TagCategoriesPanel(tag_categories, parent=self)
        layout.addWidget(self.panel)

        # TagCategoriesPanel is also used standalone (its own dialog, outside
        # the Hub) -- mark roles on this wrapped instance only, not in
        # tag_categories_dialog.py itself, so the standalone dialog keeps its
        # current appearance. findChildren rather than a list of attribute
        # names: a rename over there would otherwise raise AttributeError in
        # here, and a new button would fail the role guard in the wrong file.
        for button in self.panel.findChildren(QPushButton):
            set_button_role(button, "secondary")

    def collect(self) -> dict:
        return {"tag_categories": self.panel.get_categories()}

    def validate(self) -> tuple[bool, list[str]]:
        ok, errors = self.panel.validate_categories()
        if ok:
            return True, []
        return False, ["Tag Categories validation errors:", *[f"- {e}" for e in errors]]


class _ColumnConfigPage(SettingsPage):
    """Adapter: ColumnConfigPanel self-saves through table_config_manager
    and contributes nothing to save_settings()'s collect loop."""

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        if main_window is None or not hasattr(main_window, "table_config_manager"):
            layout.addWidget(QLabel("Column configuration is not available in this context."))
            return

        from gui.column_config_dialog import ColumnConfigPanel

        layout.setContentsMargins(10, 10, 10, 10)
        layout.addWidget(FormSection(
            "Column Configuration",
            "Configure which columns are visible in the analysis table, "
            "their order, and saved views.",
        ))

        self.panel = ColumnConfigPanel(
            main_window.table_config_manager, main_window=main_window, parent=self
        )
        layout.addWidget(self.panel)
