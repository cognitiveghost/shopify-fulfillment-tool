import json
import logging
from typing import ClassVar

import pandas as pd
from PySide6.QtCore import QRectF, QSettings, QSize, Qt, QThreadPool, QTimer
from PySide6.QtGui import QColor, QIcon, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from gui.components.error_banner import show_error
from gui.components.inline_message import InlineMessage
from gui.components.toast import toast
from gui.settings.base import SettingsPage
from gui.settings.general import GeneralPage
from gui.settings.mappings import OrdersMappingPage, StockMappingPage
from gui.settings.reports import ReportsPage
from gui.settings.rules import RulesPage
from gui.settings.sets import SetsPage
from gui.settings.weight import WeightPage
from gui.theme_manager import apply_dialog_button_roles, apply_font, set_button_role
from gui.worker import Worker
from shared.theme import font_css, on_theme_changed

logger = logging.getLogger(__name__)

NAV_ICON_PX = 12
UNSAVED_DOT_PX = 8
DIRTY_POLL_MS = 400

# Page name -> words a person might search for that are not in the name.
SETTINGS_SEARCH_KEYWORDS: dict[str, list[str]] = {
    "General": ["delimiter", "csv", "low stock", "threshold", "repeat"],
    "Orders Mapping": ["columns", "csv", "headers", "courier", "carrier", "shipping"],
    "Stock Mapping": ["columns", "csv", "headers", "expiry", "batch", "lot", "fifo"],
    "Rules": ["conditions", "actions", "tags", "status", "priority", "automation"],
    "Sets": ["bundles", "kits", "components", "decoder"],
    "Weight": ["volumetric", "divisor", "dimensions", "boxes", "packaging", "kg"],
    "Reports": ["packing list", "stock export", "filters", "output", "writeoff"],
    "Tag Categories": ["tags", "labels", "colours", "colors", "writeoff", "sku"],
}


def unsaved_summary(names: list[str]) -> str:
    """Footer copy for the unsaved pages, given in nav order."""
    if not names:
        return ""
    if len(names) == 1:
        return f"Unsaved changes on {names[0]}"
    if len(names) == 2:
        return f"Unsaved changes on {names[0]} and {names[1]}"
    return f"Unsaved changes on {len(names)} pages"


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
        ("Data", ["General", "Orders Mapping", "Stock Mapping"]),
        ("Fulfillment Logic", ["Rules", "Sets", "Weight"]),
        ("Output", ["Reports"]),
        ("Organization", ["Tag Categories"]),
    ]

    # Stored by *name*, not row index: the nav groups have gained entries
    # twice already and an index would silently point at a different page.
    NAV_SETTINGS_KEY = "settings_hub/last_page"

    def __init__(
        self,
        client_id,
        client_config,
        profile_manager,
        analysis_df=None,
        parent=None,
        initial_page=None,
    ):
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
            initial_page (str, optional): Nav entry to open on, by the same
                name SETTINGS_NAV_GROUPS uses. A caller that already knows
                which page answers the user's problem says so; everyone else
                gets the last page they were on. Defaults to None.
        """
        super().__init__(parent)
        self._initial_page = initial_page
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
                "stock_required": [],
            }

        if "courier_mappings" not in self.config_data:
            self.config_data["courier_mappings"] = {}

        if "settings" not in self.config_data:
            self.config_data["settings"] = {
                "low_stock_threshold": 5,
                "stock_csv_delimiter": ";",
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
        self._settings_nav.setIconSize(QSize(NAV_ICON_PX, NAV_ICON_PX))

        nav_column = QVBoxLayout()
        self._nav_search = QLineEdit()
        self._nav_search.setPlaceholderText("Search settings")
        self._nav_search.setClearButtonEnabled(True)
        self._nav_search.setFixedWidth(170)
        self._nav_search.textChanged.connect(self.filter_nav)
        self._nav_search.returnPressed.connect(self._select_first_visible_page)
        nav_column.addWidget(self._nav_search)
        self._no_match_label = QLabel("No page matches")
        on_theme_changed(
            self._no_match_label,
            lambda tokens: self._no_match_label.setStyleSheet(
                f"{font_css('caption')} color: {tokens.text_secondary};"
            ),
        )
        self._no_match_label.hide()
        nav_column.addWidget(self._no_match_label)
        nav_column.addWidget(self._settings_nav, 1)
        content_layout.addLayout(nav_column)
        QShortcut(QKeySequence(QKeySequence.StandardKey.Find), self).activated.connect(
            self._nav_search.setFocus
        )

        page_column = QVBoxLayout()
        self._validation_message = InlineMessage()
        page_column.addWidget(self._validation_message)
        self.tab_widget = QStackedWidget()
        page_column.addWidget(self.tab_widget, 1)
        content_layout.addLayout(page_column, 1)

        self._page_index_by_name = {}
        self._pages: list[SettingsPage] = []
        self._pages_by_name: dict[str, SettingsPage] = {}
        self._unsaved: set[str] = set()

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
            _TagCategoriesPage(
                self.config_data.get("tag_categories", {"version": 2, "categories": {}})
            ),
            "Tag Categories",
        )
        self._build_settings_nav()

        button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.save_button = button_box.button(QDialogButtonBox.Save)
        apply_dialog_button_roles(button_box)
        set_button_role(button_box.button(QDialogButtonBox.Cancel), "secondary")
        button_box.accepted.connect(self.save_settings)
        button_box.rejected.connect(self.reject)

        self._unsaved_label = QLabel("")
        on_theme_changed(
            self._unsaved_label,
            lambda tokens: self._unsaved_label.setStyleSheet(
                f"{font_css('body')} color: {tokens.text_secondary};"
            ),
        )
        self._footer = QWidget()
        footer_row = QHBoxLayout(self._footer)
        footer_row.setContentsMargins(0, 0, 0, 0)
        footer_row.addWidget(self._unsaved_label, 1)
        footer_row.addWidget(button_box)
        main_layout.addWidget(self._footer)

        # The close guard replaces the footer in place: the pages it names are
        # on screen beside it, so it is not a message box.
        self._close_guard = QWidget()
        guard_row = QHBoxLayout(self._close_guard)
        guard_row.setContentsMargins(0, 0, 0, 0)
        self._close_guard_label = QLabel("")
        self._close_guard_label.setWordWrap(True)
        guard_row.addWidget(self._close_guard_label, 1)
        self.keep_editing_button = QPushButton("Keep editing")
        set_button_role(self.keep_editing_button, "ghost")
        self.keep_editing_button.clicked.connect(self._hide_close_guard)
        self.discard_button = QPushButton("Discard")
        set_button_role(self.discard_button, "danger")
        self.discard_button.clicked.connect(self._discard)
        # "&&": a single "&" is a Qt mnemonic and would underline the "c".
        self.save_and_close_button = QPushButton("Save && close")
        set_button_role(self.save_and_close_button, "primary")
        self.save_and_close_button.clicked.connect(self.save_settings)
        for button in (
            self.keep_editing_button,
            self.discard_button,
            self.save_and_close_button,
        ):
            guard_row.addWidget(button)
        self._close_guard.hide()
        main_layout.addWidget(self._close_guard)

        _screen = parent.screen() if parent else QApplication.primaryScreen()
        _geo = _screen.availableGeometry()
        self.resize(min(1250, _geo.width() - 40), min(820, _geo.height() - 100))

        for page in self._pages:
            page.mark_clean()
        on_theme_changed(self._settings_nav, self._rebuild_nav_marks)
        # ponytail: polls the visible page's snapshot (one collect() plus one
        # json.dumps) every 400ms. Ceiling: a page whose snapshot costs tens of
        # milliseconds makes the dialog stutter; upgrade to a per-page
        # `edited` signal then.
        self._dirty_poll = QTimer(self)
        self._dirty_poll.setInterval(DIRTY_POLL_MS)
        self._dirty_poll.timeout.connect(self._poll_current_page)
        self._dirty_poll.start()

    def _add_page(self, page: SettingsPage, name: str) -> None:
        """Register a settings page under `name`. Tracked in _pages so
        save_settings validates and collects from it.

        Replaces the old `self.tab_widget.addTab(page, name)` calls — the
        10-tab horizontal strip is replaced by a grouped left-nav
        (_build_settings_nav) that looks up pages by this same name.
        """
        self._pages.append(page)
        self._pages_by_name[name] = page
        self.tab_widget.addWidget(page)
        self._page_index_by_name[name] = self.tab_widget.count() - 1

    def _build_settings_nav(self) -> None:
        """Populate the left-nav list from SETTINGS_NAV_GROUPS with
        non-selectable section headers, and wire selection to the stack."""
        listed = self._nav_page_names()
        problems = []
        if any(not names for _group, names in self.SETTINGS_NAV_GROUPS):
            problems.append("a nav group has no pages")
        if sorted(listed) != sorted(self._page_index_by_name):
            problems.append(
                f"nav lists {sorted(listed)} but pages are {sorted(self._page_index_by_name)}"
            )
        if sorted(SETTINGS_SEARCH_KEYWORDS) != sorted(listed):
            problems.append(
                "SETTINGS_SEARCH_KEYWORDS does not name exactly the nav's pages"
            )
        if problems:
            # A page missing from the nav is unreachable, and nothing else says so.
            raise ValueError("; ".join(problems))

        for group_name, page_names in self.SETTINGS_NAV_GROUPS:
            header = QListWidgetItem(group_name.upper())
            header.setFlags(Qt.ItemFlag.NoItemFlags)
            apply_font(header, "caption", bold=True)
            self._settings_nav.addItem(header)
            for page_name in page_names:
                item = QListWidgetItem(page_name)
                item.setData(
                    Qt.ItemDataRole.UserRole, self._page_index_by_name[page_name]
                )
                self._settings_nav.addItem(item)
        self._settings_nav.currentItemChanged.connect(self._on_settings_nav_changed)
        self._restore_nav_selection()

    def _first_selectable_row(self) -> int:
        for row in range(self._settings_nav.count()):
            if self._settings_nav.item(row).flags() & Qt.ItemFlag.ItemIsSelectable:
                return row
        return -1

    def _restore_nav_selection(self) -> None:
        """Select the requested page, else the last-viewed one, else the first."""
        wanted = self._initial_page or QSettings(
            "ShopifyFulfillmentTool", "FulfillmentApp"
        ).value(self.NAV_SETTINGS_KEY)
        for row in range(self._settings_nav.count()):
            item = self._settings_nav.item(row)
            if item.text() == wanted and item.flags() & Qt.ItemFlag.ItemIsSelectable:
                self._settings_nav.setCurrentRow(row)
                return
        row = self._first_selectable_row()
        if row >= 0:
            self._settings_nav.setCurrentRow(row)

    def filter_nav(self, text: str) -> list[str]:
        """Show nav rows whose name or keywords contain `text`; return them."""
        query = text.strip().casefold()
        visible: list[str] = []
        header, header_has_rows = None, False
        for row in range(self._settings_nav.count()):
            item = self._settings_nav.item(row)
            if item.data(Qt.ItemDataRole.UserRole) is None:
                if header is not None:
                    header.setHidden(not header_has_rows)
                header, header_has_rows = item, False
                continue
            name = item.text()
            haystack = [name, *SETTINGS_SEARCH_KEYWORDS[name]]
            match = not query or any(query in word.casefold() for word in haystack)
            item.setHidden(not match)
            if match:
                visible.append(name)
                header_has_rows = True
        if header is not None:
            header.setHidden(not header_has_rows)
        self._no_match_label.setHidden(not query or bool(visible))
        return visible

    def _select_first_visible_page(self) -> None:
        for row in range(self._settings_nav.count()):
            item = self._settings_nav.item(row)
            if item.data(Qt.ItemDataRole.UserRole) is not None and not item.isHidden():
                self._settings_nav.setCurrentRow(row)
                return

    def _on_settings_nav_changed(self, current, _previous):
        self._validation_message.clear()
        if current is None:
            return
        index = current.data(Qt.ItemDataRole.UserRole)
        if index is not None:
            self.tab_widget.setCurrentIndex(index)
            QSettings("ShopifyFulfillmentTool", "FulfillmentApp").setValue(
                self.NAV_SETTINGS_KEY, current.text()
            )

    def _nav_page_names(self) -> list[str]:
        return [name for _group, names in self.SETTINGS_NAV_GROUPS for name in names]

    def _select_page(self, name: str) -> None:
        for row in range(self._settings_nav.count()):
            item = self._settings_nav.item(row)
            if item.text() == name and item.data(Qt.ItemDataRole.UserRole) is not None:
                self._settings_nav.setCurrentRow(row)
                return

    def refresh_dirty(self) -> list[str]:
        """Re-check every page; return the unsaved page names in nav order."""
        self._unsaved = {
            name for name, page in self._pages_by_name.items() if page.is_dirty()
        }
        self._render_unsaved()
        return [name for name in self._nav_page_names() if name in self._unsaved]

    def _poll_current_page(self) -> None:
        page = self.tab_widget.currentWidget()
        name = next((n for n, p in self._pages_by_name.items() if p is page), None)
        if name is None:
            return
        if page.is_dirty() != (name in self._unsaved):
            self._unsaved ^= {name}
            self._render_unsaved()

    def _render_unsaved(self) -> None:
        names = [name for name in self._nav_page_names() if name in self._unsaved]
        summary = unsaved_summary(names)
        self._unsaved_label.setText(summary)
        self._close_guard_label.setText(
            f"{summary}. Closing now discards them." if names else ""
        )
        self._apply_nav_marks()

    def _rebuild_nav_marks(self, tokens) -> None:
        dot = QPixmap(NAV_ICON_PX, NAV_ICON_PX)
        dot.fill(Qt.GlobalColor.transparent)
        painter = QPainter(dot)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        # accent_fill: the colour of the Save button the page is waiting for.
        painter.setBrush(QColor(tokens.accent_fill))
        inset = (NAV_ICON_PX - UNSAVED_DOT_PX) / 2
        painter.drawEllipse(QRectF(inset, inset, UNSAVED_DOT_PX, UNSAVED_DOT_PX))
        painter.end()
        blank = QPixmap(NAV_ICON_PX, NAV_ICON_PX)
        blank.fill(Qt.GlobalColor.transparent)
        self._unsaved_icon = QIcon(dot)
        self._clean_icon = QIcon(blank)
        self._apply_nav_marks()

    def _apply_nav_marks(self) -> None:
        for row in range(self._settings_nav.count()):
            item = self._settings_nav.item(row)
            if item.data(Qt.ItemDataRole.UserRole) is None:
                continue  # group header
            unsaved = item.text() in self._unsaved
            item.setIcon(self._unsaved_icon if unsaved else self._clean_icon)
            item.setToolTip("Unsaved changes" if unsaved else "")
            item.setData(
                Qt.ItemDataRole.AccessibleTextRole,
                f"{item.text()}, unsaved changes" if unsaved else item.text(),
            )

    def reject(self):
        if self._is_saving:
            return
        # isHidden, not isVisible: children of a dialog that was never shown
        # (every test) report invisible.
        if not self._close_guard.isHidden():
            self._hide_close_guard()
            return
        if self.refresh_dirty():
            self._show_close_guard()
            return
        super().reject()

    def _show_close_guard(self) -> None:
        self._footer.hide()
        self._close_guard.show()
        self.save_and_close_button.setFocus()

    def _hide_close_guard(self) -> None:
        self._close_guard.hide()
        self._footer.show()

    def _discard(self) -> None:
        self._hide_close_guard()
        super().reject()

    def done(self, result):
        self._dirty_poll.stop()
        super().done(result)

    def save_settings(self):
        """Validate every page, collect them all, and write the profile once.

        Save always writes, even when no page reads unsaved: the unsaved state
        drives warnings only, so a snapshot that misses a field costs a
        warning, never an edit.
        """
        self._hide_close_guard()
        self._validation_message.clear()
        for name in self._nav_page_names():
            ok, errors = self._pages_by_name[name].validate()
            if not ok:
                self._select_page(name)
                self._validation_message.show_message("\n".join(errors))
                return

        try:
            for page in self._pages:
                for key, value in page.collect().items():
                    self.config_data[key] = value
        except Exception:
            logger.exception("Failed to collect settings")
            show_error(
                self,
                "Settings weren't saved",
                "A value couldn't be read. Details are in Logs.",
            )
            return

        # Save to server via ProfileManager (background -- avoids blocking the
        # GUI thread on the lock-contention retry sleep)
        self.save_button.setEnabled(False)
        self.save_button.setText("Saving...")
        self._is_saving = True

        worker = Worker(
            self.profile_manager.save_shopify_config, self.client_id, self.config_data
        )
        worker.signals.result.connect(self._on_save_settings_result)
        worker.signals.error.connect(self._on_save_settings_error)
        # Keep a strong reference until the worker finishes -- a bare local var
        # is garbage-collected the instant this method returns, which (in this
        # PySide6 build) destroys the QRunnable's unparented signals object
        # before its queued result reaches the main thread. See
        # MainWindow._client_load_worker for the verified repro.
        self._save_worker = worker
        QThreadPool.globalInstance().start(worker)

    def _on_save_settings_result(self, success: bool):
        self._is_saving = False
        self.save_button.setEnabled(True)
        self.save_button.setText("Save")
        if success:
            # Raised on the parent: this dialog is about to close.
            toast(self.parentWidget() or self, "Settings saved")
            self.accept()
        else:
            show_error(
                self,
                "Settings weren't saved",
                "The profile may be open on another PC, or the server can't be reached. "
                "Wait a few seconds, then press Save again.",
            )

    def _on_save_settings_error(self, error):
        _exctype, value, tb = error
        logger.error(f"Failed to save settings: {value}\n{tb}")
        self._is_saving = False
        self.save_button.setEnabled(True)
        self.save_button.setText("Save")
        show_error(self, "Settings weren't saved", "Details are in Logs.")


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
