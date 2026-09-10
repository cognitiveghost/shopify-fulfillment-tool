# Phase 9 Bundle 9 — Message boxes sort into four routes

**Date:** 2026-09-10
**Item:** 9.25, alone
**Todoist:** bundle `6hQXj6xFwpmjx3WV`, item `6hQVj56RqJfXC8x3`
**Artboard:** G3. The canvas could not be read from this VM (DesignSync needs
`/design-login`), so this spec works from the roadmap
(`docs/superpowers/plans/2026-09-03-phase9-roadmap.md` § 9.25) and the Todoist
brief, which the phase parent names as the contract. §9 lists the departures.

**Classification:** architectural. Four new components that Bundles 10 and 14
build on, a change to how every result, problem and confirmation in `gui/`
reaches the operator, and one change to the log handler. There is no new
dependency, no `shared/` change, no new token and no new glyph.

**Scope decisions (user, 2026-09-10):**
1. Call sites that a later bundle rewrites are skipped and allow-listed with
   their owner (§2).
2. Non-bulk `QInputDialog` prompts stay native.
3. All four routes ship in this PR, the error banner included.
4. A toast appears on whichever window raised it.

---

## 1. What ships today

`gui/` makes 217 `QMessageBox` calls (41 `information`, 86 `warning`, 63
`critical`, 25 `question`, 2 hand-built `QMessageBox(...)`) and 17
`QInputDialog` calls, across 21 files. Every one of them blocks the thread,
whether it reports good news, a typo in a field, or a failed network write.

Three facts the design depends on:

- **Logs does not hold the traceback.** The brief says the error banner "links
  to Logs where the traceback already is". It does not:
  `QtLogHandler.emit` (`gui/log_handler.py`) builds its `LogEntry` from
  `record.getMessage()` and drops `record.exc_info`. Only the JSON file log
  (`shared/logger.py`) keeps it. §5 fixes this.
- **Tests read message boxes.** `tests/conftest.py` stubs the four static
  methods and records the calls. Tests for `actions_handler`,
  `session_browser_1e`, `pdf_printing`, `barcode_generator_widget`,
  `settings_window_weight_quick_add`, `reference_labels_widget`, `shell`,
  `rule_test_dialog` and `generate_reports_dialog` assert on them.
- **"Generate Writeoff Report Only"** (`gui/report_selection_dialog.py`) calls
  `ActionsHandler.generate_writeoff_report`, its only caller. The queue already
  carries a `writeoff_reports` report type, so deleting the button removes a
  bypass, not a feature.

## 2. Scope

**Converted here:** every `QMessageBox` call in `gui/` except the ones below.

**Not converted, allow-listed in the route guard (§10) with the owner named:**

| Where | Owner | Why |
|---|---|---|
| `gui/actions_handler.py` — every `bulk_*` function | Bundle 14 (9.17) | 9.17 deletes these dialog chains and replaces them with `BulkActionPopover` |
| `gui/actions_handler.py` — `open_settings_window`'s save feedback ("Settings Updated", "Settings were saved, but…") | Bundle 10 (9.23) | 9.23 owns settings save feedback |
| `gui/settings/window.py` | Bundle 10 (9.23) | Same, and the brief names this toast explicitly |
| `gui/settings/sets.py` | Bundle 10 (9.23) | 9.23 rewrites Sets to buffer its writes |
| `gui/column_config_dialog.py` | Bundles 10 (9.23) and 13 (9.16) | 9.16 replaces `ColumnConfigPanel`; 9.23 buffers `_ColumnConfigPage` |
| `gui/main_window_pyside.py` — `_init_managers` | stays native | It runs during `MainWindow` construction and quits the app; no window exists to host a banner |

`open_settings_window`'s other two sites, the no-client guard and the
failed-to-open error, are converted here.

**Out of scope:** `QFileDialog` (native, as the brief says), and every
`QInputDialog` outside the `bulk_*` functions: `add_tag_manually`, the group,
tag and category name prompts, and the session comment. Those ask for a value;
none of the four routes does that.

## 3. The routes, and the rule that picks one

A **message route** is where one message goes. Ask in this order and stop at
the first yes:

1. **Is it a guard for something the operator could not do yet?** (no client,
   no session, no analysis, no selection, nothing to export.)
   → **Disabled action.** The message is deleted; the control that led here is
   disabled in that state. The guard's early `return` stays, silent, as a
   backstop. Most of these controls are already disabled by `BarState` or the
   selection state: check before wiring anything new. If the entry point cannot
   be disabled (a shortcut, a signal from elsewhere), route it to **Error banner**.
2. **Does the problem have a location on screen?** (a field, a card, a form.)
   → **Inline message**, beside that location. The operator's typed input is
   never cleared, and the message clears when the field it names is edited.
3. **Is the operator about to destroy data that Undo cannot reach?**
   → **Confirm.** An undoable operation never confirms. Its toast carries Undo
   instead.
4. **Did it fail?**
   → **Error banner.** Log first with `exc_info`, then show what to do next.
5. **Did it work?**
   → **Toast.** When the operation called `undo_manager.record_operation`, the
   toast carries **Undo**.
6. **Does it say nothing an operator would miss?** ("No changes were made.")
   → **Deleted.**

## 4. Components

All four live in `gui/components/`, one module each, and are exported from
`gui/components/__init__.py`. Each styles itself through `on_theme_changed`
(ADR 0003) and composes rather than subclasses where a QSS selector would
otherwise be needed in `shared/theme.py`. Both themes come from the tokens;
nothing here is theme-specific.

Call sites import the functions and classes at module level
(`from gui.components import toast, show_error, ConfirmDialog, InlineMessage`),
so tests patch them on the calling module (`gui.actions_handler.show_error`).

### 4.1 `Toast` — `gui/components/toast.py`

```python
def toast(source: QWidget, text: str, *, role: str = "success",
          action_text: str = "", on_action: Callable[[], None] | None = None) -> "Toast"

class Toast(QFrame):
    DURATION_MS = 4000
    BADGE_AT = 3
    @classmethod
    def for_window(cls, window: QWidget) -> "Toast | None": ...
    def text(self) -> str: ...
    def count(self) -> int: ...
    def dismiss(self) -> None: ...
```

- **Host:** `source.window()`. That is the main window almost everywhere, and a
  dialog when the dialog raised it and stays open (scope decision 4). A message
  that follows a dialog's `accept()` passes the dialog's **parent** as `source`,
  because the dialog is closing.
- **One per host.** `toast()` finds the host's `Toast` child or creates it.
  Calling it again while a toast is showing replaces the text, role and action,
  restarts the timer and adds one to `count()` (the first toast has a count of
1). At `BADGE_AT` or more a badge
  shows the count, so a fast bulk run reads as "7", not as one message.
  Hiding resets the count.
- **Timing:** hides after `DURATION_MS`. The timer pauses while the pointer is
  over the toast, so an Undo can be reached. No fade: the brief allows "at most"
  150ms, and 9.17's argument applies here too, since a toast you can click
  before it has arrived is worse than none.
- **Placement:** bottom-right, 16px from the host's edges; on a `QMainWindow`,
  above the status bar. An event filter on the host re-places the toast on
  `Resize`; that is how "positioned in `resizeEvent`" is written without
  subclassing every host. Width is at most 360px, text wraps, and `raise_()` is
  called on every show.
- **Anatomy:** one `QLabel`, up to one ghost button (`set_button_role(…,
  "ghost")`), and the badge. Pressing the button calls `on_action`, then
  dismisses.
- **Look:** `surface_overlay` ground, 1px `border`, a 3px left edge in
  `status_success` or `status_info` (the only two roles; a failure is never a
  toast), `radius_md`, text in `text` with `font_css("body")`, and the badge in
  `caption` and `text_secondary`.
- **Focus:** a toast never takes focus, and its button has `Qt.NoFocus`. Ctrl+Z
  stays the keyboard path to Undo. Accessible name: "Notification".

### 4.2 `ConfirmDialog` — `gui/components/confirm_dialog.py`

```python
class ConfirmDialog(QDialog):
    def __init__(self, parent, *, title: str, body: str, verb: str): ...
    @classmethod
    def ask(cls, parent, *, title: str, body: str, verb: str) -> bool: ...
```

- A `QDialogButtonBox` holding **Cancel** (`RejectRole`) and a `QPushButton`
  labelled with the verb (`AcceptRole`). `apply_dialog_button_roles(box)` marks
  the verb primary, as the brief keeps it.
- **Cancel is the default button**, so Enter never destroys anything.
- `verb` equal to "OK", "Yes", "Confirm" or "Continue" (case-insensitive)
  raises `ValueError`. The verb names the act ("Delete group").
- Copy: the title is the question ("Delete group North?") and the body states
  the count and the consequence ("3 clients lose their group. This cannot be
  undone.").
- `ask` returns `exec() == QDialog.Accepted`.

### 4.3 `ErrorBanner` — `gui/components/error_banner.py`

```python
def show_error(source: QWidget, headline: str, what_to_do: str) -> "ErrorBanner"

class ErrorBanner(QFrame):
    def __init__(self, parent=None, *, open_logs: Callable[[], None] | None = None): ...
    @classmethod
    def for_window(cls, window: QWidget) -> "ErrorBanner | None": ...
    def headline(self) -> str: ...
    def dismiss(self) -> None: ...
```

- **Host:** `source.window()`, using the same rule as the toast.
  - **Main window:** `UIManager.create_widgets` builds
    `self.mw.error_banner = ErrorBanner(open_logs=…)` between the command bar and
    `main_tabs`, hidden. `open_logs` sets `main_tabs` to the Logs index, looked
    up from `_RAIL_LABELS`, never the literal `3`.
  - **Dialog:** created on first use, inserted at index 0 of the dialog's
    `QBoxLayout`, and stored as `window.error_banner`. A layout that is not a
    `QBoxLayout` raises `TypeError`. Every dialog in scope uses `QVBoxLayout`.
- **Behaviour:** persists until dismissed, with no timer. A second error
  replaces the first. It never takes focus, and its buttons stay reachable
  with Tab.
- **Anatomy:** the headline (`font_css("body", bold=True)`), the what-to-do
  line (`body`), and on the right an **Open Logs** ghost button, present only
  when `open_logs` is given, then a **Dismiss** ghost button. There is no `x`
  glyph in the asset library, and a word needs no `shared/` PR.
- **Look:** `status_danger_bg` ground, a 3px `status_danger` left edge (the same
  edge as the toast, so the two read as one family), `radius_md`, text in
  `text`. Accessible name: "Error".
- **Copy:** the headline states the consequence ("The session wasn't
  created"). The what-to-do line says what to try ("Check that the server
  share is reachable, then create it again."). Neither repeats the exception
  text; that is in Logs (§5). In a dialog there is no Logs button, so when the
  cause matters the line ends "Details are in Logs."

### 4.4 `InlineMessage` — `gui/components/inline_message.py`

```python
class InlineMessage(QLabel):
    def __init__(self, parent=None): ...
    def show_message(self, text: str) -> None: ...
    def clear(self) -> None: ...
```

- Hidden while empty; word-wrapped; `status_danger` text in `font_css("body")`.
- Placed directly under the field it names. When a form has no per-field slot,
  it goes directly above the form's button box. The call site connects the
  named field's `textChanged` (or its equivalent) to `clear`.

## 5. Logs carries the exception

`QtLogHandler.emit` appends the exception's one-line summary to the entry's
message when `record.exc_info` is set:
`f"{record.getMessage()} — {traceback.format_exception_only(etype, value)[-1].strip()}"`.
One line, so a log row stays one row; the full traceback stays in the JSON file
log. Every call site converted to the error banner must log the failure with
`exc_info=True` (or `logger.exception`) before calling `show_error`. Most
already do; those that do not gain the call.

## 6. "Generate Writeoff Report Only" is deleted

That removes the button and its `clicked` handler in
`gui/report_selection_dialog.py`, the `writeoff_handler` parameter, the
`writeoff_handler=` argument in `open_generate_reports_dialog`,
`ActionsHandler.generate_writeoff_report` with its three message boxes, and any
test that exercises them.

## 7. Copy rules

- No "successfully", no exclamation marks, no "Error" as a title, and no
  exception text shown to the operator.
- A toast states what happened in the past tense, with the object named:
  "Session 2026-09-10_1 created.", "Removed TS-4409-B from order 1042."
- An action keeps one name through the whole flow: the button, the confirm verb
  and the toast use the same word ("Delete group" → "Deleted group North.").
- The stale "Output/Options section" text in `pdf_printing.py`, owed by
  Bundle 8, becomes "Choose a Raw ZPL printer under Print options, then print
  again."

## 8. Per-site triage

Routes: **T** toast · **T+U** toast with Undo · **T+A** toast with one action ·
**I** inline · **D** disabled action · **C** confirm · **B** error banner ·
**X** deleted · **N** native. Sites are named by function and today's title,
because line numbers drift.

### `gui/actions_handler.py` (non-`bulk_*`)

| Function | Today | Route | Note |
|---|---|---|---|
| `create_new_session` | No Client Selected | D | |
| | Session Created | T | "Session {name} created." |
| | Session Error / File System Error / Unexpected Error | B | "The session wasn't created" |
| `run_analysis` | Session Error, Client Error | D | |
| `on_analysis_complete` | Analysis Complete | T | |
| | Analysis Error | B | "The analysis didn't finish" |
| `on_task_error` | Task Exception | B | "A background task failed" |
| `open_settings_window` | No Client Selected | D | |
| | Error (failed to load) | B | |
| | Settings Updated, Warning | skipped | Bundle 10 |
| `open_tag_categories_dialog` | No Client Selected, No Configuration Loaded | D | |
| `on_categories_updated` | Save Error | B | |
| `open_generate_reports_dialog` | No Analysis Data, No Client Selected, No Active Session | D | |
| | Configuration Error | B | |
| | No Reports Configured | T+A | role `info`, action "Open Settings" → `open_settings_window` |
| `_generate_reports` | Some Reports Failed | B | headline counts them; names in the what-to-do line |
| `_generate_single_report` | Generation Failed | B | |
| `generate_writeoff_report` | all three | X | function deleted (§6) |
| `toggle_fulfillment_status_for_order` | Error ×2 | B | |
| `remove_item_from_order` | Confirm Delete | X → T+U | undoable, so no confirm |
| `remove_entire_order` | Confirm Delete | X → T+U | undoable, so no confirm |
| `show_add_product_dialog` | No Analysis, No Stock Data | D | |
| | Error Loading Stock | B | |
| `_add_product_to_order` | Error (order not found) | B | |
| | Product Added | T+U if the path records an undo, else T | |
| `handle_multi_session_stock_export` | Error: No client selected | D | |
| | Error: Could not resolve 2+ session paths | D | the action needs 2+ selected sessions; otherwise B |
| | No Data | B | "Nothing to combine": none of the selected sessions has a stock export |
| | Done | T | |
| | Save Error | B | |

### `gui/main_window_pyside.py`

| Function | Today | Route | Note |
|---|---|---|---|
| `_init_managers` | Initialization Error ×2 | N | allow-listed (§2) |
| `load_client_config` | Configuration Error, Error | B | |
| `undo_last_operation` | Undo: Nothing to undo | X | Undo is already disabled by `_update_undo_button`; Ctrl+Z with nothing to undo does nothing |
| | Undo (result) | T | |
| | Undo Failed | B | |
| `open_column_config_dialog` | No Client Selected | D | |
| `_on_client_data_loaded` | Configuration Error, Error | B | |
| `_on_client_data_load_error` | Error | B | |
| `on_sidebar_refresh` | Refresh Error | B | |
| `on_session_selected` | Open Session (question) | X | opening is not destructive; open directly |
| `load_existing_session` | Session Loaded, Session Opened | T | |
| | Error | B | |

### `gui/file_handler.py`

| Function | Today | Route | Note |
|---|---|---|---|
| `select_orders_file`, `select_stock_file` | Delimiter Detected + Update Settings (two questions each) | T+A | load with the detected delimiter; role `info`, "Loaded with ';' — settings say ','.", action "Save as default" |
| `select_stock_file` | File Load Error | B | |
| | Inventory Anomaly Detected (Yes/No) | C | verb "Use this stock file" (§9) |
| `load_folder` | No Files Found, Validation Error, No Valid Files, Merge Failed | B | |
| `show_file_preview` | Confirm Merge | C | verb "Merge {n} files" (§9) |

### Dialogs

| File · function | Today | Route | Note |
|---|---|---|---|
| `add_product_dialog` · `_validate` | Validation Error ×4 | I | under the named field |
| | SKU Not Found (question) | I | "TS-4409-B isn't in the stock file." The Add button reads "Add anyway" until the SKU field changes |
| `client_settings_dialog` · `validate_and_accept` | Validation Error ×3, Profile Exists | I | |
| | Success | T | source = the dialog's parent |
| | Error ×2 | B | in the dialog |
| · `refresh_clients` | Error | B | |
| · `__init__` | Error (config load) | B | source = the dialog's parent; the dialog has no layout yet |
| · `_save_and_accept`, `_on_save_error` | Error | B | |
| · `_on_save_result` | Success | T | source = the dialog's parent |
| | Save Failed | B | |
| `groups_management_dialog` · `_create_group`, `_edit_group`, `_delete_group` | Success ×3 | T | the dialog stays open, so it hosts |
| | Error / unexpected / not found | B | |
| · `_edit_group` | No Changes | X | |
| · `_delete_group` | Delete Group (question) | C | verb "Delete group" |
| · `_load_groups` | Error | B | |
| `tag_categories_dialog` · `_on_add_tag`, `_on_add_mapping`, `_on_new_category` | Invalid / Duplicate ×8 | I | |
| · `_on_add_mapping` | No Tags | D | "Add mapping" is disabled while the category has no tags |
| · `_validate` | Validation Failed | I | above the button box |
| · `_on_apply` | Saved | T | |
| · `_on_delete_category` | Delete Category (question) | C | verb "Delete category" |
| · `_on_cancel` | Unsaved Changes (question) | C | verb "Discard changes" |
| `rule_test_dialog` · `_run_test` | Test Error | B | |

### Tools, Browse, Logs

| File · function | Today | Route | Note |
|---|---|---|---|
| `barcode_generator_widget` · `_on_generate_clicked` | No Orders | D | |
| | Confirm Generation (question) | X | unless generation overwrites an existing PDF for this packing list, in which case C with verb "Replace barcodes" |
| · `_on_generation_complete` | Generation Complete | T | |
| | PDF Generation Failed | B | |
| · `_on_generation_error` | Generation Error | B | |
| `reference_labels_widget` · `_validate_inputs` | Validation Error | I | above the Process button |
| · `_on_processing_complete` | Success | T | |
| · `_on_processing_error` | (title) | B | its existing `suggestion` becomes the what-to-do line |
| · `_open_pdf` | Cannot Open File | B | |
| `pdf_printing` · `_print_pdf_raw_zpl_mode` | No Printer Configured | B | new copy (§7) |
| | Print Failed | B | |
| · `_print_pdf_driver_mode` | Print Failed ×2 | B | |
| `ui_manager` · `_open_session_folder` | No Session | D | |
| | Error | B | |
| `session_browser_widget` · `_do_refresh_sync`, `_on_load_error` | Error / Error Loading Sessions | B | if the widget already shows a failed `StatePanel` for this case, use that and delete the box |
| · `_open_selected_session` | Selected session has no valid path | D | |
| · `_apply_status_to_selection`, `_on_status_changed` | Error | B | |
| `client_directory` · `_on_refresh_error`, `_toggle_pin`, `_move_to_group` | Refresh Error / Error | B | |
| · `_delete_client` | Delete Client (question), Not Implemented, Error | X | the Delete action is removed from the menu (§9) |
| `log_viewer` · `_save_as_text` | Could not save log | B | |

### Settings pages (hosted by the settings dialog)

| File · function | Today | Route | Note |
|---|---|---|---|
| `settings/mappings` · `_load_headers_from_csv` | Could Not Read CSV, No Columns Found | B | |
| `settings/rules` · `_test_rule` | No Data | D | Test disabled without analysis data; if the page cannot know that, I |
| | No Conditions | I | beside the Test button |
| `settings/weight` · `_weight_quick_add_product` | Duplicate SKU | I | |
| · `_weight_import_*` | Warning / Column Not Found | B | the file is the problem, and it has no on-screen location |
| | Import Complete | T | |
| | Import Error | B | |
| · `_weight_import_products_from_csv`, `_weight_import_boxes_from_csv` | hand-built "Duplicates Found" (Skip / Update) | T+A | import skips duplicates, then toasts "Added 12. Skipped 4 already in the table." with action "Update them", which re-runs the import with `update_existing=True` (§9) |
| · `_weight_export_*` | Export: nothing to export | D | the Export button is disabled while its table is empty |
| | Export Complete | T | |
| | Export Error | B | |

## 9. Departures from the brief

1. **A toast lives on the window that raised it**, not always on the main
   window. A large modal can cover the main window's bottom-right corner (scope
   decision 4).
2. **No fade.** The brief allows "at most 150ms"; zero is within that.
3. **Logs gains the exception summary** (§5). The brief assumed it was already
   there.
4. **Two non-destructive confirms stay confirms.** "Merge {n} files" is a
   preview the operator commits. "Use this stock file" gates an analysis whose
   allocation is written into the session and that Undo cannot reach.
5. **The weight import's duplicate prompt becomes a toast action.** The page is
   buffered until Save, so the safe default (skip) applies and "Update them" is
   one click away.
6. **Client delete is removed from the menu**, not converted. It confirms, then
   says "Not implemented". An action that cannot run should not be offered.
7. **The error banner has a text Dismiss button**, not an `x` glyph, because
   the asset library has none.

## 10. Testing seams

- **Component tests**, one file each, in the style of
  `tests/test_state_panel.py` (`qapp` fixture, a real host widget):
  - `tests/test_components_toast.py`: the host is the source's window, both a
    `QMainWindow` and a `QDialog`; a second call replaces the text and a third
    shows the badge; the timer's timeout hides the toast and resets the count;
    the action button calls `on_action` and dismisses; the toast sits inside the
    host rect after a resize; the edge colour follows a theme toggle.
  - `tests/test_components_confirm_dialog.py`: the verb is the accept button
    and carries role `primary`; Cancel is the default; "OK" and "Yes" raise;
    `ask` returns `True` or `False` with `exec` patched.
  - `tests/test_components_error_banner.py`: on the main window it uses the
    slot and Open Logs selects the Logs tab; on a dialog it is inserted at
    layout index 0 with no Logs button; a second error replaces the first;
    there is no timer; Dismiss hides it.
  - `tests/test_components_inline_message.py`: hidden while empty, shown with
    text, hidden again on clear.
- **Log handler:** an entry built from a record with `exc_info` carries the
  exception's type and message on one line.
- **Route guard** (`tests/test_message_routes.py`): an AST walk over `gui/`
  fails on any `QMessageBox.information|warning|critical|question` or
  `QMessageBox(...)` outside an allow-list keyed by file and function, each
  entry naming its owner (§2). Each later bundle deletes its own entries.
- **Existing tests** that asserted a message box in a converted module now
  patch the name on the calling module (`gui.pdf_printing.show_error`) and
  assert its arguments. `tests/conftest.py`'s recorder stays, because
  `gui/settings/window.py` still uses it.

## 11. Risks

- **Many call sites, one PR.** The route guard makes "done" checkable, and the
  triage table makes each conversion mechanical rather than a judgement call.
- **Disabled-action conversions can silently strand a flow** if the control was
  not actually disabled in that state. Each **D** conversion checks the enabling
  code before deleting the message, and falls back to **B** (§3, rule 1).
- **A `source.window()` that is not yet shown** (a dialog's `__init__`) would
  host a banner nobody sees. The table marks those sites to use the parent.
