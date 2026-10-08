"""What every web page's bridge shares, in both apps (ADR 0016, ADR 0017).

A page's bridge extends PageBridge and adds its own named members; mount_page
loads the page into a view with the theme already written into it.
"""

import logging
import weakref
from pathlib import Path

from PySide6.QtCore import Property, QObject, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QColor
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineWidgets import QWebEngineView

from shared.theme import on_theme_changed, theme_css_vars

logger = logging.getLogger(__name__)

SHARED_WEB_DIR = Path(__file__).resolve().parent / "web"
THEME_MARKER = "/* theme-vars */"
# How long the chrome waits for the visible page to paint a new theme.
THEME_ACK_TIMEOUT_MS = 150

# bridge -> its view, for switch_theme. Weak: a closed page drops out.
_pages: weakref.WeakKeyDictionary[PageBridge, QWebEngineView] = (
    weakref.WeakKeyDictionary()
)


class PageBridge(QObject):
    """The theme, the toast and the revision: what every web page is told."""

    themeCssChanged = Signal()
    # Python-facing: the page has painted the theme it was last sent.
    themePainted = Signal()
    # JS-facing: the page draws its own toast, because a Qt child widget
    # cannot paint above a web view's surface (ADR 0007).
    toastRaised = Signal(str, bool)
    revisionChanged = Signal()
    # Python-facing: the page has painted this revision.
    painted = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._theme_css = ""
        self._revision = 0
        self.painted_revision = -1  # nothing reported yet
        # Every property that can change raises the revision, whichever
        # subclass declares it: none can be forgotten.
        # (QObject's own objectName is not page state.)
        meta = self.metaObject()
        for index in range(QObject.staticMetaObject.propertyCount(), meta.propertyCount()):
            prop = meta.property(index)
            if prop.hasNotifySignal() and prop.name() != "revision":
                signal = getattr(self, bytes(prop.notifySignal().name()).decode())
                signal.connect(self._bump)

    def _bump(self, *_args) -> None:
        self._revision += 1
        self.revisionChanged.emit()

    def _get_revision(self) -> int:
        return self._revision

    revision = Property(int, _get_revision, notify=revisionChanged)

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

    @Slot(int)
    def paintedRevision(self, revision) -> None:
        """Called by the page, two frames after it drew `revision`."""
        self.painted_revision = int(revision)
        self.painted.emit(self.painted_revision)

    def raise_toast(self, message: str, undoable: bool = False) -> None:
        self.toastRaised.emit(str(message), bool(undoable))


def mount_page(
    view: QWebEngineView, bridge: PageBridge, page: Path, channel_name: str, *, tokens
) -> None:
    """Load `page` into `view` with `bridge` as the object it talks to.

    `tokens` is a zero-argument callable returning the app's current
    ThemeTokens, the ones that carry its bundled font family. The theme is
    written into the page before it loads, so the first paint is already
    themed, then pushed through the bridge on every theme or density change,
    so the document repaints without a reload. The channel is parented to
    `view` and dies with it. The page's own folder is its base URL.
    """
    channel = QWebChannel(view)
    channel.registerObject(channel_name, bridge)
    view.page().setWebChannel(channel)

    def _push_theme(_tokens) -> None:
        current = tokens()
        # What shows wherever the page has not painted yet: the page's own
        # plane, not Chromium's white.
        view.page().setBackgroundColor(QColor(current.surface_sunken))
        bridge.set_theme_css(theme_css_vars(current))

    _pages[bridge] = view
    on_theme_changed(view, _push_theme)  # runs once now, then on every change

    html = page.read_text(encoding="utf-8").replace(THEME_MARKER, bridge.themeCss)
    view.setHtml(html, QUrl.fromLocalFile(str(page.parent) + "/"))


_finish_pending = None  # completes the switch in flight, if there is one


def switch_theme(name: str, *, current_name, tokens_for, set_theme) -> None:
    """Change the theme so the window turns over in one step.

    The three callables are the app's theme manager, which shared/ cannot
    import.

    ThemeManager.set_theme() repaints the Qt chrome at once and each web page
    a frame or more later, in its own process. So the visible pages are sent
    the new theme first, and the chrome follows when they have painted it --
    or after THEME_ACK_TIMEOUT_MS, so a page that never answers costs a
    moment and never a stuck theme. No animation: ADR 0016.
    """
    global _finish_pending
    if _finish_pending is not None:
        _finish_pending()
    if name == current_name():
        return

    waiting = set()
    for bridge, view in list(_pages.items()):
        try:
            if view.isVisible():
                waiting.add(bridge)
        except RuntimeError:
            continue  # the C++ view is gone; its bridge is on its way out
    if not waiting:
        set_theme(name)
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
        set_theme(name)

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

    css = theme_css_vars(tokens_for(name))
    for bridge in connected:
        bridge.set_theme_css(css)


PAINT_TIMEOUT_MS = 150


def when_painted(bridge: PageBridge, callback, timeout_ms: int = PAINT_TIMEOUT_MS) -> None:
    """Run `callback` once the page has painted the bridge's current revision.

    At once if it already has; otherwise on the page's report, or after
    `timeout_ms`, whichever comes first. A page that never answers costs the
    timeout and a log line, never a stuck screen.
    """
    target = bridge.revision
    if bridge.painted_revision >= target:
        callback()
        return

    done = False

    def finish(timed_out: bool = False) -> None:
        nonlocal done
        if done:
            return
        done = True
        try:
            bridge.painted.disconnect(on_painted)
            last = bridge.painted_revision
        except RuntimeError:
            last = -1  # the bridge was destroyed while we waited
        if timed_out:
            logger.warning(
                "%s did not report revision %s within %s ms (last painted %s)",
                type(bridge).__name__,
                target,
                timeout_ms,
                last,
            )
        callback()

    def on_painted(revision: int) -> None:
        if revision >= target:
            finish()

    bridge.painted.connect(on_painted)
    QTimer.singleShot(timeout_ms, lambda: finish(timed_out=True))
