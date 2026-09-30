# UI refresh phase 1: shell sidebar and Polaris palette. Implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-colour the app to the approved mockup's palette (within the contrast floors). Replace the 56px rail and the
status bar with a 200px collapsible sidebar that has a footer for Client settings, the theme and the server connection.

**Architecture:** The palette and four new tokens go in `shared/theme.py`. `shared/navrail.py` gains an opt-in
sidebar mode, so `NavRail(expanded_width=200)` behaves as a sidebar while `NavRail()` stays exactly as it is for
Packing Tool. A new app-local `gui/components/sidebar.py` wraps that rail with a header and a footer.
`gui/ui_manager.py` wires it in, deletes the status bar, and puts the destination-enabling rule in one method.

**Tech Stack:** Python 3.14, PySide6 (Qt widgets, QSS), pytest + pytest-qt, offscreen rendering.

**Spec:** `docs/superpowers/specs/2026-09-30-ui-refresh-phase1-shell-design.md`. Read §3 to §8 before starting.
Mockup: `docs/design/ui-refresh/mockups/app-shell.html` (render: `mockups/renders/app-shell.png`).

## Global Constraints

- Work in `/home/gloopy/Desktop/Projects/shopify-fulfillment-tool/.claude/worktrees/dr-13` on branch
  `dr/13-mock-up-of-fulfilment-tool`. Never `cd` to the main checkout. If `.venv` is missing, run
  `./scripts/setup_venv.sh`.
- Run tests only as `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q <paths>`. A hook blocks any other
  Bash text that contains the word "pytest", so write test files with Write/Edit, never with heredocs.
- Git: `/usr/bin/git`, one plain command per Bash call, with no `;`, `&&` or `$VAR`. Commit with
  `/usr/bin/git commit -F <absolute path to a message file>`, and write the message file under your job's tmp dir.
  End every message with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`, or with the attribution
  line your session is given.
- No hardcoded colours in QSS. Every colour comes from a token (`current_tokens()` / `ThemeTokens` fields).
- No `pyproject.toml`, no new dependencies, no unused imports (`ruff check .` must pass).
- `shared/` is canonical here (ADR 0017). Edit it directly. Never touch `packing-tool/`.
- **Pre-existing failures:** three tests in `tests/test_label_printing.py::TestImageToZpl` already fail on
  `origin/main` (553b7e1, Pillow 12.3.0). They are not this task's. Do not fix them. The PR body mentions them.
- Copy is verbatim from the spec: "Fulfilment Tool", "Collapse sidebar", "Expand sidebar", "Client settings",
  "Light", "Dark", "Switch to Dark", "Switch to Light", "Server connected", "Server unreachable", "Retry",
  "Keyboard shortcuts…", "Keyboard shortcuts" (window title),
  "Analysis Results — available after Run analysis (Ctrl+2)".

## Review Focus

1. **Ctrl+F with no analysis.** `_focus_results_search` calls `main_tabs.setCurrentIndex(1)` directly, which
   bypasses the rail. With Results disabled it must do nothing (test in Task 6).
2. **A long UNC server path** (`\\warehouse-fs01.corp.local\shares\fulfilment\production`) must elide inside
   the footer, not widen the 200px sidebar (test in Task 4).
3. **Going offline while on Logs** keeps the operator on Logs, and **going offline while on Browse** sends them to
   Setup (test in Task 6).
4. **The collapsed theme button after a toggle.** It must emit the *other* theme each time, not the theme it was
   built with (test in Task 4).
5. **Stale colours after a theme toggle.** The sidebar must repaint its own sheet on a theme change, because a
   widget's own sheet outranks the app's (test in Task 4).

---

### Task 1: Palette, new tokens, disabled buttons (`shared/theme.py`)

**Files:**
- Modify: `shared/theme.py`: the `ThemeTokens` fields (class at line 25), `LIGHT_THEME` (line 121),
  `DARK_THEME` (line 163), `_COLOR_FIELDS` (tuple near line 474), the two `:disabled` rules in `build_stylesheet`
  (near lines 1134 and 1181)
- Create: `tests/test_theme_palette.py`
- Modify: `tests/test_shared_theme_buttons.py` (lines 26-31 and 68-73)

**Interfaces:**
- Produces: `ThemeTokens.status_success_dot`, `.status_danger_dot`, `.status_danger_border`, `.control_disabled_bg`
  (all `str`, `#RRGGBB`), which Task 4 uses.

- [ ] **Step 1: Write the failing test**

Create `tests/test_theme_palette.py`:

```python
"""Phase 1 palette: the mockup's values, fitted to the contrast floors.

Spec docs/superpowers/specs/2026-09-30-ui-refresh-phase1-shell-design.md
section 3; ADR 0018 says why four of them are darker than the mockup.
"""

import pytest

from shared.theme import DARK_THEME, LIGHT_THEME, build_stylesheet, validate_theme

PALETTE = {
    "surface_sunken": ("#F1F1F1", "#0F1012"),
    "surface": ("#FFFFFF", "#1A1B1E"),
    "surface_raised": ("#F7F7F7", "#232428"),
    "surface_overlay": ("#FFFFFF", "#2A2B30"),
    "text": ("#303030", "#E3E3E3"),
    "text_secondary": ("#616161", "#A3A3A8"),
    "text_disabled": ("#888888", "#767676"),
    "text_placeholder": ("#6C6C6C", "#949494"),
    "border": ("#888888", "#767676"),
    "border_subtle": ("#E3E3E3", "#34353A"),
    "border_strong": ("#888888", "#767676"),
    "status_info": ("#00527C", "#7CC4F8"),
    "status_info_bg": ("#E0F0FF", "#0B2A40"),
    "status_success": ("#0C5132", "#6ED3A0"),
    "status_success_bg": ("#CDFEE1", "#0E3222"),
    "status_warning": ("#5E4200", "#F5C451"),
    "status_warning_bg": ("#FFEF9D", "#3A2C05"),
    "status_danger": ("#8E0B21", "#FF9A9A"),
    "status_danger_bg": ("#FEE9E8", "#43141A"),
    "accent_fill": ("#303030", "#E3E3E3"),
    "accent_fill_hover": ("#1A1A1A", "#FFFFFF"),
    "accent_fill_active": ("#000000", "#C4C4C8"),
    "on_accent": ("#FFFFFF", "#1A1B1E"),
    "selection_border": ("#005BD3", "#4A9CFF"),
    "selection_bg": ("#EAF4FF", "#12243B"),
    "focus_ring": ("#005BD3", "#4A9CFF"),
    "hover": ("#F7F7F7", "#232428"),
    # New in phase 1 (spec section 3.2).
    "status_success_dot": ("#29845A", "#6ED3A0"),
    "status_danger_dot": ("#E51C00", "#FF9A9A"),
    "status_danger_border": ("#FDB5B4", "#6B2029"),
    "control_disabled_bg": ("#F1F1F1", "#141518"),
}

THEMES = pytest.mark.parametrize("theme", [LIGHT_THEME, DARK_THEME], ids=["light", "dark"])


@pytest.mark.parametrize("token", sorted(PALETTE))
def test_the_palette_is_the_mockups_fitted_to_the_floors(token):
    light, dark = PALETTE[token]
    assert getattr(LIGHT_THEME, token) == light
    assert getattr(DARK_THEME, token) == dark


@THEMES
def test_both_themes_still_validate(theme):
    validate_theme(theme)


@THEMES
@pytest.mark.parametrize(
    "selector", ["QPushButton:disabled {", 'QPushButton[role="danger"]:disabled {']
)
def test_a_disabled_button_drops_its_fill_and_dashes_its_edge(theme, selector):
    """Audit A6: a disabled button used to differ only by a lighter label."""
    block = build_stylesheet(theme).split(selector, 1)[1].split("}", 1)[0]
    assert f"background-color: {theme.control_disabled_bg};" in block
    assert f"border: 1px dashed {theme.border_strong};" in block
    assert f"color: {theme.text_disabled};" in block
```

- [ ] **Step 2: Run it to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_theme_palette.py`
Expected: FAIL (old values, and `AttributeError` on `status_success_dot`).

- [ ] **Step 3: Implement**

In `ThemeTokens`, directly after `status_danger_bg: str`, add:

```python
    # Phase 1 (spec 2026-09-30 section 3.2): the sidebar's connection dot and
    # unreachable edge, and the disabled-button fill.
    status_success_dot: str
    status_danger_dot: str
    status_danger_border: str
    control_disabled_bg: str
```

In `_COLOR_FIELDS`, directly after `"status_danger_bg",`, add:

```python
    "status_success_dot",
    "status_danger_dot",
    "status_danger_border",
    "control_disabled_bg",
```

Replace the colour arguments of `LIGHT_THEME` and `DARK_THEME` with the values in the `PALETTE` table above,
light and dark respectively. Keep `name=` and the `# aliases` comment. Add the four new keywords after
`status_danger_bg=`. Set the aliases to their canonical values:

```python
    # aliases
    background=<surface>,
    background_elevated=<surface_raised>,
    accent_blue=<accent_fill>,
    accent_green=<status_success>,
    accent_orange=<status_warning>,
    accent_red=<status_danger>,
    active_background=<selection_bg>,
    active_border=<selection_border>,
```

with `button_hover_light` and `button_hover_dark` both set to `<accent_fill_active>`. Write the literal hex in
each case. `validate_theme` rejects any alias that differs from its canonical token.

In `build_stylesheet`, change both disabled rules. The plain `QPushButton:disabled {{ ... }}` and the
role-qualified `QPushButton[role="primary"]:disabled, ... QPushButton[role="danger"]:disabled {{ ... }}` get this
body:

```
            background-color: {theme.control_disabled_bg};
            color: {theme.text_disabled};
            border: 1px dashed {theme.border_strong};
```

In `tests/test_shared_theme_buttons.py`, the palette makes dark `accent_fill` equal to dark `text` (#E3E3E3), so
the bare-hex checks now match the label colour. Check the fill instead.

```python
def test_the_unmarked_button_rule_is_secondary():
    # 2026-08-29: the default flipped from accent-filled to secondary -- primary
    # is now something a screen declares, not what every unmarked button gets.
    # The fill, not the bare hex: since phase 1, dark accent_fill is also dark
    # text (#E3E3E3), so the bare hex matches the label colour.
    sheet = build_stylesheet(DARK_THEME)
    plain = sheet.split('QPushButton[role=')[0]
    assert f"background-color: {DARK_THEME.accent_fill}" not in plain
```

```python
def test_an_unmarked_button_is_not_primary():
    """The whole point: primary is declared, never defaulted into."""
    for theme in (DARK_THEME, LIGHT_THEME):
        block = _default_button_block(build_stylesheet(theme))
        assert theme.surface_raised in block
        assert f"background-color: {theme.accent_fill}" not in block
```

- [ ] **Step 4: Run the theme tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_theme_palette.py tests/test_shared_theme_buttons.py tests/test_theme_contrast.py tests/test_theme_css_vars.py tests/test_shared_theme_widgets.py tests/test_status_style.py tests/test_status_channels.py tests/test_status_edge_delegate.py tests/test_theme_manager_button_roles.py tests/test_results_bridge.py tests/test_style_literals_guard.py`
Expected: PASS. At Stage A, this exact palette ran against the whole suite, and the only failures were the two
button tests fixed above (plus the three pre-existing ZPL ones).

- [ ] **Step 5: Commit**

```
/usr/bin/git add shared/theme.py tests/test_theme_palette.py tests/test_shared_theme_buttons.py
/usr/bin/git commit -F <msg>
```
Message: `theme: Polaris palette fitted to the contrast floors, disabled buttons look disabled (phase 1 §3)`

---

### Task 2: NavRail sidebar mode (`shared/navrail.py`)

**Files:**
- Modify: `shared/navrail.py`
- Modify: `tests/test_components_navrail.py` (append tests)

**Interfaces:**
- Produces: `NavRail(parent=None, width: int = RAIL_WIDTH, expanded_width: int | None = None)`,
  `NavRail.set_expanded(expanded: bool) -> None` (raises `RuntimeError` when `expanded_width is None`), and
  `NavRail.is_expanded() -> bool`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_components_navrail.py`)

```python
def test_the_default_rail_is_untouched_by_sidebar_mode(qapp):
    """Packing Tool builds NavRail(width=76) and must see no change."""
    from PySide6.QtCore import Qt

    rail = NavRail()
    index = rail.add_item(icon("package"), "Orders")
    assert rail.button(index).toolButtonStyle() == Qt.ToolButtonTextUnderIcon
    assert rail.width() == 56
    with pytest.raises(RuntimeError):
        rail.set_expanded(False)


def test_sidebar_mode_starts_expanded_with_labels_beside_icons(qapp):
    from PySide6.QtCore import Qt

    rail = NavRail(expanded_width=200)
    index = rail.add_item(icon("package"), "Setup")
    assert rail.is_expanded()
    assert rail.width() == 200
    assert rail.button(index).toolButtonStyle() == Qt.ToolButtonTextBesideIcon
    assert rail.button(index).width() == 184
    assert rail.button(index).height() == 32


def test_collapsing_the_sidebar_leaves_a_56px_icon_rail(qapp):
    from PySide6.QtCore import Qt

    rail = NavRail(expanded_width=200)
    index = rail.add_item(icon("package"), "Setup")
    rail.set_expanded(False)
    assert not rail.is_expanded()
    assert rail.width() == 56
    assert rail.button(index).toolButtonStyle() == Qt.ToolButtonIconOnly
    assert rail.button(index).width() == 40
    # The label survives the collapse: expanding again must not lose it.
    assert rail.button(index).text() == "Setup"
    rail.set_expanded(True)
    assert rail.button(index).width() == 184


def test_an_item_added_while_collapsed_takes_the_collapsed_shape(qapp):
    from PySide6.QtCore import Qt

    rail = NavRail(expanded_width=200)
    rail.set_expanded(False)
    index = rail.add_item(icon("package"), "Setup")
    assert rail.button(index).toolButtonStyle() == Qt.ToolButtonIconOnly


def test_the_checked_sidebar_item_is_bold_on_the_surface_plane(qapp):
    from shared.theme import current_tokens

    rail = NavRail(expanded_width=200)
    sheet = rail.styleSheet()
    checked = sheet.split("NavRail QToolButton:checked {", 1)[1].split("}", 1)[0]
    tokens = current_tokens()
    assert f"background-color: {tokens.surface};" in checked
    assert f"border: 1px solid {tokens.border_subtle};" in checked
    assert "font-weight: bold;" in checked
```

- [ ] **Step 2: Run to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_components_navrail.py`
Expected: the new tests FAIL (`TypeError: unexpected keyword argument 'expanded_width'`), and the old ones pass.

- [ ] **Step 3: Implement** (`shared/navrail.py`)

Add a paragraph to the module docstring:

```
Sidebar mode (UI refresh phase 1, spec 2026-09-30 section 4.1) is opt-in
through expanded_width: the same destinations drawn as a 200px list with the
label beside the icon, collapsing to a 56px icon rail. Without expanded_width
the rail is exactly what it was, which is what packing-tool gets at its sync.
```

Replace `__init__`, `_apply_theme` and `_make_button`, and add the three methods below. `add_item`, `button`,
`current_index` and `set_current` stay unchanged.

```python
    def __init__(
        self, parent=None, width: int = RAIL_WIDTH, expanded_width: int | None = None
    ) -> None:
        super().__init__(parent)
        self._width = width
        self._expanded_width = expanded_width
        self._expanded = expanded_width is not None
        self.setFixedWidth(expanded_width or width)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        self._buttons: list[QToolButton] = []
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        # Not read from self._group.checkedId(): by the time a clicked() slot
        # runs, Qt has already flipped the exclusive group's checked button,
        # so that state can no longer tell a genuine change from a re-click.
        self._current = -1

        layout = QVBoxLayout(self)
        if expanded_width is None:
            layout.setContentsMargins(0, 8, 0, 8)
            layout.setSpacing(4)
        else:
            layout.setContentsMargins(8, 8, 8, 8)
            layout.setSpacing(2)
        layout.addStretch()
        self._layout = layout

        self._apply_theme()
        # A widget sheet outranks the app's, so baking the colours in once
        # would leave a light rail over dark pages after a theme toggle.
        theme_notifier.changed.connect(self._apply_theme)

    def _apply_theme(self, _name: str | None = None) -> None:
        # Takes the signal's argument and ignores it, so the same method can
        # be the slot and the constructor's direct call.
        theme = current_tokens()
        if self._expanded_width is None:
            # No border: the rail is separated by its own darker plane, not a line.
            # Scoped to NavRail: a bare rule would repaint the buttons too, leaving
            # the checked item indistinguishable from the rest of the rail.
            self.setStyleSheet(
                f"NavRail {{ background-color: {theme.surface_sunken}; border: none; }}"
                f"NavRail QToolButton {{ background-color: transparent; border: none;"
                f" color: {theme.text_secondary}; }}"
                f"NavRail QToolButton:hover {{ background-color: {theme.hover}; }}"
                f"NavRail QToolButton:checked {{ background-color: {theme.surface_raised};"
                f" color: {theme.text}; }}"
            )
            return
        # Sidebar mode: the mockup's active item is a white plane with a
        # hairline edge and a bold label. Padding only while labels show --
        # in the 40px icon-only button it would push the glyph off centre.
        padding = 9 if self._expanded else 0
        self.setStyleSheet(
            f"NavRail {{ background-color: {theme.surface_sunken}; border: none; }}"
            f"NavRail QToolButton {{ background-color: transparent;"
            f" border: 1px solid transparent; border-radius: 8px;"
            f" padding-left: {padding}px; color: {theme.text_secondary};"
            f" {font_css('body')} }}"
            f"NavRail QToolButton:hover {{ background-color: {theme.hover}; }}"
            f"NavRail QToolButton:checked {{ background-color: {theme.surface};"
            f" border: 1px solid {theme.border_subtle}; color: {theme.text};"
            f" font-weight: bold; }}"
            f"NavRail QToolButton:disabled {{ color: {theme.text_disabled}; }}"
        )

    def _make_button(self, glyph: QIcon, label: str) -> QToolButton:
        button = QToolButton(self)
        button.setIcon(glyph)
        button.setText(label)
        button.setAutoRaise(True)
        if self._expanded_width is None:
            button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            button.setFixedWidth(self._width)
            # ponytail: caption size is baked in once, so a density switch does not
            # resize the labels -- set_current() no-ops on an unchanged theme name,
            # so set_density() never reaches the notifier. Re-apply from a density
            # signal when 8.9 moves packing-tool to floor density.
            button.setStyleSheet(font_css("caption"))
        else:
            # No per-button sheet in sidebar mode: a widget's own sheet outranks
            # the rail's, and would cancel the checked item's bold.
            self._shape(button)
        return button

    def _shape(self, button: QToolButton) -> None:
        """Sidebar mode's two shapes: 184x32 with a label, or a 40x32 icon."""
        if self._expanded:
            button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            button.setFixedSize(self._expanded_width - 16, 32)
        else:
            button.setToolButtonStyle(Qt.ToolButtonIconOnly)
            button.setFixedSize(self._width - 16, 32)

    def set_expanded(self, expanded: bool) -> None:
        """Sidebar mode only: the 200px list, or the 56px icon rail."""
        if self._expanded_width is None:
            raise RuntimeError("NavRail was built without expanded_width")
        self._expanded = expanded
        self.setFixedWidth(self._expanded_width if expanded else self._width)
        for button in self._buttons:
            self._shape(button)
        self._apply_theme()

    def is_expanded(self) -> bool:
        return self._expanded
```

- [ ] **Step 4: Run the rail tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_components_navrail.py tests/test_navrail_labels_fit.py tests/test_components_render_roles.py`
Expected: PASS.

- [ ] **Step 5: Commit**

Message: `navrail: opt-in sidebar mode; the default rail is unchanged (phase 1 §4.1)`

---

### Task 3: Glyphs

**Files:**
- Create: `shared/assets/icons/panel-left-close.svg`, `panel-left-open.svg`, `sun.svg`, `moon.svg`, `server.svg`
- Modify: `tests/test_ui_assets.py` (`EXPECTED_ICONS`)

- [ ] **Step 1: Add the names to `EXPECTED_ICONS`** (append after `"toggle-on",`):

```python
    "panel-left-close", "panel-left-open", "sun", "moon", "server",
```

- [ ] **Step 2: Run to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_ui_assets.py`
Expected: FAIL for the five new names.

- [ ] **Step 3: Download them from the pinned tag.** Run one `curl` per glyph from the worktree root:

```
curl -fsSL -o shared/assets/icons/panel-left-close.svg https://raw.githubusercontent.com/lucide-icons/lucide/1.31.0/icons/panel-left-close.svg
curl -fsSL -o shared/assets/icons/panel-left-open.svg https://raw.githubusercontent.com/lucide-icons/lucide/1.31.0/icons/panel-left-open.svg
curl -fsSL -o shared/assets/icons/sun.svg https://raw.githubusercontent.com/lucide-icons/lucide/1.31.0/icons/sun.svg
curl -fsSL -o shared/assets/icons/moon.svg https://raw.githubusercontent.com/lucide-icons/lucide/1.31.0/icons/moon.svg
curl -fsSL -o shared/assets/icons/server.svg https://raw.githubusercontent.com/lucide-icons/lucide/1.31.0/icons/server.svg
```

- [ ] **Step 4: Run** `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_ui_assets.py`. Expected: PASS,
  including the `currentColor` check.

- [ ] **Step 5: Commit.** Message: `assets: vendor five Lucide 1.31.0 glyphs for the sidebar`

---

### Task 4: The Sidebar widget (`gui/components/sidebar.py`)

**Files:**
- Create: `gui/components/sidebar.py`
- Create: `tests/test_sidebar.py`

**Interfaces:**
- Consumes: `NavRail(parent, expanded_width=200)`, `set_expanded`, `is_expanded` (Task 2), the four tokens
  (Task 1), and the glyphs (Task 3).
- Produces (used by Task 5):

```python
SIDEBAR_WIDTH = 200

class Sidebar(QWidget):
    settingsRequested = Signal()
    themeRequested = Signal(str)      # "light" | "dark"
    retryRequested = Signal()
    expandedChanged = Signal(bool)    # only from the header buttons
    rail: NavRail
    settings_button: QToolButton
    light_button: QToolButton; dark_button: QToolButton; theme_toggle: QToolButton
    collapse_button: QToolButton; expand_button: QToolButton
    connection_label: QLabel; path_label: QLabel; retry_button: QPushButton; connection_icon: QLabel
    def set_expanded(self, expanded: bool) -> None
    def is_expanded(self) -> bool
    def set_connection(self, connected: bool, server_path: str) -> None
    def set_theme_name(self, name: str) -> None
    def set_settings_enabled(self, enabled: bool) -> None
```

- [ ] **Step 1: Write the failing tests** (`tests/test_sidebar.py`)

```python
"""The shell's sidebar: header, destinations, footer (phase 1 spec section 4.2)."""

import pytest
from PySide6.QtWidgets import QApplication

from gui.components.sidebar import SIDEBAR_WIDTH, Sidebar
from shared.theme import current_tokens

LONG_PATH = r"\\warehouse-fs01.corp.local\shares\fulfilment\production"


@pytest.fixture
def sidebar(qapp):
    bar = Sidebar()
    bar.resize(SIDEBAR_WIDTH, 700)
    bar.show()
    QApplication.processEvents()
    yield bar
    bar.close()


def test_it_starts_expanded_at_200(sidebar):
    assert sidebar.is_expanded()
    assert sidebar.width() == 200
    assert sidebar.rail.is_expanded()


def test_connected_has_no_retry(sidebar):
    sidebar.set_connection(True, r"\\fs01\fulfilment")
    assert sidebar.connection_label.text() == "Server connected"
    assert not sidebar.retry_button.isVisible()


def test_unreachable_offers_retry_and_retry_asks(sidebar):
    sidebar.set_connection(False, r"\\fs01\fulfilment")
    assert sidebar.connection_label.text() == "Server unreachable"
    assert sidebar.retry_button.isVisible()
    asked = []
    sidebar.retryRequested.connect(lambda: asked.append(1))
    sidebar.retry_button.click()
    assert asked == [1]


def test_a_long_server_path_elides_instead_of_widening(sidebar):
    sidebar.set_connection(True, LONG_PATH)
    QApplication.processEvents()
    assert sidebar.width() == 200
    assert "…" in sidebar.path_label.text()
    assert sidebar.path_label.toolTip() == LONG_PATH


def test_the_theme_segments_ask_for_their_theme(sidebar):
    seen = []
    sidebar.themeRequested.connect(seen.append)
    sidebar.dark_button.click()
    sidebar.light_button.click()
    assert seen == ["dark", "light"]


def test_the_collapsed_theme_button_always_asks_for_the_other_theme(sidebar):
    seen = []
    sidebar.themeRequested.connect(seen.append)
    sidebar.set_theme_name("light")
    sidebar.theme_toggle.click()
    sidebar.set_theme_name("dark")
    sidebar.theme_toggle.click()
    assert seen == ["dark", "light"]
    assert sidebar.theme_toggle.toolTip() == "Switch to Light"


def test_collapsing_leaves_a_56px_rail_and_says_so(sidebar):
    seen = []
    sidebar.expandedChanged.connect(seen.append)
    sidebar.collapse_button.click()
    QApplication.processEvents()
    assert seen == [False]
    assert sidebar.width() == 56
    assert not sidebar.rail.is_expanded()
    assert sidebar.expand_button.isVisible()
    assert not sidebar.collapse_button.isVisible()
    assert sidebar.connection_icon.isVisible()
    assert not sidebar.retry_button.isVisible()
    sidebar.expand_button.click()
    assert seen == [False, True]
    assert sidebar.width() == 200


def test_set_expanded_is_silent(sidebar):
    """Only the operator's click is a preference worth saving."""
    seen = []
    sidebar.expandedChanged.connect(seen.append)
    sidebar.set_expanded(False)
    assert seen == []


def test_client_settings_asks_and_can_be_disabled(sidebar):
    asked = []
    sidebar.settingsRequested.connect(lambda: asked.append(1))
    sidebar.settings_button.click()
    assert asked == [1]
    sidebar.set_settings_enabled(False)
    assert not sidebar.settings_button.isEnabled()


def test_the_sidebar_repaints_on_a_theme_change(sidebar):
    """Its own sheet outranks the app's, so it has to re-run on a toggle."""
    from gui.theme_manager import get_theme_manager

    manager = get_theme_manager()
    start = "dark" if manager.is_dark_theme() else "light"
    other = "light" if start == "dark" else "dark"
    try:
        manager.set_theme(other)
        QApplication.processEvents()
        assert current_tokens().surface_sunken in sidebar.styleSheet()
        assert current_tokens().name == other
    finally:
        manager.set_theme(start)
```

- [ ] **Step 2: Run to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_sidebar.py`
Expected: FAIL (`ModuleNotFoundError: gui.components.sidebar`).

- [ ] **Step 3: Implement** `gui/components/sidebar.py`:

```python
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
        self.header.setFixedHeight(44)
        header = QHBoxLayout(self.header)
        header.setContentsMargins(8, 0, 8, 0)
        header.setSpacing(8)
        self.mark = QLabel(self.header)
        self.mark.setObjectName("SidebarMark")
        self.mark.setFixedSize(28, 28)
        self.mark.setAlignment(Qt.AlignCenter)
        self.title = QLabel("Fulfilment Tool", self.header)
        self.title.setMinimumWidth(0)
        self.collapse_button = self._header_button("Collapse sidebar", 28, 28)
        self.expand_button = self._header_button("Expand sidebar", 40, 32)
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

        self.theme_toggle = self._header_button("", 40, 32)
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

    def _header_button(self, tip: str, width: int, height: int) -> QToolButton:
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
```

Notes for the implementer:
- `on_theme_changed(self, self._apply_theme)` calls `_apply_theme` immediately. Every widget it touches must
  exist before that line, and they do.
- `set_expanded(True)` runs at the end of `__init__`. Tests call `sidebar.show()` before checking `isVisible()`.
- The elided path uses the label's font before `path_label.setStyleSheet` changes it to Consolas. If the render
  in Task 7 shows the text running past its box, call `self.path_label.ensurePolished()` before building
  `QFontMetrics`.

- [ ] **Step 4: Run** `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_sidebar.py`. Expected: PASS.

- [ ] **Step 5: Commit.** Message: `sidebar: header, NavRail and a footer for settings, theme and connection (phase 1 §4.2)`

---

### Task 5: Wire the sidebar in and delete the status bar

**Files:**
- Modify: `gui/ui_manager.py`: imports (lines 1-26), `create_widgets` (lines 160-225), `_on_connection_changed`
  (lines 226-260)
- Modify: `gui/main_window_pyside.py`: `update_ui_state` (the four `showMessage` calls around line 513) and the
  two `if hasattr(self, "statusBar"):` blocks (around lines 575 and 654)
- Modify: `gui/actions_handler.py` (the two `statusBar().showMessage` calls around lines 822 and 830)
- Modify: `gui/components/commandbar.py` (`_apply_theme` background, and the client selector's placeholder)
- Modify: `tests/test_shell.py`, `tests/test_first_run.py`, `tests/test_label_pdf_invalidation.py`

**Interfaces:**
- Consumes: `Sidebar` and `SIDEBAR_WIDTH` (Task 4).
- Produces: `self.mw.sidebar` (a `Sidebar`), `self.mw.nav_rail` (the same object as `self.mw.sidebar.rail`), and
  the module-level `gui.ui_manager._shell_settings() -> QSettings` plus `_COLLAPSED_KEY = "shell/sidebar_collapsed"`.
  Task 6 uses these.

- [ ] **Step 1: Write the failing tests**

In `tests/test_shell.py`, replace `test_the_shell_leaves_the_page_the_size_later_screens_assume` with:

```python
def test_the_shell_leaves_the_page_the_size_later_screens_assume(main_window):
    """1366x768 minus the 200px sidebar and the 48px command bar; no status bar.

    main_tabs keeps the 5px inset every Qt page was laid out against (phase 1
    spec section 5.1), so the page is 1366 - 200 - 10 wide.
    """
    from PySide6.QtWidgets import QStatusBar

    main_window.resize(1366, 768)
    QApplication.processEvents()

    assert main_window.sidebar.width() == 200
    assert main_window.nav_rail is main_window.sidebar.rail
    assert main_window.command_bar.height() == 48
    assert main_window.findChild(QStatusBar) is None
    assert main_window.main_tabs.width() == 1156
```

Add to `tests/test_shell.py`:

```python
def test_the_sidebar_footer_names_the_server(main_window, tmp_path):
    assert main_window.sidebar.connection_label.text() == "Server connected"
    assert main_window.sidebar.path_label.toolTip() == str(tmp_path)


def test_retry_rechecks_the_connection(main_window):
    """Retry is the Server Connection dialog's own recheck: it re-emits."""
    seen = []
    main_window.connectionChanged.connect(seen.append)
    main_window.sidebar.retryRequested.emit()
    assert seen == [True]


def test_the_sidebar_asks_for_client_settings(main_window):
    calls = []
    main_window.actions_handler.open_settings_window = lambda: calls.append(1)
    main_window.sidebar.settings_button.setEnabled(True)
    main_window.sidebar.settings_button.click()
    assert calls == [1]


def test_the_command_bar_sits_on_the_sunken_plane(main_window):
    from shared.theme import current_tokens

    assert current_tokens().surface_sunken in main_window.command_bar.styleSheet()
    assert main_window.command_bar.client_selector.placeholderText() == "Choose a client"
```

In `tests/test_first_run.py`, replace `test_the_status_bar_says_so_too` with:

```python
def test_the_sidebar_says_so_too(offline_window):
    sidebar = offline_window.sidebar
    assert sidebar.connection_label.text() == "Server unreachable"
    assert sidebar.retry_button.isVisible()
```

In `tests/test_label_pdf_invalidation.py::test_empty_list_says_so_instead_of_report_saved`, replace the `msg = ...`
line with:

```python
    msg = h.mw.results_bridge.raise_toast.call_args[0][0]
```

Also search that file and `tests/` for any other `statusBar.return_value.showMessage` and change each one the
same way:
`grep -rn "statusBar" tests`.

- [ ] **Step 2: Run to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_shell.py tests/test_first_run.py tests/test_label_pdf_invalidation.py`
Expected: the new and changed tests FAIL (`AttributeError: 'MainWindow' object has no attribute 'sidebar'`, and a
status bar is found).

- [ ] **Step 3: Implement**

`gui/ui_manager.py` imports: add `from PySide6.QtCore import QSettings` to the existing `QtCore` import (it
becomes `from PySide6.QtCore import QSettings, Qt`). Add `from gui.components.sidebar import Sidebar`. Delete
`from shared.navrail import NavRail`. Change `from shared.theme import StatusChip, on_theme_changed` to
`from shared.theme import on_theme_changed`. Below the imports, near `_SCREEN_ACTIONS`, add:

```python
# The sidebar's collapsed state is this PC's, like the theme -- same QSettings
# pair theme_manager and log_viewer use. A function so tests can point it at
# an INI file under tmp_path.
_COLLAPSED_KEY = "shell/sidebar_collapsed"


def _shell_settings() -> QSettings:
    return QSettings("ShopifyFulfillmentTool", "FulfillmentApp")
```

In `create_widgets`, replace everything from `# The rail is the outermost chrome` through
`main_horizontal.addWidget(right_side, 1)` with:

```python
        # The sidebar is the outermost chrome, left of everything else. Its
        # NavRail keeps the name nav_rail, so every call site stays as it was.
        self.mw.sidebar = Sidebar(self.mw)
        self.mw.nav_rail = self.mw.sidebar.rail
        main_horizontal.addWidget(self.mw.sidebar)

        right_side = QWidget()
        right_layout = QVBoxLayout(right_side)
        right_layout.setSpacing(0)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # The command bar runs edge to edge; its own border-bottom is the divider.
        right_layout.addWidget(self._create_command_bar())

        # The pages keep the 5px inset they were laid out against (phase 1 §5.1).
        page_area = QWidget()
        page_layout = QVBoxLayout(page_area)
        page_layout.setSpacing(5)
        page_layout.setContentsMargins(5, 5, 5, 5)

        # 9.25: a failure waits here, under the command bar, until dismissed.
        logs_index = self._RAIL_LABELS.index("Logs")
        self.mw.error_banner = ErrorBanner(
            open_logs=lambda: self.mw.main_tabs.setCurrentIndex(logs_index)
        )
        page_layout.addWidget(self.mw.error_banner)

        self._create_tabs()
        page_layout.addWidget(self.mw.main_tabs, 1)

        right_layout.addWidget(page_area, 1)
        main_horizontal.addWidget(right_side, 1)

        self._wire_sidebar()
```

Replace the `on_theme_changed(self.mw, lambda _t: self._refresh_icons())` line with:

```python
        on_theme_changed(self.mw, self._on_theme)
```

Delete the whole status-bar block (from `# Status bar: a fixed-height chip` through
`self.mw.statusBar().addPermanentWidget(self.mw.connection_chip)`). Keep
`self.mw.connectionChanged.connect(self._on_connection_changed)`.

Add these methods to `UIManager`:

```python
    def _wire_sidebar(self) -> None:
        """The footer's three requests, and the collapse this PC remembers."""
        sidebar = self.mw.sidebar
        sidebar.settingsRequested.connect(
            lambda: self.mw.actions_handler.open_settings_window()
        )
        sidebar.themeRequested.connect(
            lambda name: get_theme_manager().set_theme(name)
        )
        sidebar.retryRequested.connect(self.mw.recheck_connection)
        sidebar.expandedChanged.connect(
            lambda expanded: _shell_settings().setValue(_COLLAPSED_KEY, not expanded)
        )
        collapsed = _shell_settings().value(_COLLAPSED_KEY, False, type=bool)
        sidebar.set_expanded(not collapsed)

    def _on_theme(self, tokens) -> None:
        self._refresh_icons()
        self.mw.sidebar.set_theme_name(tokens.name)
```

In `_on_connection_changed`, delete the `for index in self._OFFLINE_RAIL_ITEMS:` loop, the
`if not connected: self.mw.nav_rail.set_current(0)` lines under it, and the `self.mw.connection_chip.set_status(...)`
call along with its comment. Also delete the `_OFFLINE_RAIL_ITEMS` class attribute. In place of the chip call,
add:

```python
        self.mw.sidebar.set_connection(
            connected, str(self.mw.profile_manager.base_path)
        )
```

Keep this Task's rail behaviour correct for now by adding the following at the top of `_on_connection_changed`.
Task 6 replaces it with `self._refresh_nav()`:

```python
        for index in (1, 2, 4):
            self.mw.nav_rail.button(index).setEnabled(connected)
        if not connected:
            self.mw.nav_rail.set_current(0)
```

`gui/main_window_pyside.py`: in `update_ui_state`, delete the `# Update status bar` comment and the whole
`if has_analysis: ... else: self.statusBar().showMessage(...)` chain after it. `has_client` is then used
nowhere. Delete its assignment too, unless ruff shows another use. Delete both
`if hasattr(self, "statusBar"): self.statusBar().showMessage(...)` blocks (around lines 575 and 654).

`gui/actions_handler.py`: replace the two `self.mw.statusBar().showMessage(<text>, 5000)` calls with
`self._results_toast(<text>)`, keeping the text exactly. Replace the banner comment above them with
`# Reports are generated from Results, where the toast lives (ADR 0007).`.

`gui/components/commandbar.py`: in `_apply_theme`, change `theme.surface_raised` to `theme.surface_sunken`. After
`self.client_selector.setModel(...)`, add `self.client_selector.setPlaceholderText("Choose a client")`.

Confirm nothing still calls the status bar: `grep -rn "statusBar()" gui shopify_tool` must print nothing.

- [ ] **Step 4: Run**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_shell.py tests/test_first_run.py tests/test_label_pdf_invalidation.py tests/test_commandbar_states.py tests/test_components_commandbar.py tests/test_report_filters.py tests/test_packing_lists.py`
Expected: PASS.

- [ ] **Step 5: Commit.** Message: `shell: sidebar replaces the rail and the status bar (phase 1 §5.1-5.3)`

---

### Task 6: One enabling rule, the overflow, the shortcuts dialog

**Files:**
- Modify: `gui/ui_manager.py` (`_refresh_nav`, `_on_connection_changed`, `_populate_overflow`)
- Modify: `gui/main_window_pyside.py` (`update_ui_state` calls `_refresh_nav`; `_focus_results_search` guard)
- Create: `gui/shortcuts_dialog.py`
- Create: `tests/test_shortcuts_dialog.py`
- Modify: `tests/test_shell.py`, `tests/test_first_run.py`, `tests/test_settings_entry_points.py`

**Interfaces:**
- Consumes: `self.mw.sidebar`, `self.mw.nav_rail`, `_shell_settings`, `_COLLAPSED_KEY` (Task 5).
- Produces: `UIManager._refresh_nav() -> None`, and `gui.shortcuts_dialog.SHORTCUTS: tuple[tuple[str, str], ...]`
  and `ShortcutsDialog(QDialog)`.

- [ ] **Step 1: Write the failing tests**

Add a helper and tests to `tests/test_shell.py`:

```python
def _enabled(window):
    return [i for i in range(5) if window.nav_rail.button(i).isEnabled()]


def _pick_client(window, client_id="M"):
    window.profile_manager.create_client_profile(client_id, f"Client {client_id}")
    window.command_bar.set_clients([client_id])
    window.command_bar.set_current_client(client_id)
    QApplication.processEvents()
    # The client's config may finish loading after this returns; the rule is
    # what is under test, so run the refresh the load would end with.
    window.update_ui_state()


def _go_offline(window):
    # _refresh_nav asks is_connected(), exactly as the real emitter does.
    window.profile_manager.is_network_available = False
    window.connectionChanged.emit(False)


def test_with_no_client_only_setup_and_logs_are_offered(main_window):
    assert main_window.current_client_id is None
    assert _enabled(main_window) == [0, 3]


def test_results_waits_for_an_analysis(main_window):
    import pandas as pd

    _pick_client(main_window)
    assert _enabled(main_window) == [0, 2, 3, 4]
    assert "available after Run analysis" in main_window.nav_rail.button(1).toolTip()
    assert "Analysis Results" in main_window.nav_rail.button(1).toolTip()

    main_window.analysis_results_df = pd.DataFrame({"Order_Number": ["1"]})
    main_window.update_ui_state()
    assert _enabled(main_window) == [0, 1, 2, 3, 4]
    assert "available after" not in main_window.nav_rail.button(1).toolTip()


def test_the_jump_to_results_after_a_run_survives_the_rule(main_window):
    """actions_handler (after a run) and load_existing_session (a past session
    with an analysis) both set the frame, jump to Results, then refresh. The
    rule must not bounce that jump back to Setup."""
    import pandas as pd

    _pick_client(main_window)
    main_window.analysis_results_df = pd.DataFrame({"Order_Number": ["1"]})
    main_window.main_tabs.setCurrentIndex(1)
    main_window.update_ui_state()
    assert main_window.main_tabs.currentIndex() == 1
    assert main_window.nav_rail.button(1).isEnabled()


def test_going_offline_on_browse_returns_to_setup(main_window):
    _pick_client(main_window)
    main_window.main_tabs.setCurrentIndex(2)
    _go_offline(main_window)
    assert main_window.main_tabs.currentIndex() == 0


def test_going_offline_on_logs_stays_on_logs(main_window):
    main_window.main_tabs.setCurrentIndex(3)
    _go_offline(main_window)
    assert main_window.main_tabs.currentIndex() == 3


def test_ctrl_f_does_not_open_a_results_page_that_is_not_offered(main_window):
    assert not main_window.nav_rail.button(1).isEnabled()
    main_window._focus_results_search()
    assert main_window.main_tabs.currentIndex() == 0


def test_client_settings_needs_a_client(main_window):
    assert not main_window.sidebar.settings_button.isEnabled()
    _pick_client(main_window)
    assert main_window.sidebar.settings_button.isEnabled()


def test_the_overflow_keeps_only_what_the_sidebar_does_not(main_window):
    menu = main_window.command_bar.overflow
    texts = [a.text() for a in menu.actions() if not a.isSeparator()]
    assert texts == [
        "No client",
        "New session…",
        "THIS PC",
        "Server connection…",
        "Keyboard shortcuts…",
    ]
    assert not any(a.isCheckable() for a in menu.actions())


def test_collapsing_is_remembered_on_this_pc(tmp_path, monkeypatch):
    from PySide6.QtCore import QSettings

    import gui.ui_manager as ui

    ini = str(tmp_path / "shell.ini")
    monkeypatch.setattr(ui, "_shell_settings", lambda: QSettings(ini, QSettings.IniFormat))
    monkeypatch.setenv("FULFILLMENT_SERVER_PATH", str(tmp_path))
    from gui.main_window_pyside import MainWindow

    first = MainWindow()
    first.show()
    QApplication.processEvents()
    first.sidebar.collapse_button.click()
    assert QSettings(ini, QSettings.IniFormat).value(ui._COLLAPSED_KEY, type=bool) is True
    first.close()

    second = MainWindow()
    second.show()
    QApplication.processEvents()
    try:
        assert not second.sidebar.is_expanded()
        assert second.sidebar.width() == 56
        # Collapsed, the tooltip is the only place a destination is named.
        assert "Session Setup" in second.nav_rail.button(0).toolTip()
    finally:
        second.close()
```

Update `test_clicking_the_rail_moves_the_page` in `tests/test_shell.py`, because destinations are now gated:

```python
@pytest.mark.parametrize("index", range(5))
def test_clicking_the_rail_moves_the_page(main_window, index):
    # The binding, not the gate: the gate has its own tests above.
    main_window.nav_rail.button(index).setEnabled(True)
    main_window.nav_rail.button(index).click()
    assert main_window.main_tabs.currentIndex() == index
```

In `tests/test_first_run.py`, replace `test_every_rail_item_is_enabled_once_the_share_answers` with:

```python
def test_the_share_answering_offers_what_needs_no_client(online_window):
    """Phase 1 spec section 5.4: Browse and Tools need a client, Results an
    analysis. Setup and Logs are always offered."""
    rail = online_window.nav_rail
    assert [i for i in range(5) if rail.button(i).isEnabled()] == [0, 3]
```

In `tests/test_settings_entry_points.py::test_settings_buttons_are_labelled_settings`, change the docstring and
the source file it reads:

```python
def test_settings_buttons_are_labelled_settings():
    """Settings opens SettingsWindow from one entry point: the sidebar footer's
    "Client settings" (UI refresh phase 1, spec section 4.2), which replaced the
    command-bar overflow item. Object config, not a screen action."""
    from pathlib import Path

    import gui.components.sidebar as sidebar
    import gui.ui_manager as mod

    source = Path(mod.__file__).read_text()
    assert source.count('QPushButton("Settings")') == 0
    assert '"Client settings…"' not in source
    assert 'QPushButton("Client Settings")' not in source
    assert '"Client Settings",' not in source
    assert '"Client settings"' in Path(sidebar.__file__).read_text()
```

Create `tests/test_shortcuts_dialog.py`:

```python
"""The Keyboard shortcuts list must stay true to what the window binds."""

import pytest
from PySide6.QtGui import QShortcut
from PySide6.QtWidgets import QApplication

from gui.shortcuts_dialog import SHORTCUTS, ShortcutsDialog


@pytest.fixture
def main_window(tmp_path, monkeypatch):
    monkeypatch.setenv("FULFILLMENT_SERVER_PATH", str(tmp_path))
    from gui.main_window_pyside import MainWindow

    win = MainWindow()
    win.show()
    QApplication.processEvents()
    yield win
    win.close()


def _listed_keys():
    keys = []
    for combo, _action in SHORTCUTS:
        if combo == "Ctrl+1 … Ctrl+5":
            keys += [f"Ctrl+{n}" for n in range(1, 6)]
        else:
            keys.append(combo)
    return keys


def test_every_listed_shortcut_is_bound(main_window):
    bound = {s.key().toString() for s in main_window.findChildren(QShortcut)}
    missing = [k for k in _listed_keys() if k not in bound]
    assert missing == []


def test_the_dialog_shows_every_row(qapp):
    from PySide6.QtWidgets import QLabel

    dialog = ShortcutsDialog()
    try:
        assert dialog.windowTitle() == "Keyboard shortcuts"
        texts = {label.text() for label in dialog.findChildren(QLabel)}
        for combo, action in SHORTCUTS:
            assert combo in texts
            assert action in texts
    finally:
        dialog.deleteLater()
```

- [ ] **Step 2: Run to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_shell.py tests/test_first_run.py tests/test_settings_entry_points.py tests/test_shortcuts_dialog.py`
Expected: the new tests FAIL.

- [ ] **Step 3: Implement**

`gui/shortcuts_dialog.py`:

```python
"""Keyboard shortcuts, from the command-bar overflow (phase 1 spec section 5.7).

SHORTCUTS is hand-kept; tests/test_shortcuts_dialog.py fails when a row names a
key the main window no longer binds.
"""

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLabel, QVBoxLayout

from shared.theme import current_tokens

SHORTCUTS = (
    ("Ctrl+1 … Ctrl+5", "Go to Setup, Results, Browse, Logs, Tools"),
    ("Ctrl+R", "Run analysis"),
    ("Ctrl+F", "Search results"),
    ("Ctrl+Z", "Undo the last change"),
)


class ShortcutsDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Keyboard shortcuts")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        mono = current_tokens().font_family_mono
        for combo, action in SHORTCUTS:
            keys = QLabel(combo)
            keys.setStyleSheet(f"font-family: {mono};")
            form.addRow(keys, QLabel(action))
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
```

`gui/ui_manager.py`: add `_refresh_nav`:

```python
    def _refresh_nav(self) -> None:
        """The one rule for which destinations the rail offers. Phase 1 spec §5.4.

        Setup and Logs always: Logs is where an operator reads why the server
        is unreachable. Browse and Tools need the share and a client; Results
        needs an analysis. Disabled, never hidden.
        """
        connected = self.mw.is_connected()
        has_client = bool(self.mw.current_client_id)
        analysed = self.mw.analysis_results_df is not None
        offered = (
            True,
            connected and analysed,
            connected and has_client,
            True,
            connected and has_client,
        )
        rail = self.mw.nav_rail
        for index, on in enumerate(offered):
            rail.button(index).setEnabled(on)
        label, tip = self._TAB_LABELS[1], self._TAB_TOOLTIPS[1]
        rail.button(1).setToolTip(
            f"{label} — {tip}"
            if analysed
            else f"{label} — available after Run analysis (Ctrl+2)"
        )
        self.mw.sidebar.set_settings_enabled(connected and has_client)
        if not offered[rail.current_index()]:
            rail.set_current(0)
```

In `_on_connection_changed`, replace the temporary block from Task 5 (the `for index in (1, 2, 4):` loop and the
`if not connected: set_current(0)`) with `self._refresh_nav()`, and keep the rest of the method.

In `_populate_overflow`, delete the `"Client settings…"` item (both of its lines) and the `current = ...` /
`menu.add_choice_group(...)` lines. After `menu.add_item("Server connection…", self._open_connection_settings)`,
add:

```python
        menu.add_item("Keyboard shortcuts…", lambda: ShortcutsDialog(self.mw).exec())
```

Add `from gui.shortcuts_dialog import ShortcutsDialog` to the imports. Update the docstring's first line to
`"""New session for the client, then this PC's server and shortcuts. Phase 1 spec §5.6.`. The sidebar owns
Client settings and the theme now.

`gui/main_window_pyside.py`:
- At the end of `update_ui_state`, add `self.ui_manager._refresh_nav()`.
- At the top of `_focus_results_search`, add:

```python
        if not self.nav_rail.button(1).isEnabled():
            return  # Results is not offered until an analysis exists (phase 1 §5.4)
```

- [ ] **Step 4: Run**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_shell.py tests/test_first_run.py tests/test_settings_entry_points.py tests/test_shortcuts_dialog.py tests/test_session_setup_layout.py`
Expected: PASS. If `test_resuming_a_past_session_reaches_the_session_state` or any analysis-finished test fails
because the current index bounced to 0, check the order: `analysis_results_df` has to be set before
`update_ui_state()` runs. Both call sites (`actions_handler` about line 276, `main_window_pyside` about line 1025)
already set it first, and `_refresh_nav` must not break that.

- [ ] **Step 5: Commit.** Message: `shell: one rule for which destinations are offered; overflow slimmed; shortcuts dialog (phase 1 §5.4-5.7)`

---

### Task 7: Glossary, visual check, full gate

**Files:**
- Modify: `CONTEXT.md` (§ Shell, lines ~220-233)

- [ ] **Step 1: Update `CONTEXT.md` § Shell.** Replace the **Shell**, **Destination** and **Overflow** entries and
  add **Sidebar** between Shell and Destination:

```markdown
**Shell** — the chrome around every screen: the sidebar, the command bar and
the page. Not a screen itself, and it never scrolls.

**Sidebar** — the shell's left column: the destinations, and a footer holding
what configures the client and this PC (Client settings, the theme, the server
connection). It collapses to a 56px **rail**, and that choice is saved per PC.

**Destination** — a place the sidebar navigates to and stays on. The sidebar
holds destinations in its list and configuration only in its footer, never
mixed.

**Overflow** — the menu beside an object holding what configures it.
Qualified when the scope matters: the **command-bar overflow** holds what the
sidebar footer does not (New session, the server connection, the keyboard
shortcuts); the **screen overflow** holds actions scoped to the screen you are
on.
```

- [ ] **Step 2: Render and look.** Write this script to your job's tmp dir as `render_shell.py` and run it with
  `QT_QPA_PLATFORM=offscreen PYTHONPATH=. .venv/bin/python <path>/render_shell.py <out dir>`:

```python
import os
import sys
import tempfile
from pathlib import Path

from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
os.environ["FULFILLMENT_SERVER_PATH"] = tempfile.mkdtemp()
app = QApplication([])
from gui.main_window_pyside import MainWindow  # noqa: E402
from gui.theme_manager import get_theme_manager  # noqa: E402

win = MainWindow()
win.resize(1366, 768)
win.show()
manager = get_theme_manager()
start = "dark" if manager.is_dark_theme() else "light"
for theme in ("light", "dark"):
    manager.set_theme(theme)
    for expanded in (True, False):
        for connected in (True, False):
            win.sidebar.set_expanded(expanded)
            win.sidebar.set_connection(connected, os.environ["FULFILLMENT_SERVER_PATH"])
            app.processEvents()
            image = QImage(win.size(), QImage.Format_ARGB32)
            win.render(image)
            name = f"{theme}-{'wide' if expanded else 'rail'}-{'ok' if connected else 'down'}.png"
            image.save(str(out / name))
manager.set_theme(start)
win.close()
```

  Open all eight PNGs with the Read tool. Compare `light-wide-ok.png` with
  `docs/design/ui-refresh/mockups/renders/app-shell.png`. Check the sidebar layout, the active item's white plane
  and bold label, the sunken command bar, the footer order (Client settings, Light/Dark, connection), the elided
  path, Retry in the `down` images, and a readable dark theme. Fix anything that differs from spec §4.2 and is
  not listed in spec §7. Keep `light-wide-ok.png` and `dark-rail-down.png` for the PR body.

- [ ] **Step 3: Full gate**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
Expected: everything passes except the three pre-existing `tests/test_label_printing.py::TestImageToZpl` failures.
Run: `.venv/bin/ruff check .` and expect no errors. (If `ruff` is not in `.venv/bin`, use `ruff check .`.)

- [ ] **Step 4: Refresh the graph.** Run `graphify update .` (CLAUDE.md: always after modifying code).

- [ ] **Step 5: Commit.** Message: `docs: CONTEXT.md shell glossary follows the sidebar (phase 1 §6)`

---

## PR notes (Stage C)

Title: `UI refresh: mockups, 9-phase roadmap, phase 1 (sidebar + Polaris palette)`. The body must say:
- what is in it (docs: mockups, roadmap, ADR 0018, spec, plan; code: phase 1)
- **Packing Tool:** `shared/theme.py` (palette, disabled buttons, four tokens), `shared/navrail.py` (opt-in
  sidebar mode, default unchanged) and five glyphs reach it at its next `sync_shared.py`. It can hold the sync
  until it wants the new look, and its mirrored floor test needs no change because no floor moved.
- the three pre-existing `test_label_printing.py::TestImageToZpl` failures on `origin/main` (Pillow 12.3.0),
  which this PR does not touch
- the two renders from Task 7
- the owner adds the Todoist tasks for phases 2 to 9 from `docs/design/ui-refresh/roadmap.md`
