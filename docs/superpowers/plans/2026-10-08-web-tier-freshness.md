# Web Tier Freshness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A web page never shows the previous session: pages stay painted while covered, report the revision they
painted, Results forgets the previous session's view, a dead render process is reloaded, and the shared web code
moves to `shared/`.

**Architecture:** `gui/web_page.py` and `gui/web/kit.css` move to `shared/` (Task 1) and Fulfilment keeps a thin
adapter. `PageBridge` gains a revision number bumped by every property change, and a tiny shared script reports the
revision each page painted (Task 2). The page stack runs in Qt's stack-all mode so covered pages keep painting
(Task 3). Results gets a "forget your view" command (Task 4), session opening waits for the painted report
(Task 5), and `mount_page` reloads a page whose render process died (Task 6).

**Tech Stack:** Python 3.11+ (CI) / 3.14 (dev VM), PySide6 (QtWebEngine, QtWebChannel), plain JavaScript and CSS,
pytest + pytest-qt.

**Spec:** `docs/superpowers/specs/2026-10-08-web-tier-freshness-design.md`. Read it first; this plan implements it
section by section.

## Global Constraints

- Follow this repo's `CLAUDE.md`. In particular:
  - Gate: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`, plus `.venv/bin/ruff check .`. Both must pass
    at the end of every task.
  - A hook blocks Bash text containing "pytest" other than the plain run form. To run one file, try
    `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/<file>.py`; if the hook refuses, run the plain
    gate. Write test files with the Write/Edit tools, never with a shell heredoc.
  - `/usr/bin/git`, one plain git command per Bash call; commit with `git commit -F <absolute path to message file>`.
  - No hardcoded colours, no `pyproject.toml`, no unused imports, no UI calls from background threads.
  - Run `graphify update .` after each task's code change.
- Never mark a test skip or xfail. These tests drive a real Chromium; use `_eval` and `_until_js` from
  `tests/test_results_bridge.py`, as every page test already does.
- `shared/` must not import from `gui/` or `shopify_tool/`. Packer Assistant mirrors `shared/` as it is.
- Do not touch `../packing-tool`. Nothing in this plan edits that repo.
- JavaScript style in `gui/web/` and `shared/web/`: plain functions, no modules, no build step, 2-space indent,
  double quotes. `shared/style_lint.py` scans web assets: no gradients, transitions, transforms, opacity or px font
  sizes.
- The spec's exact values: painted-report cap **150 ms**; reload limit **3 terminations within 60 seconds**.

## Review Focus

1. **A Qt button on a covered page is clicked from elsewhere** (for example "Re-run analysis" calls
   `run_analysis_button.click()` while Setup is covered). It must still work: covered pages lose focus, they are
   never disabled. Test in Task 3 (`test_a_covered_page_stays_enabled`).
2. **Tab or a click moves keyboard focus into a page the user cannot see.** Covered web views must refuse focus,
   including the lazily created focus proxy. Test in Task 3.
3. **A page that never answers** (still loading at start-up, or hung) when a session is opened. The switch to
   Results must still happen, at the 150 ms cap, exactly once. Tests in Task 2 (`when_painted` timeout) and Task 5.
4. **A page that crashes every time it loads.** Reloading must stop after the third death in a minute rather than
   spin. Test in Task 6.
5. **The same session reopened, or a client switch, with a search typed.** Both go through
   `_reset_session_state`, so both must clear the Results view. Test in Task 4
   (`test_every_way_into_a_session_forgets_the_view`).

## File Structure

| File | Responsibility |
|---|---|
| `shared/web_page.py` (moved from `gui/web_page.py`) | `PageBridge`, `mount_page`, `switch_theme`, `when_painted`, `keep_pages_painted`. No app imports. |
| `shared/web/kit.css` (moved from `gui/web/kit.css`) | The web kit stylesheet, unchanged. |
| `shared/web/page.js` (new) | `reportPaints(bridge)`: the painted report every page sends. |
| `gui/web_page.py` (rewritten) | Thin adapter: binds this app's theme manager into the shared functions and re-exports the rest. |
| `gui/web/*.html`, `gui/web/*.js` | Link the kit and `page.js` from `shared/web/`; call `reportPaints`. |
| `gui/results_bridge.py`, `gui/web/results.js` | `sessionEpoch`, `forget_view()`, `resetView()`. |
| `gui/ui_manager.py`, `gui/main_window_pyside.py`, `gui/actions_handler.py` | Call `keep_pages_painted`, `forget_view`, `show_results_when_painted`. |
| `tests/test_web_page.py` | Unit tests of the shared module (revision, `when_painted`, stack, crash). |
| `tests/test_web_freshness.py` (new) | One freshness test per page, plus the Results view reset. |
| `scripts/stress_ui.py` | Two new scenarios. |

---

### Task 1: Move the shared web code to `shared/` (no behaviour change)

**Files:**
- Move: `gui/web_page.py` → `shared/web_page.py`; `gui/web/kit.css` → `shared/web/kit.css`
- Create: `gui/web_page.py` (adapter)
- Modify: `gui/web/browse.html`, `logs.html`, `results.html`, `settings.html`, `setup.html`, `tools.html` (line 9 of
  each), `tests/web/kit_sheet.html:7`, `tests/test_web_kit.py`, `tests/test_results_columns.py:484`,
  `tests/test_theme_switch.py`, `.github/workflows/build_release.yml:134`, `README.md:52`, `CONTEXT.md:37`,
  `shared/README.md`, `docs/design/ui-refresh/roadmap.md:230`
- Test: `tests/test_web_page.py`

**Interfaces:**
- Produces (in `shared/web_page.py`):
  - `class PageBridge(QObject)`: unchanged in this task.
  - `mount_page(view: QWebEngineView, bridge: PageBridge, page: Path, channel_name: str, *, tokens: Callable[[], ThemeTokens]) -> None`
  - `switch_theme(name: str, *, current_name: Callable[[], str], tokens_for: Callable[[str], ThemeTokens], set_theme: Callable[[str], None]) -> None`
  - `THEME_MARKER`, `THEME_ACK_TIMEOUT_MS`, `SHARED_WEB_DIR` (`Path`, the `shared/web` directory)
- Produces (in `gui/web_page.py`): `WEB_DIR`, `THEME_MARKER`, `THEME_ACK_TIMEOUT_MS`, `PageBridge`,
  `mount_page(view, bridge, page, channel_name)`, `switch_theme(name)`: the signatures every caller uses today.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_web_page.py`:

```python
def test_the_shared_module_imports_nothing_from_an_app():
    import ast
    from pathlib import Path

    import shared.web_page as shared_page

    tree = ast.parse(Path(shared_page.__file__).read_text(encoding="utf-8"))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    assert not roots & {"gui", "shopify_tool"}


def test_the_adapter_hands_out_the_shared_bridge():
    import gui.web_page as adapter
    import shared.web_page as shared_page

    assert adapter.PageBridge is shared_page.PageBridge
    assert adapter.THEME_MARKER == shared_page.THEME_MARKER
    assert adapter.WEB_DIR.name == "web" and adapter.WEB_DIR.parent.name == "gui"


def test_the_kit_lives_in_shared_and_every_page_links_it_there():
    import shared.web_page as shared_page

    assert (shared_page.SHARED_WEB_DIR / "kit.css").is_file()
    for page in sorted(WEB_DIR.glob("*.html")):
        html = page.read_text(encoding="utf-8")
        assert 'href="../../shared/web/kit.css"' in html, page.name
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_web_page.py`
Expected: the three new tests FAIL with `ModuleNotFoundError: No module named 'shared.web_page'`.

- [ ] **Step 3: Move the two files**

Run each as its own Bash call:

```bash
/usr/bin/git mv gui/web_page.py shared/web_page.py
```
```bash
mkdir -p shared/web
```
```bash
/usr/bin/git mv gui/web/kit.css shared/web/kit.css
```

- [ ] **Step 4: Make `shared/web_page.py` app-free**

Edit `shared/web_page.py`:

1. Replace the docstring's first line with
   `"""What every web page's bridge shares, in both apps (ADR 0016, ADR 0017).` and keep the rest.
2. Delete `from gui.theme_manager import get_theme_manager`.
3. Replace `WEB_DIR = Path(__file__).resolve().parent / "web"` with
   `SHARED_WEB_DIR = Path(__file__).resolve().parent / "web"`.
4. Replace `mount_page` with:

```python
def mount_page(
    view: QWebEngineView, bridge: PageBridge, page: Path, channel_name: str, *, tokens
) -> None:
    """Load `page` into `view` with `bridge` as the object it talks to.

    `tokens` is a zero-argument callable returning the app's current
    ThemeTokens, the ones that carry its bundled font family. The theme is
    written into the page before it loads, so the first paint is already
    themed, then pushed through the bridge on every theme or density change,
    so the document repaints without a reload. The channel is parented to
    `view` and dies with it. The page's own folder is its base URL.
    """
    channel = QWebChannel(view)
    channel.registerObject(channel_name, bridge)
    view.page().setWebChannel(channel)

    def _push_theme(_tokens) -> None:
        current = tokens()
        # What shows wherever the page has not painted yet: the page's own
        # plane, not Chromium's white.
        view.page().setBackgroundColor(QColor(current.surface_sunken))
        bridge.set_theme_css(theme_css_vars(current))

    _pages[bridge] = view
    on_theme_changed(view, _push_theme)  # runs once now, then on every change

    html = page.read_text(encoding="utf-8").replace(THEME_MARKER, bridge.themeCss)
    view.setHtml(html, QUrl.fromLocalFile(str(page.parent) + "/"))
```

5. Change `switch_theme`'s signature to
   `def switch_theme(name: str, *, current_name, tokens_for, set_theme) -> None:` and in its body: delete
   `manager = get_theme_manager()`, replace `manager.get_current_theme_name()` with `current_name()`, both
   `manager.set_theme(name)` with `set_theme(name)`, and `manager.tokens_for(name)` with `tokens_for(name)`. Add one
   sentence to its docstring: `The three callables are the app's theme manager, which shared/ cannot import.`

- [ ] **Step 5: Write the adapter**

Create `gui/web_page.py`:

```python
"""This app's face of shared/web_page.py (ADR 0016, ADR 0017).

The shared module cannot import an app's theme manager, so it takes the theme
as arguments. This binds Fulfilment's in, and every bridge keeps importing
from here.
"""

from pathlib import Path

from gui.theme_manager import get_theme_manager
from shared import web_page as _shared
from shared.web_page import (  # noqa: F401  (re-exported for the bridges and their tests)
    THEME_ACK_TIMEOUT_MS,
    THEME_MARKER,
    PageBridge,
)

WEB_DIR = Path(__file__).resolve().parent / "web"


def mount_page(view, bridge, page, channel_name) -> None:
    """shared.web_page.mount_page with this app's tokens."""
    _shared.mount_page(
        view,
        bridge,
        page,
        channel_name,
        tokens=lambda: get_theme_manager().get_current_theme(),
    )


def switch_theme(name: str) -> None:
    """shared.web_page.switch_theme with this app's theme manager."""
    manager = get_theme_manager()
    _shared.switch_theme(
        name,
        current_name=manager.get_current_theme_name,
        tokens_for=manager.tokens_for,
        set_theme=manager.set_theme,
    )
```

- [ ] **Step 6: Point every page and test at the kit's new home**

In each of the six `gui/web/*.html` files replace `<link rel="stylesheet" href="kit.css">` with
`<link rel="stylesheet" href="../../shared/web/kit.css">`.

`tests/web/kit_sheet.html:7`: read `tests/test_web_kit.py` to see which base URL that sheet is loaded with. If it is
loaded with `WEB_DIR` as base, change the link to `../../shared/web/kit.css`; if with `tests/web/`, change it to
`../../shared/web/kit.css` as well (both folders are two levels below the repo root).

`tests/test_web_kit.py`: add `from shared.web_page import SHARED_WEB_DIR`, set `KIT = SHARED_WEB_DIR / "kit.css"`,
and replace both `'href="kit.css"'` on lines 56-57 with `'href="../../shared/web/kit.css"'`.

`tests/test_results_columns.py:484`: replace `(web / "kit.css")` with `(SHARED_WEB_DIR / "kit.css")` and import
`SHARED_WEB_DIR` from `shared.web_page`.

`tests/test_theme_switch.py`: it reads `web_page.THEME_ACK_TIMEOUT_MS`, which the adapter re-exports, so it keeps
working. Run `rg -n "web_page\._|monkeypatch.*web_page" tests` and repoint any patch of a private name
(`_pages`, `_finish_pending`) to `shared.web_page`.

- [ ] **Step 7: Bundle `shared/web` in the release build**

In `.github/workflows/build_release.yml`, directly after the line `--add-data "gui/web;gui/web"`, add a line with
the same indentation: `--add-data "shared/web;shared/web"`.

- [ ] **Step 8: Update the docs that name the old paths**

- `README.md:52`: `- \`gui/\`: Qt UI; \`gui/web/\` holds the web pages (QtWebEngine); their shared kit is \`shared/web/\``
- `CONTEXT.md:37`: change `gui/web/kit.css` to `shared/web/kit.css`.
- `shared/README.md`: add `web_page.py` and `web/` to its list of what the package holds, one line each, in the
  style of the lines already there: `web_page.py` is "what every web page's bridge shares (theme, toast, mount,
  painted report)"; `web/` is "the web kit stylesheet and the page script every web page loads".
- `docs/design/ui-refresh/roadmap.md:230`: replace the line with
  `- ~~\`gui/web/kit.css\` moves to \`shared/\` when Packing Tool adopts it.~~ Moved 2026-10-08 with \`web_page.py\` (web tier freshness spec).`

- [ ] **Step 9: Run the gate**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` then `.venv/bin/ruff check .`
Expected: all pass. A page test failing with an unstyled page means a link path is wrong: open the HTML and check
the `href`.

- [ ] **Step 10: Commit**

Message: `Move the web page base and the web kit to shared/`. Stage with `git add -A`, then commit with `-F`.

---

### Task 2: Revision and painted report

**Files:**
- Modify: `shared/web_page.py`, `gui/web_page.py`
- Create: `shared/web/page.js`
- Modify: the six `gui/web/*.html` and `browse.js`, `logs.js`, `results.js`, `settings.js`, `setup.js`, `tools.js`
- Test: `tests/test_web_page.py`, `tests/test_web_freshness.py` (new)

**Interfaces:**
- Consumes: Task 1's `shared/web_page.py` and adapter.
- Produces:
  - `PageBridge.revision` (Qt `int` property, notify `revisionChanged`), `PageBridge.painted_revision: int`
    (Python attribute, `-1` until the first report), `PageBridge.painted = Signal(int)`,
    slot `PageBridge.paintedRevision(int)`.
  - `when_painted(bridge: PageBridge, callback: Callable[[], None], timeout_ms: int = 150) -> None`, in
    `shared/web_page.py` and re-exported by `gui/web_page.py`.
  - JavaScript: `reportPaints(bridge)` in `shared/web/page.js`; the page sets
    `document.documentElement.dataset.painted` to the revision it reported.

- [ ] **Step 1: Write the failing unit tests**

Append to `tests/test_web_page.py` (add `import logging` at the top if it is not there):

```python
def _bridges():
    from gui.browse_bridge import BrowseBridge
    from gui.logs_bridge import LogsBridge
    from gui.settings.bridge import SettingsBridge
    from gui.setup_bridge import SetupBridge
    from gui.tools_bridge import ToolsBridge

    return [ResultsBridge, BrowseBridge, LogsBridge, SettingsBridge, SetupBridge, ToolsBridge]


def test_every_notifying_property_of_every_bridge_raises_the_revision():
    for cls in _bridges():
        bridge = cls()
        meta = bridge.metaObject()
        for index in range(meta.propertyCount()):
            prop = meta.property(index)
            if not prop.hasNotifySignal() or prop.name() == "revision":
                continue
            before = bridge.revision
            getattr(bridge, bytes(prop.notifySignal().name()).decode()).emit()
            assert bridge.revision == before + 1, f"{cls.__name__}.{prop.name()}"


def test_the_revision_is_announced_with_the_change():
    bridge = PageBridge()
    seen = []
    bridge.revisionChanged.connect(lambda: seen.append(bridge.revision))
    bridge.set_theme_css(":root { --a: 1 }")
    assert seen == [1]


def test_a_painted_report_is_kept_and_announced():
    bridge = PageBridge()
    seen = []
    bridge.painted.connect(seen.append)
    assert bridge.painted_revision == -1
    bridge.paintedRevision(4)
    assert bridge.painted_revision == 4
    assert seen == [4]


def test_when_painted_runs_at_once_if_the_page_is_current():
    from shared.web_page import when_painted

    bridge = PageBridge()
    bridge.paintedRevision(bridge.revision)
    ran = []
    when_painted(bridge, lambda: ran.append(1))
    assert ran == [1]


def test_when_painted_waits_for_the_report_and_runs_once(qtbot):
    from shared.web_page import when_painted

    bridge = PageBridge()
    bridge.set_theme_css(":root { --a: 1 }")  # revision 1, nothing painted
    ran = []
    when_painted(bridge, lambda: ran.append(1), timeout_ms=100)
    assert ran == []
    bridge.paintedRevision(0)  # an older frame is not the answer
    assert ran == []
    bridge.paintedRevision(1)
    assert ran == [1]
    qtbot.wait(200)  # the timeout must not run it again
    assert ran == [1]


def test_when_painted_gives_up_at_the_timeout_and_says_so(qtbot, caplog):
    from shared.web_page import when_painted

    bridge = PageBridge()
    bridge.set_theme_css(":root { --a: 1 }")
    ran = []
    with caplog.at_level(logging.WARNING, logger="shared.web_page"):
        when_painted(bridge, lambda: ran.append(1), timeout_ms=50)
        qtbot.waitUntil(lambda: ran == [1], timeout=2000)
    assert "PageBridge" in caplog.text and "revision 1" in caplog.text
    bridge.paintedRevision(1)  # a late report must not run it again
    assert ran == [1]
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_web_page.py`
Expected: FAIL with `AttributeError: ... has no attribute 'revision'` and `cannot import name 'when_painted'`.

- [ ] **Step 3: Implement the revision in `PageBridge`**

In `shared/web_page.py` add `import logging` and, after the imports, `logger = logging.getLogger(__name__)`.
Replace the `PageBridge` class with:

```python
class PageBridge(QObject):
    """The theme, the toast and the revision: what every web page is told."""

    themeCssChanged = Signal()
    # Python-facing: the page has painted the theme it was last sent.
    themePainted = Signal()
    # JS-facing: the page draws its own toast, because a Qt child widget
    # cannot paint above a web view's surface (ADR 0007).
    toastRaised = Signal(str, bool)
    revisionChanged = Signal()
    # Python-facing: the page has painted this revision.
    painted = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._theme_css = ""
        self._revision = 0
        self.painted_revision = -1  # nothing reported yet
        # Every property that can change raises the revision, whichever
        # subclass declares it: none can be forgotten.
        meta = self.metaObject()
        for index in range(meta.propertyCount()):
            prop = meta.property(index)
            if prop.hasNotifySignal() and prop.name() != "revision":
                signal = getattr(self, bytes(prop.notifySignal().name()).decode())
                signal.connect(self._bump)

    def _bump(self, *_args) -> None:
        self._revision += 1
        self.revisionChanged.emit()

    def _get_revision(self) -> int:
        return self._revision

    revision = Property(int, _get_revision, notify=revisionChanged)

    def _get_theme_css(self) -> str:
        return self._theme_css

    themeCss = Property(str, _get_theme_css, notify=themeCssChanged)

    def set_theme_css(self, css: str) -> None:
        if css == self._theme_css:
            return
        self._theme_css = css
        self.themeCssChanged.emit()

    @Slot()
    def themeApplied(self) -> None:
        """Called by the page, two frames after it wrote a changed theme."""
        self.themePainted.emit()

    @Slot(int)
    def paintedRevision(self, revision) -> None:
        """Called by the page, two frames after it drew `revision`."""
        self.painted_revision = int(revision)
        self.painted.emit(self.painted_revision)

    def raise_toast(self, message: str, undoable: bool = False) -> None:
        self.toastRaised.emit(str(message), bool(undoable))
```

If `test_every_notifying_property_of_every_bridge_raises_the_revision` fails because `self.metaObject()` inside the
base `__init__` does not list a subclass's properties, move the wiring loop into a method
`_watch_properties(self)` and call it from `mount_page` (first line) as well as from `__init__`, guarded by a
`self._watched` flag so it connects once. Do not add a bump call to each subclass.

- [ ] **Step 4: Implement `when_painted`**

Append to `shared/web_page.py`:

```python
PAINT_TIMEOUT_MS = 150


def when_painted(bridge: PageBridge, callback, timeout_ms: int = PAINT_TIMEOUT_MS) -> None:
    """Run `callback` once the page has painted the bridge's current revision.

    At once if it already has; otherwise on the page's report, or after
    `timeout_ms`, whichever comes first. A page that never answers costs the
    timeout and a log line, never a stuck screen.
    """
    target = bridge.revision
    if bridge.painted_revision >= target:
        callback()
        return

    done = False

    def finish(timed_out: bool = False) -> None:
        nonlocal done
        if done:
            return
        done = True
        try:
            bridge.painted.disconnect(on_painted)
        except RuntimeError:
            pass  # the bridge was destroyed while we waited
        if timed_out:
            logger.warning(
                "%s did not report revision %s within %s ms (last painted %s)",
                type(bridge).__name__,
                target,
                timeout_ms,
                bridge.painted_revision,
            )
        callback()

    def on_painted(revision: int) -> None:
        if revision >= target:
            finish()

    bridge.painted.connect(on_painted)
    QTimer.singleShot(timeout_ms, lambda: finish(timed_out=True))
```

If the bridge can be destroyed before the timer fires, `bridge.painted_revision` in the log call raises
`RuntimeError`; wrap only that read in `try/except RuntimeError` and log `-1`.

In `gui/web_page.py` add `when_painted` to the names imported from `shared.web_page`.

- [ ] **Step 5: Run the unit tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_web_page.py`
Expected: PASS.

- [ ] **Step 6: Write the failing page test**

Create `tests/test_web_freshness.py`:

```python
"""A page never shows an old session (2026-10-08 web tier freshness spec).

Driven through a real Chromium. Never mark skip.
"""

import pytest
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QStackedWidget, QWidget
from test_browse_state import make_state as browse_state_of
from test_browse_state import session
from test_logs_page import row as log_row
from test_results_bridge import _eval, _until_js
from test_results_document import results_lines
from test_setup_state import loaded
from test_setup_state import make_state as setup_state_of
from test_tools_state import make_state as tools_state_of

from gui.browse_bridge import mount_browse_page
from gui.logs_bridge import mount_logs_page
from gui.results_bridge import mount_results_page
from gui.settings.bridge import mount_settings_page
from gui.setup_bridge import mount_setup_page
from gui.tools_bridge import mount_tools_page

MOUNTS = {
    "setup": mount_setup_page,
    "results": mount_results_page,
    "browse": mount_browse_page,
    "logs": mount_logs_page,
    "tools": mount_tools_page,
    "settings": mount_settings_page,
}


def _ready(qtbot, view):
    _until_js(qtbot, view, "document.documentElement.dataset.bridge === 'ready'")


def _painted(qtbot, view, bridge):
    """Wait until the page has reported the bridge's current revision."""
    qtbot.waitUntil(lambda: bridge.painted_revision == bridge.revision, timeout=15000)
    assert _eval(qtbot, view, "Number(document.documentElement.dataset.painted)") == bridge.revision


@pytest.mark.parametrize("name", sorted(MOUNTS))
def test_every_page_reports_the_revision_it_painted(qtbot, name):
    view = QWebEngineView()
    qtbot.addWidget(view)
    bridge = MOUNTS[name](view)
    view.resize(1166, 720)
    view.show()
    _ready(qtbot, view)
    _painted(qtbot, view, bridge)
    bridge.set_theme_css(bridge.themeCss + "\n/* again */")
    _painted(qtbot, view, bridge)
```

`mount_settings_page` and `mount_logs_page` may take more arguments than the view: open
`gui/settings/bridge.py` and `gui/logs_bridge.py`, and if they do, wrap them in `MOUNTS` with a lambda that passes
the same defaults their own page tests pass (`tests/test_settings_web_page.py`, `tests/test_logs_page.py`). The
unused imports at the top (`QStackedWidget`, `QWidget`, the state builders, `log_row`, `results_lines`, `session`,
`loaded`) are used by Tasks 3 and 4; add each import in the task that first uses it, so ruff stays clean now.

- [ ] **Step 7: Run it and confirm it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_web_freshness.py`
Expected: six FAILs, each a `waitUntil` timeout (no page reports yet).

- [ ] **Step 8: Write `shared/web/page.js`**

```js
// What every web page does besides drawing itself (shared/web_page.py).
// Loaded before the page's own script; no module, no build step.

// Tell Python which revision of the bridge's state this page has painted.
// Two frames: the first callback runs before the frame that holds the new
// DOM is painted. Pages render synchronously in their signal handlers, so
// the DOM is current by then whatever order the handlers ran in.
function reportPaints(bridge) {
  let sent = -1;
  const report = () => {
    const revision = bridge.revision;
    requestAnimationFrame(() => requestAnimationFrame(() => {
      if (revision <= sent) return;
      sent = revision;
      document.documentElement.dataset.painted = String(revision);
      bridge.paintedRevision(revision);
    }));
  };
  bridge.revisionChanged.connect(report);
  report();
}
```

- [ ] **Step 9: Load it and call it in every page**

In each of the six `gui/web/*.html` files, add one line directly after the `qwebchannel.js` script tag:
`<script src="../../shared/web/page.js" defer></script>`. (`defer` scripts run in document order, so it runs before
the page's own scripts.)

In each of `browse.js`, `logs.js`, `results.js`, `settings.js`, `setup.js`, `tools.js`, find the
`new QWebChannel(qt.webChannelTransport, function (channel) {` callback and add `reportPaints(bridge);` as the last
statement before the line that sets `document.documentElement.dataset.bridge = "ready"`. If a page sets
`dataset.bridge` earlier in the callback, still put `reportPaints(bridge);` as the callback's last statement.
In `results.js` the variable is also named `bridge`.

- [ ] **Step 10: Run the gate**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` then `.venv/bin/ruff check .`
Expected: all pass, including `tests/test_style_lint*.py` (it scans `shared/web/page.js` too).

- [ ] **Step 11: Commit**

Message: `Every web page reports the revision it painted`.

---

### Task 3: Pages stay painted

**Files:**
- Modify: `shared/web_page.py`, `gui/web_page.py`, `gui/ui_manager.py` (`_create_tabs`, after the loop that adds the
  pages)
- Test: `tests/test_web_page.py`, `tests/test_web_freshness.py`, `tests/test_shell.py`

**Interfaces:**
- Consumes: Task 2's `painted_revision`, `revision`, `dataset.painted`.
- Produces: `keep_pages_painted(stack: QStackedWidget) -> None` in `shared/web_page.py`, re-exported by
  `gui/web_page.py`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_web_page.py`:

```python
def _stack(qtbot, pages=3):
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QStackedWidget, QVBoxLayout, QWidget

    stack = QStackedWidget()
    qtbot.addWidget(stack)
    views = []
    for _ in range(pages):
        holder = QWidget()
        layout = QVBoxLayout(holder)
        view = QWebEngineView(holder)
        layout.addWidget(view)
        stack.addWidget(holder)
        views.append(view)
    stack.resize(800, 600)
    stack.show()
    return stack, views


def test_kept_pages_are_all_visible_and_only_the_current_takes_focus(qtbot):
    from PySide6.QtCore import Qt

    from shared.web_page import keep_pages_painted

    stack, views = _stack(qtbot)
    before = views[0].focusPolicy()
    keep_pages_painted(stack)
    assert all(view.isVisible() for view in views)
    assert views[0].focusPolicy() == before
    assert views[1].focusPolicy() == Qt.FocusPolicy.NoFocus
    assert views[2].focusPolicy() == Qt.FocusPolicy.NoFocus

    stack.setCurrentIndex(2)
    assert views[2].focusPolicy() == before
    assert views[0].focusPolicy() == Qt.FocusPolicy.NoFocus
    proxy = views[0].focusProxy()
    assert proxy is None or proxy.focusPolicy() == Qt.FocusPolicy.NoFocus


def test_a_covered_page_stays_enabled(qtbot):
    from PySide6.QtWidgets import QPushButton

    from shared.web_page import keep_pages_painted

    stack, _views = _stack(qtbot)
    button = QPushButton("Run", stack.widget(1))
    clicks = []
    button.clicked.connect(lambda: clicks.append(1))
    keep_pages_painted(stack)
    assert stack.currentIndex() == 0
    button.click()  # the shell clicks buttons parked on covered pages
    assert clicks == [1]
```

Append to `tests/test_shell.py`:

```python
def test_every_page_of_the_shell_stays_painted(main_window):
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QStackedLayout, QStackedWidget

    stack = main_window.main_tabs.findChild(QStackedWidget)
    assert stack.layout().stackingMode() == QStackedLayout.StackingMode.StackAll
    pages = [main_window.main_tabs.widget(i) for i in range(main_window.main_tabs.count())]
    assert all(page.isVisible() for page in pages)
    main_window.main_tabs.setCurrentIndex(3)
    for index, page in enumerate(pages):
        views = [page] if isinstance(page, QWebEngineView) else page.findChildren(QWebEngineView)
        assert views, index
        for view in views:
            assert (view.focusPolicy() == Qt.FocusPolicy.NoFocus) == (index != 3), index
```

(`Qt` must be imported in `tests/test_shell.py`; add `from PySide6.QtCore import Qt` if it is not.) If a page's view
already has `NoFocus` as its own policy before this task (check with a print in a scratch run), drop the `==`
comparison for that index and assert only that covered views are `NoFocus`.

Append to `tests/test_web_freshness.py` (add the imports `QStackedWidget`, `QWidget`, the state builders,
`session`, `loaded`, `log_row`, `results_lines` now):

```python
from gui.web_page import keep_pages_painted

OLD, NEW = "OLD-SESSION-MARK", "NEW-SESSION-MARK"


def _in_stack(qtbot, name):
    """The page beside a filler in a kept stack, with the page current."""
    stack = QStackedWidget()
    qtbot.addWidget(stack)
    stack.addWidget(QWidget())
    view = QWebEngineView()
    stack.addWidget(view)
    bridge = MOUNTS[name](view)
    keep_pages_painted(stack)
    stack.resize(1166, 720)
    stack.setCurrentIndex(1)
    stack.show()
    _ready(qtbot, view)
    return stack, view, bridge


def _body(qtbot, view):
    return _eval(qtbot, view, "document.body.innerText")


def _state_push(name, mark):
    """A push that puts `mark` on the page, per page."""
    if name == "setup":
        return lambda bridge: bridge.set_state(
            setup_state_of(orders=loaded("orders", path=f"/d/{mark}.csv"))
        )
    if name == "browse":
        return lambda bridge: bridge.set_state(browse_state_of([session(mark, age=3600)]))
    if name == "tools":
        return lambda bridge: bridge.set_state(tools_state_of(client=mark))
    if name == "results":
        def push(bridge):
            lines = results_lines(12)
            lines["Order_Number"] = [f"{mark}-{n}" for n in lines["Order_Number"]]
            bridge.set_orders(lines)
        return push
    raise AssertionError(name)


@pytest.mark.parametrize("name", ["browse", "results", "setup", "tools"])
def test_a_page_pushed_while_covered_is_current_when_shown(qtbot, name):
    stack, view, bridge = _in_stack(qtbot, name)
    _state_push(name, OLD)(bridge)
    _painted(qtbot, view, bridge)
    assert OLD in _body(qtbot, view)  # the mark really is on the page

    stack.setCurrentIndex(0)  # cover it
    _state_push(name, NEW)(bridge)
    _painted(qtbot, view, bridge)  # it paints while covered
    stack.setCurrentIndex(1)

    assert bridge.painted_revision == bridge.revision
    body = _body(qtbot, view)
    assert NEW in body
    assert OLD not in body


def test_log_rows_sent_while_covered_are_there_when_shown(qtbot):
    stack, view, bridge = _in_stack(qtbot, "logs")
    stack.setCurrentIndex(0)
    bridge.send([log_row(1, NEW)])
    stack.setCurrentIndex(1)
    _until_js(qtbot, view, f"document.body.innerText.includes('{NEW}')")
```

The marker for each page is a guess at a field the page draws. The line `assert OLD in _body(...)` is what proves
it: if it fails for a page, read that page's state builder (`tests/test_setup_state.py`,
`tests/test_browse_state.py`, `tests/test_tools_state.py`) and pick a field the page does draw, keeping the test's
shape. `session(...)` and `log_row(...)` argument names are in `tests/test_browse_state.py` and
`tests/test_logs_page.py`; match them.

- [ ] **Step 2: Run them and confirm they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_web_page.py tests/test_web_freshness.py tests/test_shell.py`
Expected: FAIL with `cannot import name 'keep_pages_painted'`.

- [ ] **Step 3: Implement `keep_pages_painted`**

In `shared/web_page.py` add `from PySide6.QtCore import Qt` to the QtCore import and
`from PySide6.QtWidgets import QStackedLayout, QStackedWidget`, then append:

```python
def keep_pages_painted(stack: QStackedWidget) -> None:
    """Keep every page of `stack` painting, so a switch never shows an old frame.

    A hidden QWebEngineView stops painting and shows its last frame when it
    comes back, for as long as a new one takes. Stacked "all", the covered
    pages stay visible to Qt and to Chromium and are simply underneath.

    A covered page must not take the keyboard, so its web views (and their
    focus proxies, which are created lazily with the page) refuse focus until
    the page is current again. Pages are not disabled: that would disable the
    Qt buttons parked on them, which the shell clicks from elsewhere.
    """
    stack.layout().setStackingMode(QStackedLayout.StackingMode.StackAll)
    own_policy: dict[QWebEngineView, Qt.FocusPolicy] = {}

    def views_of(page) -> list[QWebEngineView]:
        if isinstance(page, QWebEngineView):
            return [page]
        return page.findChildren(QWebEngineView)

    def apply(*_args) -> None:
        for index in range(stack.count()):
            current = index == stack.currentIndex()
            for view in views_of(stack.widget(index)):
                policy = own_policy[view] if current else Qt.FocusPolicy.NoFocus
                view.setFocusPolicy(policy)
                proxy = view.focusProxy()
                if proxy is not None:
                    proxy.setFocusPolicy(policy)

    for index in range(stack.count()):
        for view in views_of(stack.widget(index)):
            own_policy[view] = view.focusPolicy()
            view.page().loadFinished.connect(apply)  # the proxy exists by now
    stack.currentChanged.connect(apply)
    apply()
```

Pages must be added to the stack before the call; say so in the docstring's last line:
`Call it after the stack's pages are added.`

In `gui/web_page.py` add `keep_pages_painted` to the names imported from `shared.web_page`.

- [ ] **Step 4: Call it from the shell**

In `gui/ui_manager.py`, in `_create_tabs`, directly after the `for page, label, rail_label, icon_name, tip in zip(`
loop ends, add:

```python
        # Covered pages keep painting, so a switch never shows a page's old
        # frame (2026-10-08 web tier freshness spec, section 4.1).
        keep_pages_painted(self.mw.main_tabs.findChild(QStackedWidget))
```

Change the import on line 27 to `from .web_page import keep_pages_painted, switch_theme` and add `QStackedWidget`
to the file's `PySide6.QtWidgets` import.

- [ ] **Step 5: Run the gate and look at what moved**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` then `.venv/bin/ruff check .`
Expected: all pass. Tests that asserted a page `isHidden()` or `not isVisible()` after a switch now see visible
pages: change those assertions to `main_tabs.currentIndex()` / `currentWidget()`. Do not weaken any other
assertion. If `tests/test_theme_switch.py` now times out, read the failure before changing anything:
`switch_theme` waits for every visible page, and every page now is; all of them must answer `themeApplied`.

- [ ] **Step 6: Render and look**

Per `CLAUDE.md`, verify the visuals by rendering. Write a scratch script outside the repo (under `$CLAUDE_JOB_DIR/tmp`
or `/tmp/<unique>`) that builds `MainWindow` offscreen as `scripts/stress_ui.py` does, switches through all five
pages, and saves `win.grab()` to a PNG for each. Read each PNG: every page must show itself and nothing of another
page (no bleed-through from a covered page at the edges). Delete the script and the PNGs.

- [ ] **Step 7: Commit**

Message: `Covered pages keep painting`.

---

### Task 4: Results forgets the previous session's view

**Files:**
- Modify: `gui/results_bridge.py`, `gui/web/results.js`, `gui/main_window_pyside.py` (`_reset_session_state`)
- Test: `tests/test_web_freshness.py`, `tests/test_results_bridge.py`

**Interfaces:**
- Produces: `ResultsBridge.sessionEpoch` (Qt `int` property, notify `sessionEpochChanged`),
  `ResultsBridge.forget_view() -> None`; JavaScript `resetView()` in `results.js`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_results_bridge.py`:

```python
def test_forget_view_raises_the_session_epoch(qtbot):
    bridge = ResultsBridge()
    seen = []
    bridge.sessionEpochChanged.connect(lambda: seen.append(bridge.sessionEpoch))
    bridge.forget_view()
    bridge.forget_view()
    assert seen == [1, 2]
```

(If `ResultsBridge` is not imported in that file, import it from `gui.results_bridge`.)

Append to `tests/test_web_freshness.py`:

```python
import json


def test_a_new_session_forgets_the_previous_view(qtbot):
    _stack, view, bridge = _in_stack(qtbot, "results")
    bridge.set_orders(results_lines(40))
    _painted(qtbot, view, bridge)
    _eval(
        qtbot,
        view,
        "(() => { const f = document.getElementById('search'); f.value = '#1';"
        " f.dispatchEvent(new Event('input', {bubbles: true}));"
        " document.querySelector('#header .col-order').click();"
        " document.querySelector('#header .col-select input').click();"
        " state.chips = [{kind: 'status', value: 'Fulfillable', label: 'Fulfillable'}];"
        " render(); els.scroller.scrollTop = 64; return true; })()",
    )
    before = json.loads(_eval(qtbot, view, "JSON.stringify({q: state.query, s: state.sort, n: state.selected.size})"))
    assert before["q"] == "#1" and before["s"] is not None and before["n"] > 0

    bridge.forget_view()
    lines = results_lines(12)
    lines["Order_Number"] = [f"{NEW}-{n}" for n in lines["Order_Number"]]
    bridge.set_orders(lines)
    _painted(qtbot, view, bridge)

    after = json.loads(
        _eval(
            qtbot,
            view,
            "JSON.stringify({q: state.query, field: document.getElementById('search').value,"
            " chips: state.chips.length, s: state.sort, n: state.selected.size,"
            " anchor: state.anchorKey, cursor: state.cursorKey, top: els.scroller.scrollTop,"
            " shown: state.view.length, columns: state.columnSettings})",
        )
    )
    assert after["q"] == "" and after["field"] == ""
    assert after["chips"] == 0 and after["s"] is None and after["n"] == 0
    assert after["anchor"] is None and after["cursor"] is None and after["top"] == 0
    assert after["shown"] == 12
    assert NEW in _body(qtbot, view)


def test_forgetting_the_view_keeps_the_column_choices(qtbot):
    _stack, view, bridge = _in_stack(qtbot, "results")
    bridge.set_orders(results_lines(12))
    bridge.setAutoHideEmpty(True)
    _painted(qtbot, view, bridge)
    bridge.forget_view()
    _painted(qtbot, view, bridge)
    assert _eval(qtbot, view, "state.columnSettings.auto_hide_empty") is True
```

Append to `tests/test_shell.py`:

```python
def test_every_way_into_a_session_forgets_the_view(main_window):
    before = main_window.results_bridge.sessionEpoch
    main_window._reset_session_state()
    assert main_window.results_bridge.sessionEpoch == before + 1
```

The chip literal in the first test must match the shape `results.js` builds (`{kind, value, label}`, see
`chipId` near line 180). If the status values there are different strings, use one of them.

- [ ] **Step 2: Run them and confirm they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_results_bridge.py tests/test_web_freshness.py tests/test_shell.py`
Expected: FAIL with `AttributeError: 'ResultsBridge' object has no attribute 'forget_view'`.

- [ ] **Step 3: Add the property to the bridge**

In `gui/results_bridge.py`:

1. With the other outgoing signals (after `tagCategoriesChanged = Signal()`), add
   `sessionEpochChanged = Signal()`.
2. In `__init__`, add `self._session_epoch = 0`.
3. After the `undoAvailable = Property(...)` line, add:

```python
    def _get_session_epoch(self) -> int:
        return self._session_epoch

    # Goes up when a different session opens: the page forgets its view state.
    sessionEpoch = Property(int, _get_session_epoch, notify=sessionEpochChanged)
```

4. In the "Python-facing API" section, before `set_orders`, add:

```python
    def forget_view(self) -> None:
        """Tell the page a different session is opening.

        The page owns its search, filters, sort and selection (ADR 0005), so
        only it can drop them; left alone they carry into the next session,
        which can then open on "no orders match".
        """
        self._session_epoch += 1
        self.sessionEpochChanged.emit()
```

- [ ] **Step 4: Reset the view in the page**

In `gui/web/results.js`, directly after `clearFilters()` (near line 743), add:

```js
// A different session is opening (bridge.sessionEpoch): nothing of the last
// one's view may carry over. Column choices stay; they are saved settings.
function resetView() {
  state.query = "";
  els.search.value = "";
  state.chips = [];
  state.sort = null;
  state.selected = new Set();
  state.anchorKey = null;
  state.cursorKey = null;
  closeMenu();
  closeBulkPopover();
  closePaneMenus(false);
  closeColumnsPanel(false);
  els.scroller.scrollTop = 0;
  render();
}
```

In the `QWebChannel` callback, after `bridge.columnsChanged.connect(onColumns);`, add
`bridge.sessionEpochChanged.connect(resetView);`.

Read `closeMenu` (`results.js`), `closeBulkPopover` (`bulk.js:230`), `closePaneMenus` (`pane.js:293`) and
`closeColumnsPanel` (`columns.js:99`) before relying on them: each must be safe to call when its surface is already
closed. If one is not (it dereferences an element that only exists while open), guard that one call with the same
condition its own callers use; do not change the function.

- [ ] **Step 5: Call it on every way into a session**

In `gui/main_window_pyside.py`, in `_reset_session_state`, directly before the final `self._update_all_views()`,
add:

```python
        if hasattr(self, "results_bridge"):
            self.results_bridge.forget_view()
```

and add one sentence to the docstring's first paragraph: `Tells the results page to forget its view state too.`

- [ ] **Step 6: Run the gate**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` then `.venv/bin/ruff check .`
Expected: all pass.

- [ ] **Step 7: Commit**

Message: `Results forgets the previous session's search, filters, sort and selection`.

---

### Task 5: Opening a session switches once the page has painted

**Files:**
- Modify: `gui/main_window_pyside.py` (new method; `load_existing_session` near line 1009),
  `gui/actions_handler.py:359-361`
- Test: `tests/test_shell.py`

**Interfaces:**
- Consumes: `when_painted` (Task 2), `results_bridge` on the main window.
- Produces: `MainWindow.show_results_when_painted() -> None`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_shell.py`:

```python
def test_results_is_shown_once_its_page_has_painted(main_window, qtbot):
    bridge = main_window.results_bridge
    main_window.main_tabs.setCurrentIndex(0)
    bridge.set_export_enabled(not bridge.exportEnabled)  # a change the page has not painted
    main_window.show_results_when_painted()
    assert main_window.main_tabs.currentIndex() == 0  # not before the report
    bridge.paintedRevision(bridge.revision)
    assert main_window.main_tabs.currentIndex() == 1


def test_results_is_shown_at_the_cap_when_the_page_never_answers(main_window, qtbot, monkeypatch):
    bridge = main_window.results_bridge
    # A page that never reports: swallow its reports for this test.
    monkeypatch.setattr(type(bridge), "paintedRevision", lambda self, revision: None)
    main_window.main_tabs.setCurrentIndex(0)
    bridge.set_export_enabled(not bridge.exportEnabled)
    main_window.show_results_when_painted()
    qtbot.waitUntil(lambda: main_window.main_tabs.currentIndex() == 1, timeout=2000)
```

In the first test the real page may report between the push and the assertion only if the event loop runs, and it
does not between those two lines, so the `== 0` assertion is safe. If the second test's monkeypatch does not stop a
Qt slot from running (the slot is bound at class creation), instead set `bridge.painted_revision = -1` after the
page reports by blocking the signal: `bridge.blockSignals(True)` before the push and `blockSignals(False)` after the
`waitUntil`; the timeout path then still has to switch.

- [ ] **Step 2: Run them and confirm they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_shell.py`
Expected: FAIL with `AttributeError: 'MainWindow' object has no attribute 'show_results_when_painted'`.

- [ ] **Step 3: Add the method**

In `gui/main_window_pyside.py`, directly before `_focus_results_search`, add:

```python
    def show_results_when_painted(self):
        """Switch to Results once its page has painted what it was just sent.

        Opening a session pushes the orders and switches in one step, and the
        page draws them a few frames later: switching at once shows the last
        session until then. A page that does not answer costs 150 ms.
        """
        when_painted(self.results_bridge, lambda: self.main_tabs.setCurrentIndex(1))
```

and add `from gui.web_page import when_painted` to the file's imports (match the import style already used there:
absolute `gui.` or relative).

- [ ] **Step 4: Use it at the two sites**

`gui/main_window_pyside.py`, in `load_existing_session`: replace

```python
                    # Auto-switch to Analysis Results tab (Tab 2)
                    self.main_tabs.setCurrentIndex(1)
```

with

```python
                    # Auto-switch to Analysis Results, once it has painted them
                    self.show_results_when_painted()
```

`gui/actions_handler.py`: replace

```python
            if hasattr(self.mw, "main_tabs"):
                self.mw.main_tabs.setCurrentIndex(1)
```

with

```python
            if hasattr(self.mw, "main_tabs"):
                self.mw.show_results_when_painted()
```

Leave `_focus_results_search` alone: it pushes nothing.

- [ ] **Step 5: Run the gate and fix what assumed an instant switch**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` then `.venv/bin/ruff check .`
A test that loads a session or finishes an analysis and then asserts `main_tabs.currentIndex() == 1` on the next
line now sees the switch up to 150 ms later. Change such an assertion to
`qtbot.waitUntil(lambda: win.main_tabs.currentIndex() == 1, timeout=2000)` (use the test's own window name). Tests
that build the main window from a `Mock` and assert `main_tabs.setCurrentIndex.assert_called_with(1)` now need
`show_results_when_painted.assert_called_once()` instead. Change nothing else in those tests.

- [ ] **Step 6: Commit**

Message: `Opening a session shows Results once the page has painted it`.

---

### Task 6: Reload a page whose render process died

**Files:**
- Modify: `shared/web_page.py` (`mount_page`)
- Test: `tests/test_web_freshness.py`

**Interfaces:**
- Consumes: `mount_page` from Task 1, `painted_revision` from Task 2.
- Produces: module constants `RELOAD_LIMIT = 3`, `RELOAD_WINDOW_S = 60` in `shared/web_page.py`. No new function.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_web_freshness.py`:

```python
import logging

from PySide6.QtCore import QUrl


def _kill(qtbot, view):
    """End the page's render process and wait for Qt to notice."""
    died = []
    view.page().renderProcessTerminated.connect(lambda *_: died.append(1))
    view.load(QUrl("chrome://crash"))
    qtbot.waitUntil(lambda: bool(died), timeout=15000)


def test_a_page_whose_render_process_died_comes_back_current(qtbot, caplog):
    _stack, view, bridge = _in_stack(qtbot, "browse")
    _state_push("browse", NEW)(bridge)
    _painted(qtbot, view, bridge)
    with caplog.at_level(logging.WARNING, logger="shared.web_page"):
        _kill(qtbot, view)
        _until_js(qtbot, view, f"document.body.innerText.includes('{NEW}')", timeout_s=30)
    assert "render process" in caplog.text
    _painted(qtbot, view, bridge)


def test_a_page_that_keeps_dying_is_not_reloaded_forever(qtbot, caplog):
    _stack, view, bridge = _in_stack(qtbot, "browse")
    with caplog.at_level(logging.WARNING, logger="shared.web_page"):
        for _ in range(2):
            _kill(qtbot, view)
            _ready(qtbot, view)
        _kill(qtbot, view)  # the third inside a minute
        qtbot.wait(1500)
    assert "giving up" in caplog.text
    assert view.page().renderProcessPid() == 0  # nothing was started again
```

If `chrome://crash` does not end the render process in this Qt build (`_kill` times out), replace `_kill`'s
`view.load(...)` line with `os.kill(view.page().renderProcessPid(), signal.SIGKILL)` (`import os, signal`): the
test suite runs on Linux only (`.github/workflows/build_release.yml`, `runs-on: ubuntu-latest`). If
`renderProcessPid() == 0` is not what a dead page reports here, assert instead that `_eval` of `"1"` times out
(`pytest.raises(QtBotTimeoutError)` with `timeout=1000`).

- [ ] **Step 2: Run them and confirm they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_web_freshness.py`
Expected: the first FAILS at `_until_js` (the page never comes back), the second at `_ready`.

- [ ] **Step 3: Implement the reload**

In `shared/web_page.py` add `import time` and, near the other constants:

```python
# A page whose render process dies is loaded again, unless it keeps dying.
RELOAD_LIMIT = 3
RELOAD_WINDOW_S = 60
```

In `mount_page`, replace the last two lines (the `html = ...` and `view.setHtml(...)`) with:

```python
    def _load() -> None:
        html = page.read_text(encoding="utf-8").replace(THEME_MARKER, bridge.themeCss)
        view.setHtml(html, QUrl.fromLocalFile(str(page.parent) + "/"))

    deaths: list[float] = []

    def _on_terminated(status, exit_code) -> None:
        now = time.monotonic()
        deaths[:] = [at for at in deaths if now - at < RELOAD_WINDOW_S] + [now]
        if len(deaths) >= RELOAD_LIMIT:
            logger.error(
                "%s: render process died %s times in %s s (%s, exit %s); giving up",
                page.name, len(deaths), RELOAD_WINDOW_S, status, exit_code,
            )
            return
        logger.warning(
            "%s: render process died (%s, exit %s); reloading the page",
            page.name, status, exit_code,
        )
        bridge.painted_revision = -1  # the new document has painted nothing
        # Not from inside the signal: the page is still tearing the old one down.
        QTimer.singleShot(0, _load)

    view.page().renderProcessTerminated.connect(_on_terminated)
    _load()
```

Add to `mount_page`'s docstring: `A page whose render process dies is loaded again and reads the bridge's current
state as a new page does; RELOAD_LIMIT deaths inside RELOAD_WINDOW_S stop that.`

The new document builds a fresh `QWebChannel` client against the channel already set on the page, and reads every
property then, so no re-push is needed. If the first test shows the reloaded page reaching `ready` with empty state,
the channel did not survive the crash: in `_load`, call `view.page().setWebChannel(channel)` again before
`setHtml`, and keep everything else.

- [ ] **Step 4: Run the gate**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` then `.venv/bin/ruff check .`
Expected: all pass.

- [ ] **Step 5: Commit**

Message: `Reload a web page whose render process died`.

---

### Task 7: Stress scenarios, the ADR note and the PR text

**Files:**
- Modify: `scripts/stress_ui.py`, `docs/adr/0016-the-web-tier-grows-screen-by-screen.md`
- Create: nothing in the repo. The PR text goes in a handoff note (Step 4).

**Interfaces:**
- Consumes: everything above.

- [ ] **Step 1: Add the two scenarios to `scripts/stress_ui.py`**

Read `main()` to its end first. After the scenario named `"Client switch A <-> B"` (and before whatever closes the
window or prints the table), add:

```python
    # Freshness (2026-10-08 spec): a page pushed while covered is current the
    # moment it is shown, and a dead render process is replaced.
    small, other = orders(300), orders(120)
    other["Order_Number"] = [n.replace("#1", "#9", 1) for n in other["Order_Number"]]
    first_row = "(document.querySelector('#rows .row') || {innerText: ''}).innerText"

    def covered_then_shown(i):
        frame, mark = (other, "#9") if i % 2 == 0 else (small, "#1")
        win.main_tabs.setCurrentIndex(0)
        win.analysis_results_df = frame
        win._update_all_views()
        bridge = win.results_bridge
        if not wait_for(lambda: bridge.painted_revision == bridge.revision, 5):
            raise RuntimeError("Results did not paint while covered")
        win.main_tabs.setCurrentIndex(1)
        if mark not in str(js(results, first_row)):
            raise RuntimeError("Results showed the previous orders on show")

    scenario("Results pushed while covered, then shown", 20, covered_then_shown)

    def killed(_i):
        from PySide6.QtCore import QUrl

        died = []
        results.page().renderProcessTerminated.connect(lambda *_: died.append(1))
        results.load(QUrl("chrome://crash"))
        if not wait_for(lambda: bool(died), 15):
            raise RuntimeError("the render process did not die")
        if not wait_for(
            lambda: js(results, "document.documentElement.dataset.bridge === 'ready'", 2) is True, 30
        ):
            raise RuntimeError("Results did not come back")
        js(results, ERROR_HOOK)

    scenario("Render process killed, page restored", 2, killed)
```

Two iterations of the kill, not three: the third inside a minute is refused by design. If Task 6 used `os.kill`
instead of `chrome://crash`, use the same here. `orders()` builds order numbers as `#10001…`; if the `replace`
does not produce distinct numbers for the second frame, build it with a different prefix instead, keeping
`mark` in step.

- [ ] **Step 2: Run the stress script**

Run: `.venv/bin/python scripts/stress_ui.py`
Expected: exit code 0, the markdown table printed with the two new rows, no line under failures. Copy the table
into the handoff note of Step 4.

- [ ] **Step 3: Record it in ADR 0016**

In `docs/adr/0016-the-web-tier-grows-screen-by-screen.md`, append to the "Consequences" list:

```markdown
- What every bridge shares moved to `shared/web_page.py` and `shared/web/` on 2026-10-08, with three additions
  (web tier freshness spec). The page stack runs in stack-all mode, so a covered page keeps painting and a switch
  never shows its old frame; covered pages refuse keyboard focus instead. Every bridge carries a revision the
  page reports back once painted. A page whose render process dies is loaded again. The cost: all five pages
  paint from start-up, not on first visit.
```

- [ ] **Step 4: Write the handoff note with the PR text**

Run (one call, text adjusted to what happened):

```bash
~/Desktop/Projects/dev-runner/host/runner <run id> note 'PR body must include: (1) spec + plan paths; (2) the stress table; (3) the section "What Packer Assistant changes when it syncs" copied from spec section 4.6 (six points); (4) the Packer Assistant stale clear_screen timer finding from spec section 2, as a separate packing-tool task, not fixed here; (5) the three departures in spec section 7 plus: per-page freshness tests run in a stack harness, not a MainWindow.'
```

Use the run id from your own Context block.

- [ ] **Step 5: Run the gate, update the graph, commit**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`, `.venv/bin/ruff check .`, `graphify update .`
Message: `Stress the freshness paths and record them in ADR 0016`.

---

## Self-review (done while writing)

- Spec 4.1 → Task 3. 4.2 → Task 2. 4.3 → Task 5. 4.4 → Task 4. 4.5 → Task 6. 4.6 → Task 1 (and Task 7 Step 4 for
  the PR text). Spec section 5 tests 1 → Task 3 (stack harness), 2-3 → Task 4, 4-5 → Task 2, 6 → Task 3,
  7 → Task 6, 8 → Task 5, 9 → Task 7.
- Names used across tasks: `revision`, `revisionChanged`, `painted_revision`, `painted`, `paintedRevision`,
  `when_painted`, `keep_pages_painted`, `sessionEpoch`, `sessionEpochChanged`, `forget_view`, `resetView`,
  `reportPaints`, `show_results_when_painted`, `SHARED_WEB_DIR`, `RELOAD_LIMIT`, `RELOAD_WINDOW_S`.
- Where a step depends on a fact not verified during planning (a state field a page draws, whether
  `chrome://crash` works in this Qt build, whether a close function is safe when closed), the step says how to
  check and what to do in each case. These are checks, not open design questions.
