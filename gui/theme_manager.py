"""Theme Manager - thin wrapper over shared.theme.

Public API (get_theme_manager(), ThemeManager.get_current_theme(), etc.)
is unchanged from before unification — see shared.theme for the actual
token definitions and stylesheet/palette builders.
"""

import logging
from collections.abc import Mapping
from dataclasses import dataclass, replace
from functools import lru_cache
from types import MappingProxyType
from typing import Optional

from PySide6.QtCore import QObject, QSettings, Signal
from PySide6.QtGui import QFont
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
        self._load_density_preference()
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

        This lands QPushButton, QComboBox and QLineEdit on `control_height`
        exactly. The QAbstractSpinBox family (QSpinBox, QDoubleSpinBox,
        QDateEdit) comes out 3px taller: its sizeHint() adds room for the
        up/down buttons *after* the rule is applied, and min-height is a floor,
        so it never binds. max-height does not clamp it either (measured, Qt
        6.11.1/Fusion). It is not a font problem -- the offset is a flat 3px in
        both profiles, against a content box with 6px of slack over the text.
        # ponytail: spin boxes run control_height + 3. Upgrade path is an
        # explicit setFixedHeight() when 8.3 routes widgets through the scale --
        # not a hardcoded -3 here, which is measured on Linux/Fusion and would
        # make Windows *shorter* than the rest if its offset differs.
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
        type_overrides=MappingProxyType({}),
    ),
    "floor": DensityProfile(
        control_height=44, row_height=40, padding_v=8, padding_h=12,
        type_overrides=MappingProxyType({"body": 12, "caption": 10}),
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
    return f"""
        QPushButton[role="primary"] {{
            background-color: {theme.accent_blue};
            color: {theme.on_accent};
            border: 1px solid {theme.accent_blue};
            font-weight: bold;
        }}
        QPushButton[role="primary"]:hover {{ background-color: {theme.accent_fill_hover}; }}
        QPushButton[role="primary"]:pressed {{ background-color: {theme.accent_fill_active}; }}

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

    Appended after shared.theme's sheet and role_stylesheet, so it outranks the
    equal-specificity `padding: 6px 12px; font-size: 10pt` that shared/theme.py
    sets on QPushButton. shared/theme.py is sync-owned by packing-tool and
    cannot be edited here -- this is the same layering seam the font override
    and the button hierarchy already use.

    Emits size but never weight: role_stylesheet's QPushButton[role="primary"]
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
