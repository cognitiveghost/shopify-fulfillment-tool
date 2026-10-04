# UI refresh phase 9: Sets, Weight, Reports and Tag categories on the web tier

**Task:** dev-runner run 59, Todoist 6hfx8cwgXhxFx76v: "UI refresh phase 9: Client settings on the web tier:
Sets, Weight, Reports, Tag categories". Brief: `docs/design/ui-refresh/roadmap.md`, phase 9. Depends on phase 8
(merged, #363).
**Path:** architectural. It replaces the last four Qt settings pages with pages of the settings document and
adds file import and export to the settings bridge.
**Mockup followed:** `docs/design/ui-refresh/mockups/client-settings.html`, for anatomy only. The mockup draws
none of these four pages. Each follows the page anatomy phases 7 and 8 built (page head, cards, label and
control rows, a hint or a problem under a control, chips, a list row that opens in place). Every place this
spec had to decide something the mockup does not show is in §11.

## 1. What this task delivers

1. Sets, Weight, Reports and Tag categories as pages of the settings document (`gui/web/settings.*`), each
   with a draft that holds its values, takes every edit and words everything the page draws (§4 to §7).
2. CSV import and export from a web page: three bridge members and a toast (§3.2, §8).
3. The Rules condition row made reusable, so a report's filters use the same control (§3.3).
4. The unsaved poll is deleted: every page now reports its own edits (§9).
5. Docs: `roadmap.md` (phase 9 as built), `CONTEXT.md` (§14).

Deleted: `gui/settings/sets.py`, `weight.py`, `reports.py`, `report_editor.py`, `base.py`,
`gui/tag_categories_dialog.py`, `ActionsHandler.open_tag_categories_dialog`, and the Qt filter-row helpers in
`gui/settings/fields.py`. After this phase no Qt page is left in the dialog. The Qt frame (nav, search,
footer, close guard) stays until phase 10.

## 2. Owner's decisions (2026-10-04, run 59)

| Question | Answer |
|---|---|
| One PR or two | One PR, four pages |
| How product dimensions are edited | In the table, as today. The list shows 200 rows at a time and the filter finds the rest |
| A tag category's colour | Not drawn. The stored colour is kept untouched, and a new category gets the default grey |
| A new tag category's ID | Made from the name, never shown, fixed once the category is first saved |
| The design (§3 to §13) | Approved. Reports and Tag categories reorder by up and down only: no drag |

**What the code does that the brief does not know** (the facts behind the answers):

- Scale in the production profiles: up to 211 sets (7 components at most), 131 product dimensions, 5 boxes,
  3 reports with at most 3 filters, 7 tag categories with about 25 tags. "Import from Stock CSV" adds every
  SKU of a stock file at once, so the products list can reach thousands.
- A tag category's `color` is read by nothing but today's editor (`get_tag_color` has no caller; Results does
  not colour tags; Packing Tool does not read tag categories). `validate_tag_categories_v2` still requires
  the key.
- A category's `order` is likewise read only by today's editor. Results lists categories in stored (dict)
  order.
- A category's ID is the key in the profile and appears nowhere else.
- `ActionsHandler.open_tag_categories_dialog` has no caller, so `TagCategoriesDialog` is dead code.
- Report filters combine with AND, and one that cannot be evaluated matches nothing
  (`shopify_tool/report_filters.py`). A report's `output_filename` is used by its base name only.
- Packing-list `columns` print in the stored order (`shopify_tool/packing_lists.py`).
- The web tier may not use `opacity`, `transition`, `transform`, a gradient or a literal colour
  (`shared/style_lint.py`, ADR 0001).

## 3. Architecture

```
SettingsWindow (QDialog, Qt frame)
 └─ SettingsWebHost ── one QWebEngineView      all eight pages
     ├─ drafts["sets"]    = SetsDraft
     ├─ drafts["weight"]  = WeightDraft
     ├─ drafts["reports"] = ReportsDraft
     └─ drafts["tags"]    = TagsDraft

draft.view() ──► SettingsBridge.state ──► settings.js render() ──► settings_<page>.js
settings_<page>.js ──► bridge.edit(action, args) ──► draft.apply ──► push, host.edited
settings_<page>.js ──► bridge.importFile(kind) ──► host: file dialog ──► draft.import_csv ──► push, toast
```

- **Python owns every value and every sentence**, as in phases 7 and 8. That includes which row is open and
  a list's filter text. The page's own state is which menu is open.
- **A row is addressed by a uid**, a number its draft gives it when it loads or is added, sent as a string.
  It is never stored. A position inside a row (a component, a filter, a write-off) is an index sent as a
  string.
- **`apply(action, args) -> bool`** under phase 7's rules: strings and booleans only, an edit of any other
  shape is dropped, and it returns whether anything changed. `open`, `close`, `filter` and `reveal` change
  what is drawn and nothing that is saved.
- **A value the draft does not draw is kept.** Each entry holds its stored dict and `collect()` writes the
  drawn keys over it.
- **`collect()` never raises.** A value that blocks Save is written as typed; Save is disabled while it
  stands.

### 3.1 Files

| File | What it is |
|---|---|
| `gui/settings/sets_state.py` (new) | `SetsDraft(PageContract)`. No Qt import |
| `gui/settings/weight_state.py` (new) | `WeightDraft(PageContract)`, and the three CSV imports as functions over a DataFrame. No Qt import |
| `gui/settings/reports_state.py` (new) | `ReportsDraft(PageContract)`, `match_text`. No Qt import |
| `gui/settings/tags_state.py` (new) | `TagsDraft(PageContract)`, `DEFAULT_TAG_COLOR`. No Qt import |
| `gui/settings/contract.py` | `FileProblem(Exception)`: a failed import the operator can act on |
| `gui/settings/rules_state.py` | `iso_date(text)` becomes a module function (it was `RulesDraft._iso_date`), so `ReportsDraft` can use it |
| `gui/settings/bridge.py` | `importFile`, `exportFile`, `toastAction` |
| `gui/settings/web_host.py` | Runs imports and exports; raises the toast |
| `gui/settings/window.py` | Builds the four drafts; every nav name is in `WEB_PAGE_KEYS`; the poll and `_TagCategoriesPage` go |
| `gui/settings/fields.py` | Keeps the vocabularies and `report_filter_fields`. The Qt helpers and every Qt import go |
| `gui/actions_handler.py` | `open_tag_categories_dialog` and its import go |
| `gui/web/settings_sets.js`, `settings_weight.js`, `settings_reports.js`, `settings_tags.js` (new) | One page each. Loaded before `settings.js` |
| `gui/web/settings_rules.js` | `conditionRow` takes its key, its data and its action names (§3.3) |
| `gui/web/settings.js` | Routes to the page scripts; the toast; Enter in a `data-enter` field |
| `gui/web/settings.css`, `settings.html` | The four pages' sections; four script tags; the toast's markup |
| Deleted | `gui/settings/sets.py`, `weight.py`, `reports.py`, `report_editor.py`, `base.py`, `gui/tag_categories_dialog.py` |

`shared/` does not change. Packing Tool needs no work.

### 3.2 `SettingsBridge`: additions to the catalogue

| member | direction | meaning |
|---|---|---|
| `importFile(kind)` → `importRequested(str)` | JS → Python | Pick a CSV and import it into the page that is showing |
| `exportFile(kind)` → `exportRequested(str)` | JS → Python | Pick where to save, and export |
| `toastAction()` → `toastActionRequested()` | JS → Python | The toast's action was pressed |
| `toastRaised(text, flag)` | Python → JS | `PageBridge`'s own, unchanged: show a toast. On this page the flag puts "Update them" on it |

Nothing the page sends is used as a path: `kind` only picks one of the draft's own imports or exports.

### 3.3 The shared condition row

`conditionRow` in `settings_rules.js` becomes
`conditionRow(e, key, at, acts, cond)`:

- `key`: the row's key prefix (`rule-4-s0-c1`, `report-2-f0`).
- `at`: the data every control of the row carries (`{uid, s, c}`, `{uid, f}`).
- `acts`: `{field, op, value, remove, removeLabel}`: the `data-act` names of the field item, the operator
  item and the ✕, the `data-input` name of the value, and the ✕'s title.

Rules calls it with `{field: "cond-field", op: "cond-op", value: "cond_value", remove: "cond-remove",
removeLabel: "Remove condition"}` and its DOM does not change. A field group whose `label` is `""` draws no
group label. Reports uses the same view shape as a rule's condition (phase 8 spec §4.7).

### 3.4 How `settings.js` routes

The four scripts define `<page>Page(view)`, `<page>Click(data, el, bridge)` and `<page>Input(data, el,
bridge)`, as Rules does. `settings.js`:

- draws `s.sets`, `s.weight`, `s.reports` or `s.tags` with that page's function;
- hands a click and an input to each page's handler in turn until one returns true;
- `HEAD_ACTION` gains `sets: ["set-add", "set-add"]` and `tags: ["cat-add", "cat-add"]`;
- `menuStillOpens` returns true on these four pages: a menu whose opener the new state no longer draws is
  closed by the check after the morph, which exists;
- Enter in a field that has `data-enter` reports `bridge.edit(data.enter, [data.uid, text])` and clears
  the field (the tag field, §7.3);
- `view.pending` takes three more requests, for a control whose key the page cannot know when it asks:
  `@css:<selector>`, `@css-select:<selector>` and `@keys:<key>|<key>`.

## 4. Sets (`gui/settings/sets_state.py`, `gui/web/settings_sets.js`)

`SetsDraft(set_decoders: dict)`. It owns `config_data["set_decoders"]`: `{set SKU: [{"sku", "quantity"}]}`.

### 4.1 Loading

One entry per stored set, in stored order: `{uid, sku, components}`. A stored value that is not a list loads
as no components. A component that is not a dict is dropped. A component is `{sku, quantity, stored}`:
`sku` as text; `quantity` as text, an integer written without a fraction (`2`, `2.0` and `"2"` all read
`2`), anything else as `str()` gives it.

### 4.2 The edit actions

| action | args | effect |
|---|---|---|
| `filter` | `[text]` | The list shows sets whose SKU or a component's SKU contains it, ignoring case, and the open set |
| `open` | `[uid]` | Opens that set's editor and closes any other |
| `close` | `[]` | |
| `reveal` | `[key]` | Opens the set a `data-key` belongs to |
| `set_add` | `[]` | A set with no SKU and one empty component (quantity `1`), first in the list, opened |
| `set_delete` | `[uid]` | |
| `set_sku` | `[uid, text]` | Kept as typed |
| `comp_add` | `[uid]` | Appends `{sku: "", quantity: "1"}` |
| `comp_remove` | `[uid, c]` | |
| `comp_sku` | `[uid, c, text]` | |
| `comp_quantity` | `[uid, c, text]` | |

### 4.3 What blocks Save

Per set, the first that applies is the collapsed row's problem:

| | Text | Key |
|---|---|---|
| No SKU | Type the set's SKU. | `set-{uid}-sku` |
| A SKU an earlier set has (compared stripped) | Another set already has this SKU. | `set-{uid}-sku` |
| No component with a SKU | Add at least one component. | `set-{uid}-comp-add` |
| A component with a SKU whose quantity is not a whole number from 1 to 9999 | Type a whole number from 1 to 9999. | `set-{uid}-c{c}-quantity` |

- `blocker()`: `Fix set “{sku}”` for the first set in list order with a problem; `Fix the new set` when it
  has no SKU. The footer reads "Fix set “SET-A” in Sets to save."
- `validate()`: every problem, as `Set “{sku}”: {message}` (`New set: {message}` with no SKU).

### 4.4 `collect()`

Clears the live dict and refills it in list order: `{sku stripped: [{**stored, "sku": stripped, "quantity":
int}]}`. A component with no SKU is left out. A set with no SKU is left out. A quantity that is not a valid
whole number is written as typed.

### 4.5 Import and export

| kind | Dialog title | What it does | Toast |
|---|---|---|---|
| `sets-merge` (import) | Import Sets from CSV | `import_sets_from_csv`; a set already listed takes the file's components, a new one is appended | Imported {n} sets from {file} |
| `sets-replace` (import) | Import Sets from CSV | The same, after dropping every set | Replaced all sets with {n} from {file} |
| `sets` (export) | Export Sets to CSV, `sets_export.csv` | `export_sets_to_csv(collect()["set_decoders"])` | Exported {n} sets to {file} |

A file with no sets raises `FileProblem("No sets found in {file}", "Each row needs Set_SKU, Component_SKU
and Component_Quantity.")`. Any other failure: "The sets weren't imported" / "The sets weren't exported",
"Details are in Logs." An import closes the open editor.

### 4.6 `view()`

```python
{
  "page": "sets", "title": "Sets",
  "subtitle": "A set SKU on an order is replaced by its components before stock is allocated.",
  "action": "Add set",                # "" when there is no set
  "sets": {
    "empty": {"title": "No sets yet",
              "text": "A set is one SKU sold as several. Add one, or import them all from a CSV.",
              "action": "Add set", "import": "Import from CSV…"} | None,
    "filter": "", "filter_placeholder": "Filter by SKU or component",
    "count": "211 sets", "no_hits": "", "more": "",
    "can_export": True,
    "import_hint": "CSV columns: Set_SKU, Component_SKU, Component_Quantity",
    "rows": [{
      "uid": "3", "sku": "SET-WINTER", "label": "SET-WINTER",      # "New set" with no SKU
      "open": False, "chips": ["HAT-001 ×1", "SCARF-02 ×1"], "more_chips": "",   # "+3 more"
      "problem": "",
      "editor": None,   # the open set: {"sku_problem": "", "components_problem": "",
                        #   "components": [{"sku", "quantity", "problem", "invalid": False}]}
    }],
  },
}
```

A row lists at most six chips. The list shows at most 500 rows; past that `more` reads "Showing 500 of
{n}. Filter to find the rest." `count` reads "1 set". `no_hits`: "No set matches “{filter}”."

### 4.7 The page

```
Sets                                                    [+ Add set]
A set SKU on an order is replaced by its components before stock is allocated.
┌──────────────────────────────────────────────────────────────────┐
│ [Filter by SKU or component]        211 sets  [Import ▾] [Export] │
│ SET-WINTER   [HAT-001 ×1] [SCARF-02 ×1] [GLOVE-7 ×2]           ✕ │
│ [SET-GIFT            ]                                         ✕ │
│   Components  [CARD-01      ] × [1 ]  ✕                          │
│               [BOX-S        ] × [1 ]  ✕                          │
│               + Add component                            [Done]  │
└──────────────────────────────────────────────────────────────────┘
```

- One card. Its bar: the filter (kit `.input`, 260px, a magnifier), the count in `--text-secondary`, then
  Import (a `.btn.secondary.compact` that opens a menu) and Export (`.btn.secondary.compact`, disabled
  with no sets).
- The Import menu: the hint as a `.menu-group` line, then "Add and update sets…" and "Replace all sets…".
- A row is the grid `minmax(0, 1fr) auto`, padding `12px 16px`, a `--border-subtle` rule above it: the SKU
  in bold mono (a button that opens the editor), the chips beside it on a wrapping line (the Rules chip:
  22px, mono, `--surface-raised`, `--border`, radius 6px), then a ghost ✕ "Delete set".
- Open: the SKU becomes a field (mono, 260px). Under it the editor, in the Rules editor's grid (a 9pt bold
  secondary label column, then the content): "Components", one row per component on the grid
  `minmax(140px, 260px) 16px 72px 28px` (SKU field mono, "×", quantity field mono, ghost ✕ "Remove
  component"), its problem under it; "Add component" (ghost, plus glyph); the foot with "Done" (secondary)
  on the right.
- Empty: the kit's `.state` in a card: the title, the sentence, a primary "Add set" and a secondary "Import
  from CSV…" (`sets-merge`). The page head has no action then.
- Add set focuses the new set's SKU field. Add component focuses the new row's SKU. A removed component
  hands focus to Add component. A deleted set hands focus to the filter.

Keys: `set-add`, `sets-filter`, `sets-import`, `sets-import-merge`, `sets-import-replace`, `sets-export`,
`set-{uid}-sku`, `-delete`, `-comp-add`, `-done`, `-c{c}-sku`, `-c{c}-quantity`, `-c{c}-remove`.

## 5. Weight (`gui/settings/weight_state.py`, `gui/web/settings_weight.js`)

`WeightDraft(weight_config: dict, column_mappings: dict, stock_csv_delimiter: str)`. It owns
`config_data["weight_config"]`: `{volumetric_divisor, products: {sku: {name, length_cm, width_cm,
height_cm, no_packaging}}, boxes: [{name, length_cm, width_cm, height_cm}]}`. An empty config loads as
divisor 6000, no products and no boxes.

### 5.1 Loading

- `divisor`: the stored number as text, an integer without a fraction.
- A product: `{uid, sku, name, l, w, h, no_packaging, stored}`. A box: `{uid, name, l, w, h, stored}`.
- A dimension is text: `""` for a missing or zero value, else the number in `g` format (`12.0` reads `12`).

A dimension's text is read as a number with a comma or a point as the decimal mark; empty is 0. It is
valid when it is a finite number, 0 or more.

### 5.2 The edit actions

| action | args | effect |
|---|---|---|
| `divisor` | `[text]` | |
| `product_filter` | `[text]` | The list shows products whose SKU or name contains it, ignoring case. A product with no SKU is always listed |
| `product_add` | `[]` | An empty product, first in the list |
| `product_remove` | `[uid]` | |
| `product_text` | `[uid, name, text]` | `name` is `sku`, `name`, `l`, `w` or `h` |
| `product_no_packaging` | `[uid, on]` | `on` is a boolean |
| `box_add` | `[]` | An empty box, last in the list |
| `box_remove` | `[uid]` | |
| `box_text` | `[uid, name, text]` | `name` is `name`, `l`, `w` or `h` |
| `reveal` | `[key]` | Lists the product a `data-key` belongs to, whatever the filter and the limit |

### 5.3 What blocks Save, and what is only said

| | Text | Key | Blocks |
|---|---|---|---|
| Divisor not a whole number from 1 to 100000 | Type a whole number from 1 to 100000. | `divisor` | Yes |
| A dimension that is not a number, 0 or more | Type a number, 0 or more. | `product-{uid}-{l,w,h}`, `box-{uid}-{l,w,h}` | Yes |
| A product whose SKU an earlier product has | {sku} is in the list twice. | `product-{uid}-sku` | Yes |
| A product with no SKU and any other value | Type a SKU, or this row isn't saved. | | No |
| A box with no name and any dimension | Type a name, or this row isn't saved. | | No |

- `blocker()`: `Set Divisor`, else `Fix product “{sku}”` (`Fix the new product`), else `Fix box “{name}”`
  (`Fix the new box`), for the first in that order.
- `validate()`: `Divisor: {message}`, `Product “{sku}”: {message}`, `Box “{name}”: {message}`.

### 5.4 `collect()`

Updates the live dict in place and returns it: `volumetric_divisor` as an `int`; `products` rebuilt in list
order as `{sku stripped: {**stored, "name": stripped, "length_cm": float, "width_cm": float, "height_cm":
float, "no_packaging": bool}}`; `boxes` as `[{**stored, "name": stripped, "length_cm", "width_cm",
"height_cm"}]`. A product with no SKU and a box with no name are left out. A value that blocks Save is
written as typed.

### 5.5 Volumetric weight, as drawn

`L × W × H ÷ divisor`, rounded to 4 places, in `g` format, with " kg": `0.2 kg`. `""` when a dimension is
0 or the divisor is not valid.

### 5.6 Import and export

The three imports keep today's behaviour and move out of the widget, as functions over a DataFrame read
with `dtype=str`:

| kind | Dialog title | Reads | Toast | Toast action |
|---|---|---|---|---|
| `products-stock` | Import SKUs from Stock CSV | The file split by `resolve_delimiter(path, stock_csv_delimiter, "stock")`. The SKU column is the stock mapping's, else the first of `SKU`, `Артикул`, `sku`, `Article`. The name column is the mapping's `Product_Name`. A SKU not listed is appended with its name | Added {n}. Skipped {m} already existing. | |
| `products-dims` | Import Product Dimensions from CSV | The file split by `detect_csv_delimiter`. Columns found by today's candidate lists, ignoring case. A SKU not listed is appended. A SKU already listed is skipped, or with `update` takes the file's name, dimensions and No packaging | Added {n}. Updated {u}. Skipped {k} already in the table. (each part only when not zero, "Added" always) | Update them, when any was skipped |
| `boxes` | Import Boxes from CSV | The same, by box name | The same | The same |

Failures the operator can act on are `FileProblem`s with today's sentences: "No SKU column found" / "Check
the Stock mapping page, then import again." (stock); "No SKU column found" / "Available columns:
{columns}. Expected one of: SKU, Артикул, Article, Код." (dimensions); "No box name column found" /
"Available columns: {columns}. Expected one of: Name, Box Name, Size, Box." Any other failure: "The SKUs
weren't imported", "The dimensions weren't imported", "The boxes weren't imported", with "Details are in
Logs."

| kind | Dialog title, default name | Writes | Toast |
|---|---|---|---|
| `products` (export) | Export Product Dimensions to CSV, `weight_products.csv` | `SKU; Name; L (cm); W (cm); H (cm); No Packaging`, `;`-separated, `utf-8-sig`, every product as shown | Exported {n} products. |
| `boxes` (export) | Export Boxes to CSV, `weight_boxes.csv` | `Name; L (cm); W (cm); H (cm)` | Exported {n} boxes. |

Other failures: "The products weren't exported", "The boxes weren't exported".

### 5.7 `view()`

```python
{
  "page": "weight", "title": "Weight",
  "subtitle": "Product and box sizes, for volumetric weight and the box an order needs.",
  "action": "",
  "weight": {
    "divisor": {"value": "6000", "unit": "cm³ per kg", "problem": "",
                "hint": "Volumetric weight is L × W × H ÷ divisor. 6000 is DPD and Speedy; 5000 is DHL and FedEx."},
    "products": {
      "text": "Each SKU's size in cm. No packaging: the SKU ships as it is and needs no box.",
      "filter": "", "filter_placeholder": "Filter by SKU or name",
      "count": "131 products, 12 with no size", "no_hits": "", "more": "",
      "empty": "No products yet. Add one, or import them from a CSV.",
      "can_export": True,
      "heads": ["SKU", "Name", "L", "W", "H", "Vol. weight", "No packaging"],
      "rows": [{"uid": "7", "sku": "TEE-01", "name": "T-shirt", "l": "30", "w": "20", "h": "2",
                "weight": "0.2 kg", "no_packaging": False,
                "invalid": [],              # of "sku", "l", "w", "h"
                "problem": "", "hint": ""}],
    },
    "boxes": {
      "text": "The boxes orders are packed in. The analysis picks the smallest one an order fits.",
      "note": "order_min_box holds the box's name, or NO_BOX_NEEDED, NO_BOX_FITS or UNKNOWN_DIMS.",
      "empty": "No boxes yet.",
      "can_export": False,
      "heads": ["Name", "L", "W", "H", "Vol. weight"],
      "rows": [{"uid": "2", "name": "S", "l": "20", "w": "15", "h": "10", "weight": "0.5 kg",
                "invalid": [], "problem": "", "hint": ""}],
    },
  },
}
```

A product has "no size" when any of its three dimensions is 0. `count` reads "131 products" when every one
has a size, and "1 product". The products list shows at most 200 rows, plus the revealed one; past that
`more` reads "Showing 200 of {n}. Filter to find the rest." `no_hits`: "No product matches “{filter}”."

### 5.8 The page

```
Volumetric weight
  Divisor   [6000] cm³ per kg     Volumetric weight is L × W × H ÷ divisor. 6000 is DPD and Speedy; …
Products                                    [Import ▾] [Export] [+ Add product]
  [Filter by SKU or name]                         131 products, 12 with no size
  SKU        Name            L     W     H    Vol. weight  No packaging
  [TEE-01 ] [T-shirt     ] [30 ] [20 ] [2  ]   0.2 kg       (○)      ✕
  Showing 200 of 3,412. Filter to find the rest.
Boxes                                       [Import…] [Export] [+ Add box]
  Name       L     W     H    Vol. weight
  [S      ] [20 ] [15 ] [10 ]  0.5 kg                                ✕
```

- **Volumetric weight:** a card with one `.card-row`: "Divisor", a mono field 96px wide, the unit, and the
  hint or the problem under it.
- **Products:** a card. Its head: the title, the text, and Import (a menu: "SKUs from a stock CSV…",
  "Dimensions from a CSV…"), Export and "Add product" (`.btn.secondary`). Then the bar (filter and count),
  the heads line, the rows, and the `more` line. With no product the `empty` sentence stands in for the
  bar and the table.
- A product row is the grid `minmax(120px, 1fr) minmax(120px, 1.4fr) 64px 64px 64px 96px 96px 28px`, gap
  8px, padding `4px 16px`: SKU (mono), Name, L, W, H (mono, `inputmode="decimal"`), the weight in mono
  secondary, the kit `.switch` (`aria-label` "No packaging"), a ghost ✕ "Remove product". The heads line is
  the same grid in 9pt bold secondary. A field named in `invalid` has `.invalid`. The row's problem or hint
  spans the row under it.
- **Boxes:** the same card without a filter: Import… (`boxes`), Export, "Add box"; the `note` as a `.hint`
  under the table. A box row is `minmax(120px, 1fr) 64px 64px 64px 96px 28px`.
- Add product focuses the new row's SKU; Add box, the new row's name. A removed row hands focus to its Add
  button.
- At the dialog's minimum the page column is about 812px: the product grid fits, and SKU and Name shrink.

Keys: `divisor`, `products-import`, `products-import-stock`, `products-import-dims`, `products-export`,
`product-add`, `products-filter`, `product-{uid}-{sku,name,l,w,h}`, `-no-packaging`, `-remove`;
`boxes-import`, `boxes-export`, `box-add`, `box-{uid}-{name,l,w,h}`, `-remove`.

## 6. Reports (`gui/settings/reports_state.py`, `gui/web/settings_reports.js`)

`ReportsDraft(packing_configs: list, stock_configs: list, analysis_df)`. It owns
`config_data["packing_list_configs"]` and `["stock_export_configs"]`. The two kinds are `packing` and
`stock`.

### 6.1 Loading

One entry per stored config, in stored order: `{uid, kind, name, filename, filters, exclude, columns,
stored}`. A config that is not a dict loads as an empty report.

- `name`, `filename` (`output_filename`): as text.
- A filter is `{field, operator, value}`: `operator` through `normalize_operator` (the legacy `!=` reads
  "does not equal"); `value` as text, a list joined by ", ". A filter that is not a dict is dropped.
- `exclude` (packing only): `exclude_skus` joined by ", ".
- `columns` (packing only): the stored list.

### 6.2 The edit actions

| action | args | effect |
|---|---|---|
| `open` | `[uid]` | Opens that report's editor and closes any other |
| `close` | `[]` | |
| `reveal` | `[key]` | Opens the report a `data-key` belongs to |
| `report_add` | `[kind]` | Appends an empty report to that kind and opens it |
| `report_delete` | `[uid]` | |
| `report_move` | `[uid, dir]` | `"up"` or `"down"`: one place, inside its kind |
| `report_name` | `[uid, text]` | |
| `report_filename` | `[uid, text]` | |
| `report_exclude` | `[uid, text]` | Packing only |
| `filter_add` | `[uid]` | Appends `{field: the first offered field, operator: "equals", value: ""}` |
| `filter_remove` | `[uid, f]` | |
| `filter_field` | `[uid, f, field]` | |
| `filter_operator` | `[uid, f, operator]` | One of `REPORT_FILTER_OPERATORS`. The value is cleared when the new operator takes another kind of value (`rules_state.value_kind`) |
| `filter_value` | `[uid, f, text]` | |
| `column_add` | `[uid, name]` | Packing only. Appends one of the offered columns |
| `column_remove` | `[uid, name]` | |

### 6.3 Fields, values and columns

- **Fields offered:** `report_filter_fields(analysis_df)`, as one group with no label. A stored field that
  is not offered is listed first and kept, marked "Not available" only when there is an analysis.
- **The value control** is the rule condition's (phase 8 spec §4.4): none, a date, or text with at most
  200 suggestions for `equals` and `does not equal` on a column of the analysis.
- **Columns offered** (packing only): `report_filter_fields(analysis_df)`, plus `Repeat`, less the chosen
  ones.

### 6.4 The match count

`count_matches(analysis_df, filters)` on the report's filters, cached by the filters' JSON for the draft's
life. `match_text` words it, as today: "Run an analysis to see how many orders this report matches." /
"Matches no orders. Check the filters." / "Matches {n} orders · {m} rows". A count that raises reads
"Can't count matches for these filters." `warn` is true only for "Matches no orders".

### 6.5 Nothing blocks Save

As today. `blocker()` is `None` and `validate()` passes. One thing is said: a report with no file name
carries the note "No file name yet, so this report can't be generated."

### 6.6 `collect()`

`{"packing_list_configs": [...], "stock_export_configs": [...]}` in list order. Each report is `{**stored,
"name", "output_filename", "filters"}`. A packing list also writes `exclude_skus` (`parse_sku_list` of the
text) and `columns` when any is chosen; with none chosen the `columns` key is removed. The draft adds
neither key to a stock export.

### 6.7 `view()`

```python
{
  "page": "reports", "title": "Reports",
  "subtitle": "The packing lists and stock exports this client generates from Results.",
  "action": "",
  "reports": {"groups": [{
    "kind": "packing", "title": "Packing lists", "text": "Generated in this order.",
    "add": "Add packing list",
    "empty": "No packing lists yet. Add one, then generate it from Results after an analysis.",
    "rows": [{
      "uid": "1", "name": "DHL", "label": "DHL",                 # "Untitled report" with no name
      "filename": "DHL.xlsx", "open": False, "can_up": False, "can_down": True,
      "summary": [{"t": "bold", "v": "Shipping_Provider"}, {"t": "text", "v": "equals"},
                  {"t": "chip", "v": "DHL"}],                     # joined by {"t": "join", "v": "and"}
      "match": {"text": "Matches 14 orders · 31 rows", "warn": False},
      "note": "",
      "editor": None,
    }],
  }, {"kind": "stock", "title": "Stock exports", "text": "Generated in this order.",
      "add": "Add stock export",
      "empty": "No stock exports yet. Add one, then generate it from Results after an analysis.",
      "rows": []}]},
}
```

A report with no filter has the summary `[{"t": "muted", "v": "Every fulfillable order."}]`. The open
report's `editor`:

```python
{
  "filename_hint": "The file's name in the session's folder, e.g. DHL.xlsx.",
  "filters_hint": "An order line is listed when it passes every filter.",
  "field_groups": [{"label": "", "fields": ["Destination_Country", ...]}],
  "operators": [...],                          # REPORT_FILTER_OPERATORS
  "filters": [ ... ],                          # a rule condition's view, each (phase 8 spec §4.7)
  "exclude": {"value": "SKU-1, SKU-2", "placeholder": "SKU-1, SKU-2",
              "hint": "Lines with these SKUs are left off the list."} | None,
  "columns": {"chips": ["Order_Number", "SKU"], "candidates": ["Quantity", ...],
              "hint": "Printed in this order. None chosen: the default layout.",
              "add_title": ""} | None,          # "Every column is chosen." with no candidate
}
```

`exclude` and `columns` are `None` on a stock export. A filter's `problem` and `hint` are `""` and its
`invalid` is false; `field_invalid` is true for a field that is not offered while there is an analysis.

### 6.8 The page

```
Packing lists                                       [+ Add packing list]
Generated in this order.
  DHL   DHL.xlsx      Shipping_Provider equals [DHL]
                      Matches 14 orders · 31 rows                  ↑ ↓ ✕
  [DPD            ]                                                ↑ ↓ ✕
    File name  [DPD.xlsx        ]   The file's name in the session's folder, e.g. DHL.xlsx.
    Filters    [Shipping_Provider ▾] [equals ▾] [DPD      ] ✕
               + Add filter         Matches no orders. Check the filters.
    Exclude SKUs [               ]  Lines with these SKUs are left off the list.
    Columns    [Order_Number ✕] [SKU ✕] [+ Add column]
               Printed in this order. None chosen: the default layout.
                                                                 [Done]
Stock exports                                       [+ Add stock export]
```

- One card per kind: `.card-head` with the title, the text and the Add button (`.btn.secondary`), then the
  rows, or the `empty` sentence.
- A row is the grid `minmax(0, 1fr) auto`, padding `12px 16px`, a `--border-subtle` rule above it. Its
  text: the name in bold (a button that opens the editor), the file name in mono secondary; under them the
  summary line (the Rules summary's parts), the match line in `--text-secondary`
  (`--status-warning` when `warn`), and the note as a `.problem` line. Its actions: up, down (24px ghost
  icon buttons, greyed at the kind's edge) and a ghost ✕ "Delete report".
- Open: the name becomes a field. The editor is the Rules editor's grid with the lines "File name" (a mono
  field, 260px, its hint beside it), "Filters" (the shared condition row per filter, "Add filter", then the
  hint and the match line), "Exclude SKUs" (a field and its hint), "Columns" (the phase 7 chips, each with a
  ✕, and an "Add column" menu of the candidates; the hint under them), and the foot with "Done".
- Add focuses the new report's name. A removed filter hands focus to Add filter. A deleted report hands
  focus to its kind's Add button. A move keeps focus on the button pressed, or on its opposite at an edge.

Keys: `report-add-{kind}`, `report-{uid}-name`, `-up`, `-down`, `-delete`, `-filename`, `-filter-add`,
`-f{f}-field`, `-f{f}-op`, `-f{f}-value`, `-f{f}-remove`, `-exclude`, `-column-add`,
`-column-remove:{name}`, `-done`.

## 7. Tag categories (`gui/settings/tags_state.py`, `gui/web/settings_tags.js`)

`TagsDraft(tag_categories: dict)`. It owns `config_data["tag_categories"]`: `{"version": 2, "categories":
{id: {label, color, order, tags, sku_writeoff: {enabled, mappings: {tag: [{sku, quantity}]}}}}}`.

### 7.1 Loading

A dict with no `version` is the categories themselves (the old format). One entry per category that is a
dict, sorted by `order` (999 when missing), ties in stored order: `{uid, id, label, tags, writeoff,
mappings, stored}`.

- `label`: as text, the ID when missing. `tags`: each as text.
- `writeoff`: `sku_writeoff.enabled`.
- `mappings`: one `{tag, sku, quantity, stored}` per stored write-off, in stored order; `quantity` as text
  in `g` format. An entry that is not a dict, or has no `sku` or no `quantity`, is dropped, as today.

### 7.2 The edit actions

| action | args | effect |
|---|---|---|
| `open` | `[uid]` | Opens that category's editor and closes any other |
| `close` | `[]` | |
| `reveal` | `[key]` | Opens the category a `data-key` belongs to |
| `cat_add` | `[]` | Appends a category named "New category" with no tags, and opens it |
| `cat_delete` | `[uid]` | |
| `cat_move` | `[uid, dir]` | `"up"` or `"down"` |
| `cat_label` | `[uid, text]` | |
| `tag_add` | `[uid, text]` | The text stripped and upper-cased. Refused, with a sentence (§7.3), when it is empty, in this category, or in another |
| `tag_remove` | `[uid, tag]` | Also removes the write-offs mapped to it |
| `writeoff` | `[uid, on]` | `on` is a boolean |
| `map_add` | `[uid]` | Appends `{tag: the category's first tag, sku: "", quantity: "1"}`. Refused with no tag |
| `map_remove` | `[uid, m]` | |
| `map_tag` | `[uid, m, tag]` | One of the category's tags |
| `map_sku` | `[uid, m, text]` | |
| `map_quantity` | `[uid, m, text]` | |

### 7.3 A refused tag

`tag_add` that is refused changes no value, sets the category's `tag_problem`, and returns true so the
page redraws. The next edit to that category clears it. Opening the row is not an edit.

| | Text |
|---|---|
| In this category | {TAG} is already in this category. |
| In another | {TAG} is already in {label}. A tag belongs to one category. |

### 7.4 What blocks Save

| | Text | Key |
|---|---|---|
| No name | Type the category's name. | `cat-{uid}-label` |
| A tag an earlier category also has (stored that way) | {TAG} is also in {label}. Remove it from one. | `cat-{uid}-tag-input` |
| A write-off with no SKU | Type the SKU to write off. | `cat-{uid}-m{m}-sku` |
| A write-off quantity that is not a number from 0.01 to 999.99 | Type a number from 0.01 to 999.99. | `cat-{uid}-m{m}-quantity` |
| The same tag and SKU twice | {sku} is mapped to {tag} twice. | `cat-{uid}-m{m}-sku` |

Write-offs are checked whether the switch is on or off: they are drawn either way.

- `blocker()`: `Fix category “{label}”`; `Name category {n}` when it has no name ({n} is its place in the
  list).
- `validate()`: every problem as `Category “{label}”: {message}`, then whatever
  `validate_tag_categories_v2(collect()["tag_categories"])` still reports.

### 7.5 `collect()` and the ID

Writes into the live dict in place: `version` 2, and `categories` rebuilt in list order, so the stored
order is the list's. Other top-level keys stay. (A dict in the old format is cleared first: its top-level
keys were the categories.) Each category is `{**stored, "label", "color": the stored colour or
DEFAULT_TAG_COLOR, "order": its place from 1, "tags", "sku_writeoff": {**stored sku_writeoff, "enabled",
"mappings": {tag: [{**stored, "sku": stripped, "quantity": float}]}}}`. A quantity that blocks Save is
written as typed. A category that had no `sku_writeoff` stored, and has no write-off and the switch off,
gets no such key: an untouched profile is written back as it was, but for `order`.

A category that loaded keeps its ID. A new one's ID is made by `collect()` from its name: lower-cased,
every run of characters outside `a-z0-9` turned into one `_`, the `_` at either end removed; `category`
when nothing is left; made unique with `_2`, `_3`. `mark_clean(snapshot)` with a snapshot (the window calls
it after a save) fixes each new category's ID at what `collect()` gives it then.

`DEFAULT_TAG_COLOR` is `#9E9E9E`, moved here from the deleted dialog with its `style-lint: allow` mark: it
is data, not a theme value.

### 7.6 `view()`

```python
{
  "page": "tags", "title": "Tag categories",
  "subtitle": "The internal tags an order can carry, in groups. A tag belongs to one category.",
  "action": "Add category",              # "" when there is no category
  "tags": {
    "empty": {"title": "No tag categories yet",
              "text": "Tags mark orders for packing and for reports. Group them into categories here.",
              "action": "Add category"} | None,
    "count": "7 categories, 26 tags",
    "rows": [{
      "uid": "2", "name": "Packaging", "label": "Packaging",     # "Unnamed category" with no name
      "open": False, "chips": ["BOX", "BAG"], "no_tags": "",     # "No tags yet."
      "badge": "Write-off",                                       # "" when off
      "can_up": True, "can_down": True, "problem": "",
      "editor": None,
    }],
  },
}
```

The open category's `editor`:

```python
{
  "label_problem": "",
  "tags": ["BOX", "BAG"], "tag_placeholder": "Add tag", "tag_problem": "",
  "tag_hint": "Press Enter to add. Tags are stored in capitals.",
  "writeoff": {
    "on": True, "label": "Packaging write-off",
    "hint": "A stock export can write off the SKUs below for each order that carries the tag.",
    "can_add": True, "add_title": "",                 # "Add a tag first."
    "rows": [{"tag": "BOX", "sku": "PKG-BOX-S", "quantity": "1", "problem": "",
              "invalid": ""}],                         # "sku" or "quantity"
  },
}
```

`count` reads "1 category, 1 tag".

### 7.7 The page

```
Tag categories                                          [+ Add category]
The internal tags an order can carry, in groups. A tag belongs to one category.
  Packaging   [BOX] [BAG] [FRAGILE]          Write-off            ↑ ↓ ✕
  [Priority       ]                                               ↑ ↓ ✕
    Tags       [VIP ✕] [URGENT ✕] [Add tag     ]
               Press Enter to add. Tags are stored in capitals.
    Packaging write-off (●)  A stock export can write off the SKUs below for each order …
               [BOX ▾] [PKG-BOX-S   ] × [1   ] ✕
               + Add write-off                                    [Done]
```

- One card. Its first line is the count in `--text-secondary`.
- A row is the grid `minmax(0, 1fr) auto`, padding `12px 16px`, a `--border-subtle` rule above it: the name
  in bold (a button that opens the editor), the tags as chips on a wrapping line (or "No tags yet." in
  secondary), the "Write-off" badge (`.badge.neutral`); then up, down and a ghost ✕ "Delete category".
- Open: the name becomes a field (260px). The editor, in the Rules editor's grid: "Tags" (the phase 7
  chips, each with a ✕ "Remove {TAG}", then a 140px field with `data-enter="tag_add"`; under them the
  `tag_problem` as a `.problem` line, else the hint); "Packaging write-off" (the kit `.switch`, then the
  hint); the write-off rows on the grid `160px minmax(140px, 260px) 16px 72px 28px` (a `.select` of the
  category's tags, the SKU field mono, "×", the quantity field mono, a ghost ✕ "Remove write-off"), each
  with its problem under it; "Add write-off" (ghost, plus glyph; disabled and titled with no tag); the foot
  with "Done".
- Add category focuses the new category's name and selects it. A tag added keeps focus in the tag field. A
  removed tag hands focus to the tag field. A removed write-off hands focus to Add write-off. A deleted
  category hands focus to Add category.

Keys: `cat-add`, `cat-{uid}-label`, `-up`, `-down`, `-delete`, `-tag-input`, `-tag-remove:{tag}`,
`-writeoff`, `-map-add`, `-m{m}-tag`, `-m{m}-sku`, `-m{m}-quantity`, `-m{m}-remove`, `-done`.

## 8. Import, export and the toast

### 8.1 The drafts' side

`SetsDraft` and `WeightDraft` have:

- `imports: dict[kind, title]` and `exports: dict[kind, (title, default name)]`;
- `import_failed` and `export_failed`: `dict[kind, headline]`, for a failure that is not a `FileProblem`;
- `import_csv(kind, path, update=False) -> (text, can_update)`;
- `export_csv(kind, path) -> text`.

`FileProblem(headline, detail)` is raised for a failure the operator can act on.

### 8.2 The host (`gui/settings/web_host.py`)

- `importRequested(kind)`: ignored unless the current draft's `imports` has `kind`. `QFileDialog
  .getOpenFileName(self, title, "", "CSV Files (*.csv);;All Files (*)")`; nothing chosen ends it. Then
  `import_csv`. A `FileProblem` goes to `show_error(self, headline, detail)`. Any other exception is logged
  with its traceback and goes to `show_error(self, import_failed[kind], "Details are in Logs.")`; the page
  is pushed and `edited` is emitted all the same, since the import may have added rows before it failed. On
  success:
  push, `edited`, and `bridge.raise_toast(text, can_update)`.
- The host remembers `(kind, path)` of the last import that could update. `toastActionRequested` runs it
  again with `update=True`. `show_page` and any new import forget it.
- `exportRequested(kind)`: ignored unless `exports` has `kind`. `QFileDialog.getSaveFileName(self, title,
  default name, the same filter)`. Then `export_csv`; failures as above; on success `bridge.raise_toast(text)`.

### 8.3 The page

`settings.html` gains the toast after `#settings`: a `.toast` (`role="status"`, `aria-live="polite"`,
hidden) holding the text, a `.toast-action` button that reads "Update them" and a `.toast-close` button
with the ✕ glyph. `settings.js` shows it on `toastRaised`, for 4 s, or 8 s when the flag is set, which also
shows the action button. That button calls `bridge.toastAction()` and dismisses the toast. A new toast
replaces the one showing.

## 9. The window (`gui/settings/window.py`)

- Builds the four drafts with the values the Qt pages took, and adds them with `_add_page(draft, name,
  self._web_host)`.
- `WEB_PAGE_KEYS` gains `"Sets": "sets"`, `"Weight": "weight"`, `"Reports": "reports"`, `"Tag categories":
  "tags"`.
- `_add_page`'s branch for a Qt page, `PAGE_MARGIN_PX` as that branch used it, `_TagCategoriesPage`,
  `_dirty_poll`, `_poll_current_page`, `_poll_page` and `DIRTY_POLL_MS` go. `_on_settings_nav_changed` no
  longer polls the page being left. The Save shortcut still re-checks every page first.
- The stack keeps its one widget, the host. The frame is phase 10's.

## 10. Errors

| What fails | What the operator sees |
|---|---|
| A value Save refuses | The line under its control, the same line on the collapsed row, the nav mark, the footer's link, Save disabled |
| An import the operator can fix | A dialog with the headline and what to do (§4.5, §5.6) |
| Any other import or export failure | A dialog: "The … weren't imported/exported", "Details are in Logs." Logged with its traceback |
| A match count that raises | "Can't count matches for these filters." Logged at debug level |
| An edit the draft does not know | Dropped, logged at debug level (phase 7's rule) |

## 11. Decided here, because the mockup does not draw it

| Page | Decision |
|---|---|
| All | Sets, Reports and Tag categories are lists whose row opens in place, one at a time: the owner's phase 8 answer for Rules, applied again |
| All | A row's delete is a ✕ on the row, with no confirm: Cancel undoes it |
| Sets | Import and Export sit in the card's bar; the CSV's columns are named in the Import menu |
| Sets | A new set is first in the list, so it is in view among hundreds |
| Weight | Three cards: the divisor, Products, Boxes. Today's two sub-tabs go |
| Weight | A table of live fields, 200 products at a time (owner) |
| Weight | "Add product" puts an empty row first; Quick Add and Add Row go |
| Reports | One card per kind, each with its own Add; no page-head action |
| Reports | Columns are chips in print order |
| Tag categories | No colour, no order number, no ID (owner). Order is the list's |
| Tag categories | Write-offs are drawn whether the switch is on or off |

## 12. What changes from today's pages, on purpose

| Today | Phase 9 | Why |
|---|---|---|
| Renaming a set to another set's SKU overwrites that set | Blocked, and said | A quiet data loss |
| A dimension that is not a number is saved as 0; a product SKU typed twice keeps the later row | Blocked, and said | The same |
| A report's `equals` value becomes a menu of the analysis's values, and a stored value not in it is replaced on save | A text field with suggestions | The same (phase 8 did this for rules) |
| A key an editor does not draw is dropped on save | Kept | The same |
| A packing list's columns are saved in alphabetical order | In the order they were added | The chip pattern gives it |
| Reports reorder by dragging | Up and down | A handful of reports; no drag code |
| A category's display order is a number from 1 to 999 | Its place in the list, set by up and down. The stored order follows, so Results' "+ Tag" menu does too | Nothing read the number |
| Deleting a tag category asks to confirm | No confirm | Cancel undoes it, as on every other page |
| A category's colour and ID are edited | Neither is drawn | Owner's decision |
| Delete Selected on Weight | ✕ per row | No row selection on the web tier |
| A search box on Boxes | None | A handful of boxes |
| A write-off is added in a small dialog and cannot be edited | Edited in its row | No dialog on the web tier |
| The standalone Tag Categories dialog | Deleted | It had no caller |
| The unsaved mark follows a Qt page within 400 ms | At once | Every page reports its edits |

Unchanged: every config key and its shape; the CSV formats and the import rules; the toasts' sentences;
the match count; that nothing on Reports blocks Save; that a tag belongs to one category and is stored in
capitals; that removing a tag removes its write-offs.

## 13. Tests (test-first; the seams)

| File | Seam | Covers |
|---|---|---|
| `tests/test_settings_draft_sets.py` (new) | `SetsDraft`, no widget | Loading (order, odd values); every action of §4.2, the dropped ones included; every line of §4.3; `blocker()`, `blocker_key()`, `validate()`; `collect()` round-trips the fixture config, keeps a component's extra key, mutates the live dict; the filter; six chips and "+n more"; the 500 limit; both imports and the export against real files in `tmp_path`; `FileProblem` on a file with no sets |
| `tests/test_settings_draft_weight.py` (new) | `WeightDraft` | Loading; every action of §5.2; every line of §5.3; comma decimals; `collect()` round-trips, keeps extra keys, updates the live dict; the weight text; the count; the filter, the 200 limit and `reveal`; the three imports (added, skipped, `update`, each `FileProblem`) and the two exports against real files |
| `tests/test_settings_draft_reports.py` (new) | `ReportsDraft` | Loading (a legacy operator, a list value); every action of §6.2; a move stays inside its kind; the value is cleared only when the kind changes; a stored field and operator that are not offered are kept; the match text in its four states and its cache; the note; `collect()` round-trips, writes `columns` only when chosen, adds neither packing key to a stock export, keeps extra keys; nothing blocks |
| `tests/test_settings_draft_tags.py` (new) | `TagsDraft` | Loading (the old format, the sort, a malformed write-off); every action of §7.2; both refusals of §7.3 and that the next edit clears them; every line of §7.4; `collect()` round-trips the default categories, keeps `color` and extra keys, writes `order` as the place, rebuilds the dict in list order; a new category's ID (plain, non-ASCII, a clash) and that `mark_clean(snapshot)` fixes it; `validate()` passes `validate_tag_categories_v2` |
| `tests/test_settings_bridge.py` | `SettingsBridge` | `importFile`, `exportFile`, `toastAction` |
| `tests/test_settings_web_host.py` | `SettingsWebHost`, file dialogs patched | An import pushes, emits `edited` and raises the toast; a cancelled dialog does nothing; a `FileProblem` and any other failure reach `show_error`; "Update them" re-imports the same file with `update`; `show_page` forgets it; an export writes the file and raises the toast; a kind the draft does not have is ignored |
| `tests/test_settings_lists_page.py` (new) | The four pages in a real Chromium, fed views built by the drafts | Per page: the row's DOM and grid; opening a row; every control sends its action; typing keeps focus; the empty state; the problem line; focus after add and remove; the menus (Import, Add column, a write-off's tag); Enter adds a tag; the toast shows, its action calls the bridge, it dismisses; both themes read from tokens |
| `tests/test_settings_rules_page.py` | The Rules page | Passes unchanged: the shared condition row draws the same DOM |
| `tests/test_settings_lists_window.py` (new) | The window | Each of the four is a draft the host draws; an edit marks its page unsaved at once; a blocker from each of Sets, Weight and Tag categories reaches the footer and its link reveals the control; Save writes each page's keys; no poll timer exists |
| Existing window tests | | `test_settings_footer.py`, `test_settings_roundtrip.py`, `test_settings_unsaved.py`, `test_settings_nav.py`, `test_settings_page_contract.py`: updated where they reach into a Qt page or the poll, same assertions. `test_icon_usage_guard.py`: its known call sites, since the Qt filter row was the only user of `trash-2` |
| Deleted | | `test_settings_page_sets.py`, `test_settings_page_weight.py`, `test_settings_window_weight_quick_add.py`, `test_settings_page_reports.py`, `test_settings_report_editor.py`, `test_tag_categories_dialog.py`: their cases move to the draft tests |

Renders, saved under `docs/design/ui-refresh/renders/phase9/` and looked at before the PR, each the whole
dialog grabbed offscreen: Sets (the list, a set open, a problem, empty); Weight (the three cards, a problem
row); Reports (the list, a packing list open); Tag categories (the list, a category open with write-offs,
a refused tag); each in light, and each page's main state in dark.

## 14. Docs

- `docs/design/ui-refresh/roadmap.md`: phase 9 as built, with its differences.
- `CONTEXT.md`: **Set** and **Component** (a SKU on an order that the analysis replaces with other SKUs
  before stock is allocated; one of those SKUs and how many). **Generate order**: "set by the up and down
  buttons", not by dragging. **Tag category**: a named group of internal tags; a tag belongs to one.

## 15. Out of scope

- The web frame (phase 10).
- Drag reorder on Reports and Tag categories. Duplicating a report or a set.
- A check that a removed tag is not used by a rule or a report.
- A colour for tag categories anywhere in the app.
- A filter on Boxes or Tag categories.
- Virtual scrolling for the products list. The 200-row limit stands in for it.

## 16. Delivery

One PR on `dr/21-ui-refresh-phase-9-client-settings-on-th`. Gate:
`QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` and `ruff check .`. The PR says that `shared/`
does not change and Packing Tool needs no work.
