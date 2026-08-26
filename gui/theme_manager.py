"""Theme Manager - thin wrapper over shared.theme.

Public API (get_theme_manager(), ThemeManager.get_current_theme(), etc.)
is unchanged from before unification — see shared.theme for the actual
token definitions and stylesheet/palette builders.
"""

import logging
from dataclasses import dataclass, replace
from functools import lru_cache
from typing import Mapping, Optional

from PySide6.QtCore import QObject, QSettings, Signal
from PySide6.QtWidgets import QApplication

from shared.theme import ThemeTokens, build_palette, build_stylesheet, get_theme

from .fonts import load_bundled_fonts

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
        return _themed_tokens(self._current_theme_name)

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
        app.setStyleSheet(build_stylesheet(theme) + role_stylesheet(theme))
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


@dataclass(frozen=True)
class TypeStyle:
    """One rung of the type scale: a point size and a default weight."""
    size_pt: int
    bold: bool


# 1.20 modular ratio anchored on a 10pt body: 10 -> 12 -> 14.4 -> 17.28,
# rounded to integers because Qt's QSS parser is unreliable on fractional pt.
# `caption` is 9pt rather than the geometric 8.33pt -- a deliberate legibility
# floor for warehouse-floor use. See the 2026-08-12 design spec.
# `display_xl` (28pt) sits off the ratio on purpose: it is a single-glance
# numeral read across an aisle, not the next rung up. Spec 2026-08-26 §2/C2.
# This dict is the *desk* baseline -- see DENSITY_PROFILES for floor's overrides.
TYPE_SCALE: dict[str, TypeStyle] = {
    "caption": TypeStyle(9, False),   # hints, tips, feedback, dense card labels
    "body": TypeStyle(10, False),     # default text and button labels
    "label": TypeStyle(12, True),     # emphasis, sub-headers, count badges
    "heading": TypeStyle(14, True),   # dialog and section headers
    "display": TypeStyle(17, True),   # stat-card numbers
    "display_xl": TypeStyle(28, True),  # KPI numerals, Packer Mode scan verdict
}


@dataclass(frozen=True)
class DensityProfile:
    """One density profile: how tall a control is, how much air it gets, and
    the two type rungs that move with it.

    Spec 2026-08-26 §2/C3. Colour and radius are deliberately absent -- density
    never touches them.
    """

    control_height: int          # px, the finished height of an interactive control
    row_height: int              # px, table and list row height
    padding_v: int               # px, must equal a shared.theme spacing token
    padding_h: int               # px, must equal a shared.theme spacing token
    type_overrides: Mapping[str, int]  # role -> pt, overriding the TYPE_SCALE baseline

    @property
    def control_content_height(self) -> int:
        """What to put in QSS `min-height:` to land on `control_height`.

        Qt's box model treats min-height as the *content* box -- padding and the
        1px border add on top of it. Emitting `control_height` directly would
        ship a 40px 'desk' control against a spec that says 32.
        """
        return self.control_height - 2 * self.padding_v - 2


# Spec 2026-08-26 §2/C3. Padding values are the shared.theme spacing tokens
# (spacing_xs 4 / spacing_sm 8 / spacing_md 12) written as literals, because
# shared/theme.py is sync-owned by packing-tool and cannot be imported into a
# frozen default here without coupling module import order to it. A test asserts
# they still match.
DENSITY_PROFILES: dict[str, DensityProfile] = {
    "desk": DensityProfile(
        control_height=32, row_height=28, padding_v=4, padding_h=8,
        type_overrides={},
    ),
    "floor": DensityProfile(
        control_height=44, row_height=40, padding_v=8, padding_h=12,
        type_overrides={"body": 12, "caption": 10},
    ),
}

# Per-app default, not a global one: a supervisor at a desk with a mouse. Packing
# Tool defaults to "floor" when it gains a theme manager of its own (8.5/8.9) --
# "a station that has not been told otherwise is a scan station".
DEFAULT_DENSITY = "desk"

_active_density: str = DEFAULT_DENSITY


def get_density() -> str:
    """Name of the active density profile."""
    return _active_density


def get_density_profile() -> DensityProfile:
    """The active density profile."""
    return DENSITY_PROFILES[_active_density]


def set_density(name: str) -> None:
    """Switch the active profile. Pure -- no QSettings, no restyle, no Qt.

    ThemeManager.set_density() is the call site that also persists and repaints.
    This one exists so tests (and any non-Qt caller) can move the flag without
    standing up an application.

    Raises KeyError on an unknown name, matching font_css()'s behaviour on an
    unknown role: a typo must fail during development, not render at some
    default density in a warehouse.
    """
    global _active_density
    if name not in DENSITY_PROFILES:
        raise KeyError(
            f"Unknown density {name!r}; expected one of {tuple(DENSITY_PROFILES)}"
        )
    _active_density = name


def type_style(role: str) -> TypeStyle:
    """The scale rung as the active density renders it.

    TYPE_SCALE is the desk baseline; `floor` overrides `body` and `caption`
    only. That is spec §2/C3's one deliberate exception to Parcker's "density
    changes control height and padding only, never type size" -- at arm's
    length a 10pt body is the failure.

    Raises KeyError on an unknown role.
    """
    style = TYPE_SCALE[role]
    override = get_density_profile().type_overrides.get(role)
    return style if override is None else replace(style, size_pt=override)


def font_css(role: str, bold: bool | None = None) -> str:
    """QSS fragment for f-string stylesheets, e.g. 'font-size: 12pt; font-weight: bold;'.

    Raises KeyError on an unknown role -- a typo must fail during development
    rather than silently render at some default size in production.
    """
    style = type_style(role)
    weight = "bold" if (style.bold if bold is None else bold) else "normal"
    return f"font-size: {style.size_pt}pt; font-weight: {weight};"


def apply_font(target, role: str, bold: bool | None = None) -> None:
    """Apply a scale role to anything exposing .font()/.setFont().

    Covers QWidget, QListWidgetItem and QPainter with one helper. Reads the
    target's existing font so the inherited family survives -- building a bare
    QFont() instead would silently drop it.
    """
    style = type_style(role)
    font = target.font()
    font.setPointSize(style.size_pt)
    font.setBold(style.bold if bold is None else bold)
    target.setFont(font)


BUTTON_ROLES = ("primary", "secondary")


def role_stylesheet(theme: ThemeTokens) -> str:
    """QSS for the button hierarchy, appended after shared.theme's sheet.

    shared/theme.py paints every QPushButton accent-blue and is sync-owned
    by packing-tool, so it cannot be edited here -- these rules layer on in
    this module, the same seam Track 1 used for the font override.

    Deliberately opt-in: a button with no `role` property keeps exactly its
    current appearance. The opposite arrangement (neutral by default, mark
    the primaries) is fewer edits but restyles every button in the app at
    once, and this is a Windows-only app with three tracks of visual change
    not yet verified on Windows.
    """
    hover = theme.button_hover_dark if theme.name == "dark" else theme.button_hover_light
    return f"""
        QPushButton[role="primary"] {{
            background-color: {theme.accent_blue};
            color: white;
            border: 1px solid {theme.accent_blue};
            font-weight: bold;
        }}
        QPushButton[role="primary"]:hover {{ background-color: {hover}; }}
        QPushButton[role="primary"]:pressed {{ background-color: {hover}; }}

        QPushButton[role="secondary"] {{
            background-color: {theme.background_elevated};
            color: {theme.text};
            border: 1px solid {theme.border};
        }}
        QPushButton[role="secondary"]:hover {{ background-color: {theme.hover}; }}
        /* shared/theme.py presses every QPushButton to dark accent-blue, which
           reads as primary for the fraction of a second it is held. */
        QPushButton[role="secondary"]:pressed {{ background-color: {theme.active_background}; }}

        QPushButton[role="primary"]:disabled, QPushButton[role="secondary"]:disabled {{
            background-color: {theme.background};
            color: {theme.text_disabled};
            border: 1px solid {theme.border_subtle};
        }}

        QListWidget#settingsNav {{
            background-color: {theme.background};
            border: none;
            border-right: 1px solid {theme.border_subtle};
            outline: none;
        }}
        QListWidget#settingsNav::item {{
            padding: 6px 10px;
            border-radius: {theme.radius}px;
            /* matches :selected's accent bar so selecting does not shift text */
            border-left: 2px solid transparent;
        }}
        QListWidget#settingsNav::item:hover {{ background-color: {theme.hover}; }}
        QListWidget#settingsNav::item:selected {{
            background-color: {theme.active_background};
            color: {theme.text};
            border-left: 2px solid {theme.accent_blue};
        }}
        QListWidget#settingsNav::item:disabled {{
            color: {theme.text_secondary};
            padding-top: 10px;
        }}
    """


def set_button_role(button, role: str) -> None:
    """Mark a button primary or secondary.

    Qt does not restyle a widget when a dynamic property changes after the
    stylesheet was applied -- the classic trap. Every call site here sets
    the role at construction, where it would not matter, but unpolish/polish
    runs unconditionally so a later live-flipping caller cannot step in it.
    """
    if role not in BUTTON_ROLES:
        raise ValueError(f"Unknown button role {role!r}; expected one of {BUTTON_ROLES}")
    button.setProperty("role", role)
    button.style().unpolish(button)
    button.style().polish(button)
