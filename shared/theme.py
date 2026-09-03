"""Shared theme system for Packing Tool and Shopify Fulfillment Tool.

Canonical source — see
docs/superpowers/specs/2026-07-26-unified-ui-design-system-design.md.
Never hand-edit shopify-fulfillment-tool/shared/theme.py; run
shopify-fulfillment-tool/scripts/sync_shared.py after changing this file.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from functools import lru_cache
from types import MappingProxyType

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QLabel, QWidget

THEME_DARK = "dark"
THEME_LIGHT = "light"


@dataclass(frozen=True)
class ThemeTokens:
    """Color/spacing/font tokens for one theme (light or dark).

    Color field names are kept identical to shopify-fulfillment-tool's
    pre-unification `ThemeColors` dataclass on purpose — ~180 call sites
    across gui/*.py read these by exact attribute name (e.g.
    `theme.text_secondary`, `theme.accent_blue`) and renaming them would
    mean touching every one of those call sites for no functional gain.

    Phase 8.2 therefore adds the design-system vocabulary alongside the old
    names rather than replacing them: `background`, `background_elevated`,
    `accent_*`, `active_*` are now aliases carrying the same literal as
    their canonical token (see `_ALIAS_PAIRS`). `validate_theme` asserts
    the pairs stay equal, so the duplication cannot drift.

    No color field carries a default. The light-mode WCAG failure this
    phase repairs was caused by `accent_*` being defaults that neither
    theme overrode, so both themes rendered identical status colors on
    opposite backgrounds. Every color is spelled out per theme; only the
    theme-independent `spacing_*` / `radius_*` / `font_*` scales default.
    """
    name: str

    # --- Surfaces: a four-step elevation scale (spec 2/C1) ---
    # surface_sunken is the app frame, nav rail and gutters: regions separate
    # by elevation, so a border is reserved for inputs and the focused control.
    surface_sunken: str
    surface: str
    surface_raised: str
    surface_overlay: str

    # --- Text (spec 3.2) ---
    text: str
    text_secondary: str
    text_disabled: str
    text_placeholder: str

    # --- Borders: the missing middle (spec 3.3) ---
    border: str
    border_subtle: str
    border_strong: str

    # --- Status roles, foreground + tint (spec 3.4) ---
    status_info: str
    status_info_bg: str
    status_success: str
    status_success_bg: str
    status_warning: str
    status_warning_bg: str
    status_danger: str
    status_danger_bg: str

    # --- Solid accent fill; on_accent is the text that sits on it (spec 3.4a) ---
    # hover and active are theme-independent: a button fill sits on itself,
    # not on a surface, so it needs no per-theme value (spec 2/C4).
    accent_fill: str
    accent_fill_hover: str
    accent_fill_active: str
    on_accent: str

    # --- Selection and focus (spec 3.5) ---
    selection_border: str
    selection_bg: str
    focus_ring: str

    # --- Unchanged interaction colors ---
    hover: str
    button_hover_light: str
    button_hover_dark: str

    # --- Aliases: same literal as the canonical token, see _ALIAS_PAIRS ---
    background: str
    background_elevated: str
    accent_blue: str
    accent_green: str
    accent_orange: str
    accent_red: str
    active_background: str
    active_border: str

    # --- Theme-independent scales ---
    radius: int = 4
    radius_sm: int = 3
    radius_md: int = 6
    radius_lg: int = 10
    spacing_xs: int = 4
    spacing_sm: int = 8
    spacing_md: int = 12
    spacing_lg: int = 16
    spacing_xl: int = 24
    spacing_2xl: int = 32
    font_family: str = "Segoe UI, sans-serif"
    font_family_mono: str = "Consolas, monospace"


LIGHT_THEME = ThemeTokens(
    name="light",
    surface_sunken="#DADADF",
    surface="#FFFFFF",
    surface_raised="#F2F2F4",
    surface_overlay="#E6E6EA",
    text="#1A1A1A",
    text_secondary="#50505A",
    text_disabled="#6B6B73",
    text_placeholder="#5C5C64",
    border="#70707A",
    border_subtle="#C6C6CC",
    border_strong="#1A1A1A",
    status_info="#005B99",
    status_info_bg="#DCEBFA",
    status_success="#2C6630",
    status_success_bg="#E2F0E3",
    status_warning="#7A4A00",
    status_warning_bg="#F8EBD8",
    status_danger="#B31308",
    status_danger_bg="#FADFDD",
    accent_fill="#006FBA",
    accent_fill_hover="#005F9F",
    accent_fill_active="#004B80",
    on_accent="#FFFFFF",
    selection_border="#005B99",
    selection_bg="#DCEBFA",
    focus_ring="#005B99",
    hover="#E6E6EA",
    button_hover_light="#004B80",
    button_hover_dark="#004B80",
    # aliases
    background="#FFFFFF",
    background_elevated="#F2F2F4",
    accent_blue="#006FBA",
    accent_green="#2C6630",
    accent_orange="#7A4A00",
    accent_red="#B31308",
    active_background="#DCEBFA",
    active_border="#005B99",
)

DARK_THEME = ThemeTokens(
    name="dark",
    surface_sunken="#08080B",
    surface="#101014",
    surface_raised="#17171A",
    surface_overlay="#232327",
    text="#F2F2F2",
    text_secondary="#B0B0B0",
    text_disabled="#787878",
    text_placeholder="#949494",
    border="#787878",
    border_subtle="#2E2E2E",
    border_strong="#F2F2F2",
    status_info="#29A0F0",
    status_info_bg="#042134",
    status_success="#4CAF50",
    status_success_bg="#112712",
    status_warning="#FF9800",
    status_warning_bg="#342104",
    status_danger="#FF6659",
    status_danger_bg="#340704",
    accent_fill="#006FBA",
    accent_fill_hover="#005F9F",
    accent_fill_active="#004B80",
    on_accent="#FFFFFF",
    selection_border="#29A0F0",
    selection_bg="#042134",
    focus_ring="#4DA9E8",
    hover="#232327",
    button_hover_light="#004B80",
    button_hover_dark="#004B80",
    # aliases
    background="#101014",
    background_elevated="#17171A",
    accent_blue="#006FBA",
    accent_green="#4CAF50",
    accent_orange="#FF9800",
    accent_red="#FF6659",
    active_background="#042134",
    active_border="#29A0F0",
)

THEMES: dict = {"light": LIGHT_THEME, "dark": DARK_THEME}


def get_theme(name: str | None) -> ThemeTokens:
    """Look up a theme by name, falling back to light for an unknown name."""
    return THEMES.get(name, LIGHT_THEME)


# --- The live theme, and the one place a change is announced ---------------


class _ThemeNotifier(QObject):
    """Signal source for theme changes.

    An instance, not a class each app subclasses: two subclasses would be two
    independent signals, and a shared widget connected to one would never hear
    the other app's toggle.
    """

    changed = Signal(str)


theme_notifier = _ThemeNotifier()

# None until an app applies a theme. Each app's apply_theme() is the only
# writer; nothing here reads QSettings, because the organisation name differs
# per app ("PackingTool" vs the shopify one) and shared/ must not know it.
_current: str | None = None


def current_theme_name() -> str | None:
    """The applied theme's name, or None if no app has applied one yet."""
    return _current


def set_current(name: str) -> None:
    """Record the applied theme and announce the change.

    Call this *last* in an app's apply path, after the stylesheet and palette
    are on the QApplication: a listener that restyles itself must not run
    while the app sheet is still the old one.
    """
    global _current
    if name == _current:
        return                      # re-applying the same theme is not a change
    _current = name
    theme_notifier.changed.emit(name)


def current_tokens() -> ThemeTokens:
    """Tokens for the live theme, without any app's bundled font family.

    Shared widgets read colours from here and never font_family: the family
    arrives through the QApplication stylesheet each app builds from its own
    font-layered tokens. A widget sheet restating it would pin the fallback
    family on the one widget that did.

    Before any app has applied a theme this falls back exactly as get_theme()
    does. It is deliberately not a second, different default: an app that
    forgets to seed _current should render one app's wrong theme, not two.
    """
    return get_theme(_current)


def on_theme_changed(widget, apply) -> None:
    """Run `apply(tokens)` now, and again whenever the rendering inputs change.

    A widget that styles itself with an interpolated string --
    `setStyleSheet(f"color: {tokens.text}")` -- bakes that hex in at build time
    and keeps it forever. Qt re-polishes the tree on an application stylesheet
    change, but re-polishing re-applies the same stale literal, so the fix is
    to re-run the recipe rather than to re-polish. See ADR 0003, which records
    the measurement.

    The connection is dropped when `widget` is destroyed. Without that, a
    closure holding a freed QWidget is called on the next toggle and Qt raises
    "Internal C++ object already deleted".
    """
    apply(current_tokens())

    def _reapply(_name: str) -> None:
        apply(current_tokens())

    theme_notifier.changed.connect(_reapply)
    widget.destroyed.connect(lambda *_: theme_notifier.changed.disconnect(_reapply))


@lru_cache(maxsize=2)
def _tokens_with_font(theme_name: str, family: str) -> "ThemeTokens":
    theme = get_theme(theme_name)
    return replace(theme, font_family=f"'{family}', {theme.font_family}")


def themed_tokens(theme_name: str, family: str | None) -> "ThemeTokens":
    """Tokens with an app's bundled family layered on, when there is one.

    Memoised because current_tokens() runs twice per table row on the scan
    path and replace() re-runs __init__ over all 50 fields every call.

    Only the success path is memoised: an app's font loader returns None
    before a QApplication exists, and caching that would leave the app on the
    fallback font for the rest of the process over one early call.
    """
    if family is None:
        return get_theme(theme_name)
    return _tokens_with_font(theme_name, family)


themed_tokens.cache_clear = _tokens_with_font.cache_clear


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


# Spec 2026-08-26 §2/C3. Padding values are the spacing tokens (spacing_xs 4 /
# spacing_sm 8 / spacing_md 12) written as literals rather than read off a
# ThemeTokens instance: these profiles are frozen module constants and the
# tokens are per-theme. tests/test_type_scale.py asserts they still match.
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


_HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")

_COLOR_FIELDS = (
    # canonical
    "surface_sunken", "surface", "surface_raised", "surface_overlay",
    "text", "text_secondary", "text_disabled", "text_placeholder",
    "border", "border_subtle", "border_strong",
    "status_info", "status_info_bg",
    "status_success", "status_success_bg",
    "status_warning", "status_warning_bg",
    "status_danger", "status_danger_bg",
    "accent_fill", "accent_fill_hover", "accent_fill_active", "on_accent",
    "selection_border", "selection_bg", "focus_ring",
    "hover", "button_hover_light", "button_hover_dark",
    # aliases
    "background", "background_elevated",
    "accent_blue", "accent_green", "accent_orange", "accent_red",
    "active_background", "active_border",
)

# Derived from _COLOR_FIELDS rather than listed again, so registering a token
# is the only step: a new plane or fill joins the validate_theme matrices
# automatically. Proving on_accent against accent_fill alone is how #2D9FE8
# shipped at 2.90:1 (spec 2/C4), and a second registration site to forget is
# how that happens again.
_SURFACE_PLANES = tuple(f for f in _COLOR_FIELDS if f.startswith("surface"))
_ACCENT_FILLS = tuple(f for f in _COLOR_FIELDS if f.startswith("accent_fill"))

# Legacy name -> canonical token. Each pair carries the same literal in both
# theme constructors; validate_theme asserts they stay equal so the
# duplication cannot drift. Aliases are real dataclass fields, not
# properties: a property would sit outside _COLOR_FIELDS and escape
# validation entirely.
_ALIAS_PAIRS = (
    ("background", "surface"),
    ("background_elevated", "surface_raised"),
    ("accent_blue", "accent_fill"),
    ("accent_green", "status_success"),
    ("accent_orange", "status_warning"),
    ("accent_red", "status_danger"),
    ("active_background", "selection_bg"),
    ("active_border", "selection_border"),
    ("button_hover_light", "accent_fill_active"),
    ("button_hover_dark", "accent_fill_active"),
)


# token -> minimum contrast ratio against every plane in _SURFACE_PLANES.
# Text floors are AAA for body and AA for secondary; 3.0 is WCAG's non-text
# minimum, applied to disabled text as well because a warehouse operator who
# cannot read a disabled control files a support ticket.
# Deliberately mirrored by a parametrized test in packing-tool's
# tests/test_theme.py: the copy there is what catches someone *weakening* a
# floor here. Keep both in step when adding a token.
_MIN_CONTRAST_ON_PLANES = {
    "text": 7.0,
    "text_secondary": 4.5,
    "text_disabled": 3.0,
    "text_placeholder": 4.5,
    "border": 3.0,
    "focus_ring": 3.0,
    "selection_border": 3.0,
    "status_info": 4.5,
    "status_success": 4.5,
    "status_warning": 4.5,
    "status_danger": 4.5,
}

_STATUS_ROLES = ("info", "success", "warning", "danger")

# Foregrounds that can land on a selected row. Selection is selection_bg with
# a selection_border ring, so the selected row is a fifth plane -- it is just
# not a `surface_*` one, which is exactly why it escaped _SURFACE_PLANES.
_SELECTION_FOREGROUNDS = (
    "text", "text_secondary",
    "status_info", "status_success", "status_warning", "status_danger",
)

# Non-text marks drawn on a selected row: the ring itself, and `border`, which
# PackingProgressDelegate uses for the progress track. 3:1 is the WCAG floor
# for non-text; `border` measures ~3.2:1 on selection_bg and cannot join the
# 4.5 tuple above.
_SELECTION_NON_TEXT = ("selection_border", "border")


def validate_theme(theme: ThemeTokens) -> None:
    """Raise ValueError if a theme violates the design-system contract.

    Checks three things: every color field is a valid #RRGGBB string, every
    alias still equals its canonical token, and every foreground clears its
    WCAG minimum on all four surface planes -- not just on the window
    background -- while on_accent clears AA against all three accent fills.
    The two matrices are the point: light mode shipped three status colors
    below AA for months, and dark's hover fill shipped at 2.90:1, because
    each was measured against exactly one partner.

    See docs/superpowers/specs/2026-08-26-phase8-unified-design-system.md
    sections 2/C1, 2/C4 and 7 in shopify-fulfillment-tool for the
    acceptance criteria.
    """
    for field_name in _COLOR_FIELDS:
        value = getattr(theme, field_name)
        if not _HEX_RE.match(value):
            raise ValueError(
                f"{theme.name}.{field_name} = {value!r} is not a valid #RRGGBB color"
            )

    for alias, canonical in _ALIAS_PAIRS:
        if getattr(theme, alias) != getattr(theme, canonical):
            raise ValueError(
                f"{theme.name}.{alias} = {getattr(theme, alias)!r} has drifted "
                f"from its canonical token {canonical} = "
                f"{getattr(theme, canonical)!r}"
            )

    for token in _SELECTION_FOREGROUNDS:
        ratio = contrast_ratio(getattr(theme, token), theme.selection_bg)
        if ratio < 4.5:
            raise ValueError(
                f"{theme.name}.{token} has {ratio:.2f}:1 contrast against "
                f"selection_bg, below the 4.5:1 minimum"
            )

    for token in _SELECTION_NON_TEXT:
        ratio = contrast_ratio(getattr(theme, token), theme.selection_bg)
        if ratio < 3.0:
            raise ValueError(
                f"{theme.name}.{token} has {ratio:.2f}:1 contrast against "
                f"selection_bg, below the 3.0:1 minimum"
            )

    for token, floor in _MIN_CONTRAST_ON_PLANES.items():
        value = getattr(theme, token)
        for plane in _SURFACE_PLANES:
            ratio = contrast_ratio(value, getattr(theme, plane))
            if ratio < floor:
                raise ValueError(
                    f"{theme.name}.{token} has {ratio:.2f}:1 contrast against "
                    f"{plane}, below the {floor}:1 minimum"
                )

    for role in _STATUS_ROLES:
        fg, tint = f"status_{role}", f"status_{role}_bg"
        ratio = contrast_ratio(getattr(theme, fg), getattr(theme, tint))
        if ratio < 4.5:
            raise ValueError(
                f"{theme.name}.{fg} has {ratio:.2f}:1 contrast against its own "
                f"tint {tint}, below the 4.5:1 minimum"
            )

    for fill in _ACCENT_FILLS:
        ratio = contrast_ratio(theme.on_accent, getattr(theme, fill))
        if ratio < 4.5:
            raise ValueError(
                f"{theme.name}.on_accent has {ratio:.2f}:1 contrast against "
                f"{fill}, below the 4.5:1 minimum"
            )


def _relative_luminance(hex_color: str) -> float:
    """WCAG 2.1 relative luminance of an #RRGGBB color."""
    raw = hex_color.lstrip("#")
    channels = [int(raw[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [
        c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
        for c in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast_ratio(fg: str, bg: str) -> float:
    """WCAG 2.1 contrast ratio between two #RRGGBB colors, 1.0 to 21.0.

    Symmetric in its arguments -- the names are for the caller's benefit.
    """
    lighter, darker = sorted(
        (_relative_luminance(fg), _relative_luminance(bg)), reverse=True
    )
    return (lighter + 0.05) / (darker + 0.05)


def clamp_geometry(
    x: int, y: int, w: int, h: int,
    avail_x: int, avail_y: int, avail_w: int, avail_h: int,
) -> tuple:
    """Clamp a saved window rect to fit inside the available screen rect.

    Shrinks w/h to fit if larger than the screen, then clamps x/y so the
    whole window is on-screen. Pure function — no Qt dependency — so a
    saved-on-a-different-monitor geometry can never restore off-screen.
    """
    w = min(w, avail_w)
    h = min(h, avail_h)
    x = max(avail_x, min(x, avail_x + avail_w - w))
    y = max(avail_y, min(y, avail_y + avail_h - h))
    return (x, y, w, h)


class StatusDot(QWidget):
    """Small colored circle for status indicators in tables/lists.

    Takes a *token field name* plus the tokens to resolve it against -- never a
    hex string. Constructing it with a colour is what let the palette escape
    the theme; a name is checked by getattr, so a typo raises here rather than
    rendering the wrong colour in production.

    `role` is any ThemeTokens colour field, not only the four status roles:
    packing-tool's STATUS_CONFIG maps "not_started" to text_secondary.

    `theme` is explicit because shared/ cannot know which theme is live -- that
    answer lives in each app (packing-tool's gui.theme.current_tokens(),
    shopify's get_theme_manager()), and shared/ must not import either.
    """

    def __init__(self, role: str, theme: ThemeTokens, diameter: int = 10, parent=None):
        super().__init__(parent)
        self._color = QColor(getattr(theme, role))
        self._diameter = diameter
        self.setFixedSize(diameter, diameter)

    def color(self) -> QColor:
        return self._color

    def set_role(self, role: str, theme: ThemeTokens) -> None:
        self._color = QColor(getattr(theme, role))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(self._color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(0, 0, self._diameter, self._diameter)


CHIP_VARIANTS = ("chip", "edge")


class StatusChip(QLabel):
    """A read-only status badge: a role name, a label, and the live tokens.

    Two variants. `chip` is a pill filled with the role's own tint and
    outlined in the role's own foreground. The fill alone cannot be trusted
    to carry the pill's shape: status_info_bg is identical to selection_bg in
    dark, and a role with no `<role>_bg` partner (text_secondary, for the
    "Not Started" row) falls back to surface_sunken at 1.05:1 on surface.
    The outline is validated everywhere the fill is not -- validate_theme
    proves every status_* on all four planes and on selection_bg. `edge` is a
    row/lane marker: a coloured left border on a transparent ground.

    That fallback is the one place a missing token is tolerated rather than
    raised -- the role itself is still resolved with getattr, so a typo in the
    role name still fails loudly.

    This is deliberately not the filter chip: a filter chip is interactive and
    dismissible. Merging them would mean one widget with a `clickable` flag.
    """

    def __init__(
        self,
        role: str,
        text: str,
        theme: ThemeTokens,
        variant: str = "chip",
        parent=None,
    ) -> None:
        super().__init__(parent)
        if variant not in CHIP_VARIANTS:
            raise ValueError(
                f"Unknown chip variant {variant!r}; expected one of {CHIP_VARIANTS}"
            )
        self._variant = variant
        self.set_status(role, text, theme)

    def set_status(self, role: str, text: str, theme: ThemeTokens) -> None:
        fg = getattr(theme, role)
        self.setText(text)
        if self._variant == "edge":
            self.setStyleSheet(
                f"background-color: transparent; color: {theme.text}; "
                f"border-left: 3px solid {fg}; padding: 2px 8px;"
            )
            return
        tint = getattr(theme, f"{role}_bg", theme.surface_sunken)
        self.setStyleSheet(
            f"background-color: {tint}; color: {fg}; "
            f"border: 1px solid {fg}; border-radius: {theme.radius}px; "
            f"padding: 2px 8px;"
        )


def save_window_geometry(window, settings, key: str = "window_geometry") -> None:
    """Save a QMainWindow/QWidget's geometry to QSettings."""
    settings.setValue(key, window.saveGeometry())


def restore_window_geometry(window, settings, key: str = "window_geometry") -> bool:
    """Restore previously-saved geometry, clamped to the available screen.

    Returns True if geometry was restored, False if there was nothing saved
    (caller should fall back to its own default size in that case).
    """
    from PySide6.QtGui import QGuiApplication

    raw = settings.value(key)
    if raw is None:
        return False
    if not window.restoreGeometry(raw):
        return False

    screen = window.screen() or QGuiApplication.primaryScreen()
    avail = screen.availableGeometry()
    geo = window.geometry()
    x, y, w, h = clamp_geometry(
        geo.x(), geo.y(), geo.width(), geo.height(),
        avail.x(), avail.y(), avail.width(), avail.height(),
    )
    window.setGeometry(x, y, w, h)
    return True


# A QPushButton with no `role` property is secondary. Primary is opt-in via
# set_button_role -- see build_stylesheet's bare QPushButton rule.
BUTTON_ROLES = ("primary", "secondary", "ghost", "danger")


def set_button_role(button, role: str) -> None:
    """Mark a button primary / secondary / ghost / danger.

    Qt does not restyle a widget when a dynamic property changes after the
    stylesheet was applied -- the classic trap. Call sites set the role at
    construction, where it would not matter, but unpolish/polish runs
    unconditionally so a later live-flipping caller cannot step in it.
    """
    if role not in BUTTON_ROLES:
        raise ValueError(f"Unknown button role {role!r}; expected one of {BUTTON_ROLES}")
    button.setProperty("role", role)
    button.style().unpolish(button)
    button.style().polish(button)


def build_stylesheet(theme: ThemeTokens) -> str:
    """Build the global Qt stylesheet (QSS) for one theme."""
    r = theme.radius
    return f"""
        QWidget {{
            background-color: {theme.surface};
            color: {theme.text};
            font-family: {theme.font_family};
        }}

        /* The default is secondary. A button is primary only where a screen or
           dialog says so -- see set_button_role. Before 2026-08-29 this rule was
           the [role="primary"] rule minus font-weight, which made every one of
           the ~103 unmarked buttons across both apps render as the screen's
           primary action. */
        QPushButton {{
            background-color: {theme.surface_raised};
            color: {theme.text};
            border: 1px solid {theme.border};
            border-radius: {r}px;
            padding: 6px 12px;
            font-size: 10pt;
        }}
        QPushButton:hover {{ background-color: {theme.hover}; }}
        QPushButton:pressed {{ background-color: {theme.selection_bg}; }}
        QPushButton:disabled {{
            background-color: {theme.surface};
            color: {theme.text_disabled};
            border: 1px solid {theme.border_subtle};
        }}

        QPushButton[role="primary"] {{
            background-color: {theme.accent_fill};
            color: {theme.on_accent};
            border: 1px solid {theme.accent_fill};
            font-weight: bold;
        }}
        QPushButton[role="primary"]:hover {{ background-color: {theme.accent_fill_hover}; }}
        QPushButton[role="primary"]:pressed {{ background-color: {theme.accent_fill_active}; }}

        QPushButton[role="secondary"] {{
            background-color: {theme.surface_raised};
            color: {theme.text};
            border: 1px solid {theme.border};
        }}
        QPushButton[role="secondary"]:hover {{ background-color: {theme.hover}; }}
        QPushButton[role="secondary"]:pressed {{ background-color: {theme.selection_bg}; }}

        QPushButton[role="ghost"] {{
            background-color: transparent;
            color: {theme.text};
            border: none;
        }}
        QPushButton[role="ghost"]:hover {{ background-color: {theme.hover}; }}
        QPushButton[role="ghost"]:pressed {{ background-color: {theme.selection_bg}; }}

        /* danger is an outline, not a fill: a destructive action must be findable
           without competing with the screen's one primary. */
        QPushButton[role="danger"] {{
            background-color: transparent;
            color: {theme.status_danger};
            border: 1px solid {theme.status_danger};
        }}
        QPushButton[role="danger"]:hover {{ background-color: {theme.status_danger_bg}; }}
        QPushButton[role="danger"]:pressed {{ background-color: {theme.status_danger_bg}; }}

        QPushButton[role="primary"]:disabled,
        QPushButton[role="secondary"]:disabled,
        QPushButton[role="ghost"]:disabled,
        QPushButton[role="danger"]:disabled {{
            background-color: {theme.surface};
            color: {theme.text_disabled};
            border: 1px solid {theme.border_subtle};
        }}

        QLineEdit, QTextEdit, QPlainTextEdit {{
            background-color: {theme.surface_raised};
            color: {theme.text};
            border: 1px solid {theme.border};
            border-radius: {r}px;
            padding: 4px 8px;
        }}
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
            border: 2px solid {theme.accent_fill};
        }}
        QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled {{
            background-color: {theme.surface};
            color: {theme.text_disabled};
            border-color: {theme.border_subtle};
        }}

        QComboBox {{
            background-color: {theme.surface_raised};
            color: {theme.text};
            border: 1px solid {theme.border};
            border-radius: {r}px;
            padding: 4px 8px;
        }}
        QComboBox:hover {{ border: 1px solid {theme.accent_fill}; }}
        QComboBox::drop-down {{ border: none; }}
        QComboBox QAbstractItemView {{
            background-color: {theme.surface_raised};
            color: {theme.text};
            selection-background-color: {theme.accent_fill};
            selection-color: {theme.on_accent};
        }}

        QSpinBox, QDoubleSpinBox, QDateEdit {{
            background-color: {theme.surface_raised};
            color: {theme.text};
            border: 1px solid {theme.border};
            border-radius: {r}px;
            padding: 4px 8px;
        }}

        QCheckBox, QRadioButton {{
            color: {theme.text};
            spacing: {theme.spacing_sm}px;
            background-color: transparent;
        }}
        QCheckBox::indicator, QRadioButton::indicator {{
            width: 18px; height: 18px;
            border: 2px solid {theme.border};
            border-radius: {r}px;
            background-color: {theme.surface};
        }}
        QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
            border: 2px solid {theme.accent_fill};
        }}
        QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
            background-color: {theme.accent_fill};
            border: 2px solid {theme.accent_fill};
        }}

        QGroupBox {{
            color: {theme.text};
            border-radius: {theme.radius_md}px;
            padding-top: 24px; padding-bottom: 8px;
            padding-left: 8px; padding-right: 8px;
            font-weight: bold;
        }}
        QGroupBox::title {{
            subcontrol-origin: padding;
            subcontrol-position: top left;
            padding: 4px 8px; left: 8px; top: 4px;
        }}

        QLabel {{ color: {theme.text}; background-color: transparent; }}

        QTableView {{
            background-color: {theme.surface};
            color: {theme.text};
            gridline-color: {theme.border_subtle};
            border-radius: {r + 4}px;
        }}
        QTableView::item {{
            border-top: 2px solid transparent;
            border-bottom: 2px solid transparent;
        }}
        QTableView::item:selected {{
            background-color: {theme.selection_bg};
            color: {theme.text};
            border-top: 2px solid {theme.selection_border};
            border-bottom: 2px solid {theme.selection_border};
        }}
        QTableView::item:selected:hover {{ background-color: {theme.selection_bg}; }}
        QTableView::item:hover {{ background-color: {theme.hover}; }}
        QHeaderView::section {{
            background-color: {theme.surface_raised};
            color: {theme.text};
            padding: 4px; font-weight: bold;
        }}
        QTableCornerButton::section {{
            background-color: {theme.surface_raised};
            border: 1px solid {theme.border};
        }}

        QListWidget {{
            background-color: {theme.surface};
            color: {theme.text};
            border-radius: {r + 4}px;
        }}
        QListWidget::item {{ border: 2px solid transparent; }}
        QListWidget::item:selected {{
            background-color: {theme.selection_bg};
            color: {theme.text};
            border: 2px solid {theme.selection_border};
            border-radius: {r}px;
        }}
        QListWidget::item:selected:hover {{ background-color: {theme.selection_bg}; }}
        QListWidget::item:hover {{ background-color: {theme.hover}; }}

        QScrollBar:vertical {{ background-color: {theme.surface}; width: 12px; border: none; }}
        QScrollBar::handle:vertical {{
            background-color: {theme.border}; min-height: 20px; border-radius: {r}px;
        }}
        QScrollBar::handle:vertical:hover {{ background-color: {theme.text_secondary}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
        QScrollBar:horizontal {{ background-color: {theme.surface}; height: 12px; border: none; }}
        QScrollBar::handle:horizontal {{
            background-color: {theme.border}; min-width: 20px; border-radius: {r}px;
        }}
        QScrollBar::handle:horizontal:hover {{ background-color: {theme.text_secondary}; }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0px; }}

        QTabWidget::pane {{ border: 1px solid {theme.border}; background-color: {theme.surface}; }}
        QTabBar::tab {{
            background-color: {theme.surface_raised};
            color: {theme.text};
            border: 1px solid {theme.border};
            padding: 8px 16px; margin-right: 2px;
        }}
        QTabBar::tab:selected {{
            background-color: {theme.surface};
            border-bottom-color: {theme.surface};
            font-weight: bold;
        }}
        QTabBar::tab:hover {{ background-color: {theme.hover}; }}

        QStatusBar {{
            background-color: {theme.surface_raised};
            color: {theme.text};
            border-top: 1px solid {theme.border};
        }}

        QMenuBar {{ background-color: {theme.surface}; color: {theme.text}; }}
        QMenuBar::item:selected {{ background-color: {theme.hover}; }}
        QMenu {{
            background-color: {theme.surface_raised};
            color: {theme.text};
            border: 1px solid {theme.border};
        }}
        QMenu::item:selected {{ background-color: {theme.accent_fill}; color: {theme.on_accent}; }}

        QToolBar {{
            background-color: {theme.surface_raised};
            spacing: {theme.spacing_xs}px;
        }}

        QDialog {{ background-color: {theme.surface}; color: {theme.text}; }}

        Card {{
            background-color: {theme.surface_raised};
            border: none;
            border-radius: {theme.radius_md}px;
        }}
    """


def build_palette(theme: ThemeTokens):
    """Build a QPalette for one theme. Import is local so this module stays
    importable in a pure-Python (no Qt) context, e.g. under plain pytest."""
    from PySide6.QtGui import QColor, QPalette

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(theme.surface))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(theme.text))
    palette.setColor(QPalette.ColorRole.Base, QColor(theme.surface_raised))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(theme.hover))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(theme.surface_raised))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(theme.text))
    palette.setColor(QPalette.ColorRole.Text, QColor(theme.text))
    palette.setColor(QPalette.ColorRole.Button, QColor(theme.surface_raised))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(theme.text))
    palette.setColor(QPalette.ColorRole.BrightText, QColor(theme.status_danger))
    palette.setColor(QPalette.ColorRole.Link, QColor(theme.accent_fill))
    palette.setColor(QPalette.ColorRole.LinkVisited, QColor("#9C27B0"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(theme.accent_fill))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(theme.text_placeholder))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(theme.text_disabled))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(theme.text_disabled))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(theme.text_disabled))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Base, QColor(theme.surface_raised))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Button, QColor(theme.surface_raised))
    return palette


def apply_theme(app, theme_name: str) -> None:
    """Apply a theme's stylesheet and palette to a running QApplication."""
    theme = get_theme(theme_name)
    app.setStyleSheet(build_stylesheet(theme))
    app.setPalette(build_palette(theme))


if __name__ == "__main__":
    validate_theme(LIGHT_THEME)
    validate_theme(DARK_THEME)
    assert get_theme("dark") is DARK_THEME
    assert get_theme("light") is LIGHT_THEME
    assert get_theme("missing") is LIGHT_THEME

    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    for theme in (LIGHT_THEME, DARK_THEME):
        sheet = build_stylesheet(theme)
        assert "QPushButton" in sheet and theme.accent_fill in sheet
        assert theme.accent_fill not in sheet.split("QPushButton {", 1)[1].split("}", 1)[0]
        for _role in BUTTON_ROLES:
            assert f'QPushButton[role="{_role}"]' in sheet
        palette = build_palette(theme)
        assert palette.color(palette.ColorRole.Window).name().upper() == theme.surface.upper()
    apply_theme(app, "dark")
    assert (theme_app_stylesheet := app.styleSheet())

    dot = StatusDot("status_success", DARK_THEME)
    assert dot.width() == 10 and dot.height() == 10
    assert dot.color().name().upper() == DARK_THEME.status_success.upper()
    dot.set_role("status_danger", DARK_THEME)
    assert dot.color().name().upper() == DARK_THEME.status_danger.upper()

    chip = StatusChip("status_success", "Completed", DARK_THEME)
    assert DARK_THEME.status_success_bg in chip.styleSheet()
    edge = StatusChip("status_danger", "Incomplete", DARK_THEME, variant="edge")
    assert "border-left: 3px solid" in edge.styleSheet()

    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QMainWindow
    test_settings = QSettings("SharedThemeSelfCheck", "GeometryTest")
    test_settings.remove("window_geometry")
    win = QMainWindow()
    win.setGeometry(50, 50, 400, 300)
    save_window_geometry(win, test_settings)
    win2 = QMainWindow()
    assert restore_window_geometry(win2, test_settings) is True
    assert win2.geometry().width() == 400
    test_settings.remove("window_geometry")

    print("shared/theme.py full self-check OK")
