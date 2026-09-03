"""The bundled Inter faces, registered with Qt on first use.

Windows always ships Segoe UI, so embedding a font buys visual consistency
and dev/prod parity rather than availability. That is exactly why nothing
here raises: a machine that cannot read the bundled TTF falls back to Segoe
UI and keeps working. Contrast shared/icons.py, which fails loudly on an
unknown name -- that is a developer typo caught in seconds, this would be a
production outage.
"""
import logging
from functools import lru_cache
from pathlib import Path

from PySide6.QtGui import QFontDatabase, QGuiApplication

logger = logging.getLogger(__name__)

FONTS_DIR = Path(__file__).resolve().parent / "assets" / "fonts"
FAMILY = "Inter"

# Regular and Bold only -- TYPE_SCALE expresses no other weight. Registering
# a real Bold face matters: without it Qt synthesizes bold by smearing the
# regular outlines, which looks muddy at 9-10pt.
_FONT_FILES = ("Inter-Regular.ttf", "Inter-Bold.ttf")


def load_bundled_fonts() -> str | None:
    """Register the bundled faces and return the family name, or None.

    Idempotent and cached -- ThemeManager.get_current_theme() calls this, and
    that runs on roughly 180 call sites across gui/*.py.

    The pre-QApplication miss is deliberately *not* cached. QFontDatabase
    segfaults rather than raising without a live Qt app, so the guard has to
    come first -- and caching that miss would pin the whole process to the
    fallback font just because something touched the theme early.
    """
    if QGuiApplication.instance() is None:
        return None
    return _register_fonts()


@lru_cache(maxsize=1)
def _register_fonts() -> str | None:
    families: set[str] = set()
    for filename in _FONT_FILES:
        path = FONTS_DIR / filename
        if not path.is_file():
            logger.warning("Bundled font missing, falling back to system font: %s", path)
            return None
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id == -1:
            logger.warning("Qt rejected bundled font, falling back: %s", path)
            return None
        families.update(QFontDatabase.applicationFontFamilies(font_id))
    if FAMILY not in families:
        logger.warning("Bundled fonts registered as %s, expected %s", families, FAMILY)
        return None
    return FAMILY


# The cache lives on the inner function now; keep the public handle tests use.
load_bundled_fonts.cache_clear = _register_fonts.cache_clear
