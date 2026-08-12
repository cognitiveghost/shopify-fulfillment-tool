"""Themed icons rendered from the bundled Lucide SVGs.

Lucide draws every glyph with stroke="currentColor". Substituting that token
in the SVG source before handing it to QSvgRenderer recolours the *vectors*,
so output stays crisp at any size and DPI -- unlike recolouring an already
rasterized pixmap with CompositionMode_SourceIn. It also means we never load
an .svg through QIcon, so the frozen build does not depend on Qt's qsvg
imageformats plugin being collected.
"""
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from .theme_manager import get_theme_manager

ICONS_DIR = Path(__file__).resolve().parent / "assets" / "icons"

# Qt picks the closest of these for the widget size and the screen's device
# pixel ratio. Querying devicePixelRatio ourselves would be wrong on a
# multi-monitor setup, where it differs per screen.
_RENDER_SIZES = (16, 24, 32, 48)


@lru_cache(maxsize=None)
def _source(name: str) -> str:
    path = ICONS_DIR / f"{name}.svg"
    if not path.is_file():
        raise KeyError(f"No bundled icon named {name!r} (looked in {ICONS_DIR})")
    return path.read_text(encoding="utf-8")


@lru_cache(maxsize=None)
def _render(name: str, color: str) -> QIcon:
    data = QByteArray(_source(name).replace("currentColor", color).encode())
    result = QIcon()
    for size in _RENDER_SIZES:
        # One renderer per size: QSvgRenderer keeps view state across render()
        # calls, and reusing it across sizes skews the later ones.
        renderer = QSvgRenderer(data)
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        renderer.render(painter)
        painter.end()
        result.addPixmap(pixmap)
    return result


def icon(name: str, color: str | None = None) -> QIcon:
    """A themed icon by Lucide glyph name, e.g. icon("trash-2").

    Defaults to the active theme's text colour. Pass `color` only where the
    icon has to read against something that is not this app's background --
    the window/taskbar icon, which sits on the OS shell's own surface.

    Raises KeyError on an unknown name, matching font_css()'s rule: a typo
    must fail during development rather than render invisible in production.

    Cached on (name, colour). A theme toggle needs no invalidation -- the
    colour is part of the key, so it simply misses into a second set of
    entries, and two themes times fifteen glyphs is the ceiling.
    """
    if color is None:
        color = get_theme_manager().get_current_theme().text
    return _render(name, color)
