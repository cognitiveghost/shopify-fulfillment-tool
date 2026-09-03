"""Theme Manager - thin wrapper over shared.theme.

Public API (get_theme_manager(), ThemeManager.get_current_theme(), etc.)
is unchanged from before unification — see shared.theme for the actual
token definitions and stylesheet/palette builders.
"""

import logging
from dataclasses import replace
from functools import lru_cache
from typing import Optional

from PySide6.QtCore import QObject, QSettings, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from shared.fonts import load_bundled_fonts
from shared.theme import (
    BUTTON_ROLES,  # noqa: F401 -- re-exported for existing `from gui.theme_manager import` call sites
    DEFAULT_DENSITY,
    DENSITY_PROFILES,
    TYPE_SCALE,  # noqa: F401
    DensityProfile,  # noqa: F401
    ThemeTokens,
    TypeStyle,  # noqa: F401
    build_palette,
    build_stylesheet,
    font_css,  # noqa: F401
    get_density,
    get_density_profile,
    get_theme,
    set_button_role,
    set_current,
    set_density,
    type_style,
    validate_theme,  # noqa: F401
)

logger = logging.getLogger(__name__)


def apply_dialog_button_roles(box) -> None:
    """Mark a dialog's accept button primary. Everything else keeps the default.

    Since the default role became secondary, only the one button that commits the
    dialog needs marking. AcceptRole is Qt's own answer to "which button is that",
    so a Close-only box correctly comes out with no primary at all.
    """
    from PySide6.QtWidgets import QDialogButtonBox

    for button in box.buttons():
        if box.buttonRole(button) == QDialogButtonBox.ButtonRole.AcceptRole:
            set_button_role(button, "primary")


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
        self._load_density_preference()
        # Seed shared.theme now, not at the first apply_theme(). Shared widgets
        # read current_tokens(), so any of them built before the first apply
        # would paint the unseeded fallback while this manager reports the
        # saved theme. gui_main.py happens to apply first today; that ordering
        # is not something a shared widget should have to rely on.
        set_current(self._current_theme_name)
        logger.info(
            f"ThemeManager initialized with theme: {self._current_theme_name}, "
            f"density: {get_density()}"
        )

    def get_current_theme(self) -> ThemeTokens:
        return _themed_tokens(self._current_theme_name)

    def is_dark_theme(self) -> bool:
        return self._current_theme_name == "dark"

    def get_current_theme_name(self) -> str:
        return self._current_theme_name

    @property
    def density(self) -> str:
        """Name of the active density profile ("desk" or "floor")."""
        return get_density()

    def set_density(self, name: str) -> None:
        """Switch density, persist it, and repaint.

        Raises KeyError on an unknown name -- the module-level set_density()
        validates before anything is persisted, so a bad name leaves both the
        flag and QSettings untouched.
        """
        if name == get_density():
            return
        # module-level set_density(), not this method: methods are not in
        # lexical scope inside a method body.
        set_density(name)
        self._save_density_preference()
        self.apply_theme()
        self.theme_changed.emit()
        logger.info(f"Density changed to: {name}")

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
        app.setStyleSheet(
            build_stylesheet(theme) + role_stylesheet(theme) + density_stylesheet()
        )
        app.setPalette(build_palette(theme))
        logger.debug(f"Applied {self._current_theme_name} theme globally")
        # shared.theme is the single record of which theme is live; this is
        # what makes shared widgets (NavRail) repaint on a toggle.
        set_current(self.get_current_theme_name())

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

    def _save_density_preference(self):
        try:
            settings = QSettings("ShopifyFulfillmentTool", "FulfillmentApp")
            settings.setValue("density", get_density())
            settings.sync()
        except Exception:
            logger.exception("Failed to save density preference")

    def _load_density_preference(self):
        try:
            settings = QSettings("ShopifyFulfillmentTool", "FulfillmentApp")
            saved = settings.value("density", DEFAULT_DENSITY)
            set_density(saved if saved in DENSITY_PROFILES else DEFAULT_DENSITY)
        except Exception:
            logger.exception("Failed to load density preference")
            set_density(DEFAULT_DENSITY)


_theme_manager_instance: ThemeManager | None = None


def get_theme_manager() -> ThemeManager:
    global _theme_manager_instance
    if _theme_manager_instance is None:
        _theme_manager_instance = ThemeManager()
    return _theme_manager_instance


def _themed_tokens(theme_name: str) -> ThemeTokens:
    """shared.theme's tokens with the bundled font family layered on top.

    shared/theme.py is sync-owned by packing-tool and must not be hand-edited,
    so the override happens here -- dataclasses.replace() on the frozen
    ThemeTokens it hands back. Memoized because get_current_theme() runs on
    roughly 180 call sites and replace() allocates.

    Only the success path is memoized. load_bundled_fonts() returns None
    before a QApplication exists, and caching that would leave the app on the
    fallback font for the rest of the process over one early call.
    """
    family = load_bundled_fonts()
    if family is None:
        return get_theme(theme_name)
    return _tokens_with_font(theme_name, family)


@lru_cache(maxsize=2)
def _tokens_with_font(theme_name: str, family: str) -> ThemeTokens:
    theme = get_theme(theme_name)
    return replace(theme, font_family=f"'{family}', {theme.font_family}")


_themed_tokens.cache_clear = _tokens_with_font.cache_clear


def apply_font(target, role: str, bold: bool | None = None, tabular: bool = False) -> None:
    """Apply a scale role to anything exposing .font()/.setFont().

    Covers QWidget, QListWidgetItem and QPainter with one helper. Reads the
    target's existing font so the inherited family survives -- building a bare
    QFont() instead would silently drop it.

    `tabular` turns on the `tnum` OpenType feature for numeral columns, so
    quantities and stock align down the column. Spec S2/C2 asked for this as a
    QSS helper, but Qt has no `font-variant-numeric` property -- it warns
    "Unknown property" and does nothing -- so it has to come from the feature
    tag, which needs Qt 6.7+. It is not cosmetic: bundled Inter ships
    proportional numerals, so at 20pt "1" advances 10.97px against "0" at
    17.03px.

    Not usable to pin a rung on the six _DENSITY_CONTROLS types: the app sheet
    emits `font-size` for those, and the app sheet outranks a widget font on the
    next re-polish, so the rung is lost the moment the theme or density changes.
    Give those a widget-level stylesheet with font_css() instead -- a widget
    sheet does outrank the app sheet.
    """
    style = type_style(role)
    font = target.font()
    font.setPointSize(style.size_pt)
    font.setBold(style.bold if bold is None else bold)
    # unset, not setFeature(..., 0): the font is read back off the target, so a
    # tnum left over from an earlier call would otherwise be sticky, and
    # setting it to 0 still counts as set.
    if tabular:
        font.setFeature(QFont.Tag("tnum"), 1)
    else:
        font.unsetFeature(QFont.Tag("tnum"))
    target.setFont(font)


def role_stylesheet(theme: ThemeTokens) -> str:
    """QSS this app layers on after shared.theme's sheet.

    The button hierarchy used to live here because shared/theme.py is
    sync-owned by packing-tool and could not be edited from this repo. 8.5
    moved it into shared/theme.py's build_stylesheet -- authored in
    packing-tool, pulled here by scripts/sync_shared.py -- so both apps read
    one definition. What is left is genuinely shopify-only chrome.
    """
    return f"""
        QListWidget#settingsNav {{
            background-color: {theme.surface};
            border: none;
            border-right: 1px solid {theme.border_subtle};
            outline: none;
        }}
        QListWidget#settingsNav::item {{
            padding: 6px 10px;
            border-radius: {theme.radius}px;
            /* The generic QListWidget::item:selected ring is a `border`
               shorthand, so it wins on all four sides unless this rule
               restates them. This nav marks position, not data selection:
               the bar is left-only, and transparent here so selecting does
               not shift the text. */
            border: 2px solid transparent;
            border-left: 2px solid transparent;
        }}
        QListWidget#settingsNav::item:hover {{ background-color: {theme.hover}; }}
        QListWidget#settingsNav::item:selected {{
            background-color: {theme.selection_bg};
            color: {theme.text};
            border: 2px solid transparent;
            border-left: 2px solid {theme.accent_fill};
        }}
        QListWidget#settingsNav::item:disabled {{
            color: {theme.text_secondary};
            padding-top: 10px;
        }}
    """


# The interactive controls whose finished height the density profile owns.
# Deliberately excludes QLabel and the item views: labels and table rows keep
# their current sizing until 8.3 routes them through the scale, so that an
# unverified visual change across the whole Windows app does not ride in the
# same commit as the mechanism. Table rows read profile.row_height directly
# -- Qt sets those through setDefaultSectionSize(), not through QSS.
_DENSITY_CONTROLS = (
    "QPushButton",
    "QComboBox",
    "QLineEdit",
    "QSpinBox",
    "QDoubleSpinBox",
    "QDateEdit",
)


def density_stylesheet() -> str:
    """QSS for the active density profile's box metrics.

    Appended after shared.theme's sheet, so it outranks the equal-specificity
    `padding: 6px 12px; font-size: 10pt` that shared/theme.py sets on
    QPushButton. shared/theme.py is sync-owned by packing-tool -- change it
    there and re-run scripts/sync_shared.py, never here.

    Emits size but never weight: build_stylesheet's QPushButton[role="primary"]
    rule is an attribute selector and outranks this one anyway, but emitting a
    weight here would still fight it for every other control.
    """
    profile = get_density_profile()
    selector = ", ".join(_DENSITY_CONTROLS)
    return f"""
        {selector} {{
            min-height: {profile.control_content_height}px;
            padding: {profile.padding_v}px {profile.padding_h}px;
            font-size: {type_style('body').size_pt}pt;
        }}
    """
