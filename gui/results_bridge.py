"""The bridge: the one object the web tier talks to (ADR 0001, roadmap 9.12).

Every message is its own named member, never a generic send(kind, data).
State Python owns crosses as a notify Property, so a page that connects late
still reads the current value with no handshake; what JS reports crosses as a
Slot. Channel members are camelCase because JS calls them.

The full catalogue, and which bundle adds each member, is section 5.2 of
docs/superpowers/specs/2026-09-11-phase9-bundle11-seam-design.md. Add a
member there before adding it here.
"""

from pathlib import Path

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot
from PySide6.QtWebChannel import QWebChannel

from gui.orders_view import order_payload
from gui.theme_manager import get_theme_manager
from shared.theme import on_theme_changed, theme_css_vars

WEB_DIR = Path(__file__).resolve().parent / "web"
PAGE = WEB_DIR / "results.html"
THEME_MARKER = "/* theme-vars */"
CHANNEL_NAME = "results"


class ResultsBridge(QObject):
    """Bundle 11's three members: orders, themeCss, setSelection."""

    ordersChanged = Signal()
    themeCssChanged = Signal()
    # Python-facing. JS reports a selection through setSelection() and never
    # connects to this, so a selection cannot echo back into the page.
    selectionChanged = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._orders: list = []
        self._theme_css = ""
        self._selection: list[str] = []

    # --- out: Python -> JS -------------------------------------------------

    def _get_orders(self) -> list:
        return self._orders

    orders = Property("QVariantList", _get_orders, notify=ordersChanged)

    def _get_theme_css(self) -> str:
        return self._theme_css

    themeCss = Property(str, _get_theme_css, notify=themeCssChanged)

    # --- in: JS -> Python --------------------------------------------------

    @Slot("QVariantList")
    def setSelection(self, order_numbers) -> None:
        selection = [str(n) for n in order_numbers]
        if selection == self._selection:
            return
        self._selection = selection
        self.selectionChanged.emit(selection)

    # --- Python-facing API -------------------------------------------------

    def selection(self) -> list[str]:
        return list(self._selection)

    def set_orders(self, df) -> None:
        self._orders = order_payload(df)
        self.ordersChanged.emit()

    def set_theme_css(self, css: str) -> None:
        if css == self._theme_css:
            return
        self._theme_css = css
        self.themeCssChanged.emit()


def mount_results_page(view) -> ResultsBridge:
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
