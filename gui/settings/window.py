import json
import logging
from typing import ClassVar

import pandas as pd
from PySide6.QtCore import QRect, QRectF, QSettings, QSize, Qt, QThreadPool, QTimer
from PySide6.QtGui import QColor, QIcon, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStackedWidget,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from gui.components import toast
from gui.components.error_banner import show_error
from gui.components.inline_message import InlineMessage
from gui.settings.base import SettingsPage
from gui.settings.contract import PageContract
from gui.settings.page_state import (
    ADDITIONAL_COLUMNS_UNREADABLE,
    GeneralDraft,
    OrdersDraft,
    StockDraft,
)
from gui.settings.reports import ReportsPage
from gui.settings.rules import RulesPage
from gui.settings.sets import SetsPage
from gui.settings.web_host import SettingsWebHost, read_file_columns
from gui.settings.weight import WeightPage
from gui.theme_manager import apply_dialog_button_roles, apply_font, set_button_role
from gui.worker import Worker
from shared.icons import icon
from shared.theme import font_css, on_theme_changed
from shopify_tool.core import effective_additional_columns

logger = logging.getLogger(__name__)

# The mockup's nav (phase 7 spec section 6.2): a 232px column, 12px of air
# around a list of 30px rows.
NAV_MARGIN_PX = 12
NAV_MIN_WIDTH_PX = 208
NAV_ROW_PX = 30
NAV_GROUP_PX = 28
NAV_SEARCH_PLACEHOLDER = "Search settings"
# Clear button, frame and text margins the placeholder has to share the field with.
NAV_SEARCH_CHROME_PX = 44
# A row's marks sit at its right edge: the alert, then the unsaved dot.
NAV_MARK_PX = 14
NAV_MARKS_WIDTH_PX = 28
UNSAVED_DOT_PX = 7
FOOTER_HEIGHT_PX = 60
FOOTER_MARGIN_PX = 16
# The air around a Qt page. The web host sits flush: its page has its own.
PAGE_MARGIN_PX = 12
DIRTY_POLL_MS = 400

# Page name -> words a person might search for that are not in the name.
SETTINGS_SEARCH_KEYWORDS: dict[str, list[str]] = {
    "General": ["delimiter", "csv", "low stock", "threshold", "repeat"],
    "Orders mapping": ["columns", "csv", "headers", "courier", "carrier", "shipping"],
    "Stock mapping": ["columns", "csv", "headers", "expiry", "batch", "lot", "fifo"],
    "Rules": ["conditions", "actions", "tags", "status", "priority", "automation"],
    "Sets": ["bundles", "kits", "components", "decoder"],
    "Weight": ["volumetric", "divisor", "dimensions", "boxes", "packaging", "kg"],
    "Reports": ["packing list", "stock export", "filters", "output", "writeoff"],
    "Tag categories": ["tags", "labels", "colours", "colors", "writeoff", "sku"],
}

# Nav name -> the key SettingsWebHost draws that page under (phase 7). Every
# other page is a Qt widget.
WEB_PAGE_KEYS: dict[str, str] = {
    "General": "general",
    "Orders mapping": "orders",
    "Stock mapping": "stock",
}


class _NavDelegate(QStyledItemDelegate):
    """Puts a nav row's marks at its right edge: the item's icon is drawn
    after the text, where the mockup has the unsaved dot."""

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        option.decorationPosition = QStyleOptionViewItem.Position.Right
        option.decorationAlignment = (
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )


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
        ("Data", ["General", "Orders mapping", "Stock mapping"]),
        ("Fulfilment logic", ["Rules", "Sets", "Weight"]),
        ("Output", ["Reports"]),
        ("Organization", ["Tag categories"]),
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
        loaded_files=None,
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
            loaded_files (dict, optional): {"orders": path, "stock": path} for
                the files loaded on Setup. A mapping page opens with that
                file's columns. Defaults to None.
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
                "stock_csv_delimiter": "auto",
                "orders_csv_delimiter": "auto",
                "delimiter_auto_migrated": True,
            }

        if "rules" not in self.config_data:
            self.config_data["rules"] = []

        if "packing_list_configs" not in self.config_data:
            self.config_data["packing_list_configs"] = []

        if "stock_export_configs" not in self.config_data:
            self.config_data["stock_export_configs"] = []

        if "set_decoders" not in self.config_data:
            self.config_data["set_decoders"] = {}

        self.setWindowTitle(f"Client settings · {self.client_id}")
        self.setMinimumSize(1100, 600)
        self.setModal(True)
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint)

        # No margins of the dialog's own: the nav panel, the web host and the
        # footer each run to its edges, as the mockup's do.
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        main_layout.addLayout(content_layout, 1)

        self._settings_nav = QListWidget()
        self._settings_nav.setObjectName("settingsNav")
        self._settings_nav.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._settings_nav.setIconSize(QSize(NAV_MARKS_WIDTH_PX, NAV_MARK_PX))
        self._settings_nav.setItemDelegate(_NavDelegate(self._settings_nav))
        self._blocked: dict[str, str] = {}

        self._nav_panel = QFrame()
        self._nav_panel.setObjectName("settingsNavPanel")
        nav_column = QVBoxLayout(self._nav_panel)
        nav_column.setContentsMargins(
            NAV_MARGIN_PX, NAV_MARGIN_PX, NAV_MARGIN_PX, NAV_MARGIN_PX
        )
        nav_column.setSpacing(NAV_MARGIN_PX)
        self._nav_search = QLineEdit()
        self._nav_search.setPlaceholderText(NAV_SEARCH_PLACEHOLDER)
        self._nav_search.setClearButtonEnabled(True)

        # The column is as wide as the placeholder needs, never narrower than
        # the mockup's. A hard 170 once clipped "Search settings" under Segoe
        # UI, which is wider than the Linux dev font -- so measure, don't guess.
        nav_width = max(
            NAV_MIN_WIDTH_PX,
            self._nav_search.fontMetrics().horizontalAdvance(NAV_SEARCH_PLACEHOLDER)
            + NAV_SEARCH_CHROME_PX,
        )
        self._settings_nav.setFixedWidth(nav_width)
        self._nav_search.setFixedWidth(nav_width)
        self._nav_search.textChanged.connect(self.filter_nav)
        self._nav_search.returnPressed.connect(self._select_first_visible_page)
        nav_column.addWidget(self._nav_search)
        self._no_match_label = QLabel("")
        self._no_match_label.setWordWrap(True)
        self._no_match_label.setFixedWidth(nav_width)
        on_theme_changed(
            self._no_match_label,
            lambda tokens: self._no_match_label.setStyleSheet(
                f"{font_css('body')} color: {tokens.text_secondary};"
            ),
        )
        self._no_match_label.hide()
        nav_column.addWidget(self._no_match_label)
        nav_column.addWidget(self._settings_nav, 1)
        content_layout.addWidget(self._nav_panel)
        QShortcut(QKeySequence(QKeySequence.StandardKey.Find), self).activated.connect(
            self._nav_search.setFocus
        )

        page_column = QVBoxLayout()
        page_column.setContentsMargins(0, 0, 0, 0)
        page_column.setSpacing(0)
        self._validation_message = InlineMessage()
        self._validation_message.setContentsMargins(
            PAGE_MARGIN_PX, PAGE_MARGIN_PX, PAGE_MARGIN_PX, 0
        )
        page_column.addWidget(self._validation_message)
        self.tab_widget = QStackedWidget()
        page_column.addWidget(self.tab_widget, 1)
        content_layout.addLayout(page_column, 1)

        self._page_index_by_name = {}
        self._pages: list[PageContract] = []
        self._pages_by_name: dict[str, PageContract] = {}
        self._unsaved: set[str] = set()

        # The three pages the web tier draws are drafts: pages with no widget.
        # One host widget shows whichever of them the nav selects.
        client = str(self.client_id)
        column_mappings = self.config_data.get("column_mappings", {})
        drafts = {
            "general": GeneralDraft(self.config_data.get("settings", {}), client),
            "orders": OrdersDraft(
                column_mappings,
                self.config_data.get("courier_mappings", {}),
                client,
                fallback_additional_columns=self._stored_additional_columns(),
                file=self._loaded_file(loaded_files, "orders"),
            ),
            "stock": StockDraft(
                column_mappings, client, file=self._loaded_file(loaded_files, "stock")
            ),
        }
        self._web_host = SettingsWebHost(drafts)
        self._web_host.edited.connect(self._on_web_edit)

        # Create all tabs (unchanged call order/method names)
        self._add_page(drafts["general"], "General", self._web_host)
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
        self._add_page(drafts["orders"], "Orders mapping", self._web_host)
        self._add_page(drafts["stock"], "Stock mapping", self._web_host)
        self._add_page(SetsPage(self.config_data.get("set_decoders", {})), "Sets")
        self._add_page(
            WeightPage(
                self.config_data.get("weight_config", {}),
                self.config_data.get("column_mappings", {}),
                self.config_data.get("settings", {}).get(
                    "stock_csv_delimiter", "auto"
                ),
            ),
            "Weight",
        )
        self._add_page(
            _TagCategoriesPage(
                self.config_data.get("tag_categories", {"version": 2, "categories": {}})
            ),
            "Tag categories",
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
        footer_rule = QFrame()
        footer_rule.setFixedHeight(1)
        on_theme_changed(
            footer_rule,
            lambda tokens: footer_rule.setStyleSheet(
                f"background-color: {tokens.border_subtle};"
            ),
        )
        main_layout.addWidget(footer_rule)

        self._footer = QWidget()
        self._footer.setFixedHeight(FOOTER_HEIGHT_PX)
        footer_row = QHBoxLayout(self._footer)
        footer_row.setContentsMargins(FOOTER_MARGIN_PX, 0, FOOTER_MARGIN_PX, 0)
        footer_row.addWidget(self._unsaved_label, 1)
        footer_row.addWidget(button_box)
        main_layout.addWidget(self._footer)

        # The close guard replaces the footer in place: the pages it names are
        # on screen beside it, so it is not a message box.
        self._close_guard = QWidget()
        self._close_guard.setFixedHeight(FOOTER_HEIGHT_PX)
        guard_row = QHBoxLayout(self._close_guard)
        guard_row.setContentsMargins(FOOTER_MARGIN_PX, 0, FOOTER_MARGIN_PX, 0)
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
        # A profile can open with a required column already unmapped.
        self._refresh_status()
        # ponytail: polls the visible page's snapshot (one collect() plus one
        # json.dumps) every 400ms. Ceiling: a page whose snapshot costs tens of
        # milliseconds makes the dialog stutter; upgrade to a per-page
        # `edited` signal then.
        self._dirty_poll = QTimer(self)
        self._dirty_poll.setInterval(DIRTY_POLL_MS)
        self._dirty_poll.timeout.connect(self._poll_current_page)
        self._dirty_poll.start()

    def _add_page(self, page: PageContract, name: str, widget=None) -> None:
        """Register a settings page under `name`. Tracked in _pages so
        save_settings validates and collects from it.

        `widget` is what the stack shows for it: the page itself when it is a
        Qt page, the web host when it is a draft. The grouped left-nav
        (_build_settings_nav) looks pages up by this same name.
        """
        if widget is None:
            widget = page
            widget.setContentsMargins(
                PAGE_MARGIN_PX, PAGE_MARGIN_PX, PAGE_MARGIN_PX, PAGE_MARGIN_PX
            )
        self._pages.append(page)
        self._pages_by_name[name] = page
        if self.tab_widget.indexOf(widget) < 0:
            self.tab_widget.addWidget(widget)
        self._page_index_by_name[name] = self.tab_widget.indexOf(widget)

    @staticmethod
    def _loaded_file(loaded_files, kind: str):
        """The columns of the file loaded on Setup, or None.

        A file that cannot be read is no file: the mapping page then says no
        CSV has been read, and the operator can pick one.
        """
        path = (loaded_files or {}).get(kind)
        if not path:
            return None
        try:
            return read_file_columns(path, loaded=True)
        except Exception:
            logger.exception(f"The loaded {kind} file's columns couldn't be read")
            return None

    def _on_web_edit(self) -> None:
        """A draft changed: its marks follow at once, with no poll."""
        self._refresh_status()

    def _refresh_status(self) -> None:
        """Re-check what an edit on a web page can change: the drafts' unsaved
        state, and what blocks the save. Both are cheap, so every edit runs it."""
        for name in WEB_PAGE_KEYS:
            if self._pages_by_name[name].is_dirty() != (name in self._unsaved):
                self._unsaved ^= {name}
        self._blocked = {
            name: blocker
            for name in self._nav_page_names()
            if (blocker := self._pages_by_name[name].blocker())
        }
        self._render_unsaved()

    def _stored_additional_columns(self):
        """The list's pre-Bundle-13 home, read only as a fallback (ADR 0006).

        Returns ADDITIONAL_COLUMNS_UNREADABLE rather than [] when the read
        fails, so a blip on the share cannot make Save write an empty list
        over the profile's real one.
        """
        try:
            client_config = self.profile_manager.load_client_config(self.client_id)
            return effective_additional_columns({}, client_config)
        except Exception:
            logger.exception("The client config's additional columns couldn't be read")
            return ADDITIONAL_COLUMNS_UNREADABLE

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
            header = QListWidgetItem(group_name)
            header.setFlags(Qt.ItemFlag.NoItemFlags)
            header.setSizeHint(QSize(0, NAV_GROUP_PX))
            header.setTextAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom
            )
            apply_font(header, "caption", bold=True)
            self._settings_nav.addItem(header)
            for page_name in page_names:
                item = QListWidgetItem(page_name)
                item.setSizeHint(QSize(0, NAV_ROW_PX))
                item.setData(
                    Qt.ItemDataRole.UserRole, self._page_index_by_name[page_name]
                )
                self._settings_nav.addItem(item)
        self._settings_nav.currentItemChanged.connect(self._on_settings_nav_changed)
        self._restore_nav_selection()

    def _page_items(self) -> list[QListWidgetItem]:
        """Every nav row that opens a page, in nav order; group headers excluded."""
        nav = self._settings_nav
        items = (nav.item(row) for row in range(nav.count()))
        return [
            item for item in items if item.data(Qt.ItemDataRole.UserRole) is not None
        ]

    def _restore_nav_selection(self) -> None:
        """Select the requested page, else the last-viewed one, else the first."""
        wanted = self._initial_page or QSettings(
            "ShopifyFulfillmentTool", "FulfillmentApp"
        ).value(self.NAV_SETTINGS_KEY)
        items = self._page_items()
        # _build_settings_nav refuses an empty group, so items is never empty.
        self._settings_nav.setCurrentItem(
            next((item for item in items if item.text() == wanted), items[0])
        )

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
        self._no_match_label.setText(f"No settings match “{text.strip()}”.")
        self._no_match_label.setHidden(not query or bool(visible))
        return visible

    def _select_first_visible_page(self) -> None:
        for item in self._page_items():
            if not item.isHidden():
                self._settings_nav.setCurrentItem(item)
                return

    def _on_settings_nav_changed(self, current, previous):
        self._validation_message.clear()
        # The page being left may hold an edit the 400ms poll hasn't seen.
        if previous is not None:
            self._poll_page(previous.text())
        # The row that is open reads bold; a QSS ::item rule cannot set a weight.
        for item in (previous, current):
            if item is not None:
                font = item.font()
                font.setBold(item is current)
                item.setFont(font)
        if current is None:
            return
        index = current.data(Qt.ItemDataRole.UserRole)
        if index is not None:
            if current.text() in WEB_PAGE_KEYS:
                self._web_host.show_page(WEB_PAGE_KEYS[current.text()])
            self.tab_widget.setCurrentIndex(index)
            QSettings("ShopifyFulfillmentTool", "FulfillmentApp").setValue(
                self.NAV_SETTINGS_KEY, current.text()
            )

    def _nav_page_names(self) -> list[str]:
        return [name for _group, names in self.SETTINGS_NAV_GROUPS for name in names]

    def _select_page(self, name: str) -> None:
        for item in self._page_items():
            if item.text() == name:
                self._settings_nav.setCurrentItem(item)
                return

    def _unsaved_names(self) -> list[str]:
        return [name for name in self._nav_page_names() if name in self._unsaved]

    def refresh_dirty(self) -> list[str]:
        """Re-check every page; return the unsaved page names in nav order."""
        self._unsaved = {
            name for name, page in self._pages_by_name.items() if page.is_dirty()
        }
        self._render_unsaved()
        return self._unsaved_names()

    def _poll_current_page(self) -> None:
        item = self._settings_nav.currentItem()
        if item is not None:
            self._poll_page(item.text())

    def _poll_page(self, name: str) -> None:
        # By the nav's name, not the stack's widget: three pages share one.
        page = self._pages_by_name.get(name)
        if page is None:
            return
        if page.is_dirty() != (name in self._unsaved):
            self._unsaved ^= {name}
            self._render_unsaved()

    def _render_unsaved(self) -> None:
        names = self._unsaved_names()
        summary = unsaved_summary(names)
        self._unsaved_label.setText(summary)
        self._close_guard_label.setText(
            f"{summary}. Closing now discards them." if names else ""
        )
        self._apply_nav_marks()

    def _rebuild_nav_marks(self, tokens) -> None:
        """One icon per combination of marks: (unsaved, blocked)."""
        alert = icon("circle-alert", tokens.status_danger)

        def marks(unsaved: bool, blocked: bool) -> QIcon:
            pixmap = QPixmap(NAV_MARKS_WIDTH_PX, NAV_MARK_PX)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            if blocked:
                alert.paint(painter, QRect(0, 0, NAV_MARK_PX, NAV_MARK_PX))
            if unsaved:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(tokens.text))
                painter.drawEllipse(
                    QRectF(
                        NAV_MARKS_WIDTH_PX - UNSAVED_DOT_PX,
                        (NAV_MARK_PX - UNSAVED_DOT_PX) / 2,
                        UNSAVED_DOT_PX,
                        UNSAVED_DOT_PX,
                    )
                )
            painter.end()
            result = QIcon(pixmap)
            # The same pixmap for a selected row: Qt would tint a missing one.
            result.addPixmap(pixmap, QIcon.Mode.Selected)
            return result

        self._marks = {
            (unsaved, blocked): marks(unsaved, blocked)
            for unsaved in (False, True)
            for blocked in (False, True)
        }
        self._apply_nav_marks()

    def _apply_nav_marks(self) -> None:
        for item in self._page_items():
            unsaved = item.text() in self._unsaved
            blocked = item.text() in self._blocked
            item.setIcon(self._marks[(unsaved, blocked)])
            notes = [
                note
                for note, on in (
                    ("Needs attention", blocked),
                    ("Unsaved changes", unsaved),
                )
                if on
            ]
            item.setToolTip(", ".join(notes))
            item.setData(
                Qt.ItemDataRole.AccessibleTextRole,
                ", ".join([item.text(), *(note.lower() for note in notes)]),
            )

    def keyPressEvent(self, event):
        # QLineEdit passes Return on, and QDialog answers it by clicking its
        # default button -- Save. In the search box Return only opens a page.
        if self.focusWidget() is self._nav_search and event.key() in (
            Qt.Key.Key_Return,
            Qt.Key.Key_Enter,
        ):
            event.accept()
            return
        super().keyPressEvent(event)

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
        _exctype, value, _tb = error
        logger.error("Failed to save settings", exc_info=value)
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
