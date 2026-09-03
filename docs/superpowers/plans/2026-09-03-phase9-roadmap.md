# Phase 9 roadmap — Fulfilment System v2

Spec: `docs/superpowers/specs/2026-09-03-phase9-fulfilment-v2-design.md`
Decision record: `docs/adr/0001-analysis-results-on-the-web-tier.md`
Mockups: Claude Design project `75385f2c-4be2-446c-8e9d-bf90ee063ff7`

Mirrored into Todoist section **Roadmap — Shopify Tool** (`6h8v45ffWwh5W5q3`),
one subtask per item below. The Todoist body is the brief a run works from;
this file is the sequencing.

---

## How to read an item

Each item is **one task, one worktree, one PR**. Track Q items are independent
of each other beyond the stated order. Track V is serial. Track W cannot begin
until 9.12 merges.

**Artboard** names the drawing. **Done when** is the completion criterion — it
is checkable, and a run is not finished until it holds.

Every item inherits the workflow in the Todoist READ FIRST guide
(`6h8v49hR5844MWxV`): tests + `ruff` before merge, `graphify update .` after,
comment the PR link on the subtask, branch and PR always. That is not repeated
per item.

---

## Track Q — Qt. Starts immediately, gated on nothing.

### 9.0 — One asset library, shared by both apps
**Artboard:** none (enabling work)
`gui/icons.py`, `gui/fonts.py` and `gui/assets/` exist twice — here and in
`packing-tool` — byte-identical apart from `message-square.svg`. Move all three
into `shared/`, where `scripts/sync_shared.py` already carries cross-repo code.
Add the glyphs v2 needs and the repo lacks: `plus`, `ellipsis-vertical`, and
the QSS sub-control set reached through `image:` — checkbox tick, radio dot,
`::up-arrow`/`::down-arrow`, and the toggle's two states.
Made in `packing-tool` first, then synced. `tests/test_icon_usage_guard.py` and
`tests/test_ui_assets.py` move with the code.
**Done when:** both repos import icons and fonts from `shared/`, no
`gui/assets/` remains in either, both guard tests pass in both repos, and a
frozen build still renders a themed icon.

### 9.1 — The token retune
**Artboard:** F0, F0b
16 light values and 6 dark, exactly as tabled in F0. Planes go
218/230/242/255. `hover` is set equal to `surface_overlay` in both themes.
`selection_border` and `focus_ring` fold onto `status_info`. Aliases follow
their canonical token automatically — `accent_green`/`accent_orange`/
`accent_red` move with `status_success`/`status_warning`/`status_danger`.
Made in `packing-tool`'s `shared/theme.py`, then synced.
Delete the `LIGHT_THEME` comment reading "retune border and status_warning
together or not at all" — this is that retune.
**Done when:** `tests/test_theme_contrast.py` fixtures carry the new values and
pass, `validate_theme` passes in both themes, and no foreground sits within
0.1 of its floor.

### 9.2 — Borders stop being furniture
**Artboard:** F1
Subtraction, not addition. `Card` drops `setFrameShape(QFrame.StyledPanel)` +
`Raised` — which draws an OS frame under the stylesheet — for
`QFrame.NoFrame` plus one type-scoped rule. The same removal in
`build_stylesheet` for `QTableView`, `QListWidget`, `QGroupBox`, `QToolBar` and
`QHeaderView::section`: five rules that each say `border: 1px solid border`
today. Borders stay on `QLineEdit`/`QComboBox`/`QSpinBox`, on `QPushButton`,
and on `:focus`. `QGroupBox`'s radius is `r + 4` today; both it and `Card`
become `radius_md`, and `radius_lg` is dialogs only.
**Done when:** a rendered screenshot of a card-on-panel-on-page composition
shows regions separated by plane with no outline between them, and the only
borders in it are on an input and the focused control.

### 9.3 — One status component, three channels
**Artboard:** F5
`StatusChip.set_status(role, text, theme)` gains `live: bool` (tint or none)
and `manual: bool` (solid mark or hollow). `StatusDot` survives as the chip's
mark, not as a standalone form. `SessionStatusDelegate.form()` stops returning
`"dot"` vs `"chip"` and returns the two flags.
This supersedes the "tint carries authorship" rule: colour is role, fill is
live-vs-resting, mark is person-vs-system.
**Done when:** all 13 states (6 Shopify, 7 Packing) render from one component,
in both themes, and a test asserts the four combinations of `live` × `manual`
produce four distinguishable renderings.

### 9.4 — Selection becomes a closed ring
**Artboard:** F4 (CONTRACT CHALLENGE accepted)
`QTableView::item` styles cells, so a QSS ring repeats at every column
boundary — the left and right edges cannot exist. Add a delegate that knows the
row's first and last visible column and paints one `QRect` across them, either
as `SelectionRingDelegate` or by extending `StatusEdgeDelegate`, which already
computes `header.visualIndex(column) == 0`.
Zebra striping stays off. The sort caret appears on the sorted column and on
hover only — never a grey caret on every header.
**Done when:** a row that is both selected and blocked renders a closed
selection rectangle with the status edge inset inside it, in both themes.

### 9.5 — The control inventory's four gaps
**Artboard:** F3, F2
The toggle switch is the only new control: a `QCheckBox` with a 36×20
`::indicator` and two bundled SVGs. No sliding thumb — QSS has no transitions
and the travel does not earn one.
Then three corrections: `build_stylesheet` hardcodes `font-size: 10pt` on
`QPushButton`, which must become `font_css("body")` so a floor-density button
grows with its rung; the focus ring on a primary button is invisible against an
accent fill, so primary alone focuses with `2px solid border_strong`; and the
spin box renders at 35px, not 32, because Qt adds room for its buttons after
`min-height` applies — specify it as it renders.
**Done when:** every control in F3 renders in all five states in both themes,
and the button font size follows the active density profile.

### 9.6 — One empty state, not forty
**Artboard:** F7
`StatePanel` with four constructors — nothing-loaded, working, no-results,
failed — swapped into the `QStackedWidget` page that would otherwise hold the
table. It composes `Card`'s plane, `FormSection`'s heading rung and the shipped
button roles; it is not a new visual language.
Every state names its cause, names the file or filter that caused it, and
offers the action that resolves it. Exactly one accent-filled action each.
**Done when:** `StatePanel` exists with all four variants tested, and no screen
in the app renders a bare "No data" message.

### 9.7 — Shell anatomy and the command bar's four states
**Artboard:** S1, S2
Rail 56, command bar 48, page padding 16, status bar 28 — the measurements
every later screen assumes. Rail items are `QToolButton`s in an exclusive group:
rest on the sunken plane, hover one plane up, current two planes up plus a 3px
`accent_fill` left edge. Labels are one word each.
The command bar becomes one `set_state(enum)` call across four states: no
client, client without session, session active, analysis running. Exactly one
primary exists at a time and it moves — "New Session" beside the selector
before a session exists, "Run Analysis" on the right once one does, nothing
while the machine holds the turn.
Degradation order at 1366 is fixed: spacer, then client name elides inside its
200px, then progress drops the phase name, then New Session goes icon-only. The
session ID, the status chip, the primary label and the overflow button never
truncate.
**Done when:** all four states render at exactly 1310px page width with the
worst realistic content and nothing in the never-truncate list is elided.

### 9.8 — Five homeless controls get one home
**Artboard:** S3
`OverflowMenu(QMenu)` owned by `CommandBar`, opened by a `QToolButton` with
`InstantPopup`. Two sections: the client's own name, then THIS PC. "New
session" and "Open session folder" move into the command bar; client settings,
server connection and the light/dark switch move into the menu. Theme is two
exclusive checkable `QAction`s in a `QActionGroup`, stored in `QSettings`
per machine — two desks on one client must be allowed to disagree about the
light.
`NavRail` loses its footer slot: delete the widget rather than hiding it, so
nothing can be added back to it by accident. This overrides the shell
anatomy's "footer item for Server Connection" — the rail is for destinations,
and a dialog is not one.
**Done when:** the rail has exactly five items and no footer, the overflow
menu opens with both sections, and switching theme from it repaints without
artifacts.

### 9.9 — First run
**Artboard:** S4
The shell with nothing configured. Rail items other than Setup and Logs are
`setEnabled(False)` — disabled, never hidden, so the app's shape is learnable.
One `StatePanel` card in the Setup stack's page 0, and "Server Connection…" is
the only accent-filled pixel in the window.
That action deliberately appears twice — here and in the overflow menu — because
an empty state that explains a problem without offering the fix is a dead end.
After first run the empty state is gone and the menu is its only home.
**Done when:** a launch with an unreachable share renders this screen, and one
`connection_state` signal drives every disabled control on it.

### 9.18 — Session setup: three steps in one card
**Artboard:** W1, W1b, W2
Four group boxes become one `Card` of four `FormSection` rows: name the
session, load the two files, choose the allocation strategy, run. The client
combo is gone (it is in the command bar) and so is "Add product to order" — it
moves to the results pane, where an order exists to add it to.
The strategy pair becomes `RadioCard`, a `QRadioButton` subclass with a title
and a wrapped description: a supervisor picks correctly without asking what
"multi-item-first" means. Each option states its consequence on this run.
File states are drop, loaded, and validation error. The error replaces the
loaded card **in place** — not a message box, because a dismissed modal leaves
no trace of which file is wrong.
The recent-sessions strip is deleted. Resume moves into the command bar's
session picker as its top item.
**Done when:** all three steps and the Run button fit above 480px at 1366×768
with no scrolling, and a stock file missing its quantity column renders the
inline error with both recovery actions.

### 9.19 — The session row learns to be scanned
**Artboard:** D1, D2
**Gated by:** `session_info.json` needs a `blocked_orders` key.
`actions_handler` computes `fulfillable_orders` at analysis time and throws the
complement away. Add it first, in this task, before the column that reads it.
Also settle the naming: Analysis Results calls it SHORT ON STOCK and the
browser calls it BLK. One number, two names — pick one in
`session_lifecycle.py`.
`STATUS_ROLES` knows four states; it needs seven plus archived. The two hard
pairs get a second channel: a half-filled disc for work in flight against a
check for work finished, and Incomplete stays full-strength amber with a solid
mark while Abandoned drops its body text to `text_secondary`. Glyphs are
painted paths in the delegate, never characters — nothing may depend on a font
shipping `◐`.
Comments render only when one exists; the message-square icon on the name cell
goes, column 7 shows the text, and writing still goes through the existing
`Comment…` button on the selection bar.
Three new columns: AGE (relative, absolute in the tooltip, and the archive
countdown past 23 days) and BLK (warning tint, blank at zero). **Proposal 3,
"last touched", is dropped** — it is the only cross-repo cost in the set.
The page gains two groups (`NEEDS ATTENTION` above `EVERYTHING ELSE`), which
means `QTableWidget` becomes `QTreeWidget`, plus the two empty states from 9.6.
No CLIENT column — the browser lists one client and the title row already
names it.
**Done when:** 40 rows can be scanned by glyph column alone, both empty states
render, and the BLK column reads from a real `blocked_orders` value.

### 9.20 — Statistics is deleted; Info becomes Logs
**Artboard:** D3
Delete `_create_statistics_subtab` in `gui/ui_manager.py` and the page it
builds. `gui/components/statcard.py` **stays** — the Analysis Results KPI strip
becomes its only caller, and always was the better one.
`shared/stats_manager.py` and `global_stats.json` stay untouched and
write-only: `record_analysis` keeps writing, nothing in the GUI reads back. The
file becomes what it already effectively was, an append-only log for whoever
pulls the monthly numbers.
Rename the destination `Info` → `Logs`. With one page left, the honest label is
the page.
**Done when:** the rail reads Logs, no statistics page is reachable, and
`global_stats.json` still gains a record when an analysis runs.

### 9.21 — Two log views become one viewer
**Artboard:** D4
`activity_log_table` (a `QTableWidget`) and `execution_log_edit` (a
`QPlainTextEdit`) become one `QTreeView` over a ring-buffer model with two
sources behind a switch — they differ by one column, not by design. The dead
CustomTkinter `gui/log_viewer.py` is deleted with them.
Level filter, text search, and follow-tail that stops the moment the user
scrolls up and shows a count of what arrived since, in a layout row at the foot
of the list rather than an overlay.
Wrapping off by default with right elision; Wrap on lets the row grow and keeps
the message column's indent. Alternating row colours are dropped — level colour
and the danger tint already carry the row. Error rows take `status_danger_bg`
plus a 3px edge through `Qt.BackgroundRole`, because QSS cannot vary a row
background by content.
No primary button: a log viewer has no committing action.
**Done when:** both sources render in one widget, a 300-character traceback
survives both wrap modes, and follow resumes correctly after a scroll-up.

### 9.22 — Tools loses its inner tabs
**Artboard:** D5, D5b, D5c
`ToolsWidget` drops its `QTabWidget` — a tab inside a tab is one nesting level
too many. Reference Labels and Barcode Labels sit side by side as two `Card`s,
each reading top to bottom: inputs, folded options, one action. Both widgets
keep their logic and lose their own group boxes.
Print options fold away behind a `QToolButton`, and the folded row shows its
own current values so nobody opens it to check which printer is selected. Print
mode is the only control always inside the fold: choosing Raw ZPL reveals
target, label size and rotation and **hides** the driver printer row — today all
five are permanently visible and four are greyed out, which is the same
information drawn as clutter. `_update_zpl_controls_enabled` becomes
`…_visible`.
Below 1180px of page width the two cards stack in a vertical scroll area by
flipping the layout direction on `resizeEvent`. Never a `QStackedLayout` —
that forks the widgets.
**Done when:** both cards fit side by side at 1366×768 with no horizontal
scroll, Raw ZPL hides the driver row, and the stacked layout appears below
1180px.

### 9.23 — Settings saves once, or not at all
**Artboard:** G1
`SetsPage` and `_ColumnConfigPage` write the moment you click inside them —
Sets through its own writes, Column Config through `table_config_manager` — so
Cancel does not cancel them. Both must buffer and return from `collect()` like
every other page. This is a correctness fault, not a layout one.
`SettingsPage` gains `is_dirty()`, feeding the nav dot, the footer count and
the close guard in `reject()`, which today only blocks while a save is in
flight. The close guard is inline, not a message box.
The nav remembers its page by name, not by row index. Add a search box over
nine pages, two of them 40 KB+, filtering by page name plus a static keyword
table.
Saving success stops being `QMessageBox.information("Settings saved
successfully!")` and becomes a toast (9.25); the dialog closes on success as it
already does.
**Done when:** changing Sets or Column Config and pressing Cancel leaves the
profile on disk unchanged, and the footer counts dirty pages accurately.

### 9.24 — Reports becomes a list and one editor
**Artboard:** G2
Six reports today means six expanded editors and six "Add New" affordances in
one scroller. The `QScrollArea` of stacked `ReportEditor` widgets becomes a
`QListWidget` plus one live editor — same editor class, one instance at a time.
The list is also where generate order is set, and it is the same order
`GenerateReportsDialog` renders.
The filter editor shows a live match count (`_apply_filters(df, filters)` with
the existing fingerprint cache), so a filter that matches nothing is caught
while it is being written rather than at generate time.
A saved field the dropdown no longer offers is still shown and still written
back — never silently repointed at the first column.
**Done when:** the page holds one editor at a time, the match count updates as
a filter is edited, and a legacy field value survives a save round-trip.

### 9.25 — 249 message boxes sort into four destinations
**Artboard:** G3
Counted across `gui/`: `QMessageBox.information/warning/critical/question`,
`QInputDialog`, `QFileDialog`. `QFileDialog` stays native and is out of scope.
- **Toast** (~92): it worked, nothing to decide. `Toast(QFrame)` parented to the
  main window, bottom-right, 4s, optional Undo. Never blocks.
- **Inline** (~74): the problem has a location on screen, so the message goes
  there and the typed input survives. A no-selection warning becomes a disabled
  action instead.
- **Confirm** (~26): `ConfirmDialog(QDialog)` — only where the act destroys data
  Undo cannot reach. States the count, names the thing, and its primary button
  is the verb.
- **Error banner** (~43): persists until dismissed, says what to do rather than
  what the exception was, and links to Logs where the traceback already is.
One toast at a time; newest replaces oldest; a count badge at three or more
inside the window. `apply_dialog_button_roles` stays the mechanism for roles.
**Done when:** `Toast` and `ConfirmDialog` exist and are tested, and the
success and validation `QMessageBox` call sites are converted.

---

## Track V — the platform under TIER WEB. Strictly serial.

### 9.10 — BUILD GATE: prove Chromium survives the frozen build
**Artboard:** none. **This gates Track W entirely.**
Add `PySide6-QtWebEngine` and make the existing `--onedir` PyInstaller spec
collect `QTWebEngineProcess.exe` and its resources. This repo was already
forced off `--onefile` once for WeasyPrint's GTK DLLs; Chromium is the harder
case.
Nothing else. No document, no styling, no bridge — a window with a
`QWebEngineView` showing a themed page.
**Done when:** a build produced by the existing CI spec launches that window on
Windows, over RDP, at 1366×768, and the app's startup time is measured before
and after so the cost is on record.
**If it fails:** stop and report. Track W does not start, and the Qt fallback
becomes a live question for the user rather than an assumption.

### 9.11 — One palette, two renderers
**Artboard:** F6
`theme_css_vars(theme)` beside `build_stylesheet(theme)` in `shared/theme.py`.
Dataclass field names with underscores turned into hyphens, mechanically, so a
new token needs no second registration site. Unitless ints become px; point
sizes stay pt. Type and density are resolved for the active density before
injection.
The ten frozen aliases are **not** exported — a web asset has no ~180 legacy
call sites to protect, so `--accent-green` would be new debt. The generator
asserts it emitted every name in `_COLOR_FIELDS` minus `_ALIAS_PAIRS`.
Then extend `shared/style_lint.py` to scan `.css` and `.html`: no hex in a web
asset, and none of the banned properties (`box-shadow`, gradients,
transitions, transforms, container opacity, px font sizes).
Finally the font seam: `templates/assets/fonts/` ships JetBrains Mono while Qt
uses Consolas. Pick Consolas.
**Done when:** the generator round-trips both themes, the linter fails on a
planted hex and on a planted `box-shadow`, and one mono face is used on both
sides.

### 9.12 — The bridge
**Artboard:** none (the mockups' largest omission)
Analysis Results is not a report. Selection, sort, filter, the column manager,
per-order actions, bulk actions and Undo all cross the Qt↔JS boundary, so the
tier needs a real protocol before it needs a document.
`QWebChannel`, one object, a named method per message — never a string-passing
hatch.
- **Out:** the order-level frame as JSON (312 orders, SKU lines nested), and
  the theme's CSS custom properties from 9.11.
- **In:** selection changes, sort and filter state, per-order and bulk action
  invocations, column config writes.
**Done when:** a round-trip test drives a selection change from JS into Python
and an order payload from Python into JS, and a theme switch repaints the web
document without a reload.

---

## Track W — Analysis Results on the web tier. Blocked until 9.12 merges.

### 9.13 — The results document
**Artboard:** W3, W3b
`QWebEngineView` filling the page area. Inside: the five-card KPI strip in
`display_xl` numerals, the filter bar with removable chips and a live count,
and the order table — one row per order, 312 rows, virtualised.
The Qt-side `pandas_model` serves an order-level frame with SKU lines nested.
**23 columns become 9**: select, STATUS, ORDER, CUSTOMER, LINES, UNITS, VALUE,
COURIER, AGE. Everything dropped is recorded in W3's table with where it went —
six per-line columns move into the pane, three identifiers collapse to one,
four money columns to one, and the booleans become filter chips.
One primary: Export. Re-run is secondary in the command bar.
The seam: the document paints `surface` to its own edges, with no border, inset
or different white against the Qt chrome above and below it.
**Done when:** the screen renders 312 orders at 1366×768 with 17 visible rows,
no horizontal scroll, and a screenshot in which the seam cannot be located.

### 9.14 — The order detail pane
**Artboard:** W4
400px wide, 508 tall at 1366, in the same document as 9.13 — the pane is web
not because Qt could not draw it (it could) but because a `QSplitter` handle
between table and pane is exactly the visible seam the design forbids.
Reading order is fixed across every state: identity (order in mono, customer,
city, courier, age) → the verdict as one bold sentence a human would say aloud
→ the numbers behind it → the SKU lines with short ones edged → tags and notes
→ at most two actions plus an overflow, bottom-left. The pane never reorders
itself; only the verdict block and the action labels change.
The verdict is generated from the allocation result, not from a status enum —
one template per reason code with the numbers substituted, so it can name the
SKU and the quantity.
No primary in the pane. The screen's one primary is Export; 44 blue buttons is
not a hierarchy.
**Done when:** all four states render at full size in both themes, including
nothing-selected, and the verdict names a real SKU and quantity.

### 9.15 — Responsive behaviour, with the numbers stated
**Artboard:** W5, W5b
Columns never reflow. Only CUSTOMER stretches; every other column is sized to
its widest real value. ADDRESS appears at ≥1600px and is the first thing
dropped. Table minimum 780, pane 400 default / 360 min / 480 max, closing it
leaves a 36px reopen strip and CUSTOMER absorbs the 400 — no column is added or
removed by closing, so nothing moves under the cursor when it comes back.
Vertically, chrome and the KPI strip and filter bar are all fixed, so every
extra pixel of window height becomes rows at 28px, no partial rows drawn.
**Done when:** 17 rows at 1366 and 28 at 1920, ADDRESS appears at 1600, and the
table only scrolls horizontally below 868px of window width — a state
unreachable at 1366.

### 9.16 — The column manager, rebuilt
**Artboard:** W6
Today it is a list that collapses to roughly 70px and starves its own scroll
area. It becomes a 400px side panel in the detail pane's slot — the pane
returns on close — because column order is only judgeable against the live
table, and both a modal and a popover cover the thing being edited.
Search, five groups with sticky headers, drag to reorder, per-column show/hide,
a live "9 shown · 14 hidden" in the header, reset in the footer. STATUS and
ORDER are pinned and not hideable: a table with no status and no identifier is
not a table anyone can act on.
**Done when:** the panel opens over a populated table without resizing it, all
23 columns are reachable through the scroller, and reorder survives a restart.

### 9.17 — Selection, bulk actions, and the toast that must live inside
**Artboard:** W7, G4
`ContextualSelectionBar` mounts with the selection, 44px, taking those pixels
from the table rather than floating over rows. Eleven equally loud buttons
become four and a menu. Its label counts both units — "3 orders · 11 items" —
because those answer two different questions on the floor.
"Mark Blocked" is deleted outright: blocked is something the run detects, not
something a person declares. The human equivalent is Hold, on one order, in the
pane. "Exclude from run" keeps its own slot as a danger outline with a
separator, so the destructive action is never adjacent to a harmless one.
Then G4: five blocking surfaces become one `BulkActionPopover`. Every
`QInputDialog` chain in `actions_handler.py` goes, along with the "Please
select orders first" guards — the actions are simply disabled without a
selection, which `_update_selection_bar_state` already computes. The confirm
step goes because the button states the consequence and Undo is real:
`undo_manager.py` already records these operations.
Destructive bulk actions keep the 9.25 confirm on top of the popover.
The toast: a Qt child window always paints above a `QWebEngineView`, so this
page emits its own toast into the web document using the same tokens. Two
implementations, one appearance — the linter enforces it.
**Done when:** adding a tag to 34 orders is one popover and one toast with a
working Undo, and no `QInputDialog` remains in `actions_handler.py`.

---

## Quick fixes — not phase work, no spec, any time

- **`AddProductDialog` hard-codes its low-stock threshold at 5** instead of
  reading `low_stock_threshold`. A bug with no design question attached.
- **Theme-switch repaint artifacts.** Widgets cache their appearance: item
  delegates hold stale brushes and `QIcon`/`QPixmap` snapshots taken at build
  time never re-render. Fix is `style().unpolish()` + `polish()` +
  `viewport().update()` off the existing `theme_changed` signal, plus
  re-creating icon snapshots — `_refresh_icons()` already does this for the
  rail, so the pattern exists and is simply not applied everywhere.

---

## Open, and who decides

Carried from the spec's section 8. None blocks Track Q.

1. **Sets imports CSV straight to disk.** Buffering it into the dialog's single
   write means holding an imported set list in memory until Save. Confirm that
   is acceptable for the largest client profile before 9.23.
2. **Logs keeps Activity as a source.** If the activity log is only ever a
   filtered view of the execution log, the switch can go. Needs one look at
   real data.
