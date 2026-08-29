# CommandBar Primary Action Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Runner note:** the roadmap runner's Stage B declines `subagent-driven-development` and stays in-session with `superpowers:executing-plans`.

**Goal:** Make "primary" something a screen declares rather than what every unmarked
`QPushButton` defaults to, then bind each Shopify screen's own primary button into the
CommandBar's dormant action slot.

**Architecture:** Two independent halves, shipped as separate commits. (1) The bare
`QPushButton` rule in `shared/theme.py` takes the `role="secondary"` appearance, so the
~103 unmarked buttons across both apps stop rendering primary blue; each app then marks
its genuine primaries opt-in. (2) `CommandBar.bind_action(button)` mirrors a screen's
existing in-page primary — its label, tooltip, enabled state and click — and hides the
in-page copy, so the enabled-state logic living in three other modules is never touched.

**Tech Stack:** Python 3, PySide6, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-08-29-commandbar-primary-action-design.md`

## Global Constraints

- **`shared/theme.py` is authored in `packing-tool`.** Editing shopify's copy directly is a
  defect the next `scripts/sync_shared.py` run silently overwrites. Tasks 1–2 happen in
  packing-tool; task 3 syncs.
- **Two PRs, packing-tool merges first.** Same shape the selection-ring item used.
- **No direct commits to `main`** in either repo, no exception for docs-only changes.
  Branch + PR always.
- **Never re-derive a hex.** This change introduces no new colour value; it re-points a
  selector at tokens that already ship.
- **The ten legacy aliases** (`background`, `background_elevated`, four `accent_*`,
  `active_background`, `active_border`, `button_hover_light/dark`) are read-only. No new
  call site may read one.
- **Navigation commits stay separate from cosmetic restyle.** Tasks 1–5 are cosmetic;
  tasks 6–7 are navigational. Do not squash across that line.
- **Structure never changes labels in the same release.** Every button keeps its exact
  current text, glyphs included ("▶ Run Analysis" stays "▶ Run Analysis").
- `python` is not on `PATH`. Use `.venv/bin/python` or the `scripts/` wrappers.
- Gate for shopify: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest` and
  `.venv/bin/ruff check . --exclude shared`. Packing-tool's gate is in its own `CLAUDE.md`.

---

## File Structure

**packing-tool** (worktree `worktree-commandbar-primary`, branched from `origin/main`):

| file | responsibility |
|---|---|
| `shared/theme.py` | Modify `build_stylesheet` — one selector. Canonical source. |
| `tests/test_shared_theme_buttons.py` | Modify — pin the default-is-not-primary rule. |
| `gui/main_window.py`, `gui/session_selector.py`, `gui/restore_session_dialog.py`, `gui/sku_mapping_dialog.py` | Modify — one `set_button_role(..., "primary")` each. |

**shopify-fulfillment-tool** (worktree `worktree-commandbar-primary`, already created):

| file | responsibility |
|---|---|
| `shared/theme.py` | Overwritten by `scripts/sync_shared.py`. Never hand-edited. |
| `gui/theme_manager.py` | Add `apply_dialog_button_roles` — marks a dialog's accept button. |
| 10 dialog modules | Modify — one helper call each after the `QDialogButtonBox` construction. |
| `gui/column_config_dialog.py`, `gui/report_selection_dialog.py` | Modify — mark the hand-rolled accept button primary. |
| `gui/ui_manager.py` | Delete two dead helpers; add `_SCREEN_ACTIONS` and `_bind_screen_action`. |
| `gui/components/commandbar.py` | Add `bind_action` and the enabled-state event filter. |
| `tests/test_theme_manager_button_roles.py` | Modify — cover the new helper. |
| `tests/test_components_commandbar.py` | Modify — cover `bind_action`. |
| `tests/test_screen_primary_actions.py` | Create — the per-screen wiring. |

---

## Task 1: The default button role becomes secondary

**Repo:** `packing-tool`. Create the worktree first:

```bash
cd /home/cognitiveghost/Desktop/Projects/packing-tool
git fetch origin
git worktree add .claude/worktrees/worktree-commandbar-primary -b worktree-commandbar-primary origin/main
cd .claude/worktrees/worktree-commandbar-primary
```

**Files:**
- Modify: `shared/theme.py:538-547` (the bare `QPushButton` block in `build_stylesheet`)
- Test: `tests/test_shared_theme_buttons.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `build_stylesheet(theme)` whose bare `QPushButton` selector renders
  `theme.surface_raised` / `theme.text` / `theme.border`. Every later task assumes an
  unmarked button is secondary.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_shared_theme_buttons.py`:

```python
def _default_button_block(sheet: str) -> str:
    """The body of the bare `QPushButton {` rule.

    `QPushButton[role="primary"] {` and `QPushButton:hover {` do not match the
    split token, so this finds the unqualified selector and only that one.
    """
    return sheet.split("QPushButton {", 1)[1].split("}", 1)[0]


def test_an_unmarked_button_is_not_primary():
    """The whole point: primary is declared, never defaulted into."""
    for theme in (DARK_THEME, LIGHT_THEME):
        block = _default_button_block(build_stylesheet(theme))
        assert theme.surface_raised in block
        assert theme.accent_fill not in block


def test_marking_a_button_primary_still_fills_it_with_the_accent():
    for theme in (DARK_THEME, LIGHT_THEME):
        sheet = build_stylesheet(theme)
        primary = sheet.split('QPushButton[role="primary"] {', 1)[1].split("}", 1)[0]
        assert theme.accent_fill in primary
```

Add whatever of `DARK_THEME`, `LIGHT_THEME`, `build_stylesheet` the file does not already
import from `shared.theme`.

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_shared_theme_buttons.py -v`

Expected: `test_an_unmarked_button_is_not_primary` FAILS on
`assert theme.surface_raised in block` — the default block currently holds `accent_fill`.
`test_marking_a_button_primary_still_fills_it_with_the_accent` PASSES already; it is the
guard that task 1 does not overshoot.

- [ ] **Step 3: Change the one selector**

In `shared/theme.py::build_stylesheet`, replace the bare `QPushButton` rule and its
`:hover` / `:pressed` lines. Leave `:disabled` and all four `[role=...]` blocks untouched.

```python
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
```

The `[role="secondary"]` block now restates the default. **Keep it** — 42 shopify call
sites name it, and an explicit role documents intent where an absent property cannot.
Delete the comment above `QPushButton[role="secondary"]:pressed` that reads *"the bare
QPushButton rule presses to dark accent-blue, which reads as primary for the fraction of a
second it is held"* — it describes behaviour this task just removed.

- [ ] **Step 4: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_shared_theme_buttons.py -v`
Expected: PASS.

Then the whole packing-tool suite — other tests may assert on button colour:
`QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest`

Any failure asserting a button is `accent_fill` is this change working. Update the
assertion; do not revert the rule. Note each such edit for the PR body.

- [ ] **Step 5: Update the `shared/theme.py` self-check**

`shared/theme.py` has a `__main__` self-check block (around line 807) that already asserts
each `QPushButton[role="..."]` selector is present. Add one line beside those asserts:

```python
        assert theme.accent_fill not in sheet.split("QPushButton {", 1)[1].split("}", 1)[0]
```

Run it: `.venv/bin/python shared/theme.py` — expected: exits 0, no assertion error.

- [ ] **Step 6: Commit**

```bash
git add shared/theme.py tests/test_shared_theme_buttons.py
git commit -m "The default button role becomes secondary, not primary"
```

---

## Task 2: packing-tool marks its four real primaries

**Files:**
- Modify: `gui/main_window.py:385`
- Modify: `gui/session_selector.py:222`
- Modify: `gui/restore_session_dialog.py:72`
- Modify: `gui/sku_mapping_dialog.py:132`

**Interfaces:**
- Consumes: task 1's default flip.
- Produces: nothing other tasks read.

Without this, task 1 leaves packing-tool with no primary anywhere — a flat hierarchy in
place of an inverted one. These four are the only buttons that pass the spec's rule: *the
single action its screen or dialog exists to perform.*

The spec's §4.1 candidate list named `Scan`. **It is wrong and must not be marked**:
`gui/packer_mode_widget.py:299`'s `sim_btn` is a developer scan simulator sitting beside a
`QLineEdit`, not the screen's action. `Add Mapping` (`sku_mapping_dialog.py:110`) is a
row-add inside a dialog whose action is `Save & Close`; leave it secondary too.

- [ ] **Step 1: Mark `Start Packing`**

`gui/main_window.py`, immediately after line 385's construction:

```python
        self.packer_mode_button = QPushButton("Start Packing")
        set_button_role(self.packer_mode_button, "primary")
```

Add `set_button_role` to the file's existing `from shared.theme import ...` (or
`gui.theme` re-export, whichever that module already uses for theme helpers).

- [ ] **Step 2: Mark the three dialog accept buttons**

`gui/session_selector.py` after line 222:

```python
        self.load_button = QPushButton("Load Session")
        set_button_role(self.load_button, "primary")
```

`gui/restore_session_dialog.py` after line 72:

```python
        self.restore_button = QPushButton("Restore Selected")
        set_button_role(self.restore_button, "primary")
```

`gui/sku_mapping_dialog.py` after line 132:

```python
        save_button = QPushButton("Save & Close")
        set_button_role(save_button, "primary")
```

Each file needs the `set_button_role` import added.

- [ ] **Step 3: Write the test**

Create `tests/test_screen_primaries.py`:

```python
"""Every screen and dialog names exactly one primary.

Pins the four call sites the 2026-08-29 default-role flip depends on: with the
bare QPushButton rule no longer painting accent_fill, a primary that loses its
set_button_role call goes silently grey rather than failing loudly.
"""
from PySide6.QtWidgets import QPushButton


def _primaries(widget) -> list[str]:
    return [
        b.text() for b in widget.findChildren(QPushButton)
        if b.property("role") == "primary"
    ]
```

Then one test per dialog that can be constructed without a live server. Follow whatever
construction pattern that dialog's existing tests use; if a dialog has no existing test and
needs a session manager or server path, assert on the module instead:

```python
def test_the_packer_mode_button_is_marked_primary():
    import inspect
    from gui import main_window
    source = inspect.getsource(main_window)
    assert 'set_button_role(self.packer_mode_button, "primary")' in source
```

Use the source assertion only where constructing the widget needs I/O. A constructed-widget
assertion via `_primaries()` is better wherever it is possible.

- [ ] **Step 4: Run the gate**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest`
Expected: PASS. Then packing-tool's lint per its `CLAUDE.md`.

- [ ] **Step 5: Commit and push**

```bash
git add -A
git commit -m "The four buttons packing-tool actually wants primary say so"
git push -u origin worktree-commandbar-primary
```

- [ ] **Step 6: Open the packing-tool PR (draft)**

Body must state: the default button role changed, ~39 packing-tool buttons now render
secondary, four are explicitly primary, and shopify's companion PR cannot merge first.

---

## Task 3: shopify pulls the shared change

**Repo:** shopify, worktree `worktree-commandbar-primary` (already created, branch
`worktree-commandbar-primary`).

**Files:**
- Modify: `shared/theme.py` (by sync only — never by hand)

**Interfaces:**
- Consumes: task 1's `shared/theme.py`.
- Produces: shopify's `shared/` matching packing-tool's, so tasks 4–7 build on the flipped
  default.

- [ ] **Step 1: Sync**

The sibling default resolves to `.claude/worktrees/packing-tool` from inside a worktree and
does not exist, so pass the path explicitly — to the packing-tool **worktree** holding
task 1's commit:

```bash
.venv/bin/python scripts/sync_shared.py \
  /home/cognitiveghost/Desktop/Projects/packing-tool/.claude/worktrees/worktree-commandbar-primary
```

- [ ] **Step 2: Confirm the sync landed and nothing else moved**

```bash
git diff --stat
```

Expected: `shared/theme.py` only. If any other file under `shared/` changed, that is an
unrelated drift between the repos — stop and report it rather than folding it in.

- [ ] **Step 3: Run the gate and record the fallout**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest`

No shopify test currently asserts on the bare `QPushButton` rule (verified 2026-08-29
against `tests/test_theme_button_roles.py` and `tests/test_theme_manager_button_roles.py`),
so this is expected to pass unchanged. If something does fail on a button colour, fix the
assertion, not the rule, and list it in the PR body.

- [ ] **Step 4: Commit**

```bash
git add shared/theme.py
git commit -m "Sync shared/: the default button role becomes secondary"
```

---

## Task 4: shopify marks its dialogs' accept buttons

**Files:**
- Modify: `gui/theme_manager.py` — add `apply_dialog_button_roles`
- Modify: the 10 modules constructing a `QDialogButtonBox` (listed in step 3)
- Modify: `gui/column_config_dialog.py:269`, `gui/report_selection_dialog.py:105`
- Test: `tests/test_theme_manager_button_roles.py`

**Interfaces:**
- Consumes: task 3's flipped default.
- Produces: `apply_dialog_button_roles(box: QDialogButtonBox) -> None`, importable from
  `gui.theme_manager`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_theme_manager_button_roles.py`:

```python
def test_the_dialog_accept_button_is_the_dialogs_one_primary(qapp):
    from PySide6.QtWidgets import QDialogButtonBox

    from gui.theme_manager import apply_dialog_button_roles

    box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
    apply_dialog_button_roles(box)
    assert box.button(QDialogButtonBox.Save).property("role") == "primary"
    # Cancel keeps the default, which is now secondary -- no property needed.
    assert box.button(QDialogButtonBox.Cancel).property("role") is None


def test_a_close_only_dialog_gets_no_primary(qapp):
    """A dialog that only dismisses has no action to promote."""
    from PySide6.QtWidgets import QDialogButtonBox

    from gui.theme_manager import apply_dialog_button_roles

    box = QDialogButtonBox(QDialogButtonBox.Close)
    apply_dialog_button_roles(box)
    assert box.button(QDialogButtonBox.Close).property("role") is None
```

- [ ] **Step 2: Run it to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_theme_manager_button_roles.py -v`
Expected: FAIL with `ImportError: cannot import name 'apply_dialog_button_roles'`.

- [ ] **Step 3: Implement the helper**

In `gui/theme_manager.py`, beside the existing `set_button_role` re-export:

```python
def apply_dialog_button_roles(box) -> None:
    """Mark a dialog's accept button primary. Everything else keeps the default.

    Since the default role became secondary, only the one button that commits the
    dialog needs marking. AcceptRole is Qt's own answer to "which button is that",
    so a Close-only box correctly comes out with no primary at all.
    """
    from PySide6.QtWidgets import QDialogButtonBox

    for button in box.buttons():
        if box.buttonRole(button) == QDialogButtonBox.ButtonRole.AcceptRole:
            set_button_role(button, "primary")
```

- [ ] **Step 4: Run the test**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_theme_manager_button_roles.py -v`
Expected: PASS.

- [ ] **Step 5: Call it at all ten `QDialogButtonBox` sites**

One line after each construction, importing `apply_dialog_button_roles` from
`gui.theme_manager` in each file:

| file | line |
|---|---|
| `gui/client_settings_dialog.py` | 118 |
| `gui/client_settings_dialog.py` | 411 |
| `gui/rule_test_dialog.py` | 99 |
| `gui/column_config_dialog.py` | 1049 |
| `gui/settings/sets.py` | 393 |
| `gui/add_product_dialog.py` | 124 |
| `gui/tag_categories_dialog.py` | 686 |
| `gui/tag_categories_dialog.py` | 842 |
| `gui/settings/window.py` | 184 |
| `gui/groups_management_dialog.py` | 109 |

The Close-only boxes (`rule_test_dialog.py:99`, `groups_management_dialog.py:109`) are
included deliberately — the helper is a no-op there, and a uniform call means the next
dialog that grows an Ok button is already correct.

`gui/settings/window.py:186-187` already marks Save primary and Cancel secondary by hand.
Replace line 186 with the helper call; **leave line 187 alone** — removing an existing
explicit `secondary` is churn, and the rule for this task is *do not add new explicit
secondary marks, do not remove existing ones*.

- [ ] **Step 6: Mark the two hand-rolled accept buttons**

These two dialogs commit through a plain `QPushButton`, not a button box:

`gui/column_config_dialog.py` after line 269:

```python
        self.apply_button = QPushButton("Apply Column Configuration")
        set_button_role(self.apply_button, "primary")
```

`gui/report_selection_dialog.py` after line 105:

```python
        self.generate_btn = QPushButton("Generate Report")
        set_button_role(self.generate_btn, "primary")
```

Everything else in those two files stays secondary: `↑ Move Up`, `Show All`, `Reset to
Default`, `Generate Writeoff Report Only` and the rest are alternatives and row actions, not
the dialog's single action. Likewise leave every button in `bulk_operations_toolbar.py`,
`settings/weight.py`, `settings/sets.py`, `tag_categories_dialog.py` and
`groups_management_dialog.py` unmarked — they are toolbars and peer actions with no single
primary among them.

- [ ] **Step 7: Run the gate**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest
.venv/bin/ruff check . --exclude shared
```
Expected: PASS, PASS.

- [ ] **Step 8: Commit**

```bash
git add gui/ tests/test_theme_manager_button_roles.py
git commit -m "Shopify's dialogs name their one primary now that nothing defaults to it"
```

---

## Task 5: Delete the two dead `ui_manager` helpers

**Files:**
- Modify: `gui/ui_manager.py` — delete `_create_session_management_group` (`:515`) and
  `_create_actions_layout` (`:753`)

**Interfaces:**
- Consumes: nothing.
- Produces: `self.mw.new_session_btn` unambiguously refers to `ui_manager.py:1105`, which
  task 7's `_SCREEN_ACTIONS` resolves.

Both helpers have no callers and no tests — `grep -rn` over the whole repo (excluding
`.venv`) finds only their `def` lines. `_create_session_management_group` constructs a
**second** `self.mw.new_session_btn` that the live one at `:1105` overwrites; leaving it in
place while task 7 binds that attribute is a landmine, because wiring the dead helper up
later would silently rebind the CommandBar to an orphan widget.

- [ ] **Step 1: Re-confirm they are dead before deleting anything**

```bash
grep -rn "_create_session_management_group\|_create_actions_layout" --include=*.py . | grep -v "\.venv"
```

Expected: exactly two lines, both the `def` in `gui/ui_manager.py`. **If anything else
appears, stop** — the premise is wrong and this task must be re-planned.

- [ ] **Step 2: Delete both methods**

Delete `_create_session_management_group` in full (`:515` through the line before the next
`def`) and `_create_actions_layout` in full (`:753` through the line before `def
_create_reports_group`). Delete only these two; `_create_reports_group` and
`_create_main_actions_group` are both live from `_create_session_setup_panel`.

- [ ] **Step 3: Run the gate**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest
.venv/bin/ruff check . --exclude shared
```
Expected: PASS, PASS. Ruff will flag any import that only these two methods used — remove
those too.

- [ ] **Step 4: Commit**

```bash
git add gui/ui_manager.py
git commit -m "Delete two ui_manager helpers nothing has ever called"
```

---

## Task 6: `CommandBar.bind_action`

**Files:**
- Modify: `gui/components/commandbar.py`
- Test: `tests/test_components_commandbar.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `CommandBar.bind_action(button: QPushButton | None) -> None`. Task 7 calls it.
  `set_action(label) -> QPushButton` is unchanged and stays public — it is the primitive
  `bind_action` builds on, and the one packing-tool's 8.6b will need for a screen that has
  no pre-existing button to bind.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_components_commandbar.py`:

```python
def test_bind_action_mirrors_the_bound_buttons_label_and_state(qapp):
    source = QPushButton("▶ Run Analysis")
    source.setToolTip("Start the fulfillment analysis")
    source.setEnabled(False)

    bar = CommandBar()
    bar.bind_action(source)

    assert bar.action_button.text() == "▶ Run Analysis"
    assert bar.action_button.toolTip() == "Start the fulfillment analysis"
    assert not bar.action_button.isEnabled()
    assert not bar.action_button.isHidden()


def test_a_later_setEnabled_on_the_source_reaches_the_bar(qapp):
    """QWidget has no enabledChanged signal; EnabledChange is the only notice."""
    source = QPushButton("Run")
    source.setEnabled(False)
    bar = CommandBar()
    bar.bind_action(source)

    source.setEnabled(True)

    assert bar.action_button.isEnabled()


def test_the_bars_click_fires_the_bound_buttons_own_connections(qapp):
    source = QPushButton("Run")
    seen = []
    source.clicked.connect(lambda: seen.append(1))
    bar = CommandBar()
    bar.bind_action(source)

    bar.action_button.click()

    assert seen == [1]


def test_binding_none_hides_the_slot(qapp):
    bar = CommandBar()
    bar.bind_action(QPushButton("Run"))
    bar.bind_action(None)
    assert bar.action_button.isHidden()


def test_rebinding_stops_the_old_button_reaching_the_bar(qapp):
    first, second = QPushButton("First"), QPushButton("Second")
    bar = CommandBar()
    bar.bind_action(first)
    bar.bind_action(second)

    first.setEnabled(False)

    assert bar.action_button.text() == "Second"
    assert bar.action_button.isEnabled()
```

`QPushButton` is already imported in that test file's `CommandBar` tests; add the import if
it is not.

`isHidden()` rather than `isVisible()` throughout: an unshown widget with no shown parent is
never `isVisible()`, so only the explicit hide/show state is meaningful offscreen.

- [ ] **Step 2: Run them to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_components_commandbar.py -v`
Expected: five FAILs, `AttributeError: 'CommandBar' object has no attribute 'bind_action'`.

- [ ] **Step 3: Implement**

In `gui/components/commandbar.py`, add `QEvent` to the `PySide6.QtCore` import.

In `__init__`, after line 113's `clicked.connect(self.actionTriggered.emit)`:

```python
        self._bound_action = None
        self.action_button.clicked.connect(self._forward_action_click)
```

`actionTriggered` keeps firing alongside the forward — it stays the signal for a screen that
uses `set_action` with nothing to bind.

Then, below `set_action`:

```python
    def bind_action(self, button: QPushButton | None) -> None:
        """Mirror a screen's own primary button in the bar's action slot.

        The bound button stays the command: its clicked connections and the
        setEnabled call sites in file_handler and main_window_pyside keep working
        untouched, and the bar is a second presentation of it rather than a
        replacement. Passing None hides the slot, for a screen with no primary.

        ponytail: a hidden QPushButton as the command's model is what QAction
        does properly, but QPushButton cannot consume a QAction -- only
        QToolButton can, via setDefaultAction -- so retrofitting one would change
        the widget class at every call site that touches these three buttons.
        Revisit if a third presentation of the same command ever appears.
        """
        if self._bound_action is not None:
            self._bound_action.removeEventFilter(self)
        self._bound_action = button
        if button is None:
            self.action_button.hide()
            return
        button.installEventFilter(self)
        self.action_button.setToolTip(button.toolTip())
        self.action_button.setEnabled(button.isEnabled())
        self.set_action(button.text())

    def _forward_action_click(self) -> None:
        if self._bound_action is not None:
            self._bound_action.click()

    def eventFilter(self, watched, event):
        # QWidget has no enabledChanged signal; this event is Qt's only notice.
        if (watched is self._bound_action
                and event.type() == QEvent.Type.EnabledChange):
            self.action_button.setEnabled(watched.isEnabled())
        return super().eventFilter(watched, event)
```

The label and tooltip are copied once, at bind time: no `setText` call site exists for any
of the three buttons task 7 binds (verified 2026-08-29), so no text observer is warranted.

- [ ] **Step 4: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_components_commandbar.py -v`
Expected: PASS, including the four pre-existing `set_action` tests.

- [ ] **Step 5: Commit**

```bash
git add gui/components/commandbar.py tests/test_components_commandbar.py
git commit -m "CommandBar.bind_action mirrors a screen's own primary button"
```

---

## Task 7: Each screen declares its primary

**Files:**
- Modify: `gui/ui_manager.py` — module constant `_SCREEN_ACTIONS`, method
  `_bind_screen_action`, wiring at the end of `_create_tabs`
- Test: `tests/test_screen_primary_actions.py` (create)

**Interfaces:**
- Consumes: `CommandBar.bind_action` from task 6; the unambiguous `new_session_btn` from
  task 5.
- Produces: the shipped behaviour. Nothing later depends on it.

- [ ] **Step 1: Write the failing test**

Create `tests/test_screen_primary_actions.py`:

```python
"""The CommandBar's one primary follows the current screen.

Before 2026-08-29 nothing called CommandBar.set_action, so the bar's right-hand
side was empty on all five screens while each screen kept its primary in the page
body -- next to an unmarked Settings button that the theme was painting primary
blue. See docs/superpowers/specs/2026-08-29-commandbar-primary-action-design.md.
"""
import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture
def main_window(tmp_path, monkeypatch):
    monkeypatch.setenv("FULFILLMENT_SERVER_PATH", str(tmp_path))
    from gui.main_window_pyside import MainWindow

    win = MainWindow()
    win.resize(1100, 900)
    win.show()
    QApplication.processEvents()
    yield win
    win.close()


def test_each_screen_puts_its_own_primary_in_the_bar(main_window, qapp):
    expected = {
        0: "▶ Run Analysis",
        1: "Generate Reports",
        2: "Create New Session",
    }
    for index, label in expected.items():
        main_window.main_tabs.setCurrentIndex(index)
        QApplication.processEvents()
        assert main_window.command_bar.action_button.text() == label
        assert not main_window.command_bar.action_button.isHidden()


def test_a_screen_with_no_primary_hides_the_slot(main_window, qapp):
    for index in (3, 4):
        main_window.main_tabs.setCurrentIndex(index)
        QApplication.processEvents()
        assert main_window.command_bar.action_button.isHidden()


def test_the_bar_mirrors_the_bound_buttons_enabled_state(main_window, qapp):
    """Run Analysis is disabled until the files load; the bar must agree."""
    main_window.main_tabs.setCurrentIndex(0)
    QApplication.processEvents()
    bar_button = main_window.command_bar.action_button
    assert bar_button.isEnabled() == main_window.run_analysis_button.isEnabled()

    main_window.run_analysis_button.setEnabled(True)
    assert bar_button.isEnabled()
    main_window.run_analysis_button.setEnabled(False)
    assert not bar_button.isEnabled()


def test_the_moved_buttons_stop_rendering_in_the_page(main_window, qapp):
    assert main_window.run_analysis_button.isHidden()
    assert main_window.generate_reports_button_tab2.isHidden()


def test_session_setups_new_session_button_keeps_rendering(main_window, qapp):
    """SessionBrowserWidget has no New Session control, so screen 2 borrows Session
    Setup's -- where it is not the primary and must stay visible."""
    main_window.main_tabs.setCurrentIndex(0)
    QApplication.processEvents()
    assert not main_window.new_session_btn.isHidden()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_screen_primary_actions.py -v`
Expected: FAIL — the bar's action button is empty and hidden on every screen.

- [ ] **Step 3: Add the mapping**

Near the other module constants at the top of `gui/ui_manager.py`:

```python
# Tab index -> (main_window attribute holding that screen's primary button,
# whether the button lives on this screen and should stop painting itself).
#
# Screen 2 is the exception: SessionBrowserWidget has no New Session control of
# its own, so it borrows Session Setup's -- which must keep rendering there,
# where Run Analysis is the primary and this is not. Hence an explicit flag
# rather than inferring hiding from the mapping.
_SCREEN_ACTIONS = {
    0: ("run_analysis_button", True),
    1: ("generate_reports_button_tab2", True),
    2: ("new_session_btn", False),
}
```

- [ ] **Step 4: Wire it at the end of `_create_tabs`**

Append to `_create_tabs`, after the existing `self._setup_tab_shortcuts()` call. It must go
here and not beside `_create_command_bar`: the bar is built at `ui_manager.py:153`, before
`_create_tabs()` at `:155` constructs the buttons this reads.

```python
        # The screen's primary action moves into the command bar's one slot.
        for attribute, hide_in_page in _SCREEN_ACTIONS.values():
            if hide_in_page:
                getattr(self.mw, attribute).hide()
        self.mw.main_tabs.currentChanged.connect(self._bind_screen_action)
        self._bind_screen_action(self.mw.main_tabs.currentIndex())
```

And the method, beside `_create_command_bar`:

```python
    def _bind_screen_action(self, index: int) -> None:
        """Point the command bar's one primary at this screen's primary button."""
        entry = _SCREEN_ACTIONS.get(index)
        self.mw.command_bar.bind_action(
            None if entry is None else getattr(self.mw, entry[0])
        )
```

- [ ] **Step 5: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_screen_primary_actions.py -v`
Expected: PASS.

- [ ] **Step 6: Run the full gate**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest
.venv/bin/ruff check . --exclude shared
```

Expected: PASS, PASS. `tests/test_session_setup_layout.py` measures whether action buttons
are clipped by the setup column; Run Analysis is now hidden, so a test that counts or
locates it may need its expectation updated. That is this change working — update the
expectation and name the edit in the PR body.

- [ ] **Step 7: Commit**

```bash
git add gui/ui_manager.py tests/test_screen_primary_actions.py
git commit -m "Each screen's primary action moves into the command bar's one slot"
```

- [ ] **Step 8: Push and refresh the graph**

```bash
git push -u origin worktree-commandbar-primary
graphify update .
```

`graphify update .` is required by this repo's `CLAUDE.md` after code changes — a stale
graph answers wrong about `shared/` ownership and theme delegation with no error.

---

## Notes for the reviewer (Stage C)

- The visual blast radius is every button in both apps; the diff is small. Judge the
  opt-in pass button by button, not commit by commit — a missed primary renders grey and
  still works, which is the intended failure mode.
- Tasks 1–5 are cosmetic; tasks 6–7 are navigational. Phase 8's standing rule requires
  those stay in separate commits so navigation can be reverted on its own.
- The PR body owes: which existing tests changed expectation and why; and a note that
  Run Analysis has moved out of the page into the top bar, for the release note spec §9 of
  the selection-ring item already says is owed before the next warehouse build.
