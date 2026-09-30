# UI refresh bug fixes (StatePanel clipping, Browse `CLIENT_None`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the two bugs the 2026-09-30 UI audit found: a `StatePanel` whose text wraps is clipped
(both apps), and Browse says "CLIENT_None has no sessions" when no client is selected.

**Architecture:** S1 is fixed in packing-tool's canonical `shared/components/state_panel.py` (centre
the card with stretches, not `Qt.AlignCenter`), then synced into this repo with
`scripts/sync_shared.py`. B1 adds a `"no_client"` empty reason to `SessionBrowserWidget`.

**Tech Stack:** Python 3.14, PySide6 6.11, pytest.

**Spec:** `docs/superpowers/specs/2026-09-30-ui-refresh-audit-and-prompts-design.md` (section
"Built at Stage B"). The docs it lists under "Written at Stage A" are already committed. Do not
edit them.

## Global Constraints

- Two worktrees, both on branch `dr/11-can-we-think-about-improved-ui-and-optim`:
  - `F` = `/home/gloopy/Desktop/Projects/shopify-fulfillment-tool/.claude/worktrees/dr-11`
  - `P` = `/home/gloopy/Desktop/Projects/packing-tool/.claude/worktrees/dr-11`
- **Never hand-edit `F/shared/`.** Edit `P/shared/`, then run
  `.venv/bin/python scripts/sync_shared.py /home/gloopy/Desktop/Projects/packing-tool/.claude/worktrees/dr-11` from `F`.
- Git: `/usr/bin/git`, one plain command per Bash call, no `;`/`&&` chaining, no `$VAR` paths.
  Commit with `/usr/bin/git commit -F <absolute path to a message file>`. Every commit message ends with:
  ```
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  ```
  (Replace the model name with your own if you are a different model.)
- Tests are written with Write/Edit, never with shell heredocs (a hook blocks Bash text containing
  "pytest" other than the plain run form).
- Test run form: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`, run from the repo root.
  If a single-file run is refused by the hook, run the whole suite.
- Gates: F: the suite above plus `.venv/bin/ruff check . --exclude shared`. P: the suite above plus
  `.venv/bin/ruff check .`.
- Copy: the no-client panel reads exactly title `Choose a client`, cause
  `Pick a client in the bar above to see its sessions.`, and has **no button**.
- Do not open PRs. Stage C opens them. Push both branches at the end.

## Review Focus

1. **A cause that wraps to three or more lines** (a long server path in `StatePanel.failed`'s
   detail): every label must still get its `heightForWidth`. Pinned in Task 1 (parametrized cause lengths).
2. **A wrapped panel with a button** (`nothing_loaded` with action text): the button must stay inside
   the card below the full text. Pinned in Task 1 (button bottom ≤ card height).
3. **Fonts growing after construction** (theme toggle or density change re-runs `font_css`): the card
   must re-grow, which is why the fix is layout-driven and not a fixed minimum height. Pinned in
   Task 1 (a bigger `font-size` stylesheet after `show()`; verified at planning: the old layout
   clips, the fixed layout re-grows the card from 122px to 159px).
4. **Choosing a client after the no-client panel showed**: the panel must switch to "No sessions yet"
   with *New session*. Pinned in Task 3.
5. **No client but a filter active**: the reason stays `"filtered"`, not `"no_client"`. Pinned in Task 3.

---

### Task 1: StatePanel sizes wrapped text (packing-tool)

**Files:**
- Modify: `P/shared/components/state_panel.py:19-20` (imports) and `:73-78` (the centring block)
- Test: `P/tests/test_state_panel.py` (append)

**Interfaces:**
- Consumes: `StatePanel`, `StatePanel.nothing_loaded(title, cause, action_text)`,
  `StatePanel.failed(title, cause, detail, action_text)`; `panel.card` (a `Card`), `panel.button`.
- Produces: no API change. Later tasks rely only on the behaviour: a wrapped label is never clipped.

- [ ] **Step 1: Write the failing tests.** Append to `P/tests/test_state_panel.py` (it already
  imports `pytest`, `QLabel`, `QPushButton` and `StatePanel`; the `qapp` fixture comes from
  `tests/conftest.py`):

```python
# Audit 2026-09-30 S1: a cause that wraps was clipped, because the card was
# centred with Qt.AlignCenter and so sized from sizeHint(), never from its
# labels' heightForWidth().

_WRAPPING = "Pick a client in the bar above. Sessions, stock and reports all belong to one client."


def _shown(panel, qapp, size=(1300, 700)):
    panel.resize(*size)
    panel.show()
    qapp.processEvents()
    return panel


def _clipped(panel):
    return [
        label.text()
        for label in panel.card.findChildren(QLabel)
        if label.height() < label.heightForWidth(label.width())
    ]


@pytest.mark.parametrize("repeat", [1, 3, 6])
def test_a_wrapping_cause_is_never_clipped(qapp, repeat):
    panel = _shown(StatePanel.nothing_loaded("Choose a client to begin", " ".join([_WRAPPING] * repeat), ""), qapp)
    assert _clipped(panel) == []


def test_a_long_detail_line_is_never_clipped(qapp):
    detail = "\\\\warehouse-fs01\\fulfilment\\clients\\CLIENT_ACME\\sessions\\" * 4
    panel = _shown(StatePanel.failed("The server can't be reached", _WRAPPING, detail, "Server connection…"), qapp)
    assert _clipped(panel) == []


def test_the_button_stays_inside_the_card_below_wrapped_text(qapp):
    panel = _shown(StatePanel.nothing_loaded("No sessions yet", _WRAPPING * 2, "New session"), qapp)
    assert _clipped(panel) == []
    assert panel.button.geometry().bottom() <= panel.card.height()


def test_the_card_regrows_when_its_font_grows(qapp):
    # The route a theme or density change takes (ADR 0003): the label's
    # stylesheet is re-run with a new font_css. setFont() would be overridden
    # by the stylesheet, so it would not test anything.
    panel = _shown(StatePanel.nothing_loaded("Choose a client to begin", _WRAPPING, ""), qapp)
    for label in panel.card.findChildren(QLabel):
        label.setStyleSheet(label.styleSheet() + " font-size: 20pt;")
    # Two passes: the first delivers the font change, the second the relayout.
    qapp.processEvents()
    qapp.processEvents()
    assert _clipped(panel) == []
```

- [ ] **Step 2: Run the suite from `P` and confirm the new tests fail.**
  Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
  Expected: every new test FAILS (measured at planning: the cause label is 22px tall and needs
  36px; the button test fails on its first assert).
  If any of them passes before the fix, stop and report. The test is not exercising the bug.

- [ ] **Step 3: Fix the centring.** In `P/shared/components/state_panel.py`, change the import
  line to:

```python
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout, QWidget
```

  and replace the block

```python
        # Centring is stretches, not margins -- a margin has to be recomputed
        # for every page size the card lands on.
        outer = QVBoxLayout(self)
        outer.addStretch(1)
        outer.addWidget(self.card, 0, Qt.AlignCenter)
        outer.addStretch(1)
```

  with

```python
        # Centring is stretches, not margins -- a margin has to be recomputed
        # for every page size the card lands on. Not Qt.AlignCenter either: an
        # aligned layout item is sized from sizeHint(), so a cause that wraps
        # never gets its heightForWidth() and is clipped (audit 2026-09-30 S1).
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.card)
        row.addStretch(1)
        outer = QVBoxLayout(self)
        outer.addStretch(1)
        outer.addLayout(row)
        outer.addStretch(1)
```

  `Qt` is still used by the button's `Qt.AlignCenter` above, so keep its import.

- [ ] **Step 4: Run the suite and lint from `P`.**
  Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`, then `.venv/bin/ruff check .`
  Expected: all pass, including the existing `test_state_panel.py` tests and the five new ones.

- [ ] **Step 5: Look at it.** Write `/home/gloopy/.claude/jobs/<your job id or any scratch dir>/panel.py`
  (outside both repos) with:

```python
import sys
sys.path.insert(0, ".")
from PySide6.QtWidgets import QApplication
app = QApplication([])
from shared.components.state_panel import StatePanel
p = StatePanel.nothing_loaded("Choose a client to begin", "Pick a client in the bar above. Sessions, stock and reports all belong to one client.", "")
p.resize(900, 500); p.show(); app.processEvents()
p.grab().save(sys.argv[1])
```

  Run it from `P` with `QT_QPA_PLATFORM=offscreen .venv/bin/python <that file> <scratch>/panel.png`
  and Read the PNG. Both sentences must be fully visible inside the grey card.

- [ ] **Step 6: Commit in `P`.**
  `/usr/bin/git add shared/components/state_panel.py tests/test_state_panel.py`, then
  `/usr/bin/git commit -F <msg file>` with the message:

```
fix(shared): StatePanel no longer clips a cause that wraps

The card was centred with Qt.AlignCenter, so the layout sized it from
sizeHint() and never asked its wrapped labels for heightForWidth(). Centre
it with stretches instead. Found by the fulfilment tool's 2026-09-30 UI
audit on Setup's "Choose a client to begin".

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

---

### Task 2: Sync `shared/` into the fulfilment tool

**Files:**
- Modify (by the sync script only): `F/shared/components/state_panel.py`

**Interfaces:**
- Consumes: Task 1's committed `P/shared/`.
- Produces: `F/shared/components/state_panel.py` identical to P's.

- [ ] **Step 1: Sync.** From `F`:
  `.venv/bin/python scripts/sync_shared.py /home/gloopy/Desktop/Projects/packing-tool/.claude/worktrees/dr-11`

- [ ] **Step 2: Check the sync changed only that file.** `/usr/bin/git status --short` in `F` must
  list `shared/components/state_panel.py` and nothing else under `shared/`. If other `shared/` files
  changed, P's `origin/main` has moved ahead of F's copy. Stop, record it with the runner's `note`,
  and do not commit unrelated shared changes.

- [ ] **Step 3: Run F's gate.**
  `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`, then `.venv/bin/ruff check . --exclude shared`.
  Expected: all pass.

- [ ] **Step 4: Commit in `F`.** `/usr/bin/git add shared/components/state_panel.py`, then commit with:

```
chore(shared): sync StatePanel wrap fix from packing-tool

Setup's "Choose a client to begin" no longer clips its second sentence.
Depends on the packing-tool PR from branch
dr/11-can-we-think-about-improved-ui-and-optim.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

---

### Task 3: Browse shows "Choose a client" with no client

**Files:**
- Modify: `F/gui/session_browser_widget.py`: `_empty_reason` (around line 689) and
  `_update_empty_state` (around line 701)
- Test: `F/tests/test_session_browser_columns.py`, class `TestEmptyStates` (around line 256)

**Interfaces:**
- Consumes: `SessionBrowserWidget.current_client_id: str | None`, `.sessions_data: list[dict]`,
  `._populate_tree()`, `._empty_reason() -> str | None`, `.empty_panel: StatePanel | None`,
  `StatePanel.nothing_loaded(title, cause, action_text)`.
- Produces: `_empty_reason()` may now return `"no_client"`, alongside `None`, `"nothing"` and `"filtered"`.

- [ ] **Step 1: Write the failing tests.** Add these methods to `class TestEmptyStates` in
  `F/tests/test_session_browser_columns.py` (the module already imports `QLabel`; the `browser`
  fixture sets `current_client_id = "M"` and `USE_ASYNC = False`; `calm_sessions` is an existing
  fixture):

```python
    # Audit 2026-09-30 B1: with no client the panel said "CLIENT_None has no
    # sessions" and offered New session, which needs a client.
    def test_no_client_asks_for_one_and_offers_nothing(self, browser):
        browser.current_client_id = None
        browser.sessions_data = []
        browser._populate_tree()
        assert browser._empty_reason() == "no_client"
        assert browser.empty_panel.button is None
        texts = [label.text() for label in browser.empty_panel.findChildren(QLabel)]
        assert "Choose a client" in texts
        assert "Pick a client in the bar above to see its sessions." in texts
        assert not any("None" in text for text in texts)

    def test_choosing_a_client_brings_back_new_session(self, browser):
        browser.current_client_id = None
        browser.sessions_data = []
        browser._populate_tree()
        browser.current_client_id = "M"
        browser._populate_tree()
        assert browser._empty_reason() == "nothing"
        assert browser.empty_panel.button.text() == "New session"

    def test_a_filter_with_no_client_is_still_a_filter(self, browser, calm_sessions):
        browser.current_client_id = None
        browser.sessions_data = calm_sessions
        browser.filter_bar.search_field.setText("tuesday")
        browser._populate_tree()
        assert browser._empty_reason() == "filtered"
```

- [ ] **Step 2: Run the suite from `F` and confirm the first test fails** (reason is `"nothing"`,
  and the panel says `CLIENT_None …`). The second and third should already pass. They guard the fix.

- [ ] **Step 3: Implement.** In `_empty_reason`, update the docstring's first line to
  `None, "no_client", "nothing" or "filtered" -- why the tree has no rows.` and replace its last line

```python
        return "filtered" if self.sessions_data else "nothing"
```

  with

```python
        if self.sessions_data:
            return "filtered"
        # No client means there is nothing to list yet, not an empty server.
        return "nothing" if self.current_client_id else "no_client"
```

  In `_update_empty_state`, replace `if reason == "nothing":` with a new first branch and keep
  the rest as it is:

```python
        if reason == "no_client":
            # No button: a new session needs a client, and the selector is
            # the command bar's, one line above.
            panel = StatePanel.nothing_loaded(
                "Choose a client",
                "Pick a client in the bar above to see its sessions.",
                "",
            )
        elif reason == "nothing":
```

  Nothing after the branches touches `panel.button` (checked at planning: only
  `self.empty_panel = panel` and `self.main_layout.insertWidget(1, panel, 1)` follow), so no guard is
  needed. The `"nothing"` and `"filtered"` branches connect their own buttons.

- [ ] **Step 4: Run F's gate.** `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`, then
  `.venv/bin/ruff check . --exclude shared`. Expected: all pass.

- [ ] **Step 5: Look at it.** Write a scratch script outside the repo:

```python
import os, sys, tempfile
os.environ["FULFILLMENT_SERVER_PATH"] = tempfile.mkdtemp()
sys.path.insert(0, ".")
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer, QEventLoop
app = QApplication([])
from gui.main_window_pyside import MainWindow
w = MainWindow(); w.resize(1366, 768); w.show()
loop = QEventLoop(); QTimer.singleShot(1500, loop.quit); loop.exec()
w.main_tabs.setCurrentIndex(2)
loop = QEventLoop(); QTimer.singleShot(600, loop.quit); loop.exec()
w.grab().save(sys.argv[1] + "/browse.png")
w.main_tabs.setCurrentIndex(0)
loop = QEventLoop(); QTimer.singleShot(600, loop.quit); loop.exec()
w.grab().save(sys.argv[1] + "/setup.png")
```

  Run it from `F` with `QT_QPA_PLATFORM=offscreen .venv/bin/python <file> <scratch dir>` and Read
  both PNGs. Browse must show "Choose a client" with no button, and Setup's "Choose a client to
  begin" must show both sentences in full. Compare with
  `docs/design/ui-refresh/current/light-browse-no-client.png` and `light-setup-no-client.png`, which
  show the bugs.

- [ ] **Step 6: Commit in `F`.** `/usr/bin/git add gui/session_browser_widget.py tests/test_session_browser_columns.py`,
  then commit with:

```
fix(browse): ask for a client instead of "CLIENT_None has no sessions"

With no client selected, Browse's empty state named CLIENT_None and offered
New session, which cannot work without a client. It now says "Choose a
client" and offers nothing. Found by the 2026-09-30 UI audit.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

- [ ] **Step 7: Refresh the graph and push both branches.**
  From `F`: `graphify update .` (CLAUDE.md: always after modifying code; `graphify-out/` is
  gitignored, so there is nothing to commit).
  Then `/usr/bin/git push` in `F`, and `/usr/bin/git push -u origin dr/11-can-we-think-about-improved-ui-and-optim` in `P`.
