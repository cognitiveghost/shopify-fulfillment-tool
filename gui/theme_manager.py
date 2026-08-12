"""Theme Manager - thin wrapper over shared.theme.

Public API (get_theme_manager(), ThemeManager.get_current_theme(), etc.)
is unchanged from before unification — see shared.theme for the actual
token definitions and stylesheet/palette builders.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import QObject, QSettings, Signal
from PySide6.QtWidgets import QApplication

from shared.theme import ThemeTokens, build_palette, build_stylesheet, get_theme

logger = logging.getLogger(__name__)


class ThemeManager(QObject):
    """Manages application themes (singleton). See shared.theme for tokens."""

    theme_changed = Signal()
    _instance: Optional["ThemeManager"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        super().__init__()
        self._initialized = True
        self._current_theme_name = "light"
        self._load_theme_preference()
        logger.info(f"ThemeManager initialized with theme: {self._current_theme_name}")

    def get_current_theme(self) -> ThemeTokens:
        return get_theme(self._current_theme_name)

    def is_dark_theme(self) -> bool:
        return self._current_theme_name == "dark"

    def get_current_theme_name(self) -> str:
        return self._current_theme_name

    def toggle_theme(self):
        self.set_theme("dark" if self._current_theme_name == "light" else "light")

    def set_theme(self, theme_name: str):
        if theme_name not in ("light", "dark"):
            logger.warning(f"Unknown theme: {theme_name}, using light theme")
            theme_name = "light"
        if theme_name == self._current_theme_name:
            return
        self._current_theme_name = theme_name
        self._save_theme_preference()
        self.apply_theme()
        self.theme_changed.emit()
        logger.info(f"Theme changed to: {theme_name}")

    def apply_theme(self):
        app = QApplication.instance()
        if app is None:
            logger.warning("QApplication not found, cannot apply theme")
            return
        theme = self.get_current_theme()
        app.setStyleSheet(build_stylesheet(theme))
        app.setPalette(build_palette(theme))
        logger.debug(f"Applied {self._current_theme_name} theme globally")

    def _save_theme_preference(self):
        try:
            settings = QSettings("ShopifyFulfillmentTool", "FulfillmentApp")
            settings.setValue("theme", self._current_theme_name)
            settings.sync()
        except Exception:
            logger.exception("Failed to save theme preference")

    def _load_theme_preference(self):
        try:
            settings = QSettings("ShopifyFulfillmentTool", "FulfillmentApp")
            saved_theme = settings.value("theme", "light")
            self._current_theme_name = saved_theme if saved_theme in ("light", "dark") else "light"
        except Exception:
            logger.exception("Failed to load theme preference")
            self._current_theme_name = "light"


_theme_manager_instance: ThemeManager | None = None


def get_theme_manager() -> ThemeManager:
    global _theme_manager_instance
    if _theme_manager_instance is None:
        _theme_manager_instance = ThemeManager()
    return _theme_manager_instance


@dataclass(frozen=True)
class TypeStyle:
    """One rung of the type scale: a point size and a default weight."""
    size_pt: int
    bold: bool


# 1.20 modular ratio anchored on a 10pt body: 10 -> 12 -> 14.4 -> 17.28,
# rounded to integers because Qt's QSS parser is unreliable on fractional pt.
# `caption` is 9pt rather than the geometric 8.33pt -- a deliberate legibility
# floor for warehouse-floor use. See the 2026-08-12 design spec.
TYPE_SCALE: dict[str, TypeStyle] = {
    "caption": TypeStyle(9, False),   # hints, tips, feedback, dense card labels
    "body": TypeStyle(10, False),     # default text and button labels
    "label": TypeStyle(12, True),     # emphasis, sub-headers, count badges
    "heading": TypeStyle(14, True),   # dialog and section headers
    "display": TypeStyle(17, True),   # stat-card numbers
}


def font_css(role: str, bold: bool | None = None) -> str:
    """QSS fragment for f-string stylesheets, e.g. 'font-size: 12pt; font-weight: bold;'.

    Raises KeyError on an unknown role -- a typo must fail during development
    rather than silently render at some default size in production.
    """
    style = TYPE_SCALE[role]
    weight = "bold" if (style.bold if bold is None else bold) else "normal"
    return f"font-size: {style.size_pt}pt; font-weight: {weight};"


def apply_font(target, role: str, bold: bool | None = None) -> None:
    """Apply a scale role to anything exposing .font()/.setFont().

    Covers QWidget, QListWidgetItem and QPainter with one helper. Reads the
    target's existing font so the inherited family survives -- building a bare
    QFont() instead would silently drop it.
    """
    style = TYPE_SCALE[role]
    font = target.font()
    font.setPointSize(style.size_pt)
    font.setBold(style.bold if bold is None else bold)
    target.setFont(font)
