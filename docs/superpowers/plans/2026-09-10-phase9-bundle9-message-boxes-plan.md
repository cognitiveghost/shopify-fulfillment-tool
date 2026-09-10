# Phase 9 Bundle 9 — Message Boxes Sort Into Four Routes: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task by task, in this session. Do not fan out to subagents. Steps use checkbox (`- [ ]`) syntax for tracking. If a run ends mid-plan, tick what is done, commit, and name the next task in the runner's `state.md`.

**Goal:** Replace the blocking `QMessageBox` calls in `gui/` with four routes (toast, inline message, confirm, error banner), plus the two non-routes (disabled action, deletion), and make the Logs viewer carry each exception's summary.

**Architecture:** Build bottom-up.
1. Task 1 makes Logs carry the exception, so the banner's pointer to Logs is true.
2. Tasks 2–5 build the four components, each tested against a real host widget.
3. Task 6 adds a route guard: an AST test with an owned allow-list and a `PENDING` set of unconverted files.
4. Tasks 7–11 convert call sites file by file. Each deletes its files from `PENDING`, so the guard proves the conversion.
5. Task 12 deletes `PENDING` and runs the gate.

**Tech Stack:** Python 3.12, PySide6 6.11.2, pytest, `QT_QPA_PLATFORM=offscreen`.

**Spec:** `docs/superpowers/specs/2026-09-10-phase9-bundle9-message-boxes-design.md`. Read it first; **§8 is the per-site routing table this plan converts from**, and §9 lists the departures from the brief that are deliberate. Do not "fix" them back.

## Global Constraints

- **Worktree / branch:** `.claude/worktrees/worktree-phase9-bundle9-message-boxes` on `worktree-phase9-bundle9-message-boxes`. PR-only. Never commit to `main`.
- **Never call bare `python`.** Use `.venv/bin/python`.
- **Git:** use `/usr/bin/git` for `add`, `commit`, `log`, `status` and `push`. Run each as its own command. The worktree guard refuses `&&` chains and heredocs; pass multi-line commit messages as repeated `-m` flags.
- **Run tests as:** `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest`
- **Lint as:** `.venv/bin/python -m ruff check . --exclude shared`. After each task, remove any import the task left unused (ruff `F401`), usually `QMessageBox`.
- **Never hand-edit anything under `shared/`.** This bundle adds no token, no glyph and no QSS selector, and never runs `scripts/sync_shared.py`.
- **No hardcoded colours.** Every colour comes from a theme token via the `tokens` argument `on_theme_changed` passes (ADR 0003).
- **Call sites import at module level:** `from gui.components import ConfirmDialog, InlineMessage, show_error, toast`. Tests then patch the name on the calling module (`monkeypatch.setattr("gui.pdf_printing.show_error", Mock())`). If a module-level import from `gui.components` raises a circular `ImportError`, import from the submodule (`from gui.components.toast import toast`) instead; the patch target stays `gui.<module>.toast`.
- **Many tests pass fakes as the parent:** `None`, a `SimpleNamespace` `mw`, or a `_FakeWidget`. `toast()` and `show_error()` raise `TypeError` for anything that is not a `QWidget`, so any test reaching a converted call site with a fake must patch the function on the module.
- **Before routing a failure to the banner, log it with `exc_info=True`** (or `logger.exception(...)`) if the `except` block does not already.
- **Copy rules (spec §7):**
  - No "successfully", no "!", no "Error" as a title, and no exception text shown to the operator.
  - A toast is past tense with the object named.
  - A banner headline states the consequence, and its second line says what to do.
- **Skipped sites stay untouched:** `bulk_*` in `gui/actions_handler.py`, `open_settings_window`'s "Settings Updated" and "Warning" boxes, `gui/settings/window.py`, `gui/settings/sets.py`, `gui/column_config_dialog.py`, and `MainWindow._init_managers`.
- **`QInputDialog` and `QFileDialog` stay native.**
- **The version string is not bumped.** It stays `1.9.9.1`.
- **Write-hook quirk on this VM:** the write hook strips an import that was just added before its usage exists. Add the usage first, then the import, or write both in one edit.
- **Commit subjects:** `9.25: <what changed, in plain words>`. End every commit message with `-m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"`.

## File map

| File | Responsibility |
|---|---|
| `gui/log_handler.py` | Modify: append the exception summary to the entry message |
| `gui/components/inline_message.py` | Create: `InlineMessage` |
| `gui/components/confirm_dialog.py` | Create: `ConfirmDialog` |
| `gui/components/toast.py` | Create: `Toast`, `toast()` |
| `gui/components/error_banner.py` | Create: `ErrorBanner`, `show_error()` |
| `gui/components/__init__.py` | Modify: export the six new names |
| `gui/ui_manager.py` | Modify: build `mw.error_banner` under the command bar; convert its two sites |
| `gui/report_selection_dialog.py` | Modify: delete the writeoff bypass |
| `gui/actions_handler.py`, `gui/main_window_pyside.py`, `gui/file_handler.py` | Modify: convert (Tasks 7–8) |
| `gui/add_product_dialog.py`, `gui/client_settings_dialog.py`, `gui/groups_management_dialog.py`, `gui/tag_categories_dialog.py`, `gui/rule_test_dialog.py` | Modify: convert (Task 9) |
| `gui/barcode_generator_widget.py`, `gui/reference_labels_widget.py`, `gui/pdf_printing.py`, `gui/session_browser_widget.py`, `gui/client_directory.py`, `gui/log_viewer.py` | Modify: convert (Task 10) |
| `gui/settings/mappings.py`, `gui/settings/rules.py`, `gui/settings/weight.py` | Modify: convert (Task 11) |
| `tests/test_log_handler.py` | Modify: exception summary test |
| `tests/test_components_inline_message.py`, `tests/test_components_confirm_dialog.py`, `tests/test_components_toast.py`, `tests/test_components_error_banner.py` | Create |
| `tests/test_message_routes.py` | Create: the route guard |
| `tests/test_actions_handler.py`, `tests/test_shell.py`, `tests/test_add_product_dialog.py`, `tests/test_client_directory.py`, `tests/test_pdf_printing.py`, `tests/test_barcode_generator_widget.py`, `tests/test_reference_labels_widget.py`, `tests/test_settings_window_weight_quick_add.py`, `tests/test_file_handler.py` | Modify: follow the new routes |

## The conversion patterns

Tasks 7–11 apply these to the rows of spec §8. Each pattern shows a real site.

**T: toast.**
```python
# before
QMessageBox.information(self.mw, "Session Created",
    f"New session created successfully:\n{session_name}\n\nYou can now load Orders and Stock files.")
# after
toast(self.mw, f"Session {session_name} created.")
```

**T+U: toast with Undo.** Only where the operation called `undo_manager.record_operation`: `remove_item_from_order` and `remove_entire_order`. (`toggle_fulfillment_status_for_order` and `add_tag_manually` record too, but show no success message today, and none is added.)
```python
toast(self.mw, f"Removed order {order_number}.",
      action_text="Undo", on_action=self.mw.undo_last_operation)
```

**T+A: toast with one action.** Role `info` when nothing succeeded yet.
```python
toast(self.mw, f"No reports are set up for CLIENT_{client_id}.", role="info",
      action_text="Open Settings", on_action=self.open_settings_window)
```

**B: error banner.**
```python
# before
except Exception as e:
    self.log.error(f"Failed to create session: {e}", exc_info=True)
    QMessageBox.critical(self.mw, "Unexpected Error", f"An unexpected error occurred.\n\nError: {e}")
# after
except Exception as e:
    self.log.error(f"Failed to create session: {e}", exc_info=True)
    show_error(self.mw, "The session wasn't created",
               "Check that the server share is reachable, then create the session again.")
```
When the host is a dialog, it has no Open Logs button. So when the cause matters, end the second line with "Details are in Logs."

**C: confirm.**
```python
# before
reply = QMessageBox.question(self, "Delete Group",
    f"Delete group '{name}'?\n\nThis will unassign {client_count} client(s) from this group.", ...)
if reply != QMessageBox.Yes:
    return
# after
if not ConfirmDialog.ask(self, title=f"Delete group {name}?",
                         body=f"{client_count} clients lose their group. This cannot be undone.",
                         verb="Delete group"):
    return
```

**I: inline message.** Build one `InlineMessage` per named field, directly under it, and clear it when that field changes:
```python
# construction, right after the field's own row
self.order_error = InlineMessage(self)
form_layout.addRow("", self.order_error)
self.order_input.textChanged.connect(self.order_error.clear)
# in the validator, instead of the warning box
self.order_error.show_message("Enter an order number.")
return False
```

**D: disabled action.** Delete the message but keep the guard, silent apart from a log line.
```python
if not self.mw.current_client_id:
    self.log.warning("create_new_session called with no client selected")
    return
```
**Before deleting any D message, find the control that reaches this function and prove it is disabled in that state.** `rg -n "<function_name>" gui` finds the connection; `rg -n "<button>.setEnabled" gui` finds its enabling. `BarState` in `gui/components/commandbar.py` and `_update_selection_bar_state` in `gui/actions_handler.py` already cover most of them. If the control is not disabled and cannot be disabled from state that already exists, use **B** instead (spec §3, rule 1).

**X: deleted.** Remove the call and any branch that existed only to show it.

---

### Task 1: Logs carries the exception

**Files:**
- Modify: `gui/log_handler.py`
- Test: `tests/test_log_handler.py`

**Interfaces:**
- Produces: `LogEntry.message` ends with `" — <ExceptionType>: <message>"` when the record has `exc_info`.

- [ ] **Step 1: Write the failing test.** Append to `tests/test_log_handler.py`:

```python
def test_an_exception_summary_rides_on_the_message(qapp):
    import sys

    handler = QtLogHandler()
    received = []
    handler.entry_received.connect(received.append)
    try:
        raise PermissionError("share is read-only")
    except PermissionError:
        record = logging.LogRecord(
            name="gui.actions_handler", level=logging.ERROR, pathname=__file__,
            lineno=1, msg="Save failed", args=(), exc_info=sys.exc_info(),
        )

    handler.emit(record)

    assert received[0].message == "Save failed — PermissionError: share is read-only"


def test_a_record_without_an_exception_keeps_its_message(qapp):
    handler = QtLogHandler()
    received = []
    handler.entry_received.connect(received.append)

    handler.emit(_record())

    assert received[0].message == "careful now"
```

- [ ] **Step 2: Run to verify the first fails.**
  Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_log_handler.py -v`
  Expected: `test_an_exception_summary_rides_on_the_message` FAILS (message is `"Save failed"`).

- [ ] **Step 3: Implement.** In `gui/log_handler.py`, replace `emit`:

```python
    def emit(self, record):
        """Turn a LogRecord into a LogEntry and emit it.

        An exception's one-line summary rides on the message: the error banner
        (9.25) sends the operator here for the cause, and a row per record
        keeps the viewer one line per entry. The full traceback stays in the
        JSON file log.
        """
        message = record.getMessage()
        if record.exc_info and record.exc_info[1] is not None:
            etype, value = record.exc_info[:2]
            summary = traceback.format_exception_only(etype, value)[-1].strip()
            message = f"{message} — {summary}"
        entry = LogEntry(
            timestamp=datetime.fromtimestamp(record.created).astimezone(),
            level=record.levelno,
            source=record.name,
            message=message,
        )
        self.entry_received.emit(entry)
```
Then add `import traceback` beside `import logging`.

- [ ] **Step 4: Run to verify both pass.** Same command; expected PASS.

- [ ] **Step 5: Commit.**
```
/usr/bin/git add gui/log_handler.py tests/test_log_handler.py
/usr/bin/git commit -m "9.25: Logs carries the exception behind an error" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: `InlineMessage`

**Files:**
- Create: `gui/components/inline_message.py`
- Modify: `gui/components/__init__.py`
- Test: `tests/test_components_inline_message.py`

**Interfaces:**
- Produces: `InlineMessage(parent=None)`, `.show_message(text: str) -> None`, `.clear() -> None`, and `.text()` from `QLabel`.

- [ ] **Step 1: Write the failing test.** Create `tests/test_components_inline_message.py`:

```python
"""9.25: a problem shown where it happened.

Spec: docs/superpowers/specs/2026-09-10-phase9-bundle9-message-boxes-design.md §4.4
"""

from PySide6.QtWidgets import QWidget

from gui.components.inline_message import InlineMessage
from shared.theme import current_tokens


def test_it_is_hidden_until_there_is_something_to_say(qapp):
    parent = QWidget()
    assert InlineMessage(parent).isHidden()


def test_show_message_shows_the_text(qapp):
    parent = QWidget()
    message = InlineMessage(parent)
    message.show_message("Enter an order number.")
    assert not message.isHidden()
    assert message.text() == "Enter an order number."


def test_clear_hides_it_again(qapp):
    parent = QWidget()
    message = InlineMessage(parent)
    message.show_message("Enter an order number.")
    message.clear()
    assert message.isHidden()
    assert message.text() == ""


def test_it_is_drawn_in_the_danger_colour(qapp):
    parent = QWidget()
    assert current_tokens().status_danger in InlineMessage(parent).styleSheet()
```

- [ ] **Step 2: Run to verify it fails.**
  Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_components_inline_message.py -v`
  Expected: FAIL, `ModuleNotFoundError: gui.components.inline_message`.

- [ ] **Step 3: Implement.** Create `gui/components/inline_message.py`:

```python
"""A problem shown where it happened.

The inline route (9.25): the message sits under the field it names, the typed
input survives, and the call site clears it when that field changes.

Spec: docs/superpowers/specs/2026-09-10-phase9-bundle9-message-boxes-design.md §4.4
"""

from PySide6.QtWidgets import QLabel

from shared.theme import font_css, on_theme_changed


class InlineMessage(QLabel):
    """A danger-coloured line that is hidden while it has nothing to say."""

    def __init__(self, parent=None) -> None:
        super().__init__("", parent)
        self.setWordWrap(True)
        self.setVisible(False)
        on_theme_changed(
            self,
            lambda tokens: self.setStyleSheet(
                f"{font_css('body')} color: {tokens.status_danger}; background: transparent;"
            ),
        )

    def show_message(self, text: str) -> None:
        self.setText(text)
        self.setVisible(bool(text))

    def clear(self) -> None:
        self.setText("")
        self.setVisible(False)
```
In `gui/components/__init__.py`, add `from gui.components.inline_message import InlineMessage` in alphabetical position and `"InlineMessage"` to `__all__`.

- [ ] **Step 4: Run to verify it passes.** Same command; expected 4 PASS.

- [ ] **Step 5: Commit.**
```
/usr/bin/git add gui/components/inline_message.py gui/components/__init__.py tests/test_components_inline_message.py
/usr/bin/git commit -m "9.25: InlineMessage, a problem shown where it happened" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: `ConfirmDialog`

**Files:**
- Create: `gui/components/confirm_dialog.py`
- Modify: `gui/components/__init__.py`
- Test: `tests/test_components_confirm_dialog.py`

**Interfaces:**
- Consumes: `apply_dialog_button_roles(box)` from `gui.theme_manager`.
- Produces: `ConfirmDialog(parent, *, title: str, body: str, verb: str)` with attributes `buttons`, `verb_button`, `cancel_button` and `body_label`, plus `ConfirmDialog.ask(parent, *, title, body, verb) -> bool`.

- [ ] **Step 1: Write the failing test.** Create `tests/test_components_confirm_dialog.py`:

```python
"""9.25: a confirm names its act, and Enter destroys nothing.

Spec: docs/superpowers/specs/2026-09-10-phase9-bundle9-message-boxes-design.md §4.2
"""

import pytest
from PySide6.QtWidgets import QDialogButtonBox

from gui.components.confirm_dialog import ConfirmDialog


def _dialog(verb="Delete group"):
    return ConfirmDialog(
        None,
        title="Delete group North?",
        body="3 clients lose their group. This cannot be undone.",
        verb=verb,
    )


def test_the_accept_button_is_the_verb_and_is_primary(qapp):
    dialog = _dialog()
    assert dialog.verb_button.text() == "Delete group"
    assert dialog.buttons.buttonRole(dialog.verb_button) == QDialogButtonBox.ButtonRole.AcceptRole
    assert dialog.verb_button.property("role") == "primary"


def test_cancel_is_the_default_so_enter_destroys_nothing(qapp):
    dialog = _dialog()
    assert dialog.cancel_button.isDefault()
    assert not dialog.verb_button.isDefault()


@pytest.mark.parametrize("verb", ["OK", "yes", "Confirm", "continue"])
def test_a_verb_that_names_no_act_is_refused(qapp, verb):
    with pytest.raises(ValueError):
        _dialog(verb)


def test_the_title_and_body_are_shown(qapp):
    dialog = _dialog()
    assert dialog.windowTitle() == "Delete group North?"
    assert dialog.body_label.text() == "3 clients lose their group. This cannot be undone."


@pytest.mark.parametrize(("code", "expected"), [(1, True), (0, False)])
def test_ask_answers_with_the_dialog_result(qapp, monkeypatch, code, expected):
    monkeypatch.setattr(ConfirmDialog, "exec", lambda self: code)
    assert ConfirmDialog.ask(None, title="t", body="b", verb="Delete group") is expected
```

- [ ] **Step 2: Run to verify it fails.**
  Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_components_confirm_dialog.py -v`
  Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 3: Implement.** Create `gui/components/confirm_dialog.py`:

```python
"""The one confirm: for acts that destroy data Undo cannot reach.

The accept button is the verb, so the consequence is written on the thing you
press. Cancel is the default, so a reflexive Enter destroys nothing. An
undoable act never confirms; its toast carries Undo instead.

Spec: docs/superpowers/specs/2026-09-10-phase9-bundle9-message-boxes-design.md §4.2
"""

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QPushButton, QVBoxLayout

from gui.theme_manager import apply_dialog_button_roles
from shared.theme import font_css

_VERBS_THAT_NAME_NO_ACT = {"ok", "yes", "confirm", "continue"}


class ConfirmDialog(QDialog):
    """Title asks the question, body states count and consequence, verb acts."""

    def __init__(self, parent, *, title: str, body: str, verb: str) -> None:
        if verb.strip().lower() in _VERBS_THAT_NAME_NO_ACT:
            raise ValueError(f"A confirm names its act; {verb!r} does not")
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)

        layout = QVBoxLayout(self)
        # Fonts are baked here rather than re-run on a theme change: a modal
        # lives for seconds and nothing can toggle the theme behind it.
        heading = QLabel(title, self)
        heading.setWordWrap(True)
        heading.setStyleSheet(font_css("heading"))
        layout.addWidget(heading)

        self.body_label = QLabel(body, self)
        self.body_label.setWordWrap(True)
        self.body_label.setStyleSheet(font_css("body"))
        layout.addWidget(self.body_label)

        self.buttons = QDialogButtonBox(self)
        self.cancel_button = self.buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        self.verb_button = QPushButton(verb, self)
        self.buttons.addButton(self.verb_button, QDialogButtonBox.ButtonRole.AcceptRole)
        apply_dialog_button_roles(self.buttons)
        self.verb_button.setAutoDefault(False)
        self.cancel_button.setDefault(True)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    @classmethod
    def ask(cls, parent, *, title: str, body: str, verb: str) -> bool:
        """Show the confirm and return True only if the verb was pressed."""
        return bool(cls(parent, title=title, body=body, verb=verb).exec())
```
Export `ConfirmDialog` from `gui/components/__init__.py`, as in Task 2.

- [ ] **Step 4: Run to verify it passes.** Same command; expected PASS. If `test_cancel_is_the_default…` fails because `QDialogButtonBox` re-assigns the default, move `self.cancel_button.setDefault(True)` to after `layout.addWidget(self.buttons)`.

- [ ] **Step 5: Commit.**
```
/usr/bin/git add gui/components/confirm_dialog.py gui/components/__init__.py tests/test_components_confirm_dialog.py
/usr/bin/git commit -m "9.25: ConfirmDialog, whose button is the verb" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: `Toast`

**Files:**
- Create: `gui/components/toast.py`
- Modify: `gui/components/__init__.py`
- Test: `tests/test_components_toast.py`

**Interfaces:**
- Produces:
  - `toast(source: QWidget, text: str, *, role="success", action_text="", on_action=None) -> Toast`
  - `Toast.for_window(window) -> Toast | None`, and `Toast.DURATION_MS == 4000`, `Toast.BADGE_AT == 3`
  - Instance: `.text() -> str`, `.count() -> int`, `.dismiss()`
  - Public children for tests: `.timer` (QTimer), `.button` (QPushButton), `.badge` (QLabel)

- [ ] **Step 1: Write the failing test.** Create `tests/test_components_toast.py`:

```python
"""9.25: good news never blocks.

Spec: docs/superpowers/specs/2026-09-10-phase9-bundle9-message-boxes-design.md §4.1
"""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QMainWindow, QVBoxLayout, QWidget

from gui.components.toast import Toast, toast
from shared.theme import current_tokens


@pytest.fixture
def window(qapp):
    win = QMainWindow()
    win.setCentralWidget(QWidget())
    win.resize(800, 600)
    yield win
    win.close()


def test_the_toast_lives_on_the_window_that_raised_it(window):
    shown = toast(window.centralWidget(), "Session S1 created.")
    assert shown.parent() is window
    assert Toast.for_window(window) is shown
    assert not shown.isHidden()


def test_a_dialog_hosts_its_own_toast(window):
    dialog = QDialog(window)
    QVBoxLayout(dialog)
    shown = toast(dialog, "Group North created.")
    assert shown.parent() is dialog
    assert Toast.for_window(window) is None


def test_one_toast_per_window_and_the_newest_text_wins(window):
    first = toast(window, "One.")
    second = toast(window, "Two.")
    assert first is second
    assert second.text() == "Two."
    assert second.count() == 2


def test_the_badge_appears_at_three(window):
    for n in range(Toast.BADGE_AT - 1):
        shown = toast(window, f"Message {n}.")
    assert shown.badge.isHidden()
    shown = toast(window, "One more.")
    assert not shown.badge.isHidden()
    assert shown.badge.text() == str(Toast.BADGE_AT)


def test_the_timer_runs_for_the_stated_duration(window):
    shown = toast(window, "One.")
    assert shown.timer.isActive()
    assert shown.timer.interval() == Toast.DURATION_MS


def test_the_timer_hides_it_and_resets_the_count(window):
    shown = toast(window, "One.")
    toast(window, "Two.")
    shown.timer.timeout.emit()
    assert shown.isHidden()
    assert toast(window, "Three.").count() == 1


def test_the_action_dismisses_then_runs(window):
    seen = []
    shown = toast(window, "Removed order 1001.", action_text="Undo",
                  on_action=lambda: seen.append(Toast.for_window(window).isHidden()))
    assert shown.button.text() == "Undo"
    shown.button.click()
    assert seen == [True]
    assert shown.isHidden()


def test_a_toast_raised_by_the_action_survives(window):
    shown = toast(window, "Removed order 1001.", action_text="Undo",
                  on_action=lambda: toast(window, "Undone."))
    shown.button.click()
    assert not shown.isHidden()
    assert shown.text() == "Undone."


def test_no_action_means_no_button(window):
    assert toast(window, "Done.").button.isHidden()


def test_it_stays_inside_the_window_after_a_resize(window):
    window.show()
    shown = toast(window, "Session S1 created.")
    window.resize(520, 400)
    QApplication.processEvents()
    assert window.rect().contains(shown.geometry())


@pytest.mark.parametrize("role", ["success", "info"])
def test_the_edge_carries_the_role_colour(window, role):
    shown = toast(window, "Done.", role=role)
    assert getattr(current_tokens(), f"status_{role}") in shown.styleSheet()


def test_a_failure_is_never_a_toast(window):
    with pytest.raises(ValueError):
        toast(window, "It broke.", role="danger")


def test_a_non_widget_source_is_refused(qapp):
    with pytest.raises(TypeError):
        toast(object(), "Done.")


def test_it_never_takes_focus(window):
    shown = toast(window, "Done.", action_text="Undo", on_action=lambda: None)
    assert shown.focusPolicy() == Qt.FocusPolicy.NoFocus
    assert shown.button.focusPolicy() == Qt.FocusPolicy.NoFocus
```

- [ ] **Step 2: Run to verify it fails.**
  Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_components_toast.py -v`
  Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 3: Implement.** Create `gui/components/toast.py`:

```python
"""Good news that never blocks.

The toast route (9.25): something worked and there is nothing to decide. One
toast per window, on the window that raised it; the newest replaces the
oldest, and a badge counts a fast run of them.

No fade: the brief allows "at most" 150ms, and a toast you can click before it
has arrived is worse than none.

Spec: docs/superpowers/specs/2026-09-10-phase9-bundle9-message-boxes-design.md §4.1
"""

from collections.abc import Callable

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton, QWidget

from shared.theme import current_tokens, font_css, on_theme_changed, set_button_role


class Toast(QFrame):
    """One transient message at the bottom-right of its host window."""

    DURATION_MS = 4000
    BADGE_AT = 3
    MARGIN = 16
    MAX_WIDTH = 360
    ROLES = ("success", "info")

    def __init__(self, host: QWidget) -> None:
        super().__init__(host)
        self.setObjectName("toast")
        self.setAccessibleName("Notification")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._host = host
        self._count = 0
        self._role = "success"
        self._on_action: Callable[[], None] | None = None

        self._label = QLabel(self)
        self._label.setWordWrap(True)
        self.badge = QLabel(self)
        self.badge.setObjectName("toastBadge")
        self.badge.setVisible(False)
        self.button = QPushButton(self)
        set_button_role(self.button, "ghost")
        self.button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.button.setVisible(False)
        self.button.clicked.connect(self._run_action)

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 8, 8, 8)
        row.setSpacing(8)
        row.addWidget(self._label, 1)
        row.addWidget(self.badge)
        row.addWidget(self.button)

        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(self.DURATION_MS)
        self.timer.timeout.connect(self.dismiss)

        host.installEventFilter(self)
        self.hide()
        on_theme_changed(self, self._restyle)

    @classmethod
    def for_window(cls, window: QWidget) -> "Toast | None":
        return next((c for c in window.children() if isinstance(c, cls)), None)

    def text(self) -> str:
        return self._label.text()

    def count(self) -> int:
        return self._count

    def show_message(self, text: str, *, role: str = "success", action_text: str = "",
                     on_action: Callable[[], None] | None = None) -> None:
        if role not in self.ROLES:
            raise ValueError(f"A toast is {self.ROLES}; a failure goes to the error banner")
        self._count = self._count + 1 if not self.isHidden() else 1
        self._role = role
        self._label.setText(text)
        self.badge.setText(str(self._count))
        self.badge.setVisible(self._count >= self.BADGE_AT)
        self._on_action = on_action
        self.button.setText(action_text)
        self.button.setVisible(bool(action_text))
        self._restyle(current_tokens())
        self.show()
        self.raise_()
        self._place()
        self.timer.start()

    def dismiss(self) -> None:
        self.timer.stop()
        self.hide()
        self._count = 0
        self._on_action = None

    def _run_action(self) -> None:
        # Dismiss first: a toast the action raises (Undo's result) must survive.
        action = self._on_action
        self.dismiss()
        if action is not None:
            action()

    def _place(self) -> None:
        host = self._host
        bottom = host.height()
        if isinstance(host, QMainWindow):
            bar = host.statusBar()
            if not bar.isHidden():
                bottom -= bar.height()
        width = max(0, min(self.MAX_WIDTH, host.width() - 2 * self.MARGIN))
        self.setFixedWidth(width)
        self.adjustSize()
        self.move(host.width() - width - self.MARGIN, bottom - self.height() - self.MARGIN)

    def eventFilter(self, watched, event) -> bool:
        if watched is self._host and event.type() == QEvent.Type.Resize and not self.isHidden():
            self._place()
        return False

    def enterEvent(self, event) -> None:
        self.timer.stop()  # an Undo has to be reachable
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        if not self.isHidden():
            self.timer.start()
        super().leaveEvent(event)

    def _restyle(self, tokens) -> None:
        edge = getattr(tokens, f"status_{self._role}")
        self.setStyleSheet(
            f"QFrame#toast {{ background-color: {tokens.surface_overlay};"
            f" border: 1px solid {tokens.border}; border-left: 3px solid {edge};"
            f" border-radius: {tokens.radius_md}px; }}"
            f" QFrame#toast QLabel {{ {font_css('body')} color: {tokens.text};"
            f" background: transparent; border: none; }}"
            f" QFrame#toast QLabel#toastBadge {{ {font_css('caption')}"
            f" color: {tokens.text_secondary}; }}"
        )


def toast(source: QWidget, text: str, *, role: str = "success", action_text: str = "",
          on_action: Callable[[], None] | None = None) -> Toast:
    """Show `text` on the window `source` belongs to. After a dialog's accept(),
    pass the dialog's parent: the dialog is closing."""
    if not isinstance(source, QWidget):
        raise TypeError(f"toast() needs a QWidget source, not {type(source).__name__}")
    host = source.window()
    shown = Toast.for_window(host) or Toast(host)
    shown.show_message(text, role=role, action_text=action_text, on_action=on_action)
    return shown
```
Export `Toast` and `toast` from `gui/components/__init__.py`.

- [ ] **Step 4: Run to verify it passes.** Same command; expected all PASS. If `test_it_stays_inside_the_window_after_a_resize` fails on height, call `self._label.adjustSize()` before `self.adjustSize()` in `_place`.

- [ ] **Step 5: Commit.**
```
/usr/bin/git add gui/components/toast.py gui/components/__init__.py tests/test_components_toast.py
/usr/bin/git commit -m "9.25: Toast, good news that never blocks" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 5: `ErrorBanner` and the main window's slot

**Files:**
- Create: `gui/components/error_banner.py`
- Modify: `gui/components/__init__.py`, `gui/ui_manager.py` (`create_widgets`, after the command bar is added)
- Test: `tests/test_components_error_banner.py`

**Interfaces:**
- Produces:
  - `show_error(source: QWidget, headline: str, what_to_do: str) -> ErrorBanner`
  - `ErrorBanner(parent=None, *, open_logs: Callable[[], None] | None = None)`, `ErrorBanner.for_window(window) -> ErrorBanner | None`
  - Instance: `.headline() -> str`, `.what_to_do() -> str`, `.dismiss()`, `.show_error(headline, what_to_do)`
  - Attributes: `.logs_button` (QPushButton, or None), `.dismiss_button` (QPushButton)
  - `MainWindow.error_banner` (ErrorBanner)

- [ ] **Step 1: Write the failing test.** Create `tests/test_components_error_banner.py`:

```python
"""9.25: a failure persists until dismissed and says what to do.

Spec: docs/superpowers/specs/2026-09-10-phase9-bundle9-message-boxes-design.md §4.3
"""

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QVBoxLayout, QWidget

from gui.components.error_banner import ErrorBanner, show_error
from shared.theme import current_tokens


@pytest.fixture
def dialog(qapp):
    dlg = QDialog()
    layout = QVBoxLayout(dlg)
    layout.addWidget(QLabel("existing content"))
    yield dlg
    dlg.close()


def test_a_dialog_gets_its_banner_at_the_top(dialog):
    banner = show_error(dialog, "Tag categories weren't saved",
                        "Check that the server share is reachable, then save again.")
    assert dialog.layout().indexOf(banner) == 0
    assert ErrorBanner.for_window(dialog) is banner
    assert not banner.isHidden()
    assert banner.headline() == "Tag categories weren't saved"
    assert banner.what_to_do() == "Check that the server share is reachable, then save again."


def test_a_dialog_banner_has_no_logs_button(dialog):
    assert show_error(dialog, "h", "w").logs_button is None


def test_a_second_error_replaces_the_first(dialog):
    first = show_error(dialog, "First", "w")
    second = show_error(dialog, "Second", "w")
    assert first is second
    assert second.headline() == "Second"
    assert dialog.layout().count() == 2


def test_it_persists_until_dismissed(dialog):
    banner = show_error(dialog, "h", "w")
    assert not banner.findChildren(QTimer)
    banner.dismiss_button.click()
    assert banner.isHidden()


def test_a_window_without_a_box_layout_is_refused(qapp):
    bare = QWidget()
    with pytest.raises(TypeError):
        show_error(bare, "h", "w")


def test_a_non_widget_source_is_refused(qapp):
    with pytest.raises(TypeError):
        show_error(object(), "h", "w")


def test_the_ground_is_the_danger_background(dialog):
    assert current_tokens().status_danger_bg in show_error(dialog, "h", "w").styleSheet()


@pytest.fixture
def main_window(tmp_path, monkeypatch):
    """A real MainWindow rooted at a throwaway server path (tests/test_shell.py)."""
    monkeypatch.setenv("FULFILLMENT_SERVER_PATH", str(tmp_path))
    from gui.main_window_pyside import MainWindow

    win = MainWindow()
    win.resize(1100, 900)
    win.show()
    QApplication.processEvents()
    yield win
    win.close()


def test_the_main_window_holds_a_hidden_banner(main_window):
    assert isinstance(main_window.error_banner, ErrorBanner)
    assert main_window.error_banner.isHidden()


def test_open_logs_moves_the_main_window_to_logs(main_window):
    from gui.ui_manager import UIManager

    banner = show_error(main_window.command_bar, "The analysis didn't finish", "Details are in Logs.")
    assert banner is main_window.error_banner
    banner.logs_button.click()
    assert main_window.main_tabs.currentIndex() == UIManager._RAIL_LABELS.index("Logs")
```

- [ ] **Step 2: Run to verify it fails.**
  Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_components_error_banner.py -v`
  Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 3: Implement the component.** Create `gui/components/error_banner.py`:

```python
"""A failure that persists until dismissed, and says what to do.

The error banner route (9.25). It never repeats the exception: that is in
Logs (see gui/log_handler.py). On the main window it has a slot under the
command bar and an Open Logs button; in a dialog it is inserted at the top of
the dialog's layout, where Logs is out of reach.

"Dismiss" is a word because the asset library has no `x` glyph, and a glyph is
a packing-tool PR.

Spec: docs/superpowers/specs/2026-09-10-phase9-bundle9-message-boxes-design.md §4.3
"""

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QBoxLayout, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from shared.theme import font_css, on_theme_changed, set_button_role


class ErrorBanner(QFrame):
    """Headline, what-to-do line, optional Open Logs, and Dismiss."""

    def __init__(self, parent=None, *, open_logs: Callable[[], None] | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("errorBanner")
        self.setAccessibleName("Error")

        self._headline = QLabel(self)
        self._headline.setObjectName("errorHeadline")
        self._headline.setWordWrap(True)
        self._what = QLabel(self)
        self._what.setWordWrap(True)
        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(self._headline)
        text.addWidget(self._what)

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 8, 8, 8)
        row.setSpacing(8)
        row.addLayout(text, 1)

        self.logs_button = None
        if open_logs is not None:
            self.logs_button = QPushButton("Open Logs", self)
            set_button_role(self.logs_button, "ghost")
            self.logs_button.clicked.connect(open_logs)
            row.addWidget(self.logs_button, 0, Qt.AlignmentFlag.AlignTop)
        self.dismiss_button = QPushButton("Dismiss", self)
        set_button_role(self.dismiss_button, "ghost")
        self.dismiss_button.clicked.connect(self.dismiss)
        row.addWidget(self.dismiss_button, 0, Qt.AlignmentFlag.AlignTop)

        self.hide()
        on_theme_changed(self, self._restyle)

    @classmethod
    def for_window(cls, window: QWidget) -> "ErrorBanner | None":
        banner = getattr(window, "error_banner", None)
        return banner if isinstance(banner, cls) else None

    def show_error(self, headline: str, what_to_do: str) -> None:
        self._headline.setText(headline)
        self._what.setText(what_to_do)
        self.show()

    def headline(self) -> str:
        return self._headline.text()

    def what_to_do(self) -> str:
        return self._what.text()

    def dismiss(self) -> None:
        self.hide()

    def _restyle(self, tokens) -> None:
        self.setStyleSheet(
            f"QFrame#errorBanner {{ background-color: {tokens.status_danger_bg}; border: none;"
            f" border-left: 3px solid {tokens.status_danger};"
            f" border-radius: {tokens.radius_md}px; }}"
            f" QFrame#errorBanner QLabel {{ {font_css('body')} color: {tokens.text};"
            f" background: transparent; }}"
            f" QFrame#errorBanner QLabel#errorHeadline {{ {font_css('body', bold=True)} }}"
        )


def show_error(source: QWidget, headline: str, what_to_do: str) -> ErrorBanner:
    """Show a failure on the window `source` belongs to. Log it first."""
    if not isinstance(source, QWidget):
        raise TypeError(f"show_error() needs a QWidget source, not {type(source).__name__}")
    host = source.window()
    banner = ErrorBanner.for_window(host)
    if banner is None:
        layout = host.layout()
        if not isinstance(layout, QBoxLayout):
            raise TypeError(f"{type(host).__name__} has no box layout to hold an error banner")
        banner = ErrorBanner(host)
        layout.insertWidget(0, banner)
        host.error_banner = banner
    banner.show_error(headline, what_to_do)
    return banner
```
Export `ErrorBanner` and `show_error` from `gui/components/__init__.py`.

- [ ] **Step 4: Give the main window its slot.** In `gui/ui_manager.py` `create_widgets`, directly after `right_layout.addWidget(self._create_command_bar())`:

```python
        # 9.25: a failure waits here, under the command bar, until dismissed.
        logs_index = self._RAIL_LABELS.index("Logs")
        self.mw.error_banner = ErrorBanner(
            open_logs=lambda: self.mw.main_tabs.setCurrentIndex(logs_index)
        )
        right_layout.addWidget(self.mw.error_banner)
```
Add `ErrorBanner` to the existing `from gui.components import …` line in `gui/ui_manager.py`.

- [ ] **Step 5: Run to verify it passes.** Same command as Step 2, plus `tests/test_shell.py`; expected all PASS.

- [ ] **Step 6: Commit.**
```
/usr/bin/git add gui/components/error_banner.py gui/components/__init__.py gui/ui_manager.py tests/test_components_error_banner.py
/usr/bin/git commit -m "9.25: ErrorBanner, and its slot under the command bar" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 6: The route guard

**Files:**
- Create: `tests/test_message_routes.py`

**Interfaces:**
- Produces: `OWNED` (permanent exemptions naming their owners), `PENDING` (files Tasks 7–11 delete one by one), and `offenders(root, skip=frozenset()) -> list[str]`.

- [ ] **Step 1: Write the guard.** Create `tests/test_message_routes.py`:

```python
"""9.25: every message to the operator takes one of four routes.

A QMessageBox call left in gui/ is a message that skipped the triage. OWNED
names who owns each survivor, so the later bundle that lands deletes its own
line.

Spec: docs/superpowers/specs/2026-09-10-phase9-bundle9-message-boxes-design.md §10
"""

import ast
import fnmatch
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KINDS = {"information", "warning", "critical", "question"}

OWNED = {
    ("gui/actions_handler.py", "bulk_*"): "Bundle 14 (9.17) replaces these chains",
    ("gui/actions_handler.py", "open_settings_window"): "Bundle 10 (9.23) owns settings save feedback",
    ("gui/settings/window.py", "*"): "Bundle 10 (9.23)",
    ("gui/settings/sets.py", "*"): "Bundle 10 (9.23)",
    ("gui/column_config_dialog.py", "*"): "Bundles 10 (9.23) and 13 (9.16)",
    ("gui/main_window_pyside.py", "_init_managers"): "stays native: no window exists yet",
}

# Not converted yet. Each conversion task deletes its own lines; Task 12
# deletes this set.
PENDING = {
    "gui/actions_handler.py",  # Task 7
    "gui/main_window_pyside.py",  # Task 8
    "gui/ui_manager.py",  # Task 8
    "gui/file_handler.py",  # Task 8
    "gui/add_product_dialog.py",  # Task 9
    "gui/client_settings_dialog.py",  # Task 9
    "gui/groups_management_dialog.py",  # Task 9
    "gui/tag_categories_dialog.py",  # Task 9
    "gui/rule_test_dialog.py",  # Task 9
    "gui/barcode_generator_widget.py",  # Task 10
    "gui/reference_labels_widget.py",  # Task 10
    "gui/pdf_printing.py",  # Task 10
    "gui/session_browser_widget.py",  # Task 10
    "gui/client_directory.py",  # Task 10
    "gui/log_viewer.py",  # Task 10
    "gui/settings/mappings.py",  # Task 11
    "gui/settings/rules.py",  # Task 11
    "gui/settings/weight.py",  # Task 11
}


def _message_box_calls(tree):
    """Yield (enclosing function name, call node) for each message box call."""

    def walk(node, fn):
        for child in ast.iter_child_nodes(node):
            name = child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else fn
            if isinstance(child, ast.Call):
                f = child.func
                if (isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name)
                        and f.value.id == "QMessageBox" and f.attr in KINDS):
                    yield name, child
                elif isinstance(f, ast.Name) and f.id == "QMessageBox":
                    yield name, child
            yield from walk(child, name)

    yield from walk(tree, "<module>")


def offenders(root, skip=frozenset()):
    found = []
    for path in sorted((root / "gui").rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        if rel in skip:
            continue
        for fn, call in _message_box_calls(ast.parse(path.read_text(encoding="utf-8"))):
            if any(rel == file and fnmatch.fnmatch(fn, pattern) for file, pattern in OWNED):
                continue
            found.append(f"{rel}:{call.lineno} in {fn}")
    return found


def test_no_message_box_outside_the_owned_list():
    assert offenders(ROOT, skip=PENDING) == []


def test_every_owned_entry_still_matches_a_call():
    """A stale entry is an exemption nobody needs: delete it."""
    for (file, pattern), owner in OWNED.items():
        tree = ast.parse((ROOT / file).read_text(encoding="utf-8"))
        assert any(fnmatch.fnmatch(fn, pattern) for fn, _ in _message_box_calls(tree)), (file, owner)


def test_the_guard_catches_a_planted_message_box(tmp_path):
    (tmp_path / "gui").mkdir()
    (tmp_path / "gui" / "planted.py").write_text(
        "def save():\n    QMessageBox.information(None, 'Saved', 'Saved successfully!')\n",
        encoding="utf-8",
    )
    assert offenders(tmp_path) == ["gui/planted.py:2 in save"]
```

- [ ] **Step 2: Run it.**
  Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_message_routes.py -v`
  Expected: 3 PASS. If the first fails, a file with message boxes is missing from `PENDING`; add it with the task that owns it.

- [ ] **Step 3: Commit.**
```
/usr/bin/git add tests/test_message_routes.py
/usr/bin/git commit -m "9.25: a guard that every message box has a route or an owner" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 7: `actions_handler.py` and the writeoff bypass

**Files:**
- Modify: `gui/actions_handler.py` (every function in spec §8 "`gui/actions_handler.py` (non-`bulk_*`)"), `gui/report_selection_dialog.py`
- Test: `tests/test_actions_handler.py`, `tests/test_message_routes.py`

**Interfaces:**
- Consumes: `toast`, `show_error` (Tasks 4–5).
- Produces: `ActionsHandler.generate_writeoff_report` no longer exists, and `GenerateReportsDialog.__init__` has no `writeoff_handler` parameter.

- [ ] **Step 1: Write the failing tests.** In `tests/test_actions_handler.py`:
  - Add `undo_last_operation=Mock(),` to the `mw` fixture's `SimpleNamespace`.
  - In every existing test, replace `monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)` with `monkeypatch.setattr("gui.actions_handler.toast", Mock())`. Leave the `bulk_*` tests' patches alone; those sites are skipped.
  - Append:

```python
def test_removing_an_item_asks_nothing_and_offers_undo(mw, monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("an undoable removal must not confirm")

    monkeypatch.setattr(QMessageBox, "question", refuse)
    toasts = Mock()
    monkeypatch.setattr("gui.actions_handler.toast", toasts)

    ActionsHandler(mw).remove_item_from_order("1001", "SKU-A", row_position=1)

    toasts.assert_called_once()
    assert "SKU-A" in toasts.call_args.args[1]
    assert toasts.call_args.kwargs["action_text"] == "Undo"
    assert toasts.call_args.kwargs["on_action"] is mw.undo_last_operation


def test_the_writeoff_bypass_is_gone():
    import inspect

    from gui.report_selection_dialog import GenerateReportsDialog

    assert "writeoff_handler" not in inspect.signature(GenerateReportsDialog.__init__).parameters
    assert not hasattr(ActionsHandler, "generate_writeoff_report")
```
  Delete `"gui/actions_handler.py",  # Task 7` from `PENDING` in `tests/test_message_routes.py`.

- [ ] **Step 2: Run to verify they fail.**
  Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_actions_handler.py tests/test_message_routes.py -v`
  Expected: the two new tests and `test_no_message_box_outside_the_owned_list` FAIL.

- [ ] **Step 3: Delete the writeoff bypass (spec §6).**
  - In `gui/report_selection_dialog.py`, delete the `writeoff_handler` parameter of `GenerateReportsDialog.__init__`, `self._writeoff_handler`, the `if self._writeoff_handler:` block that builds `writeoff_only_btn` (the hardcoded stylesheet and the `writeoff_layout` it adds to), and `_on_writeoff_only`. Keep `self.writeoff_checkbox` and `apply_writeoff`; they are the queue's own writeoff setting.
  - In `gui/actions_handler.py`, delete `writeoff_handler=self.generate_writeoff_report,` in `open_generate_reports_dialog` and the whole `generate_writeoff_report` method.
  - Run `rg -n "writeoff_handler|generate_writeoff_report|writeoff_only" gui tests`. The only hits left may be the import of `shopify_tool.sku_writeoff.generate_writeoff_report` elsewhere, if any.

- [ ] **Step 4: Convert every remaining row of spec §8's `actions_handler` table,** using the patterns above. Specifics:
  - `remove_item_from_order`, `remove_entire_order`: delete the `QMessageBox.question` and its `if reply != …: return`. After the successful removal (after `record_operation` and the view refresh), add T+U: `toast(self.mw, f"Removed {sku} from order {order_number}.", action_text="Undo", on_action=self.mw.undo_last_operation)`, and `toast(self.mw, f"Removed order {order_number}.", action_text="Undo", on_action=self.mw.undo_last_operation)`.
  - `open_generate_reports_dialog` "No Reports Configured": T+A exactly as the pattern shows, with `client_id` being whatever variable that function already holds.
  - `_generate_reports` "Some Reports Failed": `show_error(self.mw, f"{len(failures)} reports weren't generated", ", ".join(failures) + ". Details are in Logs.")`. Keep the second line short; if `failures` holds long strings, name only the report names.
  - `handle_multi_session_stock_export` "No Data": `show_error(self.mw, "Nothing to combine", "None of the selected sessions has a stock export. Generate one in each session first.")`.
  - `open_settings_window`: convert only "No Client Selected" (D) and "Error" (B). Leave "Settings Updated" and "Warning" as they are.
  - Every D row: do the proof step in "D: disabled action" before deleting.
  - Add `from gui.components import show_error, toast`, and remove `QMessageBox` from the import only if a `bulk_*` or `open_settings_window` site no longer needs it. They do, so it stays.

- [ ] **Step 5: Run to verify they pass.** Same command as Step 2; expected PASS. Then run the full suite. Any new failure of the form `TypeError: toast() needs a QWidget source` or `show_error() needs a QWidget source` is a test with a fake `mw`: patch `gui.actions_handler.toast` / `show_error` in that test.

- [ ] **Step 6: Lint and commit.**
```
.venv/bin/python -m ruff check . --exclude shared
/usr/bin/git add gui/actions_handler.py gui/report_selection_dialog.py tests/test_actions_handler.py tests/test_message_routes.py
/usr/bin/git commit -m "9.25: actions report through toasts and banners; the writeoff bypass goes" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 8: The main window, the UI manager and file loading

**Files:**
- Modify: `gui/main_window_pyside.py`, `gui/ui_manager.py` (`_open_session_folder`), `gui/file_handler.py`
- Test: `tests/test_shell.py`, `tests/test_file_handler.py`, `tests/test_message_routes.py`

**Interfaces:**
- Consumes: `toast`, `show_error`, `ConfirmDialog`, `MainWindow.error_banner`.

- [ ] **Step 1: Write the failing tests.**
  - Append to `tests/test_shell.py` (add `from unittest.mock import Mock` and `from PySide6.QtWidgets import QMessageBox` at the top):

```python
def test_undo_with_nothing_to_undo_says_nothing(main_window, monkeypatch):
    toasts = Mock()
    monkeypatch.setattr("gui.main_window_pyside.toast", toasts)
    monkeypatch.setattr(QMessageBox, "information", Mock(side_effect=AssertionError("no message box")))

    main_window.undo_last_operation()

    toasts.assert_not_called()
    assert main_window.error_banner.isHidden()
```
  - In `tests/test_file_handler.py`, read the fixture that builds `FileHandler` and the test that loads an orders CSV. Add a test that writes a `;`-delimited orders CSV while the configured orders delimiter is `,`, and patches `QFileDialog.getOpenFileName` to return it. It patches `QMessageBox.question` with `Mock(side_effect=AssertionError("no question"))` and patches `gui.file_handler.toast` with a `Mock`. After calling `select_orders_file()`, it asserts: the toast was called once, `call_args.kwargs["role"] == "info"`, `call_args.kwargs["action_text"] == "Save as default"`, and `";"` is in `call_args.args[1]`.
  - Delete the three Task 8 lines from `PENDING`.

- [ ] **Step 2: Run to verify they fail.**
  Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_shell.py tests/test_file_handler.py tests/test_message_routes.py -v`
  Expected: the new tests and the guard FAIL.

- [ ] **Step 3: Convert spec §8's `main_window_pyside.py` table.** Specifics:
  - `_init_managers` stays exactly as it is (N, owned).
  - `undo_last_operation` "Nothing to undo": X. Keep `if not self.undo_manager.can_undo(): return`. The result becomes `toast(self, message)` and the failure `show_error(self, "Undo didn't complete", "Details are in Logs.")`.
  - `on_session_selected`: delete the question; call the open path directly.
  - `load_existing_session`: T with `toast(self, f"Session {session_name} opened · {len(self.analysis_results_df)} orders.")` when analysis data exists, and `toast(self, f"Session {session_name} opened. Run an analysis to see results.", role="info")` when it does not.
  - `QMessageBox` stays imported (for `_init_managers`).

- [ ] **Step 4: Convert `ui_manager._open_session_folder`** ("No Session" D, "Error" B).

- [ ] **Step 5: Convert spec §8's `file_handler.py` table.** Specifics:
  - **Delimiter (both `select_orders_file` and `select_stock_file`):** delete both questions. When `detected_delimiter != config_delimiter`, load with `detected_delimiter` and toast:
    ```python
    toast(self.mw, f"Loaded with '{detected_delimiter}' — settings say '{config_delimiter}'.",
          role="info", action_text="Save as default",
          on_action=lambda: self._save_default_delimiter("orders", detected_delimiter))
    ```
    `_save_default_delimiter(kind, delimiter)` is a new private method. It holds exactly the config write that the old "Update Settings" `Yes` branch performed, moved out of both functions, with `kind` choosing the orders or stock key.
  - `select_stock_file` "Inventory Anomaly Detected": `if not ConfirmDialog.ask(self.mw, title="Use this stock file?", body=anomaly_msg, verb="Use this stock file"): return` (keeping whatever the old `No` branch did before returning).
  - `show_file_preview` "Confirm Merge": `return ConfirmDialog.ask(self.mw, title=f"Merge {n} files?", body=msg, verb=f"Merge {n} files")`, where `n` is the file count that function already has.
  - `load_folder`: all four rows B. "No Files Found" → `show_error(self.mw, f"No CSV files in {folder_path}", "Choose a folder that holds the exported CSV files.")`.

- [ ] **Step 6: Run to verify they pass,** then run the full suite and fix fake-`mw` failures as in Task 7 Step 5.

- [ ] **Step 7: Lint and commit.**
```
.venv/bin/python -m ruff check . --exclude shared
/usr/bin/git add gui/main_window_pyside.py gui/ui_manager.py gui/file_handler.py tests/test_shell.py tests/test_file_handler.py tests/test_message_routes.py
/usr/bin/git commit -m "9.25: the main window and file loading stop blocking" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 9: Dialogs

**Files:**
- Modify: `gui/add_product_dialog.py`, `gui/client_settings_dialog.py`, `gui/groups_management_dialog.py`, `gui/tag_categories_dialog.py`, `gui/rule_test_dialog.py`
- Test: `tests/test_add_product_dialog.py`, `tests/test_message_routes.py`

**Interfaces:**
- Consumes: `InlineMessage`, `ConfirmDialog`, `toast`, `show_error`.
- Produces: `AddProductDialog.order_error`, `.sku_error`, `.quantity_error` (InlineMessage).

- [ ] **Step 1: Write the failing tests.** Append to `tests/test_add_product_dialog.py` (import `QMessageBox` from `PySide6.QtWidgets`):

```python
def test_a_missing_order_number_is_said_under_the_field(dialog):
    dialog._on_add_clicked()
    assert dialog.isVisible()
    assert not dialog.order_error.isHidden()
    assert dialog.order_error.text() == "Enter an order number."


def test_editing_the_field_clears_its_message(dialog):
    dialog._on_add_clicked()
    dialog.order_input.setText("1001")
    assert dialog.order_error.isHidden()


def test_an_unknown_sku_needs_a_second_press_not_a_dialog(dialog, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no dialog")))
    dialog.order_input.setText("1001")
    dialog.sku_input.setText("SKU-NOPE")

    dialog._on_add_clicked()

    assert dialog.isVisible()
    assert dialog.add_btn.text() == "Add anyway"
    assert "SKU-NOPE" in dialog.sku_error.text()
    dialog.sku_input.setText("SKU-A")
    assert dialog.add_btn.text() == "Add Product"
```
  Delete the five Task 9 lines from `PENDING`.

- [ ] **Step 2: Run to verify they fail.**
  Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_add_product_dialog.py tests/test_message_routes.py -v`
  Expected: FAIL.

- [ ] **Step 3: Convert `add_product_dialog.py`.**
  - In `_build_form`, after each field's row, add its `InlineMessage` row and connect `textChanged` to `clear`, as in pattern **I**. For `quantity_spin`, connect `valueChanged` to a lambda that calls `self.quantity_error.clear()`.
  - In `_validate`, the four warnings become `show_message` calls:
    - order empty → "Enter an order number."
    - order not found → f"Order {order_number} isn't in this analysis."
    - SKU empty → "Enter a product SKU."
    - quantity → "Quantity must be at least 1."
  - SKU not found: keep `self._unknown_sku_accepted = ""` in `__init__`. When the SKU is not in stock and `sku != self._unknown_sku_accepted`, do three things: `self.sku_error.show_message(f"{sku} isn't in the stock file. Press Add anyway to add it.")`, `self.add_btn.setText("Add anyway")`, `self._unknown_sku_accepted = sku`, then `return False`. When `sku == self._unknown_sku_accepted`, validation passes.
  - In `_on_sku_changed`, add `self._unknown_sku_accepted = ""` and `self.add_btn.setText("Add Product")`.

- [ ] **Step 4: Convert the other four dialogs** from spec §8's "Dialogs" table. Specifics:
  - `client_settings_dialog.validate_and_accept` and `_on_save_result` success: these follow `accept()`, so pass `self.parent()` as source, and call `toast` **after** `self.accept()`. If `self.parent()` is `None`, skip the toast; the dialog's caller refreshes the list, which is the visible result.
  - `client_settings_dialog.__init__` config-load error: `if self.parent() is not None: show_error(self.parent(), f"CLIENT_{client_id} settings couldn't be loaded", "Check that the server share is reachable, then open the settings again.")`.
  - The groups dialog stays open, so its toasts use `self` as source.
  - `tag_categories_dialog._validate` "Validation Failed": add `self.validation_error = InlineMessage(self)` directly above the dialog's button box and `show_message(error_msg)` there. The Invalid/Duplicate rows in `_on_add_tag`, `_on_add_mapping` and `_on_new_category` also use this one message.
  - `tag_categories_dialog._on_add_mapping` "No Tags": D. Find the Add mapping button and enable it only while the current category has tags, updated wherever the tag list changes.
  - `_on_cancel` → `ConfirmDialog.ask(self, title="Discard your changes?", body="Your edits to tag categories haven't been saved.", verb="Discard changes")`.
  - `_on_delete_category` → `ConfirmDialog.ask(self, title=f"Delete category {label}?", body=f"Its {n} tags are deleted with it. This cannot be undone.", verb="Delete category")`.

- [ ] **Step 5: Run to verify they pass,** then run the full suite, including `tests/test_tag_categories_dialog.py`. A test that patched `QMessageBox.question` to return `Yes` for these dialogs now patches `gui.<module>.ConfirmDialog.ask` to return `True`.

- [ ] **Step 6: Lint and commit.**
```
.venv/bin/python -m ruff check . --exclude shared
/usr/bin/git add gui/add_product_dialog.py gui/client_settings_dialog.py gui/groups_management_dialog.py gui/tag_categories_dialog.py gui/rule_test_dialog.py tests/test_add_product_dialog.py tests/test_message_routes.py
/usr/bin/git commit -m "9.25: dialogs say what is wrong where it is wrong" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```
  Also add any other test file Step 5 changed.

---

### Task 10: Tools, Browse and Logs

**Files:**
- Modify: `gui/barcode_generator_widget.py`, `gui/reference_labels_widget.py`, `gui/pdf_printing.py`, `gui/session_browser_widget.py`, `gui/client_directory.py`, `gui/log_viewer.py`
- Test: `tests/test_pdf_printing.py`, `tests/test_barcode_generator_widget.py`, `tests/test_reference_labels_widget.py`, `tests/test_client_directory.py`, `tests/test_message_routes.py`

- [ ] **Step 1: Re-point the existing tests, and add one.**
  - `tests/test_pdf_printing.py`:
    - `test_blank_target_warns_and_returns_false` → rename to `test_blank_target_says_where_to_set_it_and_returns_false`. Replace `monkeypatch.setattr(QMessageBox, "warning", warning)` with `monkeypatch.setattr(pdf_printing, "show_error", warning)`, and add `assert "Print options" in warning.call_args.args[2]`.
    - In the two `…shows_critical_and_returns_false` tests, replace `monkeypatch.setattr(QMessageBox, "critical", critical)` with `monkeypatch.setattr(pdf_printing, "show_error", critical)`.
    - Drop the now-unused `QMessageBox` import.
  - `tests/test_barcode_generator_widget.py` `_run`: replace the two `QMessageBox` patches with `monkeypatch.setattr("gui.barcode_generator_widget.toast", info)` and `monkeypatch.setattr("gui.barcode_generator_widget.show_error", critical)`. The assertions stay.
  - `tests/test_reference_labels_widget.py`: replace `monkeypatch.setattr(QMessageBox, "information", Mock())` with `monkeypatch.setattr("gui.reference_labels_widget.toast", Mock())`.
  - Append to `tests/test_client_directory.py` (import `QWidget` from `PySide6.QtWidgets`):

```python
def test_the_client_menu_offers_no_delete(directory, profile_manager):
    profile_manager.create_client_profile("alpha", "Client alpha")
    parent = QWidget()
    menu = directory.menu_for("alpha", parent)
    assert not [a for a in menu.actions() if "Delete" in a.text()]
```
  - Delete the six Task 10 lines from `PENDING`.

- [ ] **Step 2: Run to verify they fail.**
  Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_pdf_printing.py tests/test_barcode_generator_widget.py tests/test_reference_labels_widget.py tests/test_client_directory.py tests/test_message_routes.py -v`
  Expected: FAIL.

- [ ] **Step 3: Convert** from spec §8's "Tools, Browse, Logs" table. Specifics:
  - `pdf_printing._print_pdf_raw_zpl_mode` "No Printer Configured": `show_error(parent, "Nothing was printed", "Choose a Raw ZPL printer under Print options, then print again.")`, where `parent` is that function's parent argument. This also removes the stale "Output/Options section" copy Bundle 8 left.
  - `barcode_generator_widget._on_generate_clicked` "Confirm Generation": read where generation writes its PDF (`barcodes_dir` and the file name built from the packing list).
    - If a PDF for that packing list can already exist and is overwritten: `if not ConfirmDialog.ask(self, title=f"Replace barcodes for {self.current_packing_list}?", body=f"The existing PDF is overwritten with {order_count} new barcodes. This cannot be undone.", verb="Replace barcodes"): return`, asked only when the file exists.
    - Otherwise delete the question.
    - Record which case applied in the commit message body.
  - `reference_labels_widget._validate_inputs`: add `self.validation_error = InlineMessage(self)` directly above the Process button, and `show_message("Can't process yet: " + "; ".join(errors))`. Clear it at the start of the next `_validate_inputs` call.
  - `reference_labels_widget._on_processing_error`: `show_error(self, title, suggestion or "Details are in Logs.")`, reusing that function's existing variables.
  - `session_browser_widget` load errors: `rg -n "StatePanel" gui/session_browser_widget.py`. If a failed state already exists for a load failure, show it there and delete the box; otherwise B.
  - `client_directory.menu_for`: delete the `delete_action` lines and the whole `_delete_client` method.
  - `log_viewer._save_as_text`: `show_error(self, "The log wasn't saved", f"{path} couldn't be written. Choose another folder and save again.")`.

- [ ] **Step 4: Run to verify they pass,** then run the full suite.

- [ ] **Step 5: Lint and commit.**
```
.venv/bin/python -m ruff check . --exclude shared
/usr/bin/git add gui/barcode_generator_widget.py gui/reference_labels_widget.py gui/pdf_printing.py gui/session_browser_widget.py gui/client_directory.py gui/log_viewer.py tests/test_pdf_printing.py tests/test_barcode_generator_widget.py tests/test_reference_labels_widget.py tests/test_client_directory.py tests/test_message_routes.py
/usr/bin/git commit -m "9.25: tools, browse and logs report without blocking" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 11: Settings pages

**Files:**
- Modify: `gui/settings/mappings.py`, `gui/settings/rules.py`, `gui/settings/weight.py`
- Test: `tests/test_settings_window_weight_quick_add.py`, `tests/test_settings_page_weight.py`, `tests/test_message_routes.py`

**Interfaces:**
- Produces: `WeightPage.weight_quick_sku_error` (InlineMessage), `WeightPage.weight_export_products_btn` and `WeightPage.weight_export_boxes_btn` (QPushButton), `WeightPage._sync_export_buttons()`.

- [ ] **Step 1: Write the failing tests.**
  - In `tests/test_settings_window_weight_quick_add.py`, add `obj.weight_quick_sku_error = InlineMessage(obj)` to the `sw` fixture (import from `gui.components.inline_message`). Replace `test_quick_add_rejects_duplicate_sku_without_adding_a_row` with:

```python
def test_quick_add_rejects_duplicate_sku_without_adding_a_row(sw):
    sw.weight_quick_sku.setText("DUPE")
    WeightPage._weight_quick_add_product(sw)
    assert sw.weight_products_table.rowCount() == 1

    sw.weight_quick_sku.setText("DUPE")
    WeightPage._weight_quick_add_product(sw)

    assert sw.weight_products_table.rowCount() == 1
    assert sw.weight_quick_sku_error.text() == "DUPE is already in the table. Edit it there instead."
```
  - In `tests/test_settings_page_weight.py`, read how that file builds a full `WeightPage`, then add a test using that fixture. It asserts `weight_export_products_btn.isEnabled()` is False while `weight_products_table.rowCount() == 0`, and becomes True after `weight_products_table.insertRow(0)`.
  - Delete the three Task 11 lines from `PENDING`.

- [ ] **Step 2: Run to verify they fail.**
  Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_settings_window_weight_quick_add.py tests/test_settings_page_weight.py tests/test_message_routes.py -v`
  Expected: FAIL.

- [ ] **Step 3: Convert `weight.py`.** The settings dialog hosts these, because `self.window()` is the settings dialog. Specifics:
  - `_weight_quick_add_product` Duplicate SKU: build `self.weight_quick_sku_error = InlineMessage(self)` directly under the quick-add SKU field in `__init__`, and connect `self.weight_quick_sku.textChanged` to its `clear`. The site becomes `self.weight_quick_sku_error.show_message(f"{sku} is already in the table. Edit it there instead.")`.
  - **Export D:** keep `export_prod_btn` as `self.weight_export_products_btn` and `export_box_btn` as `self.weight_export_boxes_btn`. Add:
    ```python
    def _sync_export_buttons(self) -> None:
        self.weight_export_products_btn.setEnabled(self.weight_products_table.rowCount() > 0)
        self.weight_export_boxes_btn.setEnabled(self.weight_boxes_table.rowCount() > 0)
    ```
    Confirm the boxes table's attribute name with `rg -n "QTableWidget\(" gui/settings/weight.py`. At the end of `__init__`, connect each table's `model().rowsInserted` and `model().rowsRemoved` to `lambda *_: self._sync_export_buttons()`, then call `self._sync_export_buttons()` once. Delete the "No products/boxes to export" boxes, keeping a silent `return` guard.
  - **Duplicates (products and boxes imports):** give each import method the signature `(self, path: str | None = None, update_existing: bool = False)`.
    - When `path is None`, it opens the existing file dialog as today.
    - Its `clicked.connect(self._weight_import_products_from_csv)` must become `clicked.connect(lambda: self._weight_import_products_from_csv())`. `clicked` passes `checked` as the first argument, which would land in `path`.
    - Delete the hand-built `QMessageBox`: duplicates are skipped unless `update_existing`.
    - The "Import Complete" toast is `toast(self, f"Added {added}. Skipped {skipped} already in the table.")` with `action_text="Update them"` and `on_action=lambda: self._weight_import_products_from_csv(path, update_existing=True)` when `skipped` and not `update_existing`. Otherwise it is a plain toast: `f"Added {added}. Updated {updated}."`.
  - Column Not Found / Warning / Import Error / Export Error → B. Export Complete → T.

- [ ] **Step 4: Convert `mappings.py`** (both B) and **`rules.py`** `_test_rule`:
  - "No Conditions" → an `InlineMessage` beside the Test button.
  - "No Data" → D if the page can see whether analysis data exists when the Test button is built (`rg -n "analysis" gui/settings/rules.py`). Otherwise use the same inline message: "Run an analysis in the main window first."

- [ ] **Step 5: Run to verify they pass,** then run the full suite, including `tests/test_settings_page_mappings.py` and `tests/test_settings_page_rules.py`.

- [ ] **Step 6: Lint and commit.**
```
.venv/bin/python -m ruff check . --exclude shared
/usr/bin/git add gui/settings/mappings.py gui/settings/rules.py gui/settings/weight.py tests/test_settings_window_weight_quick_add.py tests/test_settings_page_weight.py tests/test_message_routes.py
/usr/bin/git commit -m "9.25: settings pages report inside the settings window" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 12: Close the guard and run the gate

**Files:**
- Modify: `tests/test_message_routes.py`

- [ ] **Step 1: Delete `PENDING`.** It is empty now. Remove the set, its comment, and the `skip=PENDING` argument in `test_no_message_box_outside_the_owned_list`.

- [ ] **Step 2: Prove what is left.**
  Run: `rg -n "QMessageBox\.(information|warning|critical|question)|QMessageBox\(" gui`
  Expected: hits only in `gui/actions_handler.py` (inside `bulk_*` and `open_settings_window`), `gui/settings/window.py`, `gui/settings/sets.py`, `gui/column_config_dialog.py`, and `gui/main_window_pyside.py` `_init_managers`.

- [ ] **Step 3: Full gate.**
  Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest`
  Expected: all PASS. The count is the pre-bundle 1445, plus the new tests, minus any deleted writeoff or client-delete tests.
  Run: `.venv/bin/python -m ruff check . --exclude shared`
  Expected: clean.

- [ ] **Step 4: Refresh the graph.**
  Run: `graphify update .`

- [ ] **Step 5: Commit and push.**
```
/usr/bin/git add tests/test_message_routes.py
/usr/bin/git commit -m "9.25: every message box has a route or an owner" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
/usr/bin/git push
```
