# UI refresh phase 7: Client settings pages on the web kit, in a Qt frame

**Task:** dev-runner run 53, Todoist 6hfx8cxJ66MV23GM: "UI refresh phase 7: Client settings on the web tier:
frame, General, mappings". Brief: `docs/design/ui-refresh/roadmap.md`, phase 7. Depends on phase 2 (merged, #356).
**Path:** architectural. It adds a sixth web view and a sixth bridge, replaces three Qt settings pages, and
changes what Save does.
**Mockup followed:** `docs/design/ui-refresh/mockups/client-settings.html`, states General, Unsaved page and
Orders mapping, both themes. Every departure is in §9.

## 1. What this task delivers

1. General, Orders mapping and Stock mapping as one web page on the kit: `gui/web/settings.html`,
   `settings.css`, `settings.js` (§5).
2. `SettingsBridge`, and three drafts that hold those pages' values and word everything the page draws (§3, §4).
3. The dialog's Qt frame restyled to the mockup: nav, search, marks and footer (§6.1, §6.2).
4. Save as the mockup draws it: disabled until a page is unsaved, and the dialog stays open (§6.3).
5. The page anatomy as kit components, for phases 8 and 9 (§5.6).
6. Docs: `roadmap.md` (phase 7 as built, a new phase 10), ADR 0016, `CONTEXT.md` (§11).

Rules, Sets, Weight, Reports and Tag categories keep their Qt widgets and their look.

## 2. Owner's decisions (2026-10-02, run 53)

| Question | Answer |
|---|---|
| How the five unported Qt pages share the dialog with the web pages | The frame stays Qt, restyled to the mockup's sizes and copy. One web view fills the page area for General and both mappings. The frame moves to the web after the last page does |
| Where a mapping page's columns come from, and whether a column can be typed | The file loaded on Setup, if any. Otherwise the card says no file has been read and offers Read columns from CSV…. Menus only, no typing. A saved column the file lacks stays selected, marked "Not in this file" |
| How Courier names shows code → patterns | One row per pattern: typed text on the left, courier on the right from a menu of the couriers in use plus a new one. The copy says "contains". The stored format does not change |
| What Save does | The mockup: disabled until a page is unsaved; it writes, the marks clear, and the footer reads "Saved. Applies from the next analysis." Cancel becomes Close. Files are re-checked when the dialog closes |
| The design (§3 to §10) | Approved, with the fill-down option on Additional columns chips |

**What the code does that the mockup does not know** (the facts behind the answers):

- A Qt widget cannot be drawn over a `QWebEngineView` (ADR 0007). The roadmap's "the pages not ported yet keep
  their Qt widgets inside the same dialog" needs a web-drawn frame with Qt pages laid over it, so it cannot be
  built as written.
- Column mapping today is an editable box per field. Column names are offered only after "Load headers from
  CSV…". The profile stores `{csv column: internal field}`, so one column can feed only one field.
- `courier_mappings` is `{code: {"patterns": [...], "case_sensitive": false}}`. The analysis matches a pattern
  as a case-insensitive substring of the shipping method, and the first code in the dict wins
  (`shopify_tool/analysis.py`, `_generalize_shipping_method`). With no mappings it falls back to DHL, DPD and
  PostOne. A legacy entry (`{"dhl": "DHL"}`) is still matched by the analysis, but today's page drops it on
  save.
- The low-stock flag is `Final_Stock < threshold`: strictly fewer.
- An additional column has two flags, `enabled` and `is_order_level` (ADR 0006, `CONTEXT.md`). Stock has no
  additional columns.
- Today Save always writes, closes the dialog and toasts on the main window.

## 3. Architecture

```
SettingsWindow (QDialog, Qt frame)
 ├─ nav, search, footer                         Qt, restyled (§6)
 └─ page stack
     ├─ SettingsWebHost ── one QWebEngineView   General, Orders mapping, Stock mapping
     └─ RulesPage, SetsPage, WeightPage, ReportsPage, _TagCategoriesPage   unchanged

draft.view() ──► SettingsBridge.state ──► settings.js render()
settings.js ──► SettingsBridge.edit(action, args) ──► draft.apply(...) ──► push again, host.edited
```

- **A draft is a settings page without a widget.** `GeneralDraft`, `StockDraft` and `OrdersDraft` meet the same
  contract as a Qt page (`collect`, `validate`, `snapshot`, `mark_clean`, `is_dirty`), so the window saves and
  marks them exactly as it does the Qt pages. They import no Qt.
- **Python owns every value and every sentence.** `draft.view()` returns one dict; the page renders it. The
  page's own state is which menu is open.
- **One view, three pages.** The nav's three web entries show the same host widget; the host pushes the view of
  the draft that was asked for. The view exists only while the dialog is open.

### 3.1 Files

| File | What it is |
|---|---|
| `gui/settings/contract.py` (new) | `PageContract`: the page contract with no widget. No Qt import |
| `gui/settings/base.py` | `SettingsPage(PageContract, QWidget)`; the contract's methods move to `contract.py` |
| `gui/settings/page_state.py` (new) | `FileColumns`, `GeneralDraft`, `MappingDraft`, `StockDraft`, `OrdersDraft`, `ADDITIONAL_COLUMNS_UNREADABLE`. No Qt import |
| `gui/settings/bridge.py` (new) | `SettingsBridge(PageBridge)`, `mount_settings_page(view)` |
| `gui/settings/web_host.py` (new) | `SettingsWebHost(QWidget)`: the view, the bridge, the drafts by key, the Read columns dialog |
| `gui/settings/window.py` | The frame restyle, the footer, Save, close; builds the drafts and the host |
| `gui/web/settings.html`, `settings.css`, `settings.js` (new) | The page |
| `gui/web/kit.css`, `tests/web/kit_sheet.html` | The page anatomy (§5.6) |
| `gui/theme_manager.py` | `QListWidget#settingsNav` rules to the mockup |
| `shopify_tool/csv_utils.py` | `read_csv_preview(path)` |
| `shared/assets/icons/circle-alert.svg` (new) | Lucide's glyph, for the nav mark and the footer |
| `gui/actions_handler.py` | Passes the loaded files; the result means "saved at least once" |
| `gui/setup_state.py`, `gui/ui_manager.py`, `gui/settings/weight.py` | `"Orders Mapping"` becomes `"Orders mapping"`, and `"Stock Mapping"` `"Stock mapping"` |
| Deleted | `gui/settings/general.py`, `gui/settings/mappings.py`, `gui/column_mapping_widget.py` |

`shared/` gains one icon file. Packing Tool gets it at its next sync and needs no change.

### 3.2 `PageContract` (`gui/settings/contract.py`)

Today's `SettingsPage` methods, moved (`collect`, `validate`, `snapshot`, `mark_clean`, `is_dirty`,
`_safe_snapshot`, `UNCOLLECTABLE`). `mark_clean(snapshot=None)` can take a snapshot made earlier with
`current_snapshot()`, so a save marks clean what it wrote and not what is on screen when it ends. Two more,
`blocker()` and `blocker_key()` (the `data-key` of the control the blocker is about, `""` by default):

```python
def blocker(self) -> str | None:
    """What stops a save right now, as the words that fit "<blocker> in <page> to save."

    None when nothing does. Checked on every edit, so it must be cheap. A page
    whose checks are not cheap returns None and reports through validate()
    when Save is pressed.
    """
    return None
```

`gui/settings/base.py` keeps its module docstring and exports `SettingsPage(PageContract, QWidget)` and
`UNCOLLECTABLE`, so no Qt page changes.

### 3.3 `SettingsBridge`: the catalogue

Channel name `settings`. Add a member here before adding it to the code.

| member | direction | meaning |
|---|---|---|
| `state` Property (`QVariantMap`, notify `stateChanged`) | Python → JS | Everything the page draws (§4.5) |
| `themeCss` | Python → JS | From `PageBridge` |
| `problemFocusRequested(str)` Signal | Python → JS | Focus the control with this `data-key` and scroll it into view |
| `edit(action, args)` → `editRequested(str, list)` | JS → Python | One edit (§3.4). `@Slot(str, "QVariant")`; dropped unless `args` is a list |
| `readColumns()` → `readColumnsRequested()` | JS → Python | The page head's Read columns from CSV… |

`set_state(state)` emits `stateChanged` only when the dict differs from the last one. `toastRaised` is inherited
and unused: the page has no toast.

### 3.4 The edit actions

`draft.apply(action: str, args: list) -> bool` returns whether anything changed. An unknown action, a wrong
number of arguments, a wrong type or a value outside the ones listed is dropped and returns False; the host
logs it at debug level, since a repeat of the current value returns False too. The page sends strings and
booleans only: a row index travels as a string (`"2"`), because a JavaScript number reaches Python as a
float. Nothing the page sends is used as a path.

| Draft | action | args | effect |
|---|---|---|---|
| General | `delimiter` | `[kind, mode]` | `kind` is `"stock"` or `"orders"`; `mode` is `"auto"`, `"comma"`, `"semicolon"`, `"tab"` or `"other"` |
| General | `delimiter_char` | `[kind, text]` | The Other character. Kept as typed |
| General | `threshold` | `[text]` | Kept as typed |
| Orders, Stock | `column` | `[field, column]` | `column` is one of the read file's columns, or `""` for Not imported on an optional field. Any other field holding that column loses it. On Orders, an additional column of that name is turned off |
| Orders | `courier_add` | `[]` | Appends a row with no text and no courier |
| Orders | `courier_pattern` | `[index, text]` | |
| Orders | `courier_code` | `[index, code]` | `code` is stripped; an empty one is dropped |
| Orders | `courier_remove` | `[index]` | |
| Orders | `column_add` | `[name]` | Keeps a candidate (§4.4). Makes an unreadable list known |
| Orders | `column_remove` | `[name]` | `enabled` becomes False; the entry stays in the list |
| Orders | `column_fill` | `[name, on]` | `is_order_level`; `on` is a boolean |

## 4. The drafts (`gui/settings/page_state.py`)

### 4.1 `FileColumns`

```python
@dataclass(frozen=True)
class FileColumns:
    name: str                    # the file's name, as the card shows it
    columns: tuple[str, ...]     # the header row, in file order
    first_row: dict[str, str]    # column -> the first data row's value; "" when empty
    loaded: bool = False         # True: the file loaded on Setup. False: picked in the dialog
```

`csv_utils.read_csv_preview(path) -> tuple[list[str], dict[str, str]]` reads the header and one row, as text,
with the delimiter `detect_csv_delimiter` finds. It does not use the General page's delimiter, which may be an
unsaved edit. A file with a header and no rows gives an empty dict.

### 4.2 `GeneralDraft(settings: dict, client: str)`

Holds the live `config_data["settings"]` dict and updates it in place on `collect()`, so keys the page does
not draw survive (the contract's rule).

- Per kind, a mode (`auto`, `comma`, `semicolon`, `tab`, `other`) and an Other character. A stored value that is not one of
  the four named ones opens as Other with that value as the character, so Pipe and a hand-edited value are
  kept.
- The threshold as text.
- `collect()` writes `stock_csv_delimiter`, `orders_csv_delimiter` (the mode, or the character under Other) and
  `low_stock_threshold` as an `int`.
- Problems: Other with no character; a threshold that is not a whole number of 0 or more.
- `blocker()`: `"Set Stock CSV delimiter"`, `"Set Orders CSV delimiter"` or `"Set Low-stock threshold"`, the
  first that applies. `validate()` returns the problems' sentences.

### 4.3 `MappingDraft(kind, column_mappings, client, file=None)`; `StockDraft`

Holds the live `config_data["column_mappings"]` dict and writes only its own sub-key into it, in place. Both
mapping drafts share that dict, as the two Qt pages do today.

`FIELDS` per kind: `(internal name, label, required, hint, example)`.

| kind | internal | label | required | example |
|---|---|---|---|---|
| orders | `Order_Number` | Order number | yes | `Name` |
| orders | `SKU` | SKU | yes | `Lineitem sku` |
| orders | `Quantity` | Quantity | yes | `Lineitem quantity` |
| orders | `Shipping_Method` | Shipping method | yes | `Shipping Method` |
| orders | `Product_Name` | Product name | | |
| orders | `Shipping_Country` | Country | | |
| orders | `Tags` | Tags | | |
| orders | `Notes` | Notes | | |
| orders | `Total_Price` | Total price | | |
| orders | `Subtotal` | Subtotal | | |
| orders | `Customer` | Customer | | |
| orders | `Created_At` | Created at | | |
| stock | `SKU` | SKU | yes | `Артикул` |
| stock | `Stock` | Quantity | yes | `Наличност` |
| stock | `Product_Name` | Product name | | |
| stock | `Expiry_Date` | Expiry date | | |
| stock | `Batch` | Batch | | |

Hints: Expiry date, "When mapped, stock is allocated oldest expiry first, and each packing list row shows its
lot. Reads YYMMDD, YYYYMMDD, DDMMYY and MMYY." Batch, "Lot or batch number. Shown per lot on packing lists, and
keeps separate deliveries of one SKU apart." `Expiry_Date` and `Batch` are the exact names
`_build_fifo_lots()` looks for; renaming them turns FIFO off.

- `chosen`: internal → CSV column, read from the stored mapping. `mappings()` returns the stored entries for
  internal names the page has no row for, untouched, plus the chosen ones. A field with no column is left out.
- `set_file(file)` replaces the file. It changes no mapping.
- `collect()` sets `column_mappings["version"] = 2` and `column_mappings[kind] = mappings()`.
- `snapshot()` covers this draft's own mapping only, so an edit on one mapping page does not mark the other.
- `blocker()`: `"Map <label>"` for the first required field with no column. `blocker_key()` is that field's
  `data-key` (§5.7), for the footer's link; `GeneralDraft` has one too. `validate()` returns the same field's
  sentence from §4.6.

### 4.4 `OrdersDraft(column_mappings, courier_mappings, client, fallback_additional_columns, file=None)`

**Courier rows.** A list of `[text, code]`, one per stored pattern, in stored order. A legacy entry
(`pattern: code`) loads as one row. `collect()` clears the live `courier_mappings` dict and refills it:
codes in the order their first row appears, each with its rows' texts as `patterns` (stripped, repeats
dropped) and `"case_sensitive": False`. A row missing its text or its courier is not saved. No row blocks the
save.

**Additional columns.** `entries` is the stored list, each with `csv_name`, `internal_name`, `enabled`,
`is_order_level`, `exists_in_df`. The source and the unreadable case are today's (ADR 0006):
`column_mappings["additional_columns"]` when the key is there, else `fallback_additional_columns`; and
`ADDITIONAL_COLUMNS_UNREADABLE` means the list is unknown, so `collect()` leaves the key alone.

- With a file read, `csv_utils.discover_additional_columns` over the file's columns, this draft's mapping and
  `entries` gives the chips (enabled), the candidates (not enabled) and which ones the file lacks.
- With no file, the chips are the enabled entries and the candidates are the others.
- `column_add` turns an entry on, or appends a discovered candidate as a new entry. Only what the operator
  kept or turned off is stored: reading a file adds nothing to the profile.
- `snapshot()` covers the mapping, the courier rows and `entries`.

### 4.5 `view()`: the state

Every draft's view has the page head:

```python
{"page": "general" | "orders" | "stock", "title": str, "subtitle": str, "action": str}
```

General adds:

```python
"general": {
    "csv_text": str, "alerts_text": str,   # the two cards' sentences
    "delimiters": [  # stock, then orders
        {"kind": "stock", "label": "Stock CSV delimiter",
         "options": [{"value": "auto", "label": "Auto", "checked": True}, ...],  # Auto Comma Semicolon Tab Other
         "other": False, "char": "", "hint": str, "problem": ""},
    ],
    "threshold": {"value": "5", "unit": "units", "hint": str, "problem": ""},
}
```

A mapping draft adds:

```python
"mapping": {
    "kind": "orders",
    "source": {"lead": str, "file": str, "tail": str},   # the Fields card's sentence; file is drawn mono
    "can_pick": bool,                                    # a file has been read
    "columns": [str, ...],                               # the read file's, in file order
    "held": {column: field label},                       # who holds each chosen column
    "fields": [
        {"name": "Order_Number", "label": "Order number", "required": True,
         "column": "Name", "placeholder": "Choose column",   # or "Not imported"
         "sample": "#10482", "sample_missing": False,         # True: sample reads "Not in this file"
         "problem": "", "example": "", "hint": ""},   # example: drawn mono, after the problem
    ],
    # Orders only:
    "couriers": {"text": str, "rows": [{"text": "dhl", "code": "DHL"}], "codes": ["DHL", "DPD"],
                 "empty": str},
    "additional": {
        "text": str,
        "chips": [{"name": "Notes", "note": "", "fill": True}],
        "candidates": [{"name": "Discount Code", "note": ""}],
        "group": str, "empty": "None kept.", "notice": "", "add_title": str,
    },
}
```

`held` and `columns` let the page build the one open menu; the page computes nothing else.

### 4.6 The sentences

`{client}` is the client id. `{file}` is the read file's name.

| Where | Text |
|---|---|
| General subtitle | How {client}'s files are read, and when stock counts as low. |
| CSV files card | The character that separates columns in {client}'s files. |
| Delimiter hint, Auto | Detected for each file as it is read. |
| Delimiter hint, Comma / Semicolon / Tab | Every file is split on commas. / semicolons. / tabs. |
| Delimiter hint, Other | Every file is split on “{char}”. |
| Delimiter problem | Type the character that separates the columns. |
| Stock alerts card | When a SKU is flagged as low stock in Results. |
| Threshold hint | A SKU is low when fewer than this are left after the session's orders are allocated. |
| Threshold problem | Type a whole number, 0 or more. |
| Mapping subtitle | Which column of {client}'s orders CSV holds each field. (or "stock CSV") |
| Page action | Read columns from CSV… |
| Fields source, loaded on Setup | Columns read from `{file}`, the file loaded on Setup. |
| Fields source, picked here | Columns read from `{file}`. |
| Fields source, none | No CSV has been read. Use Read columns from CSV… to change a field. |
| Required field, file read | {label} is required. Choose the column that holds it, e.g. `{example}`. |
| Required field, no file | {label} is required. Use Read columns from CSV…, then choose its column. |
| Courier names card | A shipping method that contains the text on the left is filed under the courier on the right. Anything else keeps its own name. |
| Courier names, no rows | No courier names yet. The built-in ones apply: DHL, DPD and PostOne. |
| Additional columns card | Orders columns with no field, carried through the analysis under their own names. |
| Additional columns, list unknown | The saved list couldn't be read, so saving leaves it as it is. Add a column to replace it. |
| Add column, nothing to add | Use Read columns from CSV… to list the file's unmapped columns. (the button's title; with a file read: "Every column in this file is mapped or kept.") |
| Add column menu group | Unmapped columns in {file} (or "Turned off earlier" with no file) |
| Chip notes | "Not in this file", "not filled down", or both joined by a comma |
| Chip menu | Fill down onto every line of the order |

## 5. The page (`gui/web/settings.*`)

### 5.1 Frame

`<main id="settings">` scrolls. Inside it, one column: `max-width: 860px`, centred, padding `20px 24px 32px`,
gap 16px. The body is `--surface-sunken` (the kit's).

Page head: the title at 14pt bold, the subtitle under it in `--text-secondary`, and on a mapping page the
action as a secondary button with a plus glyph, top-aligned on the right.

### 5.2 General

Two cards.

- **CSV files.** Card head, then one row per delimiter: the label in a 180px column, then a `.segmented`
  radiogroup of five segments. Under Other, a one-character mono field (36px wide, centred, `maxlength="1"`)
  sits beside it. The hint is under the control; a problem replaces the hint, in `--status-danger` with the
  alert glyph.
- **Stock alerts.** One row: a 72px mono, right-aligned field with `inputmode="numeric"`, then "units".

### 5.3 The Fields card

Card head with the source sentence. A column-header line (Field, CSV column, First row) in 9pt bold secondary.
Then one row per field on the grid `180px 16px 240px minmax(0, 1fr)`:

- the label in bold, with "Required" in 9pt secondary beside a required one;
- an arrow-left glyph;
- a `.select`, 240px. Its value is the column in mono. With no column it reads "Choose column" (required, in
  `--status-danger`, the select `.invalid`) or "Not imported" (optional, placeholder colour). Disabled when
  `can_pick` is false;
- the First row value in mono secondary, one line, ellipsis. "Not in this file" when the file lacks the column.

A problem or a hint sits on a second line under columns 3 and 4.

The open menu, 240px wide, at most 240px tall: "Not imported" first on an optional field, then the file's
columns in mono. The chosen one has the check. A column another field holds shows that field's label as the
`.menu-hint`. A chosen column the file lacks is listed first, with the hint "Not in this file".

### 5.4 Courier names (Orders)

Card head with "Add name" (secondary) on the right. A column-header line: "Shipping method contains", then
"Courier". One row per courier row on the grid `280px 16px 160px minmax(0, 1fr)`:

- a mono `.field` (placeholder `dhl express`);
- an arrow-right glyph;
- a `.select` showing the courier in bold, or "Choose courier";
- a ghost icon button with the ✕ glyph, title "Remove", at the row's end.

The courier menu lists the couriers in use, the row's own checked, then a separator and a `.field` with the
placeholder "New courier". Enter in it sets the row's courier and closes the menu.

Add name focuses the new row's text field.

### 5.5 Additional columns (Orders)

Card head with "Add column" (secondary) on the right; disabled, with the title from §4.6, when there is no
candidate. The body is a wrapping line of chips, or "None kept.". The notice from §4.6, when there is one,
is a line above the chips.

A chip is the column name in mono (a button that opens the chip's menu), a note in secondary when it has one,
and a ✕. The chip's menu has one `menuitemcheckbox`: "Fill down onto every line of the order". Add column
opens a menu of the candidates under the group label.

### 5.6 Kit additions (`gui/web/kit.css`, and the kit sheet)

Components phases 8 and 9 reuse. Each is drawn on `tests/web/kit_sheet.html` and checked in
`tests/test_web_kit.py`.

| Class | What it is |
|---|---|
| `.page-head.split`, `.page-head-text`, `.page-sub` | A head with the title and subtitle stacked on the left and an action on the right |
| `.card-head`, `.card-head-text`, `.card-title`, `.card-text` | A card's title (12pt bold) and its secondary sentence, with room for an action on the right; padding `14px 16px 12px` |
| `.card-row`, `.card-label`, `.card-control` | A label column (180px) and a control column; padding `12px 16px`; a `--border-subtle` rule above every row |
| `.hint` | A 9pt secondary line under a control |
| `.problem` | A `--status-danger` line with the alert glyph |
| `.chip`, `.chip-remove` | A removable value: 26px, `--surface-raised`, `--border`, radius 6px |
| `.select.invalid`, `.field.invalid` | A `--status-danger` edge |

Tools keeps its own `.tool-head` rules; folding them into `.card-head` is not this task.

### 5.7 Menus, keyboard and focus

- One menu at a time. A click outside its anchor closes it. A view that disables the open menu's select closes
  it.
- Esc closes the open menu and returns focus to its opener. With no menu open the page ignores Esc, and the
  dialog takes it.
- Up and Down walk the open menu. Left and Right move between segments. Enter and Space are the button's own.
- A text field reports on every `input` event, so the nav mark and Save follow the typing. The render keeps the
  focused field's own value and node (the Tools page's `morph`).
- Every control has a `data-key`; a render that rebuilds the focused control gives focus back by key.
- `problemFocusRequested(key)` focuses that control and scrolls it into view.

Keys: `segment-{kind}-{mode}`, `char-{kind}`, `threshold`, `read-columns`, `field-{internal}`,
`courier-add`, `courier-text-{n}`, `courier-code-{n}`, `courier-new-{n}`, `courier-remove-{n}`,
`column-add`, `chip:{name}`, `chip-fill:{name}`, `chip-remove:{name}`. A key that carries a column's name
is found by comparing `dataset.key`, never by a selector built from the name.

### 5.8 Small windows

The dialog's minimum is 1100 × 600, which leaves the page about 860px wide: the Fields grid fits, and First
row shortens with an ellipsis. Everything scrolls in `#settings`. A menu is inside the scroller, so one opened
at the bottom extends the scroll instead of being cut.

## 6. The dialog (`gui/settings/window.py`)

`SettingsWindow` stays a `QDialog` with its native title bar: `Client settings · {client_id}`. It gains one
argument, `loaded_files: dict[str, str] | None` (`{"orders": path, "stock": path}`), from
`ActionsHandler.open_settings_window`, which passes the main window's `orders_file_path` and `stock_file_path`
when set.

### 6.1 Layout

The dialog's layout has no margins and no spacing. The nav column keeps 12px margins. The page column holds
the validation message and the stack. Each Qt page sits in the stack with today's margins; the web host sits
flush.

`_add_page(page, name, widget=None)`: `page` is the `PageContract`, `widget` is what the stack shows
(`page` itself for a Qt page, the host for a draft). The nav selects by name; for a web page it also calls
`host.show_page(key)`. `_poll_current_page` finds the page by the nav's current name.

A loaded file is read once, when the dialog opens (`read_csv_preview`). A file that cannot be read is logged
and treated as no file.

### 6.2 The nav and its marks

| | Now | Phase 7 |
|---|---|---|
| Names | Orders Mapping, Stock Mapping, Tag Categories | Orders mapping, Stock mapping, Tag categories |
| Groups | DATA, FULFILLMENT LOGIC, … | Data, Fulfilment logic, Output, Organization, in 9pt bold secondary |
| Width | 170px, or the placeholder's | 232px column: 12px margins around a list at least 208px wide |
| Rows | padded text | 30px page rows, 26px group rows (`setSizeHint`) |
| Selected | selection tint, accent bar on the left | `surface_sunken` fill, bold, `text`; others `text_secondary`; radius 8px; no bar |
| Unsaved | accent dot on the left | 7px `text` dot at the row's right edge |
| Blocking | none | `circle-alert` in `status_danger` at the right edge, before the dot |
| No match | "No page matches" | `No settings match “{text}”.` |

The marks are the item's decoration, placed on the right by a delegate that sets
`QStyleOptionViewItem.decorationPosition`. Tooltips: "Unsaved changes", "Needs attention", or both joined by
", ". `NAV_SETTINGS_KEY` still stores the page by name; a stored old name finds no page and opens General.

### 6.3 The footer and Save

A hairline (`border_subtle`), then a 60px row: the status line on the left, Cancel and Save on the right.

| State, first that applies | Status line | Save |
|---|---|---|
| A page has a `blocker()` | `circle-alert`, then `{blocker} in <link>{page}</link> to save.` in `status_danger` | Disabled |
| A page is unsaved | A 7px `text` dot, then `Unsaved changes in A, B` (every name, nav order) in `text_secondary` | Enabled |
| Saved, nothing unsaved since | `check`, then `Saved. Applies from the next analysis.` in `status_success`, bold | Disabled |
| Otherwise | Empty | Disabled |

- The link selects that page, gives the web view focus and emits `problemFocusRequested` with the draft's
  `blocker_key()`. The first blocked page in nav order is the one named.
- Save's tooltip is "Ctrl+S". Ctrl+S re-checks every page first, then saves if Save would be enabled.
- While a save runs, Save reads "Saving…" and is disabled.
- The host's `edited` signal re-checks the three drafts' unsaved state and every page's `blocker()` at once.
  The Qt pages are still polled every 400ms, the visible one only.

`save_settings()`:

1. Hides the close guard and clears the validation message.
2. Calls `validate()` on every page in nav order. The first failure opens its page and shows the message above
   it, as today. This is the only check a Qt page gets.
3. Collects every page into `config_data`.
4. Hands the worker a deep copy (`json.loads(json.dumps(config_data))`), so an edit made while it runs cannot
   change what is written.
5. On success: every page is marked clean as of what was written, the footer shows the saved line, and
   Cancel reads Close. No toast. The dialog stays open, unless the save came from the close guard's Save &
   close. An edit made while the write ran still reads unsaved.
6. On failure: today's error boxes, unchanged.

An edit after a save returns the footer to the unsaved line and Close to Cancel.

### 6.4 Closing

Esc, Cancel or Close, and the title bar's ✕ all go through `reject()`:

- during a save, nothing;
- with the close guard showing, it hides the guard;
- with unsaved pages, it shows the guard: `{unsaved line}. Closing now discards them.`, Keep editing, Discard,
  Save & close. Save & close is disabled while a page has a blocker;
- otherwise it closes.

The dialog closes with `Accepted` when it saved at least once and `Rejected` otherwise, whatever closed it.
`open_settings_window` reloads the profile and re-checks the loaded files on `Accepted`, as it does today.

### 6.5 `SettingsWebHost` (`gui/settings/web_host.py`)

```python
class SettingsWebHost(QWidget):
    edited = Signal()                      # a draft changed

    def __init__(self, drafts: dict[str, PageContract], parent=None): ...   # keyed "general", "orders", "stock"
    def show_page(self, key: str) -> None: ...        # push that draft's view
    def focus_problem(self, key: str) -> None: ...    # setFocus on the view, then problemFocusRequested
```

- `editRequested` → `drafts[current].apply(action, args)`; when it returns True, push and emit `edited`.
- `readColumnsRequested` → `QFileDialog.getOpenFileName` ("CSV Files (*.csv);;All Files (*)") →
  `read_csv_preview` → `draft.set_file(FileColumns(..., loaded=False))` → push and emit `edited`. Only on a
  mapping page.

## 7. Errors

| What fails | What the operator sees |
|---|---|
| The file loaded on Setup cannot be read when the dialog opens | The Fields card says no CSV has been read. Logged |
| The picked CSV cannot be read, or is empty | `show_error`: "The column names couldn't be read", "Details are in Logs." (today's) |
| A required field has no column; a threshold or Other character is wrong | The message under the control, the nav mark, the footer line, Save disabled |
| A Qt page fails `validate()` on Save | Its page opens with the message above it (today's) |
| `collect()` raises | `show_error`: "Settings weren't saved", "A value couldn't be read. Details are in Logs." (today's) |
| The save fails | Today's two error boxes. The pages stay unsaved |
| The client config's additional columns cannot be read | The card's notice (§4.6); saving leaves the stored list alone |

## 8. Deleted

`gui/settings/general.py`, `gui/settings/mappings.py`, `gui/column_mapping_widget.py`, and their tests
(`test_settings_page_general.py`, `test_settings_page_mappings.py`, `test_settings_additional_columns.py`),
whose cases move to the draft tests. The "Settings saved" toast. `unsaved_summary`'s "on N pages" wording.
`FormSection`, `InlineMessage` and the other Qt components stay: five Qt pages still use them.

`csv_utils.discover_additional_columns` stays and is still used.

## 9. Departures from the mockup

| Mockup | Built | Why |
|---|---|---|
| A header strip with the title, a client chip and ✕ | The native title bar, `Client settings · {client}` | The dialog stays movable, resizable and maximisable, and a second ✕ would sit under the first |
| The whole dialog is one surface | The frame is Qt: flat, no card shadow on the footer's buttons | Owner's decision (§2) |
| "5 units or fewer" | "5 units", hint "A SKU is low when fewer than this are left…" | The analysis flags strictly fewer |
| "Detected from each file's header row." | "Detected for each file as it is read." | Detection reads more than the header |
| "When a SKU is flagged as low stock in Results and the stock export." | "…in Results." | The flag is a column of the analysis (`Stock_Alert`), which Results shows; no stock export code reads it |
| The field "Courier" | "Shipping method" | It maps the shipping method column; the courier is derived from it |
| Orders fields Customer, Created at, Tags, Country, Total weight | The profile's twelve fields | The mockup's list is sample data |
| Stock fields Location and Barcode; an Additional columns card on Stock | Product name, Expiry date, Batch; no card | The profile has neither |
| A courier row's left side is a fixed CSV name | A typed text, under "Shipping method contains" | The match is a substring (owner's decision) |
| The courier menu is a fixed list | The couriers in use, plus a field for a new one | There is no courier list |
| Additional column chips have only ✕ | A chip also opens one option, Fill down | `is_order_level` has no other place (approved) |
| Picking a column another field holds leaves both | The column moves | The profile stores one field per column |
| "Columns read from {file}, the last file loaded." | "…, the file loaded on Setup." or "Columns read from {file}." | The app does not remember a file between sessions |
| The search field is 30px | The theme's control height | One height for every Qt control |

## 10. Tests (test-first; the seams)

| File | Seam | Covers |
|---|---|---|
| `tests/test_settings_draft_general.py`, `test_settings_draft_mapping.py`, `test_settings_draft_orders.py` (new) | The drafts, no Qt | Loading stored values (Pipe, a hand-edited delimiter, legacy couriers, the unreadable list); every action in §3.4, including the dropped ones; `collect()` in place and what it leaves alone; `snapshot()` per draft; `blocker()`; every sentence in §4.6 |
| `tests/test_csv_utils_preview.py` (new) | `read_csv_preview` | Header and first row; `;` and tab files; no data rows; a BOM |
| `tests/test_settings_bridge.py` (new) | `SettingsBridge` | `set_state` notifies only on change; `edit` drops non-list args; `readColumns` |
| `tests/test_settings_web_page.py` (new) | The page in a real Chromium, fed views built by the drafts | Each card's DOM; a click or typing reaches `editRequested` with the right action and args; menus, Esc, arrows; focus kept while typing; the invalid select; both themes read from tokens |
| `tests/test_settings_web_host.py` (new) | `SettingsWebHost` with a patched `QFileDialog` | An edit reaches the draft, pushes and emits `edited`; Read columns; a file that cannot be read |
| `tests/test_settings_footer.py` (new) | `SettingsWindow` (the `window` fixture) | The four footer states; Save enabled only when unsaved and not blocked; the link; Ctrl+S; the dialog stays open after a save; Close; the result is `Accepted` only after a save; Save & close; the worker gets a copy |
| `tests/test_settings_nav.py`, `test_settings_unsaved.py`, `test_settings_roundtrip.py`, `test_settings_entry_points.py`, `test_theme_button_roles.py` | The window | Updated for the names, the marks, the summary wording and the drafts |
| `tests/test_web_kit.py`, `tests/web/kit_sheet.html` | The kit sheet | The §5.6 components |

The round-trip test keeps its promise: a config opened and saved with no edit is written back unchanged.

Renders, saved under `docs/design/ui-refresh/renders/phase7/` and looked at before the PR: General, the
unsaved General with Other, Orders mapping with a missing required field, Orders mapping with no file, Stock
mapping, each in light, and General and Orders mapping in dark. Each is the whole dialog, grabbed offscreen.

## 11. Docs

- `docs/design/ui-refresh/roadmap.md`: phase 7 as built, with its differences; a new row and section, phase 10,
  "Client settings on the web tier: the frame", depending on 9: the nav, search, footer and close guard move
  into the settings document and the Qt frame goes. Phases 8 and 9 add their pages to the same document.
- `docs/adr/0016-the-web-tier-grows-screen-by-screen.md`: a consequence line for the sixth bridge and view,
  which lives only while the dialog is open.
- `CONTEXT.md`: "Unsaved page" (Save is live only when a page is unsaved; it still writes every page),
  "Close guard" (Save & close needs no blocker), and two new terms, **Draft** and **Blocker**.

## 12. Out of scope

- Rules, Sets, Weight, Reports and Tag categories, and the backdrop behind them.
- The frame on the web tier (phase 10).
- Remembering a client's last CSV between sessions.
- Additional columns for stock.
- Re-ordering courier rows to change which courier wins.
- Folding Tools' `.tool-head` into the kit's `.card-head`.

## 13. Delivery

One PR on `dr/19-ui-refresh-phase-7-client-settings-on-th`. Gate:
`QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` and `ruff check .`. The PR says that `shared/` gains
one icon file and Packing Tool needs no work.
