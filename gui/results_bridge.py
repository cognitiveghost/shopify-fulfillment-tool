"""The bridge: the one object the web tier talks to (ADR 0001, roadmap 9.12).

Every message is its own named member, never a generic send(kind, data).
State Python owns crosses as a notify Property, so a page that connects late
still reads the current value with no handshake; what JS reports crosses as a
Slot. Channel members are camelCase because JS calls them.

The full catalogue, and which bundle adds each member, is section 5.2 of
docs/superpowers/specs/2026-09-11-phase9-bundle11-seam-design.md, as amended
by Bundle 12 (docs/superpowers/specs/2026-09-11-phase9-bundle12-results-doc-design.md
section 5) and Bundle 13
(docs/superpowers/specs/2026-09-11-phase9-bundle13-pane-columns-design.md
section 4). Add a member there before adding it here.
"""

from pathlib import Path

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineWidgets import QWebEngineView

from gui.orders_view import (
    ORDER_KEY,
    ORDER_LEVEL_COLUMNS,
    classify_columns,
    order_payload,
    results_summary,
)
from gui.theme_manager import get_theme_manager
from shared.theme import on_theme_changed, theme_css_vars

WEB_DIR = Path(__file__).resolve().parent / "web"
PAGE = WEB_DIR / "results.html"
THEME_MARKER = "/* theme-vars */"
CHANNEL_NAME = "results"


def normalize_column_settings(raw) -> dict:
    """A stored column layout, made safe to hand to the page (Bundle 13 §3.2).

    Python stores names only: titles, groups, defaults and pinning are the
    page's (columns.js). None means "use the page's default".
    """
    raw = raw if isinstance(raw, dict) else {}

    def names(value):
        if not isinstance(value, list):
            return None
        return list(dict.fromkeys(v for v in value if isinstance(v, str)))

    return {
        "order": names(raw.get("order")),
        "visible": names(raw.get("visible")),
        "auto_hide_empty": bool(raw.get("auto_hide_empty", False)),
    }


class ResultsBridge(QObject):
    """The results document's one channel object (Bundles 11 and 12)."""

    ordersChanged = Signal()
    summaryChanged = Signal()
    themeCssChanged = Signal()
    exportEnabledChanged = Signal()
    columnsChanged = Signal()
    tagCategoriesChanged = Signal()
    # JS-facing: Ctrl+F in the Qt window focuses the page's search field.
    focusSearchRequested = Signal()
    # Python-facing. JS reports through the slots below and never connects to
    # these, so nothing it sends can echo back into the page.
    selectionChanged = Signal(list)
    exportRequested = Signal()
    screenMenuRequested = Signal()
    # Python-facing (Bundle 13): the pane's verbs and the column layout.
    holdRequested = Signal(str)
    fulfillRequested = Signal(str)
    excludeRequested = Signal(str)
    lineRemovalRequested = Signal(str, int, str)
    tagAddRequested = Signal(str, str)
    tagRemovalRequested = Signal(str, str)
    columnSettingsChanged = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._orders: list = []
        self._summary: dict = {}
        self._theme_css = ""
        self._export_enabled = False
        self._selection: list[str] = []
        self._columns: dict = {**normalize_column_settings(None), "extras": []}
        self._tag_categories: dict = {}

    # --- out: Python -> JS -------------------------------------------------

    def _get_orders(self) -> list:
        return self._orders

    orders = Property("QVariantList", _get_orders, notify=ordersChanged)

    def _get_summary(self) -> dict:
        return self._summary

    summary = Property("QVariantMap", _get_summary, notify=summaryChanged)

    def _get_theme_css(self) -> str:
        return self._theme_css

    themeCss = Property(str, _get_theme_css, notify=themeCssChanged)

    def _get_export_enabled(self) -> bool:
        return self._export_enabled

    exportEnabled = Property(bool, _get_export_enabled, notify=exportEnabledChanged)

    def _get_columns(self) -> dict:
        return self._columns

    columns = Property("QVariantMap", _get_columns, notify=columnsChanged)

    def _get_tag_categories(self) -> dict:
        return self._tag_categories

    tagCategories = Property(
        "QVariantMap", _get_tag_categories, notify=tagCategoriesChanged
    )

    # --- in: JS -> Python --------------------------------------------------

    @Slot("QVariantList")
    def setSelection(self, order_numbers) -> None:
        selection = [str(n) for n in order_numbers]
        if selection == self._selection:
            return
        self._selection = selection
        self.selectionChanged.emit(selection)

    @Slot()
    def openExport(self) -> None:
        self.exportRequested.emit()

    @Slot()
    def openScreenMenu(self) -> None:
        self.screenMenuRequested.emit()

    @Slot(str)
    def holdOrder(self, order_number) -> None:
        self.holdRequested.emit(str(order_number))

    @Slot(str)
    def fulfillOrder(self, order_number) -> None:
        self.fulfillRequested.emit(str(order_number))

    @Slot(str)
    def excludeOrder(self, order_number) -> None:
        self.excludeRequested.emit(str(order_number))

    @Slot(str, int, str)
    def removeLine(self, order_number, line_index, sku) -> None:
        self.lineRemovalRequested.emit(str(order_number), int(line_index), str(sku))

    @Slot(str, str)
    def addOrderTag(self, order_number, tag) -> None:
        self.tagAddRequested.emit(str(order_number), str(tag))

    @Slot(str, str)
    def removeOrderTag(self, order_number, tag) -> None:
        self.tagRemovalRequested.emit(str(order_number), str(tag))

    @Slot(str)
    def copyText(self, text) -> None:
        # navigator.clipboard is not dependable under the page's file:// base.
        QGuiApplication.clipboard().setText(str(text))

    @Slot("QVariantList")
    def setColumnOrder(self, names) -> None:
        self._store_columns(order=names)

    @Slot("QVariantList")
    def setVisibleColumns(self, names) -> None:
        self._store_columns(visible=names)

    @Slot()
    def resetColumns(self) -> None:
        self._store_columns(order=None, visible=None)

    @Slot(bool)
    def setAutoHideEmpty(self, on) -> None:
        self._store_columns(auto_hide_empty=bool(on))

    def _store_columns(self, **changes) -> None:
        stored = normalize_column_settings({**self._columns, **changes})
        self._columns = {**stored, "extras": self._columns["extras"]}
        self.columnsChanged.emit()
        self.columnSettingsChanged.emit(stored)

    # --- Python-facing API -------------------------------------------------

    def selection(self) -> list[str]:
        return list(self._selection)

    def set_orders(self, df) -> None:
        """Push the session: the order payload and the KPI numbers, together."""
        self._orders = order_payload(df)
        self._summary = results_summary(df)
        extras = []
        if df is not None and not df.empty and ORDER_KEY in df.columns:
            order_level, _ = classify_columns(df)
            extras = [c for c in order_level if c not in ORDER_LEVEL_COLUMNS]
        if extras != self._columns["extras"]:
            self._columns = {**self._columns, "extras": extras}
            self.columnsChanged.emit()
        self.summaryChanged.emit()
        self.ordersChanged.emit()

    def set_export_enabled(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if enabled == self._export_enabled:
            return
        self._export_enabled = enabled
        self.exportEnabledChanged.emit()

    def set_column_settings(self, raw) -> None:
        self._columns = {
            **normalize_column_settings(raw),
            "extras": self._columns["extras"],
        }
        self.columnsChanged.emit()

    def set_tag_categories(self, categories: dict) -> None:
        self._tag_categories = dict(categories or {})
        self.tagCategoriesChanged.emit()

    def set_theme_css(self, css: str) -> None:
        if css == self._theme_css:
            return
        self._theme_css = css
        self.themeCssChanged.emit()


def mount_results_page(view: QWebEngineView) -> ResultsBridge:
    """Load the results page into `view` and return the bridge it talks to.

    The theme is written into the page before it loads, so the first paint is
    already themed, then pushed through the bridge on every theme or density
    change, so the document repaints without a reload. Both the bridge and
    the channel are parented to `view` and die with it.
    """
    bridge = ResultsBridge(view)
    channel = QWebChannel(view)
    channel.registerObject(CHANNEL_NAME, bridge)
    view.page().setWebChannel(channel)

    def _push_theme(_tokens) -> None:
        # The manager's tokens rather than the argument: only those carry the
        # bundled Inter family the Qt tier renders in.
        bridge.set_theme_css(theme_css_vars(get_theme_manager().get_current_theme()))

    on_theme_changed(view, _push_theme)  # runs once now, then on every change

    html = PAGE.read_text(encoding="utf-8").replace(THEME_MARKER, bridge.themeCss)
    view.setHtml(html, QUrl.fromLocalFile(str(WEB_DIR) + "/"))
    return bridge
