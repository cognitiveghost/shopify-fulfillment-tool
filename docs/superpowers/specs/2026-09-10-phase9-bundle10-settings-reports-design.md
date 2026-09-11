# Phase 9 Bundle 10 — Settings saves once, Reports becomes a list and one editor

**Covers:** 9.23 (G1) and 9.24 (G2). Todoist bundle `6hQXj6xPqRJVm2GV`.
**Roadmap:** `docs/superpowers/plans/2026-09-03-phase9-roadmap.md` § 9.23, § 9.24.
**Depends on:** Bundle 9 (PR #321), which shipped `toast`, `show_error`,
`InlineMessage`, `ConfirmDialog` and the message-route guard.

**Mockups:** G1 and G2 in the Claude Design project could not be opened from
this machine (DesignSync needs a login). This spec works from the roadmap
sections and the Todoist briefs, which quote the artboards' copy and numbers.
Every departure from what those quote is listed in §9.

---

## 1. What the code actually does (verified 2026-09-10)

Two premises in the brief are wrong, and the design follows the code:

- **Sets never writes to disk.** `SetsPage` mutates
  `config_data["set_decoders"]`, and `config_data` is `SettingsWindow`'s deep
  copy of the profile. Cancel already discards set edits and CSV imports. The
  brief's open question (can an imported set list be held in memory until
  Save?) is settled: it already is, for every profile size. What is actually
  wrong is that `SetsPage.collect()` returns `{}`, so nothing can tell whether
  the page changed. Its eleven message boxes are also still allow-listed to
  this bundle.
- **Column Config writes only from its own buttons.** Apply, Save View As and
  Delete View write `client_config.json` (a different file from the profile)
  immediately. Switching views mutates `TableConfigManager`'s live state, and
  Settings' Cancel never calls `revert_config()`. Results' "Configure Columns"
  opens the same panel standalone, and Bundle 13 (9.16) replaces the panel
  wholesale.
- **The nav already remembers its page by name** (`NAV_SETTINGS_KEY`). Nothing
  to do.

## 2. Decisions the user made (2026-09-10)

1. **Column Config leaves Settings.** The page, its nav row and its adapter
   are deleted. Results' "Configure Columns" is the one entry point until 9.16
   replaces it. Cancel becomes honest by deletion rather than by buffering a
   panel that 9.16 throws away.
2. **The footer counts pages, not changes.** "Unsaved changes on Sets and
   Reports" names up to two pages; three or more reads "Unsaved changes on 3
   pages". A reordered list is not N changes, so counting individual changes
   would be a number nobody can check.

## 3. The single-write model

Every page holds its edits and returns them from `collect()`. One Save is one
profile write; Cancel writes nothing. After this bundle, no page in Settings
writes anything to disk by itself.

### 3.1 The page contract gains a snapshot

`SettingsPage` (in `gui/settings/base.py`) gains three methods, with defaults
that work for every page:

| Method | Default |
|---|---|
| `snapshot() -> str` | `json.dumps(self.collect(), sort_keys=True, default=str)` |
| `mark_clean() -> None` | Stores the current snapshot as the page's clean baseline |
| `is_dirty() -> bool` | False before `mark_clean()`; otherwise, whether the current snapshot differs from the baseline |

If `snapshot()` raises (a half-typed value `collect()` can't parse), it counts
as the string `"<uncollectable>"`, so the page reads as unsaved rather than
crashing the check.

**Why a snapshot and not a `changed` signal per widget:** nine pages, some
40 KB+, build widgets dynamically (filter rows, rule steps, table cells). A
signal would need wiring in every one of them, and one missed widget would
silently under-report. Comparing `collect()` output uses the one function
that already defines what the page saves. Checked: no `collect()` in
`gui/settings/` logs, emits or opens a dialog, so calling it repeatedly is
safe.

**The one override.** `OrdersMappingPage` and `StockMappingPage` both return
the same live `column_mappings` dict, so comparing `collect()` would mark both
pages unsaved when either changes. `_MappingPageBase.snapshot()` compares only
`mapping_widget.get_mappings()`. `OrdersMappingPage` adds its courier rows,
built by a new `_courier_rows()` that `collect()` also uses.

**Sets** returns `{"set_decoders": self.set_decoders}` from `collect()`: the
same live dict, now declared.

### 3.2 How the window tracks unsaved pages

- After building the nav, the window calls `mark_clean()` on every page.
- A 400 ms `QTimer` re-checks **the page currently shown**. Only the visible
  page can change, and its snapshot is one `collect()` plus one `json.dumps`.
  This is marked `ponytail:`: the ceiling is a page whose snapshot costs tens
  of milliseconds, and the upgrade path is a per-page `edited` signal. The
  timer stops in `done()`.
- `refresh_dirty() -> list[str]` re-checks every page and returns the unsaved
  page names in nav order. The close guard calls it; so do tests.
- **Save always writes**, even when nothing reads as unsaved. The unsaved
  state drives the nav marks, the footer and the close guard, never whether
  Save does anything. A snapshot that misses a field then costs a warning, not
  a lost edit.

### 3.3 What the operator sees

**Nav mark.** An unsaved page's nav row carries an 8 px painted dot in
`accent_fill` (the colour of the Save button it is waiting for) as its item
icon. Clean rows carry a transparent icon of the same size, so text never
shifts. The dot is rebuilt through `on_theme_changed` (ADR 0003). The row's
accessible text becomes "Sets, unsaved changes", and its tooltip "Unsaved
changes". The row's *text* stays the bare page name, which nav restore and
tests match on.

**Footer.** A `QLabel` left of Save/Cancel, in `text_secondary`, empty when
nothing is unsaved. The copy comes from one pure function:

| Unsaved pages | Text |
|---|---|
| none | `""` |
| Sets | `Unsaved changes on Sets` |
| Sets, Reports | `Unsaved changes on Sets and Reports` |
| 3 or more | `Unsaved changes on 3 pages` |

**Close guard.** Cancel, Esc or the title-bar close, while
`refresh_dirty()` is non-empty, does not close. Instead the footer row is
replaced in place by:

> Unsaved changes on Sets and Reports. Closing now discards them.
> `Keep editing` (ghost) · `Discard` (danger) · `Save & close` (primary)

- **Save & close** gets focus, so Enter is the safe choice.
- **Esc** or **Keep editing** restores the normal footer.
- **Discard** closes without writing.
- **Save & close** runs the normal save; on failure the dialog stays open with
  the error banner.

It is inline, not a message box: the pages it names are on screen beside it.
While a save is in flight, `reject()` is ignored, as it is today.

**Search.** A `QLineEdit` ("Search settings", clear button, 170 px) above the
nav, focused by Ctrl+F. It filters nav rows by case-insensitive substring
against the page name and a static keyword table (§3.5). A group header hides
when none of its rows match. When nothing matches, a caption line "No page
matches" shows under the box. Enter selects the first visible page. The page
currently shown stays shown while filtered out.

**Empty groups are unreachable by construction.** `_build_settings_nav`
raises `ValueError` when a nav name has no registered page, a registered page
is missing from the nav, a group is empty, or the keyword table's names don't
equal the nav's. A typo fails the first test run instead of hiding a page.

### 3.4 Save feedback routes (9.25)

| Moment | Today | After |
|---|---|---|
| A page fails `validate()` | Warning box listing errors | The nav selects the first failing page, in nav order, and an `InlineMessage` above the page stack lists that page's errors. It clears on nav change and on the next Save. |
| `collect()` raises | Critical box with traceback | `logger.exception`, then `show_error(self, "Settings weren't saved", "A value couldn't be read. Details are in Logs.")` |
| Server write returns False | Critical box with byte count and set count | `show_error(self, "Settings weren't saved", "The profile may be open on another PC, or the server can't be reached. Wait a few seconds, then press Save again.")` |
| Worker raises | Critical box | Logged (as today), then `show_error(self, "Settings weren't saved", "Details are in Logs.")` |
| Success | Info box, then close | `toast(self.parentWidget() or self, "Settings saved")`, then `accept()` |
| `open_settings_window` after accept | Info box "Settings Updated…" | Nothing; the window's toast already said it |
| `open_settings_window` reload fails | Warning box | `show_error(self.mw, "Settings were saved but didn't reload", "Restart the app to use them. Details are in Logs.")` |

The route guard's `OWNED` entries for `gui/settings/window.py`,
`gui/settings/sets.py` and `actions_handler.open_settings_window` are deleted.
The `gui/column_config_dialog.py` entry stays, re-owned to "Bundle 13 (9.16)".

### 3.5 Search keywords

```python
SETTINGS_SEARCH_KEYWORDS = {
    "General": ["delimiter", "csv", "low stock", "threshold", "repeat"],
    "Orders Mapping": ["columns", "csv", "headers", "courier", "carrier", "shipping"],
    "Stock Mapping": ["columns", "csv", "headers", "expiry", "batch", "lot", "fifo"],
    "Rules": ["conditions", "actions", "tags", "status", "priority", "automation"],
    "Sets": ["bundles", "kits", "components", "decoder"],
    "Weight": ["volumetric", "divisor", "dimensions", "boxes", "packaging", "kg"],
    "Reports": ["packing list", "stock export", "filters", "output", "writeoff"],
    "Tag Categories": ["tags", "labels", "colours", "colors", "writeoff", "sku"],
}
```

## 4. Sets page

`collect()` per §3.1. Its message boxes route as follows:

| Call site | After |
|---|---|
| Add / Edit set: "Success" info | Removed: the row appears and the nav marks the page |
| Delete set: "Are you sure" question | Removed: deletion is immediate, and Cancel reaches it (CONTEXT: an undoable act never confirms) |
| Delete set: "Success" info | Removed |
| Import: Replace / Merge / Cancel question | Removed. **Import from CSV** becomes a button with a menu: **Add and update sets…** and **Replace all sets…**, chosen before the file picker |
| Import: "No sets found" | `show_error(self, f"No sets found in {name}", "Each row needs Set_SKU, Component_SKU and Component_Quantity.")` |
| Import: success | `toast(self, f"Imported {n} sets from {name}")`, or `f"Replaced all sets with {n} from {name}"` |
| Import: exception | `logger.exception`, then `show_error(self, "The sets weren't imported", "Details are in Logs.")` |
| Export: "No sets to export" | Removed: **Export to CSV** is disabled while there are no sets |
| Export: success | `toast(self, f"Exported {n} sets to {name}")` |
| Export: exception | `logger.exception`, then `show_error(self, "The sets weren't exported", "Details are in Logs.")` |
| `SetEditorDialog`: empty SKU | `InlineMessage` under the SKU field: "Enter the set's SKU." Clears when the SKU is edited. |
| `SetEditorDialog`: no components | `InlineMessage` under the table: "Add at least one component with a SKU." |

`{name}` is the file's base name. The `[DEBUG]` prints in the page and the
editor go too.

## 5. Column Config leaves Settings

- Delete `_ColumnConfigPage`, its `_add_page` call and its nav entry. Data
  becomes General, Orders Mapping, Stock Mapping. Settings has eight pages.
- `gui/column_config_dialog.py` is untouched. Docstrings that describe the
  panel as embedded in Settings (`gui/settings/base.py`,
  `gui/components/form_section.py`, `tests/test_column_config_dialog.py`) are
  corrected.

## 6. Reports page (9.24)

### 6.1 Layout

```
┌───────────────────────────────┬──────────────────────────────────────────┐
│ Packing lists             [+] │  Name              [DHL Express        ] │
│  DHL Express      (selected)  │  Output Filename   [dhl.xlsx           ] │
│  DPD Standard                 │  Exclude SKUs      [SHIP-01            ] │
│ Stock exports             [+] │  Filters                                 │
│  Daily ERP                    │   [Shipping_Provider][equals][DHL] [🗑]  │
│                               │   Add Filter                             │
│ Drag a report to change the   │   Matches 148 orders · 372 rows          │
│ order it generates in.        │  Columns to display  [ ] ...             │
│                               │                         [Delete report]  │
└───────────────────────────────┴──────────────────────────────────────────┘
```

- **Left column, 240 px fixed**, in a `QScrollArea`. Per kind: a heading
  label (sentence case) with an icon-only `plus` button (ghost role,
  accessible name and tooltip "Add packing list" / "Add stock export"), then a
  `QListWidget`. One list per kind, with `InternalMove` drag and drop,
  `AdjustToContents` size and no vertical scrollbar. Two lists make a
  cross-kind drag impossible by construction; the arrays are separate config
  keys. The caption "Drag a report to change the order it generates in." sits
  under them, in `text_secondary`.
- **Right side:** exactly one `ReportEditor`, for the selected report.
  Selecting a row in one list clears the other list's selection.
- **Empty (no reports):** a `StatePanel`, titled "No reports yet", reading
  "Add a packing list or a stock export, then generate it from Results after
  an analysis.", with a secondary action "Add packing list". It uses the
  secondary role because Save is the only primary inside Settings (see
  `tests/test_settings_button_roles.py`).
- **Names:** a report with a blank name lists as "Untitled report". The list
  row follows the name field as it is typed.

### 6.2 Model

- The page keeps `_store: dict[int, dict]`, from a stable integer key to one
  report config. Each list item carries its key in `Qt.UserRole`. **List order
  is config order**, read at `collect()` time, so a drag needs no bookkeeping.
- **Normalised at load.** On construction each config is passed once through
  a throwaway `ReportEditor(...).collect()` before it is stored. Without this,
  merely selecting a report with a legacy operator (`==` → `equals`) would
  mark the page unsaved.
- **Switching reports:** stash `_editor.collect()` into the store, detach the
  old editor (`setParent(None)` then `deleteLater()`), and build the new one.
  `collect()` stashes first, then returns both keys in list order.
- **Add (`+`):** appends `{"name": "", "output_filename": "", "filters": []}`
  to that kind, selects it, focuses the name field. Returns the editor.
- **Delete report** (the editor's button, renamed from "Delete"): removes the
  row and the stored config, then selects the neighbour in the same list (same
  row, else the one above), else the first report of the other kind, else the
  empty state. No confirm and no toast: Cancel reaches it.

**Generate order.** `GenerateReportsDialog` already renders
`packing_list_configs` then `stock_export_configs` in array order. Because
list order is array order, the order set here is the order it generates in.
No change to the dialog's ordering.

### 6.3 Live match count

- `shopify_tool/report_filters.py` gains
  `match_counts(filtered_df) -> tuple[int, int]` (distinct orders, rows; a
  missing `Order_Number` column falls back to the first column, as the dialog
  does today) and `count_matches(df, filters) -> tuple[int, int] | None`.
  `count_matches` is `None` without an analysis, else
  `match_counts(apply_report_filters(fulfillable_only(df), filters))`, which
  is exactly what the generated file contains.
- `GenerateReportsDialog._update_preview` replaces its inline counting with
  `match_counts(filtered)`, so the preview and the editor cannot disagree.
- `ReportEditor` shows a `match_label` under the filter rows. It recomputes
  300 ms after the last filter edit (a single-shot `QTimer`), and once
  synchronously on construction. Results are cached in a dict the page owns
  and passes to every editor, keyed by
  `json.dumps(filters, sort_keys=True, default=str)`. The analysis frame is
  fixed for the dialog's lifetime, so the cache never goes stale. This is the
  "existing fingerprint cache" the brief names, now shared.
- **Copy** (`match_text(counts)`):
  - `None`: "Run an analysis to see how many orders this report matches."
  - `(0, _)`: "Matches no orders. Check the filters." (`status_warning`)
  - `(1, 1)`: "Matches 1 order · 1 row"
  - `(148, 372)`: "Matches 148 orders · 372 rows"
  - evaluation raised: "Can't count matches for these filters." (logged at
    debug, since this can fire on every keystroke of a half-typed regex)
  - All states except the zero state use `text_secondary`. The label's tooltip
    reads "Counts fulfillable orders, the same as the generated file."

### 6.4 Filter rows (`gui/settings/fields.py`)

- `add_filter_row(..., on_change=None)`. When `on_change` is given it runs
  after a field or operator change, on every edit of the (rebuilt) value
  widget (`textChanged` / `currentTextChanged`), and when the row is removed.
- **Delete control:** the text "X" `QPushButton` becomes an icon-only button
  with `icon("trash-2")`, ghost role, tooltip and accessible name "Remove
  filter", re-iconed through `on_theme_changed`. The asset library has no `x`
  glyph.
- **Legacy values are kept.** The field combo already appends a saved field
  that isn't offered. The *value* combo (equals / does not equal on an
  analysed column) still silently falls back to the first unique value when
  the saved value is absent from the frame, then writes that value back. It
  now appends the saved value first, the same rule.

## 7. Glossary

`CONTEXT.md` gains a **Settings** section: **Unsaved page**, **Close guard**,
**Match count**, **Generate order**.

## 8. Testing seams

| Seam | Test file | What it proves |
|---|---|---|
| `SettingsPage.snapshot/mark_clean/is_dirty` | `tests/test_settings_page_contract.py` | Defaults inert before `mark_clean`; an edit reads unsaved; reverting it reads clean; a raising `collect()` reads unsaved |
| Mapping override | `tests/test_settings_page_mappings.py` | Editing Orders Mapping leaves Stock Mapping clean |
| `unsaved_summary(names)` | `tests/test_settings_unsaved.py` | The four copy rows in §3.3 |
| Window unsaved tracking | `tests/test_settings_unsaved.py` | Fresh window: `refresh_dirty() == []`; edit Sets → `["Sets"]`, nav mark set, footer text; close guard shows instead of closing; Discard closes with no worker started; Keep editing restores the footer |
| **Done when (9.23)** | `tests/test_settings_unsaved.py` | Import sets via a patched picker and importer, then Cancel → Discard: `profile_manager.save_shopify_config` never called and no worker started |
| Save routes | `tests/test_settings_roundtrip.py` | Validation failure selects the page and fills the inline message with no modal; success calls the patched `toast`; failure calls the patched `show_error` |
| Nav search + construction | `tests/test_settings_nav.py` | `filter_nav("box")` → `["Weight"]`; no match shows "No page matches"; a bad group raises `ValueError`; keyword keys equal nav names |
| Sets routes | `tests/test_settings_page_sets.py` | Collect returns the live dict; merge vs replace; export disabled when empty; toasts; editor inline messages |
| `count_matches` / `match_counts` | `tests/test_report_filters.py` | None without analysis; fulfillable-only counting; distinct orders |
| Filter rows | `tests/test_settings_page_reports.py` | A legacy equals-value survives a round-trip; `on_change` fires on value edits; delete is an icon button |
| **Done when (9.24)** | `tests/test_settings_page_reports.py` | One editor at a time; reorder changes collect order; the match count updates after a filter edit; a legacy field value survives a save round-trip |
| Route guard | `tests/test_message_routes.py` | The three entries are gone; the guard still passes |

## 9. Departures from the brief and mockups

- **Column Config is removed** from Settings rather than buffered (user
  decision §2.1).
- **The footer counts pages** rather than changes (user decision §2.2).
- **The nav remembering by name** was already shipped; no change.
- **Reports list rows have no drag-handle glyph.** The asset library has none,
  and a glyph is a `packing-tool` PR. The whole row drags, and the caption says
  so.
- **The filter delete is `trash-2`, not an `x`.** Same reason.
- **Kind headings are sentence case** ("Packing lists"), not the all-caps
  section headers `GenerateReportsDialog` uses.

## 10. Out of scope

- The column manager rebuild (9.16, Bundle 13).
- Per-report match counts in the list.
- Report name validation (none exists today).
- Arbitrary printed-column order (the existing `ponytail:` note in
  `report_editor.py` stands).
