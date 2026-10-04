# UI Refresh Quickfixes and Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix four defects left by UI-refresh phases 1–9 (session closing, border seams, the boxed Results
checkbox, the two-step theme switch) and run a verification and stress pass over the refreshed app.

**Architecture:** Each defect has one root cause in one file (see the spec's §2 table), so each fix is a
small change at that seam plus a test that fails without it. The theme switch gains a small coordinator in
`gui/web_page.py` that themes the visible web page first and repaints the Qt chrome when the page confirms.
The verification pass is a kept stress script plus a throwaway render sweep; its small findings are fixed here,
the rest become GitHub issues.

**Tech Stack:** Python 3.14, PySide6 (Qt Widgets + QtWebEngine + QWebChannel), plain JS/CSS in `gui/web/`,
pytest + pytest-qt.

**Spec:** `docs/superpowers/specs/2026-10-04-ui-refresh-quickfixes-verifying-design.md` — read it first; §2
has the measured root causes.

## Global Constraints

- Gate: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`, plus `ruff check .`. Both green before the
  last commit.
- `python` is not on `PATH`: always `.venv/bin/python`. If `.venv` is missing in the worktree, run
  `./scripts/setup_venv.sh`.
- The pytest-guard hook refuses Bash text containing "pytest" other than the plain run form above (a path
  argument after `-q` is the plain form: `... -m pytest -q tests/test_x.py`). Write test files with Write/Edit,
  never with shell heredocs.
- `/usr/bin/git`, one plain git command per Bash call, no `&&`/`;`. Commit with
  `git commit -F <absolute path to a message file>`. Never commit to `main`; the branch is
  `dr/22-ui-refresh-quickfixes-verifying`.
- Nothing in `shared/` changes. If a finding seems to need it, it is not "small": file an issue.
- No hardcoded colours, no `transition`/`transform`/`opacity`/gradients on either tier (`shared/style_lint.py`
  enforces this; ADR 0016 §3). Colours come from theme tokens (`current_tokens()` in Python, `var(--…)` in CSS).
- No UI calls from background threads.
- After modifying code run `graphify update .` (skip silently if `graphify-out/` is absent in the worktree).
- Any script that builds a `MainWindow` outside pytest must set `QT_QPA_PLATFORM=offscreen` and
  `FULFILLMENT_SERVER_PATH` to a temp dir **before** importing `gui`, and must stub
  `ThemeManager._save_theme_preference` so the developer's saved theme is not overwritten.
- `actions_handler.open_settings_window()` opens a modal window: calling it from a script blocks forever.
  Build `gui.settings.window.SettingsWindow` directly, as `tests/conftest.py::window` does.

## Review Focus

1. **Re-picking the client after its config failed to load** — the bar now stays silent for the client it last
   announced; a different client and back must still reload it. (Task 1 test `test_a_real_change_still_emits`
   covers there-and-back.)
2. **A second theme click during the 150 ms wait** — must end on the last theme asked for, with exactly one
   `set_theme` per switch. (Task 4 test `test_a_second_switch_wins`.)
3. **A page that never acknowledges** (hidden mid-switch, no handler, crashed renderer) — the theme must still
   change after the timeout. (Task 4 test `test_no_ack_falls_back_to_the_timeout`.)
4. **Additional columns whose field names contain spaces, colons or kit class words** (`Tracking code`,
   `VAT: card`) — one `col-…` class, no stray tokens. (Task 3 test `test_an_extra_column_gets_one_safe_class`.)
5. **Sidebar collapsed** — the header is still `BAR_HEIGHT` tall and the expand button still fits (it is 32px
   high). (Task 2 test `test_the_header_meets_the_bar_collapsed_too`.)

## File Structure

| File | Change |
|---|---|
| `gui/components/commandbar.py` | `_announced` dedupe in `_on_client_changed`; `session_button` sheet |
| `gui/components/sidebar.py` | header height = `BAR_HEIGHT` |
| `gui/ui_manager.py` | `PageStack` object name + pane sheet; sidebar toggle → `switch_theme` |
| `gui/theme_manager.py` | `ThemeManager.tokens_for(name)` |
| `gui/web_page.py` | `themeApplied` slot, `themePainted` signal, page registry, backing colour, `switch_theme` |
| `gui/web/results.js`, `gui/web/results.css` | `colClass()`; `col-` selectors |
| `gui/web/{setup,results,browse,logs,tools,settings}.js` | acknowledge a theme change |
| `scripts/stress_ui.py` | new: the stress script |
| `tests/test_quickfix_session.py`, `tests/test_quickfix_seams.py`, `tests/test_theme_switch.py` | new |
| `tests/test_results_document.py`, `tests/test_results_selection_bar.py`, others found by grep | `col-` selectors |
| `docs/design/ui-refresh/renders/quickfixes/` | new: after-fix renders |

---

### Task 1: The session survives a client-list refresh (spec §4.1)

**Files:**
- Modify: `gui/components/commandbar.py` (`__init__` ~line 129, `_on_client_changed` ~line 384)
- Test: `tests/test_quickfix_session.py` (create)

**Interfaces:**
- Produces: `CommandBar.clientChanged(str)` now fires only when the client differs from the last one fired.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_quickfix_session.py`:

```python
"""Quickfix: the bar announces a client only when it changed (spec §4.1)."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from gui.components.commandbar import ROW_ACTION, CommandBar


def _activate_action(bar, label):
    """What a click on an action row does: the box lands on it, then activated()."""
    model = bar.client_selector.model()
    for i in range(model.rowCount()):
        item = model.item(i)
        if item.data(Qt.UserRole) == ROW_ACTION and item.data(Qt.UserRole + 1) == label:
            bar.client_selector.setCurrentIndex(i)
            bar.client_selector.activated.emit(i)
            return
    raise AssertionError(f"no action row {label!r}")


def _action_labels(bar):
    model = bar.client_selector.model()
    return [
        model.item(i).data(Qt.UserRole + 1)
        for i in range(model.rowCount())
        if model.item(i).data(Qt.UserRole) == ROW_ACTION
    ]


@pytest.fixture
def bar(qapp):
    bar = CommandBar()
    bar.set_clients(["A", "B"])
    bar.set_current_client("A")
    return bar


def test_an_action_row_does_not_re_announce_the_client(bar):
    seen = []
    bar.clientChanged.connect(seen.append)
    for label in _action_labels(bar):
        _activate_action(bar, label)
    assert seen == []
    assert bar.current_client() == "A"


def test_a_refresh_does_not_re_announce_the_client(bar):
    seen = []
    bar.clientChanged.connect(seen.append)
    bar.set_clients(["A", "B", "C"])
    assert seen == []
    assert bar.current_client() == "A"


def test_a_real_change_still_emits(bar):
    seen = []
    bar.clientChanged.connect(seen.append)
    bar.set_current_client("B")
    bar.set_current_client("B")
    bar.set_current_client("A")
    assert seen == ["B", "A"]


@pytest.fixture
def main_window(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("FULFILLMENT_SERVER_PATH", str(tmp_path))
    from gui.main_window_pyside import MainWindow

    win = MainWindow()
    win.show()
    QApplication.processEvents()
    yield win
    win.close()


def test_an_open_session_survives_the_client_menu(main_window, qtbot, monkeypatch):
    win = main_window
    win.profile_manager.create_client_profile("M", "Client M")
    win.command_bar.set_clients(["M"])
    win.command_bar.set_current_client("M")
    qtbot.waitUntil(lambda: win.active_profile_config is not None, timeout=5000)
    qtbot.waitUntil(lambda: not win._client_load_workers, timeout=5000)

    win.session_path = "/tmp/session-under-test"
    resets = []
    monkeypatch.setattr(win, "_reset_session_state", lambda: resets.append(1))
    # The dialogs are modal; the bar's behaviour is what is under test.
    monkeypatch.setattr(win.client_directory, "open_create_client_dialog", lambda _p: None)
    monkeypatch.setattr(win.client_directory, "open_groups_dialog", lambda _p: None)

    for label in _action_labels(win.command_bar):
        _activate_action(win.command_bar, label)
    win.client_directory.loaded.emit(win.client_directory.gather())
    QApplication.processEvents()
    qtbot.wait(200)  # a wrongly-started client load would land in here

    assert resets == []
    assert win.session_path == "/tmp/session-under-test"
```

If `active_profile_config` is not `None` before a client is chosen (check `MainWindow.__init__`), replace the
first `waitUntil` with `qtbot.waitUntil(lambda: win.current_client_id == "M", timeout=5000)`.

- [ ] **Step 2: Run to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_quickfix_session.py`
Expected: `test_an_action_row…`, `test_a_refresh…` and `test_an_open_session…` FAIL (`seen == ['A', …]`,
`resets == [1, …]`); `test_a_real_change_still_emits` FAILS with `['B', 'B', 'A']` or passes — either is fine.

- [ ] **Step 3: Implement**

In `gui/components/commandbar.py::CommandBar.__init__`, next to `self._restore_client = ""`:

```python
        self._announced = ""  # the last client clientChanged carried
```

Replace the tail of `_on_client_changed` (after the `if not client_id: return`):

```python
        self._restore_client = client_id
        # Putting the box back on the client it already showed -- after an
        # action row, or after a refresh rebuilt the rows -- is not a change.
        # The window resets the open session on every clientChanged.
        if client_id == self._announced:
            return
        self._announced = client_id
        self.clientChanged.emit(client_id)
```

- [ ] **Step 4: Run to verify they pass, then the bar's existing tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_quickfix_session.py tests/test_components_commandbar.py tests/test_commandbar_states.py tests/test_shell.py`
Expected: all PASS. If an existing test picks the same client twice in one bar and expects two emissions, the
test encoded the bug: change its second pick to a different client and say so in the commit message.

- [ ] **Step 5: Commit**

Stage `gui/components/commandbar.py` and `tests/test_quickfix_session.py`. Message:
`Fix: the command bar announces a client only when it changed` + a body line naming the symptom (session closed
on New client / Manage groups / Refresh / pin).

---

### Task 2: The seams (spec §4.2)

**Files:**
- Modify: `gui/ui_manager.py::_create_tabs` (~line 278), `gui/components/sidebar.py:58`,
  `gui/components/commandbar.py::_style_labels` (~line 235)
- Test: `tests/test_quickfix_seams.py` (create)

**Interfaces:**
- Consumes: `BAR_HEIGHT` (int, 48) from `gui/components/commandbar.py`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_quickfix_seams.py`:

```python
"""Quickfix: the page area meets the chrome with no frame (spec §4.2)."""

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QStackedWidget

from gui.components.commandbar import BAR_HEIGHT
from gui.theme_manager import get_theme_manager


@pytest.fixture
def main_window(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("FULFILLMENT_SERVER_PATH", str(tmp_path))
    from gui.main_window_pyside import MainWindow

    win = MainWindow()
    win.resize(1280, 860)
    win.show()
    QApplication.processEvents()
    yield win
    win.close()


def test_the_page_stack_has_no_pane_frame(main_window):
    tabs = main_window.main_tabs
    stack = tabs.findChild(QStackedWidget)
    assert stack.mapTo(tabs, QPoint(0, 0)) == QPoint(0, 0)
    assert stack.size() == tabs.size()


def test_the_sidebar_header_rule_meets_the_bar_rule(main_window):
    assert main_window.sidebar.header.height() == BAR_HEIGHT
    assert main_window.command_bar.height() == BAR_HEIGHT


def test_the_header_meets_the_bar_collapsed_too(main_window):
    main_window.sidebar.set_expanded(False)
    QApplication.processEvents()
    assert main_window.sidebar.header.height() == BAR_HEIGHT
    assert main_window.sidebar.expand_button.height() <= BAR_HEIGHT


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_open_recent_sits_on_the_bar_plane(main_window, theme):
    get_theme_manager().set_theme(theme)
    QApplication.processEvents()
    button = main_window.command_bar.session_button
    image = button.grab().toImage()
    plane = QColor(get_theme_manager().get_current_theme().surface_sunken)
    # Just inside the top-left corner: background, never text.
    assert image.pixelColor(2, image.height() // 2) == plane
```

- [ ] **Step 2: Run to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_quickfix_seams.py`
Expected: FAIL — stack at `QPoint(1, 1)`; header height 44; pixel is `surface`, not `surface_sunken`.

- [ ] **Step 3: Implement**

`gui/ui_manager.py::_create_tabs`, after `self.mw.main_tabs.tabBar().hide()`:

```python
        # With the tab bar hidden this is a page stack, and the app sheet's
        # QTabWidget::pane border would frame every page in a 1px strip.
        self.mw.main_tabs.setObjectName("PageStack")
        self.mw.main_tabs.setStyleSheet("#PageStack::pane { border: 0; }")
```

If the stack is still inset after this, `QTabWidget` in document mode is adding its own base line: also call
`self.mw.main_tabs.setDocumentMode(False)` and re-run the test; keep whichever combination passes.

`gui/components/sidebar.py`: add `from gui.components.commandbar import BAR_HEIGHT` to the imports and replace
`self.header.setFixedHeight(44)` with:

```python
        # The bar's height, so the two rules under them are one line.
        self.header.setFixedHeight(BAR_HEIGHT)
```

(`commandbar.py` does not import `sidebar.py`, so there is no cycle. If `gui/components/__init__.py` import
order raises one, import inside `__init__` instead.)

`gui/components/commandbar.py::_style_labels`, replace
`self.session_button.setStyleSheet(font_css("caption"))` with:

```python
        # The sidebar's tool-button recipe: the app sheet would paint this on
        # `surface`, a white box on the sunken bar.
        self.session_button.setStyleSheet(
            f"QToolButton {{ {font_css('caption')} background-color: transparent;"
            " border: 1px solid transparent;"
            f" border-radius: {theme.radius_md}px; padding: 0px 8px; }}"
            f"QToolButton:hover {{ background-color: {theme.hover}; }}"
        )
```

- [ ] **Step 4: Run to verify they pass, plus the shell and sidebar tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_quickfix_seams.py tests/test_shell.py tests/test_sidebar.py tests/test_components_commandbar.py tests/test_commandbar_states.py`
Expected: PASS. A sidebar/shell test asserting the literal 44 or a page size 2px smaller is asserting the
defect: update the number.

- [ ] **Step 5: Look at it**

Render the window offscreen in both themes (script rules in Global Constraints; `win.grab().save(path)`), read
the PNGs, and confirm: no light strip at the page's top/left edge, one continuous rule at y = 47 across sidebar
and bar, "Open recent" has no box. Delete the script.

- [ ] **Step 6: Commit**

Message: `Fix: the page area meets the sidebar and the bar with no frame`.

---

### Task 3: Column cells get their own class namespace (spec §4.3)

**Files:**
- Modify: `gui/web/results.js` (lines ~441, ~614, ~679), `gui/web/results.css` (lines ~238, ~302, ~320–327 and
  any other `.cell.<key>` / `.head.<key>`)
- Modify tests: `tests/test_results_document.py:514,571`, `tests/test_results_selection_bar.py:137`, and every
  other hit of the grep in Step 3
- Test: add to `tests/test_results_columns.py`

**Interfaces:**
- Produces: JS `colClass(key: string): string` → `"col-" + key` with every character outside
  `[A-Za-z0-9_-]` replaced by `-`. Column keys today: `select, status, order, customer, lines, units, value,
  courier, age, type, reason, country, subtotal, method, internal_tags, shopify_tags, notes, status_note,
  repeat`, and `extra:<field>`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_results_columns.py` (it already imports `_eval`, `_until_js`, `results_lines` and has the
`doc` fixture and `_has_header`; reuse them):

```python
# --- quickfix: cell classes are namespaced (2026-10-04 spec §4.3) -------------

_SELECT_CELL = "document.querySelector('#rows .row .cell.col-select')"


def test_the_select_cell_is_not_styled_as_a_kit_dropdown(qtbot, doc):
    view, _bridge = doc
    style = f"getComputedStyle({_SELECT_CELL})"
    assert _eval(qtbot, view, f"{style}.borderTopWidth") == "0px"
    assert _eval(qtbot, view, f"{style}.display") != "flex"
    assert _eval(qtbot, view, "document.querySelector('#rows .cell.select') === null") is True
    assert _eval(qtbot, view, "document.querySelector('#header .cell.select') === null") is True


def test_an_extra_column_gets_one_safe_class(qtbot, doc):
    view, bridge = doc
    df = results_lines()
    df["Tracking code"] = "T"
    df["VAT: card"] = "V"
    bridge.set_orders(df)
    bridge.set_column_settings({"visible": ["extra:Tracking code", "extra:VAT: card"]})
    _until_js(qtbot, view, _has_header("Tracking code"))
    classes = _eval(
        qtbot,
        view,
        "Array.from(document.querySelectorAll('#header .cell'))"
        ".map((c) => c.className).join('|')",
    )
    assert "col-extra-Tracking-code" in classes
    assert "col-extra-VAT--card" in classes
    for cell in classes.split("|"):
        tokens = cell.split()
        assert "code" not in tokens and "card" not in tokens
        assert sum(t.startswith("col-") for t in tokens) == 1


def test_no_cell_class_is_a_kit_class():
    """A page's cell class named like a kit class takes the kit's box."""
    import re
    from pathlib import Path

    web = Path(__file__).resolve().parent.parent / "gui" / "web"
    kit = set(re.findall(r"(?m)^\.([a-z][a-z0-9-]*)", (web / "kit.css").read_text("utf-8")))
    css = (web / "results.css").read_text("utf-8")
    local = set(re.findall(r"\.(?:cell|head)\.([a-z][a-z0-9_-]*)", css))
    assert local & kit == set()
```

- [ ] **Step 2: Run to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_results_columns.py`
Expected: the three new tests FAIL (`.cell.col-select` is null → JS error/timeout; `select` in kit classes).

- [ ] **Step 3: Implement**

`gui/web/results.js`, directly above `const SELECT_COLUMN`:

```js
// A column's CSS class. Never the bare key: `select` is a kit class, and an
// additional column's key carries the profile's own field name.
function colClass(key) { return "col-" + String(key).replace(/[^A-Za-z0-9_-]/g, "-"); }
```

- `renderHeader`: `cell.className = "cell head " + colClass(col.key) + (col.numeric ? " num" : "");`
- `cellElement`: `cell.className = "cell " + colClass(col.key) + (col.numeric ? " num" : "") + (col.mono ? " mono" : "");`
- click handler: `event.target.closest(".cell.col-select")`

`gui/web/results.css`: rename every selector whose second class is a column key —
`.cell.select`→`.cell.col-select`, `.head.select`→`.head.col-select`, `.cell.status`→`.cell.col-status`,
`.cell.order`→`.cell.col-order`, `.head.value`→`.head.col-value`. Leave state classes alone: `.head.sorted`,
`.head.unmapped`, `.cell.mono`, `.cell.missing`, `.cell.sorted`, `.cell.filler`, `.num`.

Then find every remaining reference (Grep tool, or):
`rg -n "\.(cell|head)\.(select|status|order|customer|lines|units|value|courier|age|type|reason|country|subtotal|method|internal_tags|shopify_tags|notes|status_note|repeat)\b|#header \.select|\.row \.(select|status|order)\b" gui/web tests`
and rename each hit to its `col-` form (known: `tests/test_results_document.py:514` `#header .select input` →
`#header .col-select input`; `:571` `.cell.select` → `.cell.col-select`; `tests/test_results_selection_bar.py:137`;
a `.cell.lines` near `tests/…:694`). Do **not** touch `.select`, `.select-value`, `.select-meta` in
`settings`/`tools`/`test_web_kit` — those are the kit dropdown.

- [ ] **Step 4: Run the Results suites**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_results_columns.py tests/test_results_document.py tests/test_results_selection_bar.py tests/test_results_bridge.py tests/test_results_pane.py tests/test_results_bulk_popover.py tests/test_results_screen.py`
Expected: PASS.

- [ ] **Step 5: Look at it**

Render Results with orders (push a DataFrame like `tests/test_results_screen.py::lines_df` via
`win.analysis_results_df = df; win._update_all_views(); win.update_ui_state(); win.main_tabs.setCurrentIndex(1)`,
spin the event loop ~2 s, `win.grab()`), both themes. Confirm the checkbox column shows a bare 16px box,
centred in its 36px cell, header included. If it is not centred, fix it in `.cell.col-select` (the cell is
`text-align: center; padding: 0`) and re-render. Delete the script.

- [ ] **Step 6: Commit**

Message: `Fix: Results cells use col- classes, so the checkbox cell is not a kit dropdown`.

---

### Task 4: The theme changes in one step (spec §4.4)

**Files:**
- Modify: `gui/theme_manager.py` (`get_current_theme`, ~line 72), `gui/web_page.py`, `gui/ui_manager.py:200-202`,
  `gui/web/setup.js:381`, `gui/web/browse.js:588`, `gui/web/logs.js:433`, `gui/web/tools.js:544`,
  `gui/web/settings.js:620`, `gui/web/results.js::onTheme` (~line 756)
- Test: `tests/test_theme_switch.py` (create)

**Interfaces:**
- Produces:
  - `ThemeManager.tokens_for(name: str) -> ThemeTokens`
  - `PageBridge.themeApplied()` — `@Slot()`, called from JS; emits `PageBridge.themePainted` (`Signal()`)
  - `gui.web_page.switch_theme(name: str) -> None`
  - `gui.web_page.THEME_ACK_TIMEOUT_MS = 150`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_theme_switch.py`:

```python
"""Quickfix: pages take the theme first, the chrome follows (spec §4.4)."""

import pytest
from PySide6.QtGui import QColor
from PySide6.QtWebEngineWidgets import QWebEngineView
from test_results_bridge import _eval, _until_js

from gui import web_page
from gui.browse_bridge import mount_browse_page
from gui.logs_bridge import mount_logs_page
from gui.results_bridge import mount_results_page
from gui.settings.bridge import mount_settings_page
from gui.setup_bridge import mount_setup_page
from gui.theme_manager import get_theme_manager
from gui.tools_bridge import mount_tools_page
from gui.web_page import switch_theme
from shared.theme import theme_css_vars

MOUNTS = {
    "setup": mount_setup_page,
    "results": mount_results_page,
    "browse": mount_browse_page,
    "logs": mount_logs_page,
    "tools": mount_tools_page,
    "settings": mount_settings_page,
}
READY = "document.documentElement.dataset.bridge === 'ready'"


def _mounted(qtbot, mount, show=True):
    view = QWebEngineView()
    qtbot.addWidget(view)
    bridge = mount(view)
    view.resize(900, 600)
    if show:
        view.show()
        _until_js(qtbot, view, READY)
    return view, bridge


def _dark_css():
    return theme_css_vars(get_theme_manager().tokens_for("dark"))


def test_the_visible_page_is_themed_before_the_chrome(qtbot, qapp):
    _view, bridge = _mounted(qtbot, mount_setup_page)
    manager = get_theme_manager()
    # Hold the ack back so the in-between state can be observed.
    bridge.blockSignals(True)
    switch_theme("dark")
    assert bridge.themeCss == _dark_css()
    assert manager.get_current_theme_name() == "light"
    bridge.blockSignals(False)
    bridge.themePainted.emit()
    assert manager.get_current_theme_name() == "dark"


def test_the_page_acknowledges_and_the_chrome_follows(qtbot, qapp):
    _mounted(qtbot, mount_setup_page)
    switch_theme("dark")
    qtbot.waitUntil(
        lambda: get_theme_manager().get_current_theme_name() == "dark", timeout=2000
    )


def test_no_ack_falls_back_to_the_timeout(qtbot, qapp):
    _view, bridge = _mounted(qtbot, mount_setup_page)
    bridge.blockSignals(True)  # the page's themeApplied never arrives
    switch_theme("dark")
    assert get_theme_manager().get_current_theme_name() == "light"
    qtbot.wait(web_page.THEME_ACK_TIMEOUT_MS + 150)
    bridge.blockSignals(False)
    assert get_theme_manager().get_current_theme_name() == "dark"


def test_with_no_visible_page_the_switch_is_immediate(qtbot, qapp):
    _mounted(qtbot, mount_setup_page, show=False)
    switch_theme("dark")
    assert get_theme_manager().get_current_theme_name() == "dark"


def test_a_second_switch_wins(qtbot, qapp, monkeypatch):
    _view, bridge = _mounted(qtbot, mount_setup_page)
    manager = get_theme_manager()
    calls = []
    real = manager.set_theme
    monkeypatch.setattr(manager, "set_theme", lambda n: (calls.append(n), real(n))[1])
    bridge.blockSignals(True)
    switch_theme("dark")
    switch_theme("light")
    bridge.blockSignals(False)
    qtbot.wait(web_page.THEME_ACK_TIMEOUT_MS + 150)
    assert manager.get_current_theme_name() == "light"
    assert calls == ["dark", "light"] or calls == ["dark"]  # dark finished early, then back
    assert bridge.themeCss == theme_css_vars(manager.tokens_for("light"))


def test_switching_to_the_current_theme_does_nothing(qtbot, qapp, monkeypatch):
    manager = get_theme_manager()
    monkeypatch.setattr(manager, "set_theme", lambda n: pytest.fail("no switch expected"))
    switch_theme(manager.get_current_theme_name())


@pytest.mark.parametrize("name", sorted(MOUNTS))
def test_every_page_acknowledges_a_theme_change(qtbot, qapp, name):
    _view, bridge = _mounted(qtbot, MOUNTS[name])
    with qtbot.waitSignal(bridge.themePainted, timeout=5000):
        bridge.set_theme_css(_dark_css())


def test_a_page_does_not_acknowledge_its_first_load(qtbot, qapp):
    view = QWebEngineView()
    qtbot.addWidget(view)
    seen = []
    bridge = mount_setup_page(view)
    bridge.themePainted.connect(lambda: seen.append(1))
    view.show()
    _until_js(qtbot, view, READY)
    qtbot.wait(200)
    assert seen == []


def test_the_view_is_backed_by_the_page_plane(qtbot, qapp):
    view, _bridge = _mounted(qtbot, mount_setup_page)
    manager = get_theme_manager()
    assert view.page().backgroundColor() == QColor(manager.get_current_theme().surface_sunken)
    manager.set_theme("dark")
    assert view.page().backgroundColor() == QColor(manager.get_current_theme().surface_sunken)
```

`tests/conftest.py::reset_theme_and_density` (autouse) puts the theme back to light around every test, so no
cleanup is needed here. `test_a_second_switch_wins` accepts either call list on purpose: what is pinned is the
final theme and the final CSS, not the internal ordering. If `mount_logs_page` needs arguments beyond the view,
check its signature (`gui/logs_bridge.py:80`) and pass the defaults `tests/test_logs_page.py::page` uses.

- [ ] **Step 2: Run to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_theme_switch.py`
Expected: collection error — `cannot import name 'switch_theme'`.

- [ ] **Step 3: Implement the Python side**

`gui/theme_manager.py` — replace `get_current_theme`:

```python
    def tokens_for(self, theme_name: str) -> ThemeTokens:
        """A theme's tokens with this app's bundled font family layered on."""
        return themed_tokens(theme_name, load_bundled_fonts())

    def get_current_theme(self) -> ThemeTokens:
        return self.tokens_for(self._current_theme_name)
```

`gui/web_page.py` — imports become:

```python
import weakref
from pathlib import Path

from PySide6.QtCore import Property, QObject, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QColor
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineWidgets import QWebEngineView

from gui.theme_manager import get_theme_manager
from shared.theme import on_theme_changed, theme_css_vars

WEB_DIR = Path(__file__).resolve().parent / "web"
THEME_MARKER = "/* theme-vars */"
# How long the chrome waits for the visible page to paint a new theme.
THEME_ACK_TIMEOUT_MS = 150

# bridge -> its view, for switch_theme. Weak: a closed page drops out.
_pages: "weakref.WeakKeyDictionary[PageBridge, QWebEngineView]" = (
    weakref.WeakKeyDictionary()
)
```

In `PageBridge`, add the signal beside `themeCssChanged` and the slot beside `raise_toast`:

```python
    # Python-facing: the page has painted the theme it was last sent.
    themePainted = Signal()

    @Slot()
    def themeApplied(self) -> None:
        """Called by the page, two frames after it wrote a changed theme."""
        self.themePainted.emit()
```

In `mount_page`, register the pair and back the view (replace `_push_theme`, add the registry line before
`on_theme_changed`):

```python
    def _push_theme(_tokens) -> None:
        # The manager's tokens rather than the argument: only those carry the
        # bundled Inter family the Qt tier renders in.
        tokens = get_theme_manager().get_current_theme()
        # What shows wherever the page has not painted yet: the page's own
        # plane, not Chromium's white.
        view.page().setBackgroundColor(QColor(tokens.surface_sunken))
        bridge.set_theme_css(theme_css_vars(tokens))

    _pages[bridge] = view
    on_theme_changed(view, _push_theme)  # runs once now, then on every change
```

At the end of the module:

```python
_finish_pending = None  # completes the switch in flight, if there is one


def switch_theme(name: str) -> None:
    """Change the theme so the window turns over in one step.

    ThemeManager.set_theme() repaints the Qt chrome at once and each web page
    a frame or more later, in its own process. So the visible pages are sent
    the new theme first, and the chrome follows when they have painted it --
    or after THEME_ACK_TIMEOUT_MS, so a page that never answers costs a
    moment and never a stuck theme. No animation: ADR 0016.
    """
    global _finish_pending
    if _finish_pending is not None:
        _finish_pending()
    manager = get_theme_manager()
    if name == manager.get_current_theme_name():
        return

    waiting = set()
    for bridge, view in list(_pages.items()):
        try:
            if view.isVisible():
                waiting.add(bridge)
        except RuntimeError:
            continue  # the C++ view is gone; its bridge is on its way out
    if not waiting:
        manager.set_theme(name)
        return

    done = False

    def finish() -> None:
        global _finish_pending
        nonlocal done
        if done:
            return
        done = True
        _finish_pending = None
        for bridge in connected:
            try:
                bridge.themePainted.disconnect(painted[bridge])
            except RuntimeError:
                pass  # the bridge was destroyed while we waited
        manager.set_theme(name)

    def on_painted(bridge) -> None:
        waiting.discard(bridge)
        if not waiting:
            finish()

    painted = {bridge: (lambda b=bridge: on_painted(b)) for bridge in waiting}
    connected = list(waiting)
    for bridge in connected:
        bridge.themePainted.connect(painted[bridge])
    _finish_pending = finish
    QTimer.singleShot(THEME_ACK_TIMEOUT_MS, finish)

    css = theme_css_vars(manager.tokens_for(name))
    for bridge in connected:
        bridge.set_theme_css(css)
```

Notes for the implementer:
- `finish` is idempotent, so the timer firing after an ack-driven finish (or after a later switch finished it)
  is harmless.
- A `PageBridge` must be hashable and weak-referenceable for `_pages`; `QObject` is both. If PySide refuses the
  weak key, use `weakref.WeakSet` of bridges plus a `bridge._view = weakref.ref(view)` attribute instead.
- If `theme_css_vars` output depends on anything but its tokens argument (check `shared/theme.py:1135`), the
  CSS pushed here must equal what `_push_theme` pushes after `set_theme`; the
  `test_the_visible_page_is_themed_before_the_chrome` assertion pins that.

`gui/ui_manager.py::_wire_sidebar`:

```python
        sidebar.themeRequested.connect(switch_theme)
```

with `from gui.web_page import switch_theme` among the imports (drop `get_theme_manager` from this file's
imports only if nothing else in it uses it — ruff will say).

- [ ] **Step 4: Implement the page side**

In `setup.js`, `browse.js`, `logs.js`, `tools.js`, `settings.js` the handler is one line:

```js
  bridge.themeCssChanged.connect(() => { els.themeVars.textContent = bridge.themeCss; });
```

Replace it in each with:

```js
  bridge.themeCssChanged.connect(() => {
    els.themeVars.textContent = bridge.themeCss;
    // Two frames: the first callback runs before this frame is painted.
    requestAnimationFrame(() => requestAnimationFrame(() => bridge.themeApplied()));
  });
```

In `results.js`, append the same `requestAnimationFrame(…)` line (with `state.bridge.themeApplied()`) as the
last statement of `onTheme()`, after `render()`. Leave each page's initial
`els.themeVars.textContent = bridge.themeCss;` line untouched: the first load is not acknowledged.

- [ ] **Step 5: Run to verify they pass, plus the suites around it**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_theme_switch.py tests/test_shell.py tests/test_sidebar.py tests/test_setup_page.py tests/test_logs_page.py tests/test_settings_web_page.py`
Expected: PASS. A test that clicks the sidebar's theme segment and asserts the theme synchronously now needs
`qtbot.waitUntil(lambda: get_theme_manager().get_current_theme_name() == "dark", timeout=2000)`.

- [ ] **Step 6: Commit**

Message: `Fix: a theme switch themes the visible page first, then the chrome` with a body line: no fade
(ADR 0016), 150 ms fallback, web views backed by `surface_sunken`.

---

### Task 5: The stress script (spec §5.2)

**Files:**
- Create: `scripts/stress_ui.py`

**Interfaces:**
- Consumes: `gui.web_page.switch_theme`, `MainWindow`, `results_bridge.set_orders(df)`,
  `gui.settings.window.SettingsWindow` (constructor as in `tests/conftest.py::window`),
  `MainWindow.logs_widget.append(entry, stream)` (see `MainWindow._on_log_entry` and `gui/log_entry.py`).

- [ ] **Step 1: Write the script**

Skeleton — complete every scenario; this fixes the structure, the measuring and the output:

```python
"""Stress the refreshed UI and print what it cost.

    .venv/bin/python scripts/stress_ui.py

Offscreen, against a throwaway server path. Prints one markdown table and
exits non-zero on a Python exception or a JavaScript error. It measures; it
gates nothing (2026-10-04 quickfixes spec, section 5.2).
"""

import os
import resource
import statistics
import sys
import tempfile
import time
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["FULFILLMENT_SERVER_PATH"] = tempfile.mkdtemp(prefix="stress-ui-")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication([])

from gui.theme_manager import ThemeManager, get_theme_manager  # noqa: E402

# Never the developer's own saved theme.
ThemeManager._save_theme_preference = lambda self: None

from gui.main_window_pyside import MainWindow  # noqa: E402
from gui.web_page import switch_theme  # noqa: E402

ERROR_HOOK = "window.__errors = []; window.onerror = (m) => { window.__errors.push(String(m)); };"
ROWS = []
FAILURES = []


def spin(seconds: float) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.005)


def wait_for(predicate, timeout: float = 30.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.005)
    return False


def js(view, code: str, timeout: float = 30.0):
    box = []
    view.page().runJavaScript(code, 0, box.append)
    wait_for(lambda: bool(box), timeout)
    return box[0] if box else None


def rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024  # Linux: KiB


def scenario(name: str, iterations: int, step) -> None:
    """Run step(i) `iterations` times; record time per step, widgets, RSS."""
    widgets, rss, times = len(app.allWidgets()), rss_mb(), []
    try:
        for i in range(iterations):
            start = time.perf_counter()
            step(i)
            times.append((time.perf_counter() - start) * 1000)
    except Exception as error:  # a finding, not a crash of the harness
        FAILURES.append(f"{name}: {error!r}")
    spin(0.5)
    ROWS.append(
        (name, len(times),
         f"{statistics.median(times):.0f}" if times else "-",
         f"{max(times):.0f}" if times else "-",
         f"{widgets} -> {len(app.allWidgets())}",
         f"{rss:.0f} -> {rss_mb():.0f}")
    )


def orders(count: int) -> pd.DataFrame:
    rows = []
    for i in range(count):
        for line in range(1 + i % 4):
            rows.append({
                "Order_Number": f"#{10001 + i}",
                "Order_Fulfillment_Status": "Not Fulfillable" if i % 10 == 3 else "Fulfillable",
                "Shipping_Provider": ("DHL", "DPD", "Packeta", "")[i % 4],
                "Customer": f"Customer {i:05d}",
                "Total_Price": 10.0 + i,
                "SKU": f"SKU-{i:05d}-{line}",
                "Product_Name": f"Product {line}",
                "Quantity": 1 + line,
                "Internal_Tags": "[]",
                "System_note": "",
            })
    return pd.DataFrame(rows)


def main() -> int:
    get_theme_manager().apply_theme()
    win = MainWindow()
    win.resize(1280, 860)
    win.show()
    spin(2)
    for cid in ("A", "B"):
        win.profile_manager.create_client_profile(cid, f"Client {cid}")
    win.command_bar.set_clients(["A", "B"])
    win.command_bar.set_current_client("A")
    wait_for(lambda: not win._client_load_workers)

    # ... the eight scenarios of spec section 5.2, each one a scenario(...) call ...

    print("| Scenario | n | median ms | worst ms | widgets | RSS MB |")
    print("|---|---|---|---|---|---|")
    for row in ROWS:
        print("| " + " | ".join(str(c) for c in row) + " |")
    for failure in FAILURES:
        print("FAILED:", failure)
    return 1 if FAILURES else 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)  # Chromium's teardown can hang an offscreen exit
```

The eight scenarios, each implemented with the helpers above:

1. **Results at size** — `df = orders(10_000)`; one step: `win.analysis_results_df = df;
   win._update_all_views(); win.update_ui_state(); win.main_tabs.setCurrentIndex(1)`, then
   `wait_for(lambda: js(win.results_view, "document.querySelectorAll('#rows .row').length > 0") is True)`.
   Install `ERROR_HOOK` in the results view first. n = 3 (re-push the same frame).
2. **Results interaction** — per step, in the page: click the header select box
   (`document.querySelector('#header .col-select input').click()`), click it again, click two sortable headers
   (`document.querySelector('#header .col-order').click()`, `.col-customer`), and set the search field's value
   then dispatch an `input` event (find the field's id in `gui/web/results.html`). Each ends with
   `wait_for` on a JS predicate that the page is settled (`requestAnimationFrame` round trip:
   `js(view, "new Promise(r => requestAnimationFrame(() => r(true)))")`). n = 20.
3. **Theme switching** — Results visible; step: `switch_theme("dark" if i % 2 == 0 else "light")` then
   `wait_for(lambda: get_theme_manager().get_current_theme_name() == target)`. n = 100.
4. **Client switching** — set `win.session_path` via a real session if `MainWindow` exposes a create-session
   call that needs no dialog (look at how `tests/test_session_lifecycle.py` opens one); step:
   `win.command_bar.set_current_client("B" if i % 2 == 0 else "A")` then
   `wait_for(lambda: not win._client_load_workers)`. n = 50.
5. **Session loop** — step: create a session the way `tests/test_session_lifecycle.py` does, then
   `win._reset_session_state()`. n = 30.
6. **Log flood** — `win.main_tabs.setCurrentIndex(3)`; one step appends 20 000 entries through
   `logging.getLogger("stress").info("entry %d", k)` (the root handler routes them to the Logs page), then
   `spin(1)`. n = 1; also record `js(logs_view, "document.querySelectorAll('.row, tr').length")` in the name.
7. **Settings window** — step: build `SettingsWindow(client_id="A", client_config=<loaded via
   win.profile_manager.load_client_config("A")>, profile_manager=win.profile_manager)`, `show()`, `spin(0.3)`,
   `close()`, `deleteLater()`, `spin(0.1)`. n = 20. (Constructor arguments: copy from
   `tests/conftest.py::window` and `actions_handler.open_settings_window`.)
8. **Browse at size** — create 500 session directories under the temp server path in the layout
   `tests/test_browse_page.py` or `tests/test_session_browser_widget.py` builds, then step:
   `win.main_tabs.setCurrentIndex(2)`, trigger the reload the F5 shortcut calls (see
   `tests/test_shell.py::test_f5_reloads_the_session_list_on_browse_only`), `wait_for` rows present. n = 3.

After the scenarios, for each web view (`win.findChildren(QWebEngineView)`), read `window.__errors` (install
`ERROR_HOOK` on every view right after `win.show()`); any non-empty list is appended to `FAILURES`.

If a scenario cannot be driven without a modal dialog or a private API that does not exist, implement the
nearest drivable equivalent and say which in a comment on that scenario — do not leave it out silently.

- [ ] **Step 2: Run it**

Run: `timeout 600 .venv/bin/python scripts/stress_ui.py`
Expected: the table prints, exit code 0 or 1. Save the output; it goes in the PR body. Run it twice: a number
that only appears once is noise.

- [ ] **Step 3: Lint and commit**

Run: `.venv/bin/ruff check scripts/stress_ui.py` (or `ruff check .`). Commit with message
`Add scripts/stress_ui.py: a hand-run stress pass over the refreshed UI`.

---

### Task 6: Verification pass — render sweep, triage, small fixes (spec §5.1, §5.3)

**Files:**
- Create: `docs/design/ui-refresh/renders/quickfixes/*.png`
- Modify: whatever a small finding needs, each with a test

- [ ] **Step 1: Render every screen in both themes**

Throwaway script (rules in Global Constraints; put it in a temp dir, not the repo). At 1280×860 with a real
`MainWindow`, `win.grab().save(...)` for, in light and dark: Setup (no client; client, no session); Results
(orders pushed as in Task 3 Step 5; one row's checkbox clicked; one row opened in the pane); Browse (empty; with
a few session folders); Logs; Tools; a `SettingsWindow` on each of its sections (General, mappings, Rules,
Sets, Weight, Reports, Tag categories — switch with the nav the tests in `tests/test_settings_nav.py` use);
and `GroupsManagementDialog` / `ClientCreationDialog` shown non-modally with `show()` (never `exec()`).

- [ ] **Step 2: Look at every PNG**

Read each image. Compare with its mockup in `docs/design/ui-refresh/mockups/` (`app-shell.html`, `setup.html`,
`results.html`, `browse.html`, `logs.html`, `tools.html`, `client-settings.html`) and the phase renders in
`docs/design/ui-refresh/renders/phase1..9/`. Check on each: no 1px frame around the page; one rule across
sidebar header and bar; no boxed checkbox cell; no kit-styled element that should be plain; no white backing;
text contrast holds in dark; nothing clipped at this size. Also check the Settings window for the same pane
frame as `main_tabs` (it has its own layout: if it uses a `QTabWidget`/`QStackedWidget` with a pane border,
that is a small finding — same fix as Task 2).

- [ ] **Step 3: List the findings**

One list, from the renders and from Task 5's table. A finding is: an exception or JS error; widget count or
RSS that grows with iterations; a single interaction over 200 ms; anything visibly wrong. For each: where, how
to reproduce, the number or the PNG, and its class:

- **small** — at most about 30 changed lines, no new design decision, no `shared/` change. Fix it now.
- **not small** — everything else. File it.

No findings is a valid result: say so in the PR body.

- [ ] **Step 4: Fix each small finding, test first**

For each: write a test that fails for the finding (same seams as Tasks 1–4: a widget geometry/pixel assertion,
a `getComputedStyle` assertion through `_eval`, or a signal count), run it red, fix, run it green, commit with
a message naming the finding. One commit per finding.

- [ ] **Step 5: File the rest**

For each not-small finding: `gh issue create --repo cognitiveghost/shopify-fulfillment-tool --title "<what is
wrong>" --body-file <absolute path>` with the reproduction, the measurement and the screen. Label conventions:
`docs/agents/issue-tracker.md`. Keep the issue numbers for the PR body.

- [ ] **Step 6: Save the after-fix renders**

Copy the final light and dark PNGs of Setup, Results (with orders), Browse, Logs, Tools and one Settings
section to `docs/design/ui-refresh/renders/quickfixes/` named `<theme>-<screen>.png`. Delete the render script.
Commit: `Renders: the refreshed screens after the quickfixes`.

---

### Task 7: Gate and hand-over

- [ ] **Step 1: Full gate**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
Run: `ruff check .`
Expected: both clean. `shared/style_lint.py` runs inside the suite: a failure there means a banned property
or a hex slipped into a web asset or a sheet.

- [ ] **Step 2: Refresh the graph**

Run: `graphify update .` (skip if `graphify-out/` is absent). Commit anything it changed that is tracked.

- [ ] **Step 3: Notes for the PR body**

Collect: the four fixes with their root causes (spec §2), the stress table (Task 5), the findings list (fixed
here / issue numbers), "No `shared/` change: no packing-tool work", and the spec and plan paths. The PR itself
is opened by the next stage.
