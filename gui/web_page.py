"""What every web page's bridge shares (ADR 0016, phase 3 spec section 3.2).

A page's bridge extends PageBridge and adds its own named members; mount_page
loads the page into a view with the theme already written into it.
"""

import weakref
from pathlib import Path

from PySide6.QtCore import Property, QObject, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QColor
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineWidgets import QWebEngineView

from gui.theme_manager import get_theme_manager
from shared.theme import on_theme_changed, theme_css_vars

WEB_DIR = Path(__file__).resolve().parent / "web"
THEME_MARKER = "/* theme-vars */"
# How long the chrome waits for the visible page to paint a new theme.
THEME_ACK_TIMEOUT_MS = 150

# bridge -> its view, for switch_theme. Weak: a closed page drops out.
_pages: weakref.WeakKeyDictionary[PageBridge, QWebEngineView] = (
    weakref.WeakKeyDictionary()
)


class PageBridge(QObject):
    """The theme and the toast: the two things every web page is told."""

    themeCssChanged = Signal()
    # Python-facing: the page has painted the theme it was last sent.
    themePainted = Signal()
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

    @Slot()
    def themeApplied(self) -> None:
        """Called by the page, two frames after it wrote a changed theme."""
        self.themePainted.emit()

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
        tokens = get_theme_manager().get_current_theme()
        # What shows wherever the page has not painted yet: the page's own
        # plane, not Chromium's white.
        view.page().setBackgroundColor(QColor(tokens.surface_sunken))
        bridge.set_theme_css(theme_css_vars(tokens))

    _pages[bridge] = view
    on_theme_changed(view, _push_theme)  # runs once now, then on every change

    html = page.read_text(encoding="utf-8").replace(THEME_MARKER, bridge.themeCss)
    view.setHtml(html, QUrl.fromLocalFile(str(WEB_DIR) + "/"))


_finish_pending = None  # completes the switch in flight, if there is one


def switch_theme(name: str) -> None:
    """Change the theme so the window turns over in one step.

    ThemeManager.set_theme() repaints the Qt chrome at once and each web page
    a frame or more later, in its own process. So the visible pages are sent
    the new theme first, and the chrome follows when they have painted it --
    or after THEME_ACK_TIMEOUT_MS, so a page that never answers costs a
    moment and never a stuck theme. No animation: ADR 0016.
    """
    global _finish_pending
    if _finish_pending is not None:
        _finish_pending()
    manager = get_theme_manager()
    if name == manager.get_current_theme_name():
        return

    waiting = set()
    for bridge, view in list(_pages.items()):
        try:
            if view.isVisible():
                waiting.add(bridge)
        except RuntimeError:
            continue  # the C++ view is gone; its bridge is on its way out
    if not waiting:
        manager.set_theme(name)
        return

    done = False

    def finish() -> None:
        global _finish_pending
        nonlocal done
        if done:
            return
        done = True
        _finish_pending = None
        for bridge in connected:
            try:
                bridge.themePainted.disconnect(painted[bridge])
            except RuntimeError:
                pass  # the bridge was destroyed while we waited
        manager.set_theme(name)

    def on_painted(bridge) -> None:
        waiting.discard(bridge)
        if not waiting:
            finish()

    painted = {bridge: (lambda b=bridge: on_painted(b)) for bridge in waiting}
    connected = list(waiting)
    for bridge in connected:
        bridge.themePainted.connect(painted[bridge])
    _finish_pending = finish
    QTimer.singleShot(THEME_ACK_TIMEOUT_MS, finish)

    css = theme_css_vars(manager.tokens_for(name))
    for bridge in connected:
        bridge.set_theme_css(css)
