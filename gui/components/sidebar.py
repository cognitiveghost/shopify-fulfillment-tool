"""The shell's left column: header, destinations, footer.

UI refresh phase 1, spec docs/superpowers/specs/2026-09-30-ui-refresh-phase1-shell-design.md
section 4.2, following docs/design/ui-refresh/mockups/app-shell.html. The
destinations are shared/navrail.py's NavRail in its sidebar mode; the header
and footer carry this app's server and client, so they live here and not in
shared/.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from gui.components.commandbar import BAR_HEIGHT
from shared.icons import icon
from shared.navrail import RAIL_WIDTH, NavRail
from shared.theme import current_tokens, font_css, on_theme_changed

SIDEBAR_WIDTH = 200
# 200 - footer margins 16 - box padding 16 - dot 8 - gap 8 = 152, less a
# couple of px so the ellipsis never touches the box edge.
_PATH_WIDTH = 148


class Sidebar(QWidget):
    """Header, NavRail, footer. Collapses to a 56px rail."""

    settingsRequested = Signal()
    themeRequested = Signal(str)
    retryRequested = Signal()
    expandedChanged = Signal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        # A QWidget subclass paints no QSS background without this.
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._expanded = True
        self._connected = True
        self._server_path = ""
        self._theme_name = current_tokens().name

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header: mark, name, collapse -- or only the expand button.
        self.header = QFrame(self)
        self.header.setObjectName("SidebarHeader")
        # The bar's height, so the two rules under them are one line.
        self.header.setFixedHeight(BAR_HEIGHT)
        header = QHBoxLayout(self.header)
        header.setContentsMargins(8, 0, 8, 0)
        header.setSpacing(8)
        self.mark = QLabel(self.header)
        self.mark.setObjectName("SidebarMark")
        self.mark.setFixedSize(28, 28)
        self.mark.setAlignment(Qt.AlignCenter)
        self.title = QLabel("Fulfilment Tool", self.header)
        self.title.setMinimumWidth(0)
        self.collapse_button = self._icon_button("Collapse sidebar", 28, 28)
        self.expand_button = self._icon_button("Expand sidebar", 40, 32)
        self.collapse_button.clicked.connect(lambda: self._toggle(False))
        self.expand_button.clicked.connect(lambda: self._toggle(True))
        header.addWidget(self.mark)
        header.addWidget(self.title, 1)
        header.addWidget(self.collapse_button)
        header.addWidget(self.expand_button)
        layout.addWidget(self.header)

        self.rail = NavRail(self, expanded_width=SIDEBAR_WIDTH)
        layout.addWidget(self.rail, 1)

        # Footer: Client settings, theme, connection.
        self.footer = QFrame(self)
        self.footer.setObjectName("SidebarFooter")
        footer = QVBoxLayout(self.footer)
        footer.setContentsMargins(8, 8, 8, 8)
        footer.setSpacing(6)

        self.settings_button = QToolButton(self.footer)
        self.settings_button.setText("Client settings")
        self.settings_button.setToolTip("Client settings")
        self.settings_button.setAutoRaise(True)
        self.settings_button.clicked.connect(self.settingsRequested.emit)
        footer.addWidget(self.settings_button)

        self.theme_segment = QFrame(self.footer)
        self.theme_segment.setObjectName("ThemeSegment")
        segment = QHBoxLayout(self.theme_segment)
        segment.setContentsMargins(2, 2, 2, 2)
        segment.setSpacing(2)
        self.light_button = self._segment_button("Light")
        self.dark_button = self._segment_button("Dark")
        group = QButtonGroup(self.theme_segment)
        group.setExclusive(True)
        for button, name in ((self.light_button, "light"), (self.dark_button, "dark")):
            group.addButton(button)
            segment.addWidget(button)
            button.clicked.connect(lambda _c=False, n=name: self.themeRequested.emit(n))
        footer.addWidget(self.theme_segment)

        self.theme_toggle = self._icon_button("", 40, 32)
        self.theme_toggle.clicked.connect(
            lambda: self.themeRequested.emit(
                "light" if self._theme_name == "dark" else "dark"
            )
        )
        footer.addWidget(self.theme_toggle)

        self.connection_box = QFrame(self.footer)
        self.connection_box.setObjectName("ConnectionBox")
        self.connection_box.setMinimumHeight(44)
        box = QHBoxLayout(self.connection_box)
        box.setContentsMargins(8, 6, 8, 6)
        box.setSpacing(8)
        box.setAlignment(Qt.AlignTop)
        self.connection_dot = QLabel(self.connection_box)
        self.connection_dot.setFixedSize(8, 8)
        dot_column = QVBoxLayout()
        dot_column.setContentsMargins(0, 4, 0, 0)
        dot_column.addWidget(self.connection_dot)
        dot_column.addStretch()
        box.addLayout(dot_column)
        text = QVBoxLayout()
        text.setSpacing(0)
        self.connection_label = QLabel(self.connection_box)
        self.path_label = QLabel(self.connection_box)
        self.path_label.setFixedWidth(_PATH_WIDTH)
        self.retry_button = QPushButton("Retry", self.connection_box)
        self.retry_button.setObjectName("RetryButton")
        self.retry_button.setFixedHeight(24)
        self.retry_button.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.retry_button.clicked.connect(self.retryRequested.emit)
        self.retry_button.hide()
        text.addWidget(self.connection_label)
        text.addWidget(self.path_label)
        text.addSpacing(4)
        text.addWidget(self.retry_button, 0, Qt.AlignLeft)
        box.addLayout(text, 1)
        footer.addWidget(self.connection_box)

        # Collapsed: a server glyph with the same dot at its bottom-right.
        self.connection_icon = QLabel(self.footer)
        self.connection_icon.setObjectName("ConnectionIcon")
        self.connection_icon.setFixedSize(40, 32)
        self.connection_icon.setAlignment(Qt.AlignCenter)
        self.connection_icon_dot = QLabel(self.connection_icon)
        self.connection_icon_dot.setFixedSize(8, 8)
        self.connection_icon_dot.move(25, 19)
        footer.addWidget(self.connection_icon)

        layout.addWidget(self.footer)

        self.set_connection(True, "")
        on_theme_changed(self, self._apply_theme)
        self.set_expanded(True)

    # -- construction helpers -------------------------------------------------

    def _icon_button(self, tip: str, width: int, height: int) -> QToolButton:
        button = QToolButton(self)
        button.setToolTip(tip)
        button.setAutoRaise(True)
        button.setFixedSize(width, height)
        return button

    def _segment_button(self, text: str) -> QToolButton:
        button = QToolButton(self.theme_segment)
        button.setText(text)
        button.setCheckable(True)
        button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        button.setFixedHeight(24)
        button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        return button

    # -- public API -------------------------------------------------------------

    def set_expanded(self, expanded: bool) -> None:
        self._expanded = expanded
        self.setFixedWidth(SIDEBAR_WIDTH if expanded else RAIL_WIDTH)
        self.rail.set_expanded(expanded)
        for widget in (self.mark, self.title, self.collapse_button,
                       self.theme_segment, self.connection_box):
            widget.setVisible(expanded)
        for widget in (self.expand_button, self.theme_toggle, self.connection_icon):
            widget.setVisible(not expanded)
        self.settings_button.setToolButtonStyle(
            Qt.ToolButtonTextBesideIcon if expanded else Qt.ToolButtonIconOnly
        )
        self.settings_button.setFixedSize(
            (SIDEBAR_WIDTH if expanded else RAIL_WIDTH) - 16, 32
        )
        self._apply_theme(current_tokens())

    def is_expanded(self) -> bool:
        return self._expanded

    def set_connection(self, connected: bool, server_path: str) -> None:
        self._connected = connected
        self._server_path = server_path
        label = "Server connected" if connected else "Server unreachable"
        self.connection_label.setText(label)
        metrics = QFontMetrics(self.path_label.font())
        self.path_label.setText(
            metrics.elidedText(server_path, Qt.ElideMiddle, _PATH_WIDTH)
        )
        self.path_label.setToolTip(server_path)
        self.connection_icon.setToolTip(f"{label} · {server_path}")
        self.retry_button.setVisible(not connected)
        self._style_connection(current_tokens())

    def set_theme_name(self, name: str) -> None:
        self._theme_name = name
        (self.dark_button if name == "dark" else self.light_button).setChecked(True)
        self.theme_toggle.setToolTip(
            "Switch to Light" if name == "dark" else "Switch to Dark"
        )
        self.theme_toggle.setIcon(icon("sun" if name == "dark" else "moon"))

    def set_settings_enabled(self, enabled: bool) -> None:
        self.settings_button.setEnabled(enabled)

    # -- internals --------------------------------------------------------------

    def _toggle(self, expanded: bool) -> None:
        self.set_expanded(expanded)
        self.expandedChanged.emit(expanded)

    def _apply_theme(self, t) -> None:
        """Re-run on every theme change: this widget's own sheet outranks the
        app's, and a QIcon is a snapshot (ADR 0003)."""
        pad = 9 if self._expanded else 0
        self.setStyleSheet(
            f"Sidebar {{ background-color: {t.surface_sunken};"
            f" border-right: 1px solid {t.border_subtle}; }}"
            # The app sheet's `QWidget` rule would paint these two on `surface`.
            f"#SidebarHeader, #SidebarFooter {{ background-color: {t.surface_sunken}; }}"
            f"#SidebarHeader {{ border-bottom: 1px solid {t.border_subtle}; }}"
            f"#SidebarFooter {{ border-top: 1px solid {t.border_subtle}; }}"
            f"#SidebarMark {{ background-color: {t.accent_fill}; border-radius: 8px; }}"
            f"#SidebarHeader QLabel {{ color: {t.text}; {font_css('body', bold=True)} }}"
            f"#SidebarHeader QToolButton, #SidebarFooter QToolButton {{"
            f" background-color: transparent; border: 1px solid transparent;"
            f" border-radius: 8px; color: {t.text_secondary}; {font_css('body')} }}"
            f"#SidebarHeader QToolButton:hover, #SidebarFooter QToolButton:hover {{"
            f" background-color: {t.hover}; }}"
            f"#SidebarFooter QToolButton:disabled {{ color: {t.text_disabled}; }}"
            f"#SidebarFooter > QToolButton {{ padding-left: {pad}px; }}"
            f"#ThemeSegment {{ background-color: {t.surface_sunken};"
            f" border: 1px solid {t.border}; border-radius: 8px; }}"
            f"#ThemeSegment QToolButton {{ border-radius: 6px; {font_css('caption')} }}"
            f"#ThemeSegment QToolButton:checked {{ background-color: {t.surface};"
            f" border: 1px solid {t.border_subtle}; color: {t.text}; font-weight: bold; }}"
        )
        self.mark.setPixmap(icon("package", color=t.on_accent).pixmap(16, 16))
        self.collapse_button.setIcon(icon("panel-left-close"))
        self.expand_button.setIcon(icon("panel-left-open"))
        self.settings_button.setIcon(icon("settings"))
        self.light_button.setIcon(icon("sun"))
        self.dark_button.setIcon(icon("moon"))
        self.connection_icon.setPixmap(icon("server").pixmap(18, 18))
        self.set_theme_name(t.name)
        self._style_connection(t)

    def _style_connection(self, t) -> None:
        dot = t.status_success_dot if self._connected else t.status_danger_dot
        colour = t.status_success if self._connected else t.status_danger
        fill = "transparent" if self._connected else t.status_danger_bg
        edge = "transparent" if self._connected else t.status_danger_border
        for d in (self.connection_dot, self.connection_icon_dot):
            d.setStyleSheet(f"background-color: {dot}; border-radius: 4px;")
        self.connection_box.setStyleSheet(
            f"#ConnectionBox {{ background-color: {fill}; border: 1px solid {edge};"
            f" border-radius: 8px; }}"
        )
        self.connection_icon.setStyleSheet(
            f"#ConnectionIcon {{ background-color: {fill}; border-radius: 8px; }}"
        )
        self.connection_label.setStyleSheet(
            f"color: {colour}; {font_css('caption', bold=True)}"
        )
        self.path_label.setStyleSheet(
            f"color: {t.text_secondary}; font-family: {t.font_family_mono};"
            f" {font_css('caption')}"
        )
        self.retry_button.setStyleSheet(
            f"#RetryButton {{ background-color: {t.surface}; color: {t.text};"
            f" border: 1px solid {t.status_danger_border}; border-radius: 8px;"
            f" padding: 0 10px; {font_css('caption', bold=True)} }}"
        )
