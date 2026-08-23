# Session Setup Layout — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Decline the suggestion to switch to `subagent-driven-development` — this plan is small enough to run in-session.

**Goal:** Stop Tab 1's fixed 60/40 splitter from squeezing the setup column below the width its content needs — which today hides five action buttons behind a horizontal scrollbar at the app's own default window size — and shrink the Recent Sessions quick-pick to the five rows it can actually display.

**Architecture:** The setup column declares the minimum width its content reports, so the splitter can no longer squeeze it into scrolling. The quick-pick card gets a maximum width and a five-row fixed height, gives up its layout stretch, and the splitter's stretch factors send all extra width to the content column instead of the card.

**Tech Stack:** Python 3, PySide6, pytest. Layout only — no logic, signals, or data changes.

**Spec:** `docs/superpowers/specs/2026-08-23-session-setup-layout-design.md`

## Global Constraints

- One repo (`shopify-fulfillment-tool`), one PR. `../packing-tool` is not involved.
- **Never hand-edit `shared/`** — it is one-way synced from `../packing-tool`. This plan does not touch it.
- **No hardcoded colors.** This plan adds no stylesheets; if you find yourself writing one, stop — it is out of scope.
- Every change is in `gui/ui_manager.py` plus one new test file. If you find yourself editing a third file, re-read the spec.
- Gate, run from the worktree root:
  `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest` and `.venv/bin/ruff check . --exclude shared`
- Baseline before this plan: **761 passed**, ruff clean, on `worktree-session-setup-layout`.
- Every commit ends with these two trailers, verbatim:

```
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NYxnD8fYMdTE3M15pTB59C
```

## Pre-verified facts — do not re-derive

These were measured on this branch with a throwaway script. They are the
assumptions the literal code below depends on.

1. `scroll_widget.minimumSizeHint()` inside `_create_session_setup_panel`
   returns `(706, 587)` **before `show()`** — reading it at construction is
   sound and needs no realised window.
2. `QListWidget.sizeHintForRow(0)` returns **-1** while the list is empty, and
   it *is* empty when `_create_session_browser_panel` runs. Row height must come
   from `QFontMetrics`, which gives 17 — identical to `sizeHintForRow(0)` once
   the list is populated.
3. The right panel's layout is exactly `[QLabel, QListWidget, QPushButton]`.
4. `refresh_recent_sessions` already caps the list at 5 entries via `[:5]`.
5. `dev-server/` and `.venv` are both gitignored in this repo. Do not
   `git add -A` without checking `git show --stat HEAD` afterwards.

---

## Task 1 — Pin the regression with a failing test

The whole point of this change is that no control is hidden at the default
window size. Write that assertion first and watch it fail.

- [ ] Create `tests/test_session_setup_layout.py`:

```python
"""Regression tests for Tab 1's layout — gui.ui_manager.

Tab 1 splits into a setup column and a Recent Sessions quick-pick. The setup
column is wrapped in a QScrollArea, which is always willing to scroll rather
than ask for room, so a fixed 60/40 splitter squeezed it below the 706px its
content needs: a horizontal scrollbar appeared and five action buttons —
including "Generate Reports" — fell off the right edge at the app's own default
1100x900 geometry. See docs/superpowers/specs/2026-08-23-session-setup-layout-design.md.
"""
import pytest
from PySide6.QtWidgets import QApplication, QScrollArea, QSplitter, QPushButton


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def main_window(tmp_path, monkeypatch):
    monkeypatch.setenv("FULFILLMENT_SERVER_PATH", str(tmp_path))
    from gui.main_window_pyside import MainWindow
    win = MainWindow()
    win.resize(1100, 900)  # the app's own default, main_window_pyside.py:76
    win.show()
    QApplication.processEvents()
    win.main_tabs.setCurrentIndex(0)
    QApplication.processEvents()
    yield win
    win.close()


def _clipped_buttons(tab):
    """Buttons whose right edge falls outside the setup column's viewport."""
    scroll = tab.findChild(QScrollArea)
    inner = scroll.widget()
    limit = scroll.viewport().width()
    return [b.text() for b in inner.findChildren(QPushButton)
            if b.mapTo(inner, b.rect().topRight()).x() > limit]


def test_no_action_button_is_clipped_at_default_window_size(main_window):
    tab = main_window.main_tabs.widget(0)
    assert _clipped_buttons(tab) == []


def test_setup_column_never_scrolls_horizontally(main_window):
    tab = main_window.main_tabs.widget(0)
    scroll = tab.findChild(QScrollArea)
    assert not scroll.horizontalScrollBar().isVisible()


def test_recent_sessions_panel_stays_compact(main_window):
    tab = main_window.main_tabs.widget(0)
    card = tab.findChild(QSplitter).widget(1)
    assert card.width() <= 320
    assert main_window.recent_sessions_list.height() <= 200
```

- [ ] Run it and confirm **all three fail**, with these failures:

```
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_session_setup_layout.py -q
```

```
FAILED test_no_action_button_is_clipped_at_default_window_size - AssertionError: assert ['Load Stock ...ssion Folder'] == []
FAILED test_setup_column_never_scrolls_horizontally - assert not True
FAILED test_recent_sessions_panel_stays_compact - assert 383 <= 320
```

If any of them *passes* here, stop — the fixture is not reproducing the defect
and the test would be vacuous. Do not proceed to Task 2.

- [ ] Commit:

```bash
git add tests/test_session_setup_layout.py
git commit -m "$(cat <<'EOF'
Pin Tab 1's clipped action buttons with a failing test

At the app's own default 1100x900 geometry the setup column is squeezed to
574px against the 706px its content needs, so a horizontal scrollbar appears
and five buttons fall off the right edge.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NYxnD8fYMdTE3M15pTB59C
EOF
)"
```

---

## Task 2 — Give the setup column a minimum width, and cap the quick-pick

All edits are in `gui/ui_manager.py`.

- [ ] Add `QFontMetrics` to the `PySide6.QtGui` import (line 5):

```python
from PySide6.QtGui import QFontMetrics, QKeySequence, QShortcut
```

- [ ] Add the module-level constants after the imports, immediately before
  `class UIManager:`:

```python
# Tab 1 layout. The setup column is inside a QScrollArea, which is always
# willing to scroll rather than ask the splitter for room -- so it must declare
# the width its content needs, or action buttons get hidden. See
# docs/superpowers/specs/2026-08-23-session-setup-layout-design.md.
_SETUP_COLUMN_SLACK = 24  # frame + vertical scrollbar
_RECENT_PANEL_MAX_WIDTH = 320
_RECENT_SESSIONS_ROWS = 5


def _recent_list_height(widget: QListWidget) -> int:
    """Height of exactly _RECENT_SESSIONS_ROWS rows.

    From font metrics, not sizeHintForRow(), which returns -1 while the list is
    empty -- and it is empty when the panel is built.
    """
    row = QFontMetrics(widget.font()).height()
    return row * _RECENT_SESSIONS_ROWS + 2 * widget.frameWidth() + 4
```

- [ ] In `_create_session_setup_panel`, replace the tail of the method:

```python
        scroll.setWidget(scroll_widget)
        outer_layout.addWidget(scroll)

        return panel
```

with:

```python
        scroll.setWidget(scroll_widget)
        outer_layout.addWidget(scroll)

        # A QScrollArea's own minimum is tiny -- it would rather scroll than ask
        # for room, which let the splitter squeeze this column below the 706px
        # its content needs and hide action buttons behind a horizontal
        # scrollbar. Pin the minimum to what the content actually reports; the
        # hint is already correct here, before show().
        panel.setMinimumWidth(
            scroll_widget.minimumSizeHint().width() + _SETUP_COLUMN_SLACK
        )

        return panel
```

- [ ] In `_create_session_browser_panel`, cap the panel width. Replace:

```python
        panel = QWidget()
        layout = QVBoxLayout(panel)
```

with:

```python
        panel = QWidget()
        panel.setMaximumWidth(_RECENT_PANEL_MAX_WIDTH)
        layout = QVBoxLayout(panel)
```

- [ ] In the same method, stop the list taking the layout's stretch and fix its
  height. Replace:

```python
        self.mw.recent_sessions_list = QListWidget()
        self.mw.recent_sessions_list.itemDoubleClicked.connect(self._on_recent_session_double_clicked)
        layout.addWidget(self.mw.recent_sessions_list, 1)
```

with:

```python
        self.mw.recent_sessions_list = QListWidget()
        self.mw.recent_sessions_list.itemDoubleClicked.connect(self._on_recent_session_double_clicked)
        self.mw.recent_sessions_list.setFixedHeight(
            _recent_list_height(self.mw.recent_sessions_list)
        )
        layout.addWidget(self.mw.recent_sessions_list)
```

- [ ] In the same method, keep the card at the top. Replace:

```python
        layout.addWidget(open_full_link)

        return panel
```

with:

```python
        layout.addWidget(open_full_link)
        layout.addStretch()  # keep the list and its link together at the top

        return panel
```

  The stretch must come **after** `open_full_link`. Putting it between the list
  and the button strands the link at the bottom of the window.

- [ ] In `_create_tab1_session_setup`, replace the splitter sizing block:

```python
        # Set initial sizes (60:40 proportion)
        splitter.setSizes([600, 400])
        splitter.setStretchFactor(0, 6)
        splitter.setStretchFactor(1, 4)
```

with:

```python
        # All extra width goes to the setup content, not the quick-pick card --
        # a 6:4 stretch re-inflates the card to 642px on a wide monitor for a
        # five-row list.
        splitter.setSizes([1100, _RECENT_PANEL_MAX_WIDTH])
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setCollapsible(1, True)
```

- [ ] Update the class docstring of `_create_tab1_session_setup` — it still
  claims a 60/40 split. Replace:

```python
        - Left panel (60%): Session management, File loading, Actions, Reports
        - Right panel (40%): Recent Sessions quick-pick (full browser is on Tab 3)
```

with:

```python
        - Left panel: Session management, File loading, Actions, Reports. Takes
          all width the quick-pick does not need, and never less than its
          content requires.
        - Right panel: Recent Sessions quick-pick, capped at
          _RECENT_PANEL_MAX_WIDTH (full browser is on Tab 3).
```

- [ ] Tie the row count to the height. In `refresh_recent_sessions`, replace:

```python
        sessions = self.mw.session_manager.list_client_sessions(client_id)[:5]
```

with:

```python
        sessions = self.mw.session_manager.list_client_sessions(client_id)[
            :_RECENT_SESSIONS_ROWS
        ]
```

- [ ] Record the known ceiling. Add this comment inside `_create_files_group`,
  directly above `layout.addWidget(self._create_orders_file_section())`:

```python
        # ponytail: Orders and Stock side by side set this page's 706px floor.
        # Below a ~1050px window the setup column stops shrinking. The app's own
        # default is 1100px, so no responsive stacking is built; if that ever
        # matters, stack these two vertically below a width threshold.
```

- [ ] Run the new test file and confirm **all three now pass**:

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_session_setup_layout.py -q
```

- [ ] Commit:

```bash
git add gui/ui_manager.py
git commit -m "$(cat <<'EOF'
Stop the Recent Sessions panel starving Tab 1's setup column

The setup column sits in a QScrollArea, which would rather scroll than ask the
splitter for room, so the fixed 60/40 split squeezed it to 574px against the
706px its content needs -- hiding Load Stock File, Add Product to Order,
Settings, Generate Reports and Open Session Folder behind a horizontal
scrollbar at the default window size.

The column now declares its content's minimum width, so anything added to it
widens that minimum automatically. The quick-pick is capped at 320px and sized
to the five rows refresh_recent_sessions actually shows, down from 363x692.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NYxnD8fYMdTE3M15pTB59C
EOF
)"
```

---

## Task 3 — Verify the fix holds, and run the gate

- [ ] Confirm the change actually does what the spec claims, at three sizes.
  Write this to `$CLAUDE_JOB_DIR/tmp/check_layout.py` (throwaway — do **not**
  commit it):

```python
import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("FULFILLMENT_SERVER_PATH", "/tmp/sft-layout-check")
os.makedirs("/tmp/sft-layout-check", exist_ok=True)
from PySide6.QtWidgets import QApplication, QScrollArea, QSplitter, QPushButton
app = QApplication(sys.argv)
from gui.main_window_pyside import MainWindow

w = MainWindow(); w.show(); w.main_tabs.setCurrentIndex(0)
tab = w.main_tabs.widget(0)
scroll = tab.findChild(QScrollArea); inner = scroll.widget()
sp = tab.findChild(QSplitter)
for W, H in [(1920, 1080), (1400, 900), (1100, 900)]:
    w.resize(W, H); app.processEvents()
    vw = scroll.viewport().width()
    clipped = [b.text() for b in inner.findChildren(QPushButton)
               if b.mapTo(inner, b.rect().topRight()).x() > vw]
    print(f"{W}x{H}: splitter={sp.sizes()} content={vw} "
          f"list={w.recent_sessions_list.width()}x{w.recent_sessions_list.height()} "
          f"clipped={clipped}")
```

  Expected output — the numbers from the spec's "Resulting geometry" table:

```
1920x1080: splitter=[1356, 300] content=1356 list=280x91 clipped=[]
1400x900:  splitter=[836, 300]  content=836  list=280x91 clipped=[]
1100x900:  splitter=[730, 227]  content=730  list=207x91 clipped=[]
```

  Splitter numbers may vary by a pixel or two with fonts/DPI. What must hold:
  `clipped=[]` at every size, list height ~91, and the card never above 320.

- [ ] Run the full gate:

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest
.venv/bin/ruff check . --exclude shared
```

  Expect **764 passed** (761 baseline + 3 new) and ruff clean. If any
  pre-existing test fails, it is encoding the old 60/40 geometry — read it
  before changing it, and say so in the PR rather than quietly rewriting it.

- [ ] Confirm nothing stray was committed:

```bash
git show --stat HEAD
git status --short
```

  `dev-server/` and `.venv` are gitignored, but check anyway.

- [ ] Update the knowledge graph, per this repo's CLAUDE.md:

```bash
graphify update .
```

- [ ] Push the branch:

```bash
git push -u origin worktree-session-setup-layout
```

---

## Out of scope — do not do these

- Changing what the quick-pick shows, or how sessions load.
- Touching `SessionBrowserWidget` or Tab 3.
- Responsive stacking of the Orders/Stock sections (the 706px floor is a
  documented ceiling, recorded as a `ponytail:` comment in Task 2).
- Setting a minimum size on the main window.
- Any edit under `shared/`.
- A version bump — versions move together at release.
