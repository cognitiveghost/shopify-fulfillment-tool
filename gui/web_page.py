"""What every web page's bridge shares (ADR 0016, phase 3 spec section 3.2).

A page's bridge extends PageBridge and adds its own named members; mount_page
loads the page into a view with the theme already written into it.
"""

from pathlib import Path

from PySide6.QtCore import Property, QObject, QUrl, Signal
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineWidgets import QWebEngineView

from gui.theme_manager import get_theme_manager
from shared.theme import on_theme_changed, theme_css_vars

WEB_DIR = Path(__file__).resolve().parent / "web"
THEME_MARKER = "/* theme-vars */"


class PageBridge(QObject):
    """The theme and the toast: the two things every web page is told."""

    themeCssChanged = Signal()
    # JS-facing: the page draws its own toast, because a Qt child widget
    # cannot paint above a web view's surface (ADR 0007).
    toastRaised = Signal(str, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._theme_css = ""

    def _get_theme_css(self) -> str:
        return self._theme_css

    themeCss = Property(str, _get_theme_css, notify=themeCssChanged)

    def set_theme_css(self, css: str) -> None:
        if css == self._theme_css:
            return
        self._theme_css = css
        self.themeCssChanged.emit()

    def raise_toast(self, message: str, undoable: bool = False) -> None:
        self.toastRaised.emit(str(message), bool(undoable))


def mount_page(
    view: QWebEngineView, bridge: PageBridge, page: Path, channel_name: str
) -> None:
    """Load `page` into `view` with `bridge` as the object it talks to.

    The theme is written into the page before it loads, so the first paint is
    already themed, then pushed through the bridge on every theme or density
    change, so the document repaints without a reload. The channel is
    parented to `view` and dies with it.
    """
    channel = QWebChannel(view)
    channel.registerObject(channel_name, bridge)
    view.page().setWebChannel(channel)

    def _push_theme(_tokens) -> None:
        # The manager's tokens rather than the argument: only those carry the
        # bundled Inter family the Qt tier renders in.
        bridge.set_theme_css(theme_css_vars(get_theme_manager().get_current_theme()))

    on_theme_changed(view, _push_theme)  # runs once now, then on every change

    html = page.read_text(encoding="utf-8").replace(THEME_MARKER, bridge.themeCss)
    view.setHtml(html, QUrl.fromLocalFile(str(WEB_DIR) + "/"))
