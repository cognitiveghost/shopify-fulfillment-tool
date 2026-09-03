"""Themed icons rendered from the bundled Lucide SVGs.

Lucide draws every glyph with stroke="currentColor". Substituting that token
in the SVG source before handing it to QSvgRenderer recolours the *vectors*,
so output stays crisp at any size and DPI -- unlike recolouring an already
rasterized pixmap with CompositionMode_SourceIn. It also means we never load
an .svg through QIcon, so the frozen build does not depend on Qt's qsvg
imageformats plugin being collected.
"""
import hashlib
from functools import cache
from pathlib import Path

from PySide6.QtCore import QByteArray, QStandardPaths, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from shared.theme import current_tokens

ICONS_DIR = Path(__file__).resolve().parent / "assets" / "icons"

# Qt picks the closest of these for the widget size and the screen's device
# pixel ratio. Querying devicePixelRatio ourselves would be wrong on a
# multi-monitor setup, where it differs per screen.
_RENDER_SIZES = (16, 24, 32, 48)


@cache
def _source(name: str) -> str:
    path = ICONS_DIR / f"{name}.svg"
    if not path.is_file():
        raise KeyError(f"No bundled icon named {name!r} (looked in {ICONS_DIR})")
    return path.read_text(encoding="utf-8")


@cache
def _render(name: str, color: str, sizes: tuple[int, ...]) -> QIcon:
    data = QByteArray(_source(name).replace("currentColor", color).encode())
    result = QIcon()
    for size in sizes:
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


def icon(
    name: str, color: str | None = None, sizes: tuple[int, ...] = _RENDER_SIZES
) -> QIcon:
    """A themed icon by Lucide glyph name, e.g. icon("trash-2").

    Defaults to the active theme's text colour. Pass `color` only where the
    icon has to read against something that is not this app's background --
    the window/taskbar icon, which sits on the OS shell's own surface.

    Pass `sizes` only where the widget sizes above are not the whole story;
    the window icon needs 256px for Alt+Tab and Explorer's largest view, and
    these are pixmaps, so anything not rendered can only be upscaled.

    Raises KeyError on an unknown name, matching font_css()'s rule: a typo
    must fail during development rather than render invisible in production.

    Cached on (name, colour, sizes). A theme toggle needs no invalidation --
    the colour is part of the key, so it simply misses into a second set of
    entries, and two themes times fifteen glyphs is the ceiling.
    """
    if color is None:
        color = current_tokens().text
    return _render(name, color, sizes)


def glyph_url(name: str, color: str | None = None, size: int = 18) -> str:
    """A QSS-ready `url("...")` token for a themed glyph.

    QSS `image:` resolves its url() through QImageReader, not QSvgRenderer,
    so handing it an .svg would reintroduce the qsvg imageformats plugin
    dependency that icon() exists to avoid. This rasterises the recoloured
    SVG once, through the same renderer icon() uses, and caches the PNG on
    disk under a name keyed to (name, colour, size) -- a re-vendored glyph or
    a retuned token invalidates its own cache entry; nothing else does.

    The path is always spelled with as_posix(): a backslash-spelled path
    draws nothing in Qt's QSS url(), silently, on Windows only.

    Raises KeyError on an unknown name, matching icon().
    """
    if color is None:
        color = current_tokens().text
    source = _source(name).replace("currentColor", color)
    digest = hashlib.sha256(source.encode()).hexdigest()[:8]
    cache_dir = Path(QStandardPaths.writableLocation(QStandardPaths.CacheLocation)) / "glyphs"
    path = cache_dir / f"{name}-{digest}-{size}.png"
    if not path.is_file():
        cache_dir.mkdir(parents=True, exist_ok=True)
        renderer = QSvgRenderer(QByteArray(source.encode()))
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        renderer.render(painter)
        painter.end()
        pixmap.save(str(path), "PNG")
    return f'url("{path.as_posix()}")'
