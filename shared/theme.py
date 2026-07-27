"""Shared theme system for Packing Tool and Shopify Fulfillment Tool.

Canonical source — see
docs/superpowers/specs/2026-07-26-unified-ui-design-system-design.md.
Never hand-edit shopify-fulfillment-tool/shared/theme.py; run
shopify-fulfillment-tool/scripts/sync_shared.py after changing this file.
"""

import re
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

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
    """
    name: str
    background: str
    background_elevated: str
    text: str
    text_secondary: str
    text_disabled: str
    text_placeholder: str
    border: str
    border_subtle: str
    hover: str
    active_background: str
    active_border: str
    button_hover_light: str
    button_hover_dark: str
    accent_blue: str = "#007ACC"
    accent_green: str = "#4CAF50"
    accent_orange: str = "#FF9800"
    accent_red: str = "#F44336"
    radius: int = 4
    spacing_xs: int = 4
    spacing_sm: int = 8
    spacing_md: int = 12
    spacing_lg: int = 16
    spacing_xl: int = 24
    font_family: str = "Segoe UI, sans-serif"
    font_family_mono: str = "Consolas, monospace"


LIGHT_THEME = ThemeTokens(
    name="light",
    background="#FFFFFF",
    background_elevated="#FAFAFA",
    text="#1A1A1A",
    text_secondary="#5A5A5A",
    text_disabled="#AAAAAA",
    text_placeholder="#888888",
    border="#1A1A1A",
    border_subtle="#CCCCCC",
    hover="#EEEEEE",
    active_background="#F0F8F0",
    active_border="#4CAF50",
    button_hover_light="#005A9E",
    button_hover_dark="#005A9E",
)

DARK_THEME = ThemeTokens(
    name="dark",
    background="#000000",
    background_elevated="#0F0F0F",
    text="#FFFFFF",
    text_secondary="#B0B0B0",
    text_disabled="#444444",
    text_placeholder="#888888",
    border="#FFFFFF",
    border_subtle="#404040",
    hover="#1A1A1A",
    active_background="#1A3D1A",
    active_border="#4CAF50",
    button_hover_light="#2D9FE8",
    button_hover_dark="#2D9FE8",
)

THEMES: dict = {"light": LIGHT_THEME, "dark": DARK_THEME}


def get_theme(name: str) -> ThemeTokens:
    """Look up a theme by name, falling back to light for an unknown name."""
    return THEMES.get(name, LIGHT_THEME)


_HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
_COLOR_FIELDS = (
    "background", "background_elevated", "text", "text_secondary",
    "text_disabled", "text_placeholder", "border", "border_subtle",
    "hover", "active_background", "active_border", "button_hover_light",
    "button_hover_dark", "accent_blue", "accent_green", "accent_orange",
    "accent_red",
)


def validate_theme(theme: ThemeTokens) -> None:
    """Raise ValueError if any color field isn't a valid #RRGGBB string."""
    for field_name in _COLOR_FIELDS:
        value = getattr(theme, field_name)
        if not _HEX_RE.match(value):
            raise ValueError(
                f"{theme.name}.{field_name} = {value!r} is not a valid #RRGGBB color"
            )


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

    Replaces emoji glyphs (previously concatenated into table-cell text,
    e.g. packing-tool's sessions_list_widget.py STATUS_CONFIG icons) with a
    theme-independent painted widget — consistent rendering across OS/fonts.
    """

    def __init__(self, color: str, diameter: int = 10, parent=None):
        super().__init__(parent)
        self._color = QColor(color)
        self._diameter = diameter
        self.setFixedSize(diameter, diameter)

    def set_color(self, color: str) -> None:
        self._color = QColor(color)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(self._color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(0, 0, self._diameter, self._diameter)


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


def build_stylesheet(theme: ThemeTokens) -> str:
    """Build the global Qt stylesheet (QSS) for one theme."""
    hover = theme.button_hover_dark if theme.name == "dark" else theme.button_hover_light
    r = theme.radius
    return f"""
        QWidget {{
            background-color: {theme.background};
            color: {theme.text};
            font-family: {theme.font_family};
        }}

        QPushButton {{
            background-color: {theme.accent_blue};
            color: white;
            border: 1px solid {theme.border};
            border-radius: {r}px;
            padding: 6px 12px;
            font-size: 10pt;
        }}
        QPushButton:hover {{ background-color: {hover}; }}
        QPushButton:pressed {{ background-color: {theme.button_hover_dark}; }}
        QPushButton:disabled {{
            background-color: {theme.background};
            color: {theme.text_disabled};
            border: 1px solid {theme.border_subtle};
        }}

        QLineEdit, QTextEdit, QPlainTextEdit {{
            background-color: {theme.background_elevated};
            color: {theme.text};
            border: 1px solid {theme.border};
            border-radius: {r}px;
            padding: 4px 8px;
        }}
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
            border: 2px solid {theme.accent_blue};
        }}
        QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled {{
            background-color: {theme.background};
            color: {theme.text_disabled};
            border-color: {theme.border_subtle};
        }}

        QComboBox {{
            background-color: {theme.background_elevated};
            color: {theme.text};
            border: 1px solid {theme.border};
            border-radius: {r}px;
            padding: 4px 8px;
        }}
        QComboBox:hover {{ border: 1px solid {theme.accent_blue}; }}
        QComboBox::drop-down {{ border: none; }}
        QComboBox QAbstractItemView {{
            background-color: {theme.background_elevated};
            color: {theme.text};
            selection-background-color: {theme.accent_blue};
            selection-color: white;
        }}

        QSpinBox, QDoubleSpinBox, QDateEdit {{
            background-color: {theme.background_elevated};
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
            background-color: {theme.background};
        }}
        QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
            border: 2px solid {theme.accent_blue};
        }}
        QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
            background-color: {theme.accent_blue};
            border: 2px solid {theme.accent_blue};
        }}

        QGroupBox {{
            color: {theme.text};
            border: 1px solid {theme.border};
            border-radius: {r + 4}px;
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
            background-color: {theme.background};
            color: {theme.text};
            gridline-color: {theme.border_subtle};
            border: 1px solid {theme.border};
            border-radius: {r + 4}px;
        }}
        QTableView::item:selected {{ background-color: {theme.accent_blue}; color: white; }}
        QTableView::item:hover {{ background-color: {theme.hover}; }}
        QHeaderView::section {{
            background-color: {theme.background_elevated};
            color: {theme.text};
            border: 1px solid {theme.border};
            padding: 4px; font-weight: bold;
        }}
        QTableCornerButton::section {{
            background-color: {theme.background_elevated};
            border: 1px solid {theme.border};
        }}

        QListWidget {{
            background-color: {theme.background};
            color: {theme.text};
            border: 1px solid {theme.border};
            border-radius: {r + 4}px;
        }}
        QListWidget::item:selected {{ background-color: {theme.accent_blue}; color: white; }}
        QListWidget::item:hover {{ background-color: {theme.hover}; }}

        QScrollBar:vertical {{ background-color: {theme.background}; width: 12px; border: none; }}
        QScrollBar::handle:vertical {{
            background-color: {theme.border}; min-height: 20px; border-radius: {r}px;
        }}
        QScrollBar::handle:vertical:hover {{ background-color: {theme.text_secondary}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
        QScrollBar:horizontal {{ background-color: {theme.background}; height: 12px; border: none; }}
        QScrollBar::handle:horizontal {{
            background-color: {theme.border}; min-width: 20px; border-radius: {r}px;
        }}
        QScrollBar::handle:horizontal:hover {{ background-color: {theme.text_secondary}; }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0px; }}

        QTabWidget::pane {{ border: 1px solid {theme.border}; background-color: {theme.background}; }}
        QTabBar::tab {{
            background-color: {theme.background_elevated};
            color: {theme.text};
            border: 1px solid {theme.border};
            padding: 8px 16px; margin-right: 2px;
        }}
        QTabBar::tab:selected {{
            background-color: {theme.background};
            border-bottom-color: {theme.background};
            font-weight: bold;
        }}
        QTabBar::tab:hover {{ background-color: {theme.hover}; }}

        QStatusBar {{
            background-color: {theme.background_elevated};
            color: {theme.text};
            border-top: 1px solid {theme.border};
        }}

        QMenuBar {{ background-color: {theme.background}; color: {theme.text}; }}
        QMenuBar::item:selected {{ background-color: {theme.hover}; }}
        QMenu {{
            background-color: {theme.background_elevated};
            color: {theme.text};
            border: 1px solid {theme.border};
        }}
        QMenu::item:selected {{ background-color: {theme.accent_blue}; color: white; }}

        QToolBar {{
            background-color: {theme.background_elevated};
            border: 1px solid {theme.border};
            spacing: {theme.spacing_xs}px;
        }}

        QDialog {{ background-color: {theme.background}; color: {theme.text}; }}
    """


def build_palette(theme: ThemeTokens):
    """Build a QPalette for one theme. Import is local so this module stays
    importable in a pure-Python (no Qt) context, e.g. under plain pytest."""
    from PySide6.QtGui import QColor, QPalette

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(theme.background))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(theme.text))
    palette.setColor(QPalette.ColorRole.Base, QColor(theme.background_elevated))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(theme.hover))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(theme.background_elevated))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(theme.text))
    palette.setColor(QPalette.ColorRole.Text, QColor(theme.text))
    palette.setColor(QPalette.ColorRole.Button, QColor(theme.background_elevated))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(theme.text))
    palette.setColor(QPalette.ColorRole.BrightText, QColor(theme.accent_red))
    palette.setColor(QPalette.ColorRole.Link, QColor(theme.accent_blue))
    palette.setColor(QPalette.ColorRole.LinkVisited, QColor("#9C27B0"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(theme.accent_blue))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(theme.text_placeholder))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(theme.text_disabled))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(theme.text_disabled))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(theme.text_disabled))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Base, QColor(theme.background_elevated))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Button, QColor(theme.background_elevated))
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
        assert "QPushButton" in sheet and theme.accent_blue in sheet
        palette = build_palette(theme)
        assert palette.color(palette.ColorRole.Window).name().upper() == theme.background.upper()
    apply_theme(app, "dark")
    assert (theme_app_stylesheet := app.styleSheet())

    dot = StatusDot(DARK_THEME.accent_green)
    assert dot.width() == 10 and dot.height() == 10
    dot.set_color(DARK_THEME.accent_red)

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
