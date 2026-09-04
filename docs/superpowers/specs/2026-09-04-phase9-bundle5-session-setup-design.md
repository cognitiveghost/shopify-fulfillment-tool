# Phase 9 Bundle 5 — session setup

Covers 9.18 (session setup: three steps in one card) and the
`AddProductDialog` low-stock-threshold quick fix. Artboards W1, W1b, W2.

Worked from the transcription of W1/W1b/W2 in the Todoist briefs and the
roadmap, not from the canvas — the phase parent says so explicitly.
Departures are listed in §10, open questions for the owner in §11.

Prerequisite: Bundle 4, merged 2026-09-04 (`CommandBar` + `BarState`,
`OverflowMenu`, the 1310×692 page). All three are used here.

This bundle is **shopify-only**. `packing-tool` has no allocation strategy
and no two-file setup, and nothing here touches `shared/`. One worktree, one
PR.

---

## 1. The findings that change the shape of the bundle

**Validity is stored in a glyph.** `FileHandler.check_files_ready` decides
whether Run Analysis may be enabled by reading
`self.mw.orders_file_status_label.text() == "✓"` — a check mark rendered into
a `QLabel` is the app's only record that a file passed validation.
`validate_file` writes it, and the missing columns exist only inside that
label's tooltip. 9.18 replaces that label with an inline error card, so the
brief cannot be built without first giving validity somewhere real to live.
This is the largest thing in the bundle and §4 settles it: a `FileSlot`
widget owns path, validity and missing columns, and `check_files_ready`
reads booleans.

**The command bar has no session picker.** `CommandBar.session_label` is a
plain `QLabel`. The brief deletes the recent-sessions strip and says Resume
"moves into the command bar's session picker as its top item" — a picker
that does not exist. Building it extends Bundle 4's four bar states, which
is why it is called out here rather than assumed. §6.

**Three of the four group boxes are already homeless.** Bundle 4 gave New
Session, Open session folder, Client settings and Generate Reports homes in
the command bar and the two overflows, but only *hid* `new_session_btn` and
`run_analysis_button`; the widgets and their group boxes still render.
`mw.settings_button`, `mw.generate_reports_button` and
`mw.open_session_folder_button` are duplicates of controls the shell already
draws. This bundle deletes them, which is most of what "four group boxes
become one card" actually costs.

The rest is smaller than it reads:

- `add_product_button_tab2` already exists in the Results screen overflow
  (Bundle 4 §4.2), so "Add product to order moves to the results pane" is
  already half-shipped. Only the Setup copy is deleted. §10.
- `Card` and `FormSection` exist and are close enough to reuse. §3.
- `analysis_mode_combo`'s two items and their tooltip text are the two
  `RadioCard` titles and descriptions, already written.

---

## 2. Vocabulary

Two terms enter `CONTEXT.md` with this bundle.

**File slot** — the widget that holds one of the two input files. One slot
per file, three states (empty, loaded, invalid), and it is the only thing
that knows whether its file is usable. Not a "file picker": the slot
persists and changes state, the picker is a dialog it opens.

**Strategy** — how the run allocates stock across competing orders.
Two of them, `multi-item-first` and `fifo`. Supersedes the code's current
"analysis mode", which named the combo rather than the thing it chose, and
collided with the Orders/Stock "Load Mode" radios on the same screen.

`Step` is deliberately *not* a term. The card's four rows read as a
sequence, but nothing numbers them, nothing enforces an order, and a term
would invite both.

---

## 3. The page

One `Card`, four rows, no splitter, no scroll area.

```
┌─ page 1310×692 ─────────────────────────────────────────────┐
│ ┌─ Card ─────────────────────────────────────────────────┐  │
│ │ Session name    │ [Tuesday restock________________]    │  │
│ │ Orders file     │ ┌ FileSlot ─────────────────────┐    │  │
│ │                 │ └───────────────────────────────┘    │  │
│ │ Stock file      │ ┌ FileSlot ─────────────────────┐    │  │
│ │                 │ └───────────────────────────────┘    │  │
│ │ Allocation      │ ( ) Multi-item first                 │  │
│ │                 │     …consequence…                    │  │
│ │                 │ ( ) Oldest first                     │  │
│ │                 │     …consequence…                    │  │
│ └────────────────────────────────────────────────────────┘  │
│  ← 208px gutter →                                           │
└─────────────────────────────────────────────────────────────┘
```

The card is top-aligned, left-aligned, and capped at **840px** wide. Rows
are not centred and the card does not stretch to 1310: a 208px label gutter
against a 1100px field turns a four-row form into a horizon.

**Run is not a row.** The brief lists four rows ending in "run", but Bundle
4 made Run Analysis the Setup screen's command-bar primary
(`_SCREEN_ACTIONS[0]`) and hides the page's own copy. Drawing a fourth row
for it would put the same action on screen twice, which is the exact fault
this bundle is deleting three other buttons to fix. The card has **three
content rows**; the fourth step is the primary in the bar above it. §10.

### 3.1 Reusing `Card` and `FormSection`

Both are reused with small additions rather than replaced.

`Card` today is the Statistics tab's stat tile: a `QVBoxLayout` whose only
public API is `add_text`, which centres. It gains one method:

```python
def add_widget(self, widget: QWidget) -> None:      # appends, no centring
```

`FormSection` today is title + optional description + `QFormLayout`. The
brief asks for "a `QHBoxLayout` with a fixed 208px label gutter and a
stretching content widget", which is what a `QFormLayout` already lays out
once its label column is pinned. It gains one keyword argument:

```python
FormSection(title="", label_width=208)
```

`label_width` sets `row_label.setFixedWidth(208)` in `add_row` and
`setFieldGrowthPolicy(ExpandingFieldsGrow)` on the form. An empty `title`
already omits the heading; the setup card passes one `FormSection` with no
title, because the card *is* the section and a second heading over the same
box is chrome for its own sake.

This is ~10 lines across two existing components against ~60 for a new row
widget, and it keeps one row idiom in the app rather than two.

---

## 4. `FileSlot` — where validity lives

`gui/components/file_slot.py`. One widget per input file, replacing the
seven-widget cluster each file currently owns (`*_file_path_label`,
`*_file_status_label`, `*_file_list_widget`, `*_file_count_label`,
`*_options_widget`, `*_single_radio`, `*_folder_radio`).

### 4.1 Interface

```python
class FileSlot(QFrame):
    changed = Signal()                      # any state transition

    def __init__(self, title: str, hint: str, parent=None) -> None: ...

    path: Path | None                       # file or folder
    is_valid: bool                          # False while empty
    missing_columns: list[str]

    def set_loaded(self, path, summary: str) -> None: ...
    def set_invalid(self, path, missing: list[str]) -> None: ...
    def clear(self) -> None: ...
```

Deep by the deletion test: delete it and `check_files_ready`, `validate_file`
and `on_orders_mode_changed`/`on_stock_mode_changed` all have to re-learn
which of seven widgets carries which fact, in two near-identical copies.
Two callers, one per file — a real seam, not a hypothetical one.

### 4.2 The three states

**Empty.** A 2px dashed `border` rectangle, 96px tall, holding the hint and
a `Choose file…` button. Dashed borders are legal QSS. The drop itself is
`dragEnterEvent`/`dropEvent` on the slot, not CSS, and accepts a file *or* a
folder — dropping a folder is how folder mode is now entered (§10).

**Loaded.** Solid 1px `border`, the file name at `body`, and a summary line
at `caption` in `text_secondary`: `1 842 rows · 4 columns matched`, or
`3 files merged · 1 842 rows` for a folder. No check mark. A slot that is
drawn as loaded *is* valid; a tick beside it says the same thing twice.

**Invalid.** Replaces the loaded card **in place**, `status_danger` border
and `status_danger_bg` fill. Not a message box: a dismissed modal leaves no
trace of which file is wrong.

### 4.3 The error, written out

Consequence first, cause in the file's own column names, then two ways out.

> **Nothing can be allocated from this file**
> `stock_2026-09-04.csv` has no column mapped to Stock. Analysis needs one
> to know what is on hand. The file's columns are: `Артикул`, `Име`,
> `Цена`.
>
> [ Map columns… ]  [ Choose a different file ]

`Map columns…` opens the existing client column-mapping page — the fix when
the file is right and the mapping is stale, which is the common case for a
new client. `Choose a different file` re-opens the picker — the fix when the
file is wrong. Naming the columns the file *does* have is what turns the
second choice from a guess into a decision, and `core.validate_csv_headers`
already reads the header row, so the list costs nothing new.

The error names the file, never the user. It does not apologise and it does
not say "invalid" — "invalid" describes the app's opinion, "nothing can be
allocated" describes the warehouse's morning.

### 4.4 What `FileHandler` changes

`validate_file` stops writing `"✓"` / `"✗"` into a label and calls
`slot.set_loaded(...)` or `slot.set_invalid(..., missing_cols)` instead.
`check_files_ready` becomes:

```python
return self.mw.orders_slot.is_valid and self.mw.stock_slot.is_valid
```

`missing_cols` already comes back from `core.validate_csv_headers`; today it
is formatted into a tooltip string and otherwise thrown away.

---

## 5. `RadioCard` — the strategy

`gui/components/radio_card.py`. A `QRadioButton` subclass with a title at
`label` and a wrapped description at `caption` in `text_secondary`, painted
by giving the button a taller `QVBoxLayout` beside its indicator. ~40 lines.
App-local: `packing-tool` has no allocation strategy.

Two of them in a `QButtonGroup`, replacing `analysis_mode_combo`:

> **Multi-item first**
> Fills orders that can go out whole before it fills partial ones. More
> complete orders leave the warehouse; a few old orders wait for stock.
>
> **Oldest first**
> Fills strictly by order date, whatever the order contains. No order waits
> behind a newer one; more orders leave part-filled.

A combo box makes a supervisor read two words and guess. The description is
the whole point of the change: the choice is made once a day by someone who
should not have to ask a colleague what "multi-item-first" means.

`analysis_mode_combo` is kept as a property shim on `MainWindow` returning
the selected strategy string, so `actions_handler`'s existing read site does
not change in this bundle.

---

## 6. The command bar's session picker

`CommandBar.session_label` (`QLabel`) becomes `session_button`, a flat
`QToolButton` with `InstantPopup` and a caret, owning a `QMenu`:

```
  Tuesday restock            ← most recent, the one Resume meant
  Monday late orders
  Friday backlog
  ─────────────────────────
  Browse all sessions…       → Ctrl+3
```

The menu is filled from `session_manager.list_client_sessions(client_id)`,
capped at five, on client change and after a run — the same call
`refresh_recent_sessions` makes today, so the deleted strip's only data
source survives it.

Bundle 4's contract is extended, not broken:

| `BarState` | The button reads | Enabled |
|---|---|---|
| `NO_CLIENT` | hidden | — |
| `NO_SESSION` | `Open recent ▾` | only if the client has sessions |
| `SESSION` | the session id ▾ | yes |
| `RUNNING` | the session id, caret hidden | no |

Bundle 4 §3.3 says the session ID never elides at any width. A `QToolButton`
holds that: `setToolButtonStyle(TextOnly)` and no `setMaximumWidth`.

This is the one place the bundle adds to the shell, and it is why the strip
can be deleted rather than merely moved: Resume is navigation, navigation
belongs in the shell, and 148px of the page's 660 was buying a control that
pointed away from the form it sat on top of.

---

## 7. What is deleted

| Deleted | Because |
|---|---|
| `_create_session_management_section` | New Session is state-owned in the bar (Bundle 4 §3.2) |
| `_create_reports_group` | Generate Reports is the Results primary; Open folder is in the bar |
| `_create_main_actions_group` | Run is the Setup primary; Settings is in the command-bar overflow |
| `_create_session_browser_panel`, `refresh_recent_sessions`, `_on_recent_session_double_clicked`, `_recent_list_height` | the strip |
| `_RECENT_PANEL_MAX_WIDTH`, `_RECENT_SESSIONS_ROWS`, `_SETUP_COLUMN_SLACK` | the splitter and the scroll area they sized |
| `mw.new_session_btn`, `mw.settings_button`, `mw.generate_reports_button`, `mw.open_session_folder_button`, `mw.add_product_button` | duplicates of shell controls |
| the `QSplitter` and `QScrollArea` in `_create_tab1_session_setup` | the card fits; nothing scrolls |
| `_create_orders_file_section`, `_create_stock_file_section`, `on_orders_mode_changed`, `on_stock_mode_changed` | `FileSlot` |
| `_create_client_selector_group` | dead since Bundle 4; the selector is in the bar |

`main_window_pyside.py` loses the `hasattr` guards and `setEnabled` calls
that fed the deleted widgets (lines 231–232, 264–267, 341, 353–362, 643–647,
676–691). Each one is a shell control now and the shell enables it.

`docs/superpowers/specs/2026-08-23-session-setup-layout-design.md` is
superseded: every constraint it solves (the splitter squeeze, the 706px
floor, the scroll area's tiny minimum) belongs to a layout that no longer
exists. A one-line note goes at its head rather than deleting it.

---

## 8. Copy, focus and keyboard

**Row labels:** `Session name`, `Orders file`, `Stock file`, `Allocation`.
Sentence case, no colons, no all-caps. `Allocation`, not "Analysis mode" —
it names what is being decided, not the widget deciding it.

**Session name** is pre-filled with today's date in the client's format and
selected on focus, so the common case is Enter. It is the card's first focus
stop and takes focus when the page becomes current with no session loaded.

**Tab order** is card order: name → orders slot's button → stock slot's
button → the two radios (one stop, arrow keys move between them, which is
what `QButtonGroup` already does) → out to the command bar's primary.

Each slot's `Choose file…` is its default focus target, so a keyboard user
never has to reach the drop rectangle — drop is an accelerator, never the
only route.

**Empty state:** the page's own empty states are unchanged from Bundle 4 —
`StatePanel` on `setup_stack` page 0 for no-connection and no-client. The
card is page 1 and is only reached once a client is chosen, so it has no
empty state of its own.

**Degradation.** At 1366×768 the card is 840 wide against a 1310 page and
never needs to shrink. Below 1024 the label gutter drops from 208 to 96;
below 840 the gutter goes to zero and labels sit above their fields. No
scroll area returns: three rows do not need one.

---

## 9. The quick fix — `AddProductDialog`'s threshold

`gui/add_product_dialog.py:226` reads `elif current_stock < 5:`. The
client's configured `low_stock_threshold` is ignored, so the warning is
wrong for every client that changed it. The setting already exists, is
edited on Settings › General, and is already read correctly by
`shopify_tool/core.py:823`.

Root cause: the dialog has no way to know the value — its constructor takes
`analysis_df`, `stock_df`, `live_stock` and nothing else. One caller,
`ActionsHandler.show_add_product_dialog`, which already loads the client
config elsewhere in the same file.

Fix: `AddProductDialog.__init__` takes `low_stock_threshold: int = 5`, line
226 reads it, and the caller passes
`config.get("settings", {}).get("low_stock_threshold", 5)`. The default
keeps the two existing test call sites compiling and keeps the old behaviour
for a client whose config predates the setting.

`0` stays its own branch: zero stock and low stock are different sentences,
and a client who sets the threshold to 0 should still see the zero warning.

---

## 10. Departures from the brief

1. **The card has three rows, not four.** "Run" is the command-bar primary
   Bundle 4 already made it. §3.
2. **Add product to order is deleted here, not moved.** The brief sends it
   to the results detail pane; that pane is 9.14, in Bundle 13. Bundle 4
   already put `add_product_button_tab2` in the Results screen overflow, so
   the action has a home today and 9.14 moves it the last step later.
3. **Folder mode survives, inside the slot.** The brief lists three file
   states and never mentions folder loading, but multi-file merge, recursive
   scan and de-duplication are shipped behaviour with real users. Dropping a
   folder, or picking one from the slot's button menu, puts the slot in
   folder mode; `Include subfolders` and `Remove duplicates` appear inside
   the loaded slot. Deleting the feature is not in scope for a layout task.
4. **The strategy descriptions do not carry live numbers.** The brief asks
   each option to state its consequence "on this run" (`268 complete, 31
   short`). Those numbers do not exist before the run: producing them means
   allocating twice, on the slowest operation in the app, for a screen the
   user is about to leave. The descriptions state the consequence in kind
   instead. §11 Q2.
5. **`Card` and `FormSection` are extended, not replaced.** The brief names
   a `QHBoxLayout` row; a pinned `QFormLayout` label column is the same
   layout with an idiom the app already has. §3.1.

---

## 11. Open questions for the owner

Neither blocks Stage B — the plan builds the recommended answer, and either
is a small edit to the plan if the answer differs.

**Q1 — the session picker.** Bundle 4 froze four bar states. Adding a
session menu to the bar extends them. Build it here (recommended), or leave
Setup without a Resume route until Bundle 6's session browser lands?

➡️ Build it here, as §6. Deleting the strip without it makes Ctrl+3 the only
way back to yesterday's work, and the strip is being deleted for *where* it
sat, not for what it did.

**Q2 — live numbers on the strategy options.** Recommended answer is the
static consequence text in §5, because the numbers require two allocations.
The alternative worth having is showing them *after* a run, on the results
screen, as "FIFO would have completed 240" — a comparison that is useful
once and cheap only there.

➡️ Static text now; revisit as a Bundle 12 item if it is still wanted.

---

## 12. Where the tests go

Three seams, and each is a seam because it is where a fact stops being a
widget.

| Seam | Test |
|---|---|
| `FileSlot.is_valid` | `tests/test_file_slot.py` — the three transitions, and that `is_valid` is False in empty and invalid |
| `FileHandler.check_files_ready` | extend `tests/test_file_handler.py` — reads slots, never label text; a missing quantity column leaves Run disabled |
| Card fits above 480px at 1366×768 | rewrite `tests/test_session_setup_layout.py` around the card, deleting the splitter and recent-panel cases |
| `CommandBar` session button | extend `tests/test_commandbar_states.py` — label per state, no elision, disabled in `RUNNING` |
| Threshold | extend `tests/test_add_product_dialog.py` — a client threshold of 12 warns at 11 and not at 12 |

The bundle's two `Done when` clauses are both mechanical:

- **fits above 480px at 1366×768 with no scrolling** — assert the card's
  `sizeHint().height() <= 480` and that no `QScrollArea` exists under the
  Setup page.
- **a stock file missing its quantity column renders the inline error with
  both recovery actions** — a fixture CSV, then assert the slot is in the
  invalid state and both buttons exist and are enabled.
