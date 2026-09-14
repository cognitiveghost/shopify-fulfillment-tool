# Phase 9 Bundle 13 — The 400px slot: detail pane and column manager (9.14 + 9.16)

- **Todoist:** bundle `6hQXj74R5rQW4rH3`; items 9.14 `6hQVj5mHWXRVGp9V`, 9.16 `6hQVj5rQvfJvH7QV`
- **Contract:** roadmap § Track W 9.14 and 9.16
  (`docs/superpowers/plans/2026-09-03-phase9-roadmap.md`), ADR 0001, ADR 0005,
  the Bundle 11 seam spec §5 and the Bundle 12 results-document spec
  (`2026-09-11-phase9-bundle12-results-doc-design.md`), which this bundle extends.
- **Artboards:** W4 and W6, read from the canvas (Claude Design project
  `75385f2c-4be2-446c-8e9d-bf90ee063ff7`, file `W Setup and Results.dc.html`,
  through DesignSync). §11 lists every departure from them.
- **Classification:** architectural. It fills the document's slot with two
  web-tier occupants, adds bridge members, moves a config key (ADR 0006), and
  deletes the Qt column manager.
- **Repo:** shopify only. No `shared/` change.

## 1. What this bundle delivers

The results document's slot beside the table gets its two occupants. The
**detail pane** (9.14) shows the cursor order. The **column manager** (9.16)
takes the same 400px while it is open, and the pane comes back on close.

It also gives the **additional columns** editor a home again, on
Settings › Mappings. Bundle 10 deleted its Settings page and Bundle 12 its
Results entry point, while `core.py` still reads the setting on every run.

It closes these items from Bundle 12's regression window: the pane and its
line table, the tag panel, the row menu and double-click (the pane replaces
both, §2), and Configure Columns. The selection bar and bulk actions stay
Bundle 14's. **Still no release until Bundle 14 merges.**

**Bundle done when:**
- At a 1310×692 page the table is 866 wide, the pane is 400×508, and the
  table still shows 17 rows.
- The pane renders ready, short, review (detected by the run), review (set by
  a person) and nothing-selected. A short verdict names a real SKU and both of
  the run's quantities.
- Hold, Mark fulfillable, Exclude from run, Remove this line, and adding and
  removing a tag each reach their handler. The pane re-renders from the orders
  that come back.
- Hide the pane leaves a 36px strip, and the table grows to 1242. Showing it
  again returns the table to 866.
- The column manager opens over a populated table without changing the
  table's width. Every column is reachable through its scroller. Order and
  visibility survive a restart, saved per client.
- Settings › Mappings lists additional columns, and Save writes them where
  the next analysis reads them.
- A manual screenshot of the pane's states in both themes is checked at
  Stage C by the owner, because the VM has no display.

## 2. Premises the code disproved, and what was decided

Owner answers, 2026-09-11, are marked (owner).

| Premise (brief or canvas) | What the code says | Decision |
|---|---|---|
| W4's actions: Print label preview, Ship the ready lines, Hold for PO, Fix the address, Change courier | None of these exist. What exists: toggle status (which moves stock), remove order, remove line, internal tags, copy. | **Existing verbs only** (owner), §6.6. |
| A "needs review" state about the address | No review or address data. A manual toggle (`analysis.toggle_order_fulfillment`) writes only `Order_Fulfillment_Status`, never `System_note`. | **Review covers two causes** (owner): a data problem detected by the run, or a status set by a person. Both come from data that already exists, §3.1. |
| "Held by Anna", a solid mark | No user identity is recorded. | The mark is solid and the copy is "Set by a person". No name is shown. |
| Row right-click menu and double-click toggle "come back in B13/B14" | — | **Not restored.** Every per-order verb lives in the pane (owner; W7: single-order actions are in the pane only). |
| Pane 400 default, 360 min, 480 max, 36px strip | — | **Fixed 400, Hide → 36px strip, auto-collapse when narrow, no drag-resize** (owner). |
| City and postcode in the identity line | No city data. `Destination_Country` exists. | Country. |
| "23 columns" including email, phone, gross, discount, internal id | Those fields do not exist. | The real order-level fields: 8 shown by default, 10 more, plus the client's extra columns (§6.8). |
| Column config via `TableConfigManager` | `client_config.ui_settings.table_view.views`, keyed by line-level names (`SKU`…) | New key `ui_settings.results_columns`, **per client, shared** (owner). Old views are ignored, not migrated. |
| The old panel's named views and "auto-hide empty columns" | — | **Auto-hide kept, named views dropped** (owner). |
| The additional columns editor | Its only UI was `ColumnConfigPanel`. B10 deleted `_ColumnConfigPage`, and B12 deleted Configure Columns. | **Settings › Mappings › Orders** (owner). Stored with the column mappings (ADR 0006). |
| Bundle 11 catalogue: `columns: list[{name, visible, pinned}]`, `setColumnVisible(name, visible)` | Titles, groups, defaults and pinning are rendering concerns, and the page owns them. | Python stores names only. The page sends whole lists (§4). |

## 3. Python seams

### 3.1 `order_verdict` and the payload

`gui/orders_view.py` gains a pure function:

```python
def order_verdict(status, notes: list, line_skus: list, has_sku: list) -> dict
```

- **Parse:** take the first note that contains `BLOCKER_PREFIX`. Strip a
  trailing ` [NO_SKU]` first, then take the text after the prefix and split it
  on `"; "`. Each part is matched in order:

  | Pattern | Problem |
  |---|---|
  | `^(?P<sku>.+): Insufficient stock \(need (?P<need>\d+), have (?P<have>\d+)\)$` | `{"code": "short", "sku", "need": int, "have": int}` |
  | `^(?P<sku>.+): Out of stock$` | `{"code": "out_of_stock", "sku"}` |
  | `^(?P<sku>.+): Missing/invalid quantity$` | `{"code": "invalid_quantity", "sku"}` |
  | anything else | `{"code": "other", "text": part}` |

  These strings come from `analysis.py`'s allocation, in both the legacy and
  FIFO paths, and a `Repeat; ` prefix before the blocker is allowed.
- **Drop** any problem whose `sku` is not in `line_skus`, meaning the line was
  removed after the run. Then remove duplicates of the same code and SKU.
- **Append** `{"code": "no_sku", "lines": k}` when `k` lines have `has_sku`
  exactly `False`.
- **Derive:**
  - `run_blocked = bool(problems)`
  - `fulfillable = status == "Fulfillable"`
  - `by_hand = fulfillable == run_blocked`, meaning the status disagrees with
    the run.
  - `state = "review"` when `by_hand` is true, or when any code is
    `invalid_quantity`, `no_sku` or `other`. Otherwise `"short"` when not
    fulfillable, else `"ready"`.
- **Returns** `{"state", "by_hand", "problems"}`, all JSON-native.

`order_payload(df)` adds, beside the Bundle 12 keys:
- `Verdict`: `order_verdict(...)`, fed from the order's status, its lines'
  `System_note`, `SKU` and `Has_SKU`. A missing column gives `""`, `None` or
  `True` respectively.
- On each line, `Short: bool`. It is true when the line's `SKU` is named by a
  `short` or `out_of_stock` problem.

After a line is removed, an order the run blocked can have no problem left
while it is still not fulfillable. It then reads as set by a person (on hold).
That is right: a person's edit made it so, and §6.3's copy for that case is
neutral.

### 3.2 `normalize_column_settings(raw) -> dict`

This goes in `gui/results_bridge.py` at module level. It is pure and has no
Qt.
- It returns `{"order": list[str] | None, "visible": list[str] | None,
  "auto_hide_empty": bool}`.
- A non-list `order` or `visible` becomes `None`, meaning "use the page's
  default". Non-strings are dropped, and duplicates are removed with order
  kept.
- `auto_hide_empty` is `bool(raw.get(...))`, default `False`. Default off, so
  Bundle 12's "Customer shows — until mapped" still holds for unmapped profiles.

### 3.3 Where additional columns are read (ADR 0006)

`shopify_tool/core.py` gains:

```python
def effective_additional_columns(column_mappings: dict, client_config: dict) -> list
```

It returns `column_mappings["additional_columns"]` when that key is present,
even as `[]`. Otherwise it returns
`client_config["ui_settings"]["table_view"]["additional_columns"]`, or `[]`.
Two call sites use it: the injection in `_run_analysis_and_rules` (≈L814–821),
which then injects the effective list, and the logging block at ≈L1304.

## 4. The bridge — catalogue amendments

Stage B edits the Bundle 11 §5.2 table so it stays the one catalogue: it adds
the rows below marked 13, and strikes the two amended rows with a pointer
here. Each slot emits a **Python-facing** signal. The bridge holds no
main-window reference, which is Bundle 12's pattern.

| Dir | Member | Kind | Notes |
|---|---|---|---|
| out | `columns: dict` | notify property | `{"order", "visible", "auto_hide_empty", "extras"}`. **Amends** `list[{name, visible, pinned}]`: the page owns titles, groups, defaults and pinning, and Python stores names. |
| out | `tagCategories: dict` | notify property | The profile's `_normalize_tag_categories(...)` output, for "+ Tag". Bundle 14 reuses it. |
| in | `holdOrder(orderNumber: str)` | slot → `holdRequested(str)` | |
| in | `fulfillOrder(orderNumber: str)` | slot → `fulfillRequested(str)` | |
| in | `excludeOrder(orderNumber: str)` | slot → `excludeRequested(str)` | Bundle 14's plural `excludeOrders` stays its own row. |
| in | `removeLine(orderNumber: str, lineIndex: int, sku: str)` | slot → `lineRemovalRequested(str, int, str)` | `lineIndex` is the position in that order's `lines`. `sku` guards against a line that has moved. |
| in | `addOrderTag(orderNumber: str, tag: str)` | slot → `tagAddRequested(str, str)` | Singular. Bundle 14's `addTag(list, tag)` stays. |
| in | `removeOrderTag(orderNumber: str, tag: str)` | slot → `tagRemovalRequested(str, str)` | Singular. |
| in | `copyText(text: str)` | slot, handled in the bridge | `QGuiApplication.clipboard().setText`. The page cannot count on `navigator.clipboard` under a `file://` base. |
| in | `setColumnOrder(names: list[str])` | slot | The whole order. |
| in | `setVisibleColumns(names: list[str])` | slot | **Amends** `setColumnVisible(name, visible)`: Python has never seen the defaults, so it cannot apply one toggle. |
| in | `resetColumns()` | slot | Sets `order` and `visible` to `None`, and keeps `auto_hide_empty`. |
| in | `setAutoHideEmpty(on: bool)` | slot | |

**Column slots:**
- Each one updates `columns` and emits `columnsChanged`.
- Each then emits the Python-facing `columnSettingsChanged(dict)`, carrying
  the three stored keys, without `extras`.
- The page ignores a `columnsChanged` whose value equals what it already
  applied, so its own write does not re-render twice.

**Python-facing API:**
- `set_column_settings(raw)` normalizes (§3.2), keeps `extras`, and emits.
- `set_tag_categories(categories: dict)` sets and emits.
- `set_orders(df)` also sets `columns["extras"]`: the order-level columns of
  `df` (`classify_columns`) that are not in `ORDER_LEVEL_COLUMNS`, in frame
  order. It emits `columnsChanged` only when that list changed.

## 5. Files on the web tier

- **New:** `gui/web/columns.js` holds the column registry (§6.8) and the
  column manager (§6.9).
- **New:** `gui/web/pane.js` holds the pane (§6.2–6.7).
- **Unchanged role:** `gui/web/results.js` keeps the state, table, filters and
  boot.
- **Loading:** `results.html` loads `columns.js`, then `pane.js`, then
  `results.js`, all `defer`. Classic scripts share one global lexical scope.
  No top-level statement in the first two may call a function defined in
  `results.js`: only function bodies do.
- **Styles:** stay in `results.css`, in new sections.
- **Rules:** Bundle 12's rules apply unchanged: tokens only, and no shadow,
  gradient, transition, transform or opacity. Hover reveals use `visibility`.
  The style lint covers the new files.

## 6. The document

### 6.1 The slot

`.table-area` becomes a two-column grid holding:
- `.table-wrap` (`position: relative; min-width: 0; min-height: 0`), which
  holds `#table`, `#results-empty` and `#results-no-match`;
- `#slot`.

Its `data-slot` attribute picks the tracks:

| `data-slot` | `grid-template-columns` | `column-gap` |
|---|---|---|
| `pane` | `minmax(0, 1fr) 400px` | `var(--spacing-md)` (12) |
| `columns` | `minmax(0, 1fr) 400px` | 12 |
| `strip` | `minmax(0, 1fr) 36px` | 0 |
| `none` | `minmax(0, 1fr)` | 0 |

- **Mode:**
  - `none` when there are no records;
  - else `columns` while the column manager is open;
  - else `strip` when collapsed;
  - else `pane`.
- **Collapsed** = `paneHidden || (narrow && !paneForced)`.
  - `narrow` means `.table-area`'s width is under **1192** (780 + 12 + 400),
    measured in `layout()` by the existing `ResizeObserver`.
  - `paneForced` is set by the strip's button while narrow. It clears when
    `narrow` turns false, and on Hide.
  - `paneHidden` lives for the page's lifetime and is not persisted.
- **Numbers:** content 1278 → table 866 with the pane, 1242 with the strip.
  Content 1832 → 1420. The table's own 780 minimum and horizontal scroll are
  unchanged.
- **Strip:** `#pane-strip` holds one 36×28 ghost button at the top with a
  chevron-left path, labelled "Show the pane". Below it is page surface.

### 6.2 Pane anatomy

`#pane` is on the `--surface-raised` plane with `--radius-md` and no border,
the KPI card's rule. Padding is 16. It is a flex column with a 12px gap, full
height, and `overflow: hidden`, so **the pane itself never scrolls**. The
sections appear in this order whenever an order is selected; only the verdict
block and the action labels change. With nothing selected the pane keeps only
the head and the centred empty block (§6.4).

1. **Head** (28px row):
   - `Order_Number` in `--font-family-mono`, `--type-heading-size`, bold;
   - the age as `3 h old` (`fmtAge` + " old"), caption, `--text-secondary`;
   - a spacer;
   - the position `3 of 44`, caption, secondary;
   - a 24×24 ghost icon button (chevron-right) labelled **"Hide the pane"**.
2. **Who:** one line, body size, ellipsis:
   `Customer · Destination_Country · Shipping_Provider`, skipping empty parts.
   "—" when all three are empty.
3. **Verdict** (`.verdict`, `data-state`, `data-by-hand`):
   - **Title row:** an 8px mark in the role colour, then the title in
     `--type-label-size`, bold, `--text`. The mark is a hollow ring (1.5px
     border, the `.chip::before` geometry) or, when `by_hand`, a solid disc.
   - **Text:** body size, `--text`, clamped to 4 lines.
   - **Source line:** caption, secondary, review state only.
   - **Role colour:** ready → `--status-success`, short → `--status-danger`,
     review → `--status-warning`.
4. **Numbers:** caption, secondary, tabular: `5 lines · 11 units · 204.30`.
   The value part is omitted when `Total_Price` is null.
5. **Lines** (`.lines`, `flex: 1; min-height: 0; overflow-y: auto`):
   - **Sticky header:** 28px, `--surface-raised`, caption bold secondary:
     `SKU`, `Product`, `Want`, `Left`.
   - **Rows:** 28px on the grid `112px minmax(0, 1fr) 48px 48px 24px`.
     - SKU: mono, ellipsis.
     - Product: secondary, ellipsis, with a `title` holding the full name.
     - Want: `Quantity`, right, tabular.
     - Left: `Final_Stock`, right, tabular; "—" when null.
     - Last cell: a `⋯` ghost button (24×24, aria-label "Actions for this
       line"), `visibility: hidden` until the row is hovered or has focus
       within.
   - **Short line** (`Short`): a 3px `--status-danger` bar on the row's left
     edge, drawn by an absolutely positioned `::before`. It is edged only, not
     tinted.
   - **Test hook:** each row is `.line` with `data-index`, and `.short` when
     short.
6. **Tags and notes:**
   - **`.pane-tags`** (flex, wrap, 4px gap), in this order:
     - static flag chips for Repeat, Unknown SKU and Low stock, which have
       the outlined pill look but no ×;
     - one chip per `Tag_List` entry, reading `vip ×`, which removes that tag
       on click;
     - a small ghost **"+ Tag"** button (§6.5).
   - **`.pane-notes`** (caption, secondary, clamped to 3 lines), in this
     order: `Notes`, then `Status_Note`, then `Shopify tags: a, b` when
     `Tags` is non-empty. **"No notes on this order."** when there is none of
     them.
7. **Actions** (`.pane-actions`, 32px row, left-aligned, 8px gap) — never a
   primary (§6.6):
   - the status verb, `.btn.secondary`;
   - **"Exclude from run"**, `.btn.danger`;
   - a `⋯` ghost icon button labelled "More actions for this order".

`.btn.secondary` and `.btn.danger` copy `QPushButton[role="secondary"]` and
`[role="danger"]` from `build_stylesheet` (`shared/theme.py` ≈L1178–1210),
including hover, pressed and disabled.

### 6.3 Verdict copy

In the templates below, `n` is the number of lines, `k` the number of short
lines, and `plural()` is the helper `results.js` already has.

| Case | Title | Text | Source line |
|---|---|---|---|
| `ready` | **Ships complete** | `All {n} lines are in stock and reserved for this order. One parcel, {units} units{, value}. Nothing is waiting on anyone.` (`n == 1`: `Its one line is in stock…`) | — |
| `short` | **Cannot ship: {k} of {n} lines are short** (`k == 1`: `… is short`) | problem sentences, then ` The other {n−k} lines are covered.` when `n > k` (`n − k == 1`: ` The other line is covered.`) | — |
| `review`, not by hand | **Fix the data before this ships** | problem sentences | **Detected by the run, not set by a person.** |
| `review`, by hand, fulfillable | **Marked fulfillable by hand** | `The run could not ship it. ` + problem sentences + ` Someone marked it fulfillable anyway.` | **Set by a person, not detected by the run.** |
| `review`, by hand, not fulfillable | **On hold** | `Nothing in this order is short now. It stays blocked until someone marks it fulfillable.` | **Set by a person, not detected by the run.** |

Problem sentences, in problem order:
- `short`: `There were {have} units of {sku} left for this order, and it wants {need}.`
- `out_of_stock`: `{sku} had none left.`
- `invalid_quantity`: `{sku} has no valid quantity in the orders file.`
- `no_sku`: `1 line has no SKU, so no stock can be matched to it.` /
  `{k} lines have no SKU, so no stock can be matched to them.`
- `other`: the text, with a full stop added unless it already ends in one.

The sentences quote the run's numbers, meaning the stock at this order's
turn. The **Left** column shows stock left after the whole run, which is what
Mark fulfillable draws on. They can differ, and each is labelled for what it
is.

### 6.4 Which order the pane shows

- **The cursor:** the pane shows `state.cursorKey`'s record while it is in
  `state.view`. Bundle 12 already moves the cursor on click, Ctrl-click,
  Shift-click and the arrows.
- **Position:** `{index + 1} of {view.length}`.
- **Re-render:** the pane renders inside `render()`, so every `orders` push
  refreshes it. After Exclude from run, the cursor order is gone, so the
  empty state shows.
- **Empty state** (`#pane-empty`, centred in the pane below the head row):
  - The head keeps only the Hide button.
  - Title (body bold): **"No order selected"**.
  - Text (secondary): **"Click a row to see whether it can ship and, if it
    cannot, why. ↑ ↓ moves through the {N} shown."**

### 6.5 The tag menu

"+ Tag" opens an in-page `role="menu"`, styled like `#filter-menu`. It opens
**upward**, anchored to the button, with a max height of 240 and its own
scroll.
- **Tags:** one group per `tagCategories` entry, headed by its `label`.
  Items are its `tags` that the order does not already carry. Choosing one
  calls `addOrderTag` and closes the menu.
- **Last row:** an input with the placeholder **"New tag"**. Enter adds the
  trimmed value when it is non-empty; Esc closes.
- **No categories:** only the input.
- **Closing:** Esc, an outside click, or a choice closes the menu, and focus
  returns to "+ Tag".

### 6.6 Actions

- **Status verb:**
  - A fulfillable record gets **"Hold"**, which calls `holdOrder`.
  - Any other record gets **"Mark fulfillable"**, which calls `fulfillOrder`.
  - The labels follow the status, not the review cause, so a verb keeps one
    name.
  - When free stock cannot cover the order, the existing handler's error
    banner reports it.
- **"Exclude from run":** calls `excludeOrder`, with no confirm, because it
  is undoable and the handler's toast carries Undo.
- **Order `⋯` menu:** "Copy order number", which calls `copyText`.
- **Line `⋯` menu:**
  - "Remove this line" calls `removeLine(order, index, sku)`.
  - "Copy SKU" calls `copyText`.
- **No optimistic update:** the pane changes only when the `orders` push
  comes back.

### 6.7 Keyboard and focus

- Every button is a real `<button>`. Menus follow `#filter-menu`: Esc closes
  them and returns focus to their opener.
- Hide moves focus to the strip's button, and Show moves it back to Hide.
- The table keeps its Bundle 12 keys.

### 6.8 The column registry (`columns.js`)

`COLUMNS` replaces Bundle 12's array. Keys are **stable persisted
identifiers**, and Bundle 12's eight keep their names, so its tests and
`data-sort` hooks still hold. `select` stays a fixed first cell and is not
managed.

| key | Payload field | Title | Group | Width | Max | Default | Cell |
|---|---|---|---|---|---|---|---|
| `status` | `Order_Fulfillment_Status` | Status | Order | 132 | — | shown, **pinned** | chip |
| `order` | `Order_Number` | Order | Order | 84 | — | shown, **pinned** | mono |
| `customer` | `Customer` | Customer | Customer | stretch | — | shown | text |
| `lines` | `Items` | Lines | Order | 56 | — | shown | int |
| `units` | `Units` | Units | Order | 56 | — | shown | int |
| `value` | `Total_Price` | Value | Money | 84 | — | shown | money |
| `courier` | `Shipping_Provider` | Courier | Shipping | 76 | — | shown | text |
| `age` | `Created_At` | Age | Order | 56 | — | shown | age |
| `type` | `Order_Type` | Type | Order | 64 | 120 | hidden | text |
| `reason` | `Blocker` | Reason | Order | 120 | 240 | hidden | text |
| `country` | `Destination_Country` | Country | Customer | 64 | 120 | hidden | text |
| `subtotal` | `Subtotal` | Subtotal | Money | 84 | — | hidden | money |
| `method` | `Shipping_Method` | Shipping method | Shipping | 120 | 240 | hidden | text |
| `internal_tags` | `Tag_List` | Internal tags | Tags & notes | 120 | 240 | hidden | list, `", "` |
| `shopify_tags` | `Tags` | Shopify tags | Tags & notes | 120 | 240 | hidden | text |
| `notes` | `Notes` | Notes | Tags & notes | 160 | 240 | hidden | text |
| `status_note` | `Status_Note` | Status note | Tags & notes | 120 | 240 | hidden | text |
| `repeat` | `_repeat` | Repeat | Tags & notes | 64 | — | hidden | `Repeat` or empty |
| `extra:<field>` | each `columns.extras` field | the field, `_` → space | Other | 120 | 240 | hidden | text |

- **Groups**, in order: Order, Customer, Money, Shipping, Tags & notes, and
  Other, which appears only when there are extras.
- **Cells:** int, money and age columns are right-aligned. Sort follows
  Bundle 12's `compare`: numbers numeric, text by `localeCompare`, empty last.
- **Effective order:**
  1. `status`, `order` first, always;
  2. then the saved `order` keys that exist;
  3. then the remaining keys in registry order, extras last.
- **Effective visible:**
  1. pinned columns are always shown;
  2. the rest follow the saved `visible` list when it is not null, else the
     defaults;
  3. then, when `auto_hide_empty` is on, a non-pinned column is hidden if its
     cell text is empty for **every** record. This state is **auto-hidden**:
     the user's choice is unchanged.
- **Widths:** Bundle 12's `measureColumns`, over visible columns only, capped
  at Max.
  - Customer stretches while visible. When it is hidden, a trailing
    `minmax(0, 1fr)` track holds an empty `.cell.filler` in every row, so no
    other column stretches.
  - `--table-min` = the fixed widths + (Customer visible ? its minimum : 0).
    Customer's minimum stays `max(120, 780 − fixed)`.
- **Sort:** hiding the sorted column clears the sort.
- **Sticky cells:** `select` and `status` stay sticky. `status` is always the
  first managed column.

### 6.9 The column manager

- **Opening:** a ghost button **`Columns {shown}/{total}`**
  (`aria-pressed`) sits in the filter bar between the count and `⋯`. It is
  disabled when there are no records. Opening sets `data-slot="columns"` and
  focuses the panel's search. ×, **Done** and Esc close it and return focus
  to the button.
- **Look:** `#columns-panel` uses the pane's plane, radius and padding (16):
  a flex column with 8px gaps.
  1. **Header** (40): **"Columns"** (label size, bold) above the live
     caption **"{shown} shown · {hidden} hidden"**, with a 32×32 ghost ×
     labelled "Close column manager" on the right.
  2. **Search** (32): **"Find a column"**, the `#search` look at full width.
     It matches titles as a case-insensitive substring. Groups with no match
     hide, and **drag handles hide while a query is typed**.
  3. **Scroller** (`flex: 1; min-height: 0; overflow-y: auto`).
     - **Group header**, 22px, sticky, `--surface-raised`: caption, bold,
       uppercase, `letter-spacing: 0.06em`, secondary — **`ORDER`** then
       ` 5 of 7` (shown of that group).
     - **Rows**, 30px, on the grid `16px 20px minmax(0, 1fr) auto`:
       - a drag handle, an inline grip-vertical SVG (six dots), secondary,
         absent on pinned rows;
       - a checkbox, which on pinned rows is checked and disabled;
       - the title, with ellipsis;
       - a right caption: **"pinned"**, **"empty"** (auto-hidden, with the
         title drawn secondary), or nothing.
  4. **Footer** (32): on the left a checkbox **"Hide empty columns"**; on the
     right **"Reset to defaults"** (ghost) and **"Done"** (secondary).
- **Arithmetic at a 508 table area:** 16 + 40 + 8 + 32 + 8 + S + 8 + 32 + 16,
  so **S = 348**. That holds the group headers plus about 11 rows of 30.
- **Toggle:** calls `setVisibleColumns` with the user-visible keys, before
  auto-hide.
- **Reset:** calls `resetColumns()` and applies the defaults locally.
- **Hide empty columns:** calls `setAutoHideEmpty`.
- **Drag** (HTML5): non-pinned rows are `draggable`.
  - Dragging over a row R draws a 2px `--focus-ring` insertion line (a
    `::before`) on R's top or bottom half, whichever the pointer is over.
  - Dropping moves the dragged key **before** R (top half) or **after** R
    (bottom half) in the table's **one** effective order. A drop before
    `status` or `order` lands after `order`.
  - The page applies it at once, then calls `setColumnOrder` with every key.
  - The row re-renders inside its own group. The table beside it shows where
    it went, which is the reason the manager sits in the slot.
- **Keyboard:** rows have `tabindex="0"`.
  - Space toggles the row.
  - Alt+↑ moves the column before the previous visible row of the list;
    Alt+↓ moves it after the next one. These are the same semantics as a
    drop.
- **Width:** opening from pane mode keeps the table's width (400 + 12 either
  way). Opening from the strip narrows the table once, on open, never
  mid-drag.
- **Test hooks:**
  - rows are `.col-row[data-key]`, group headers `.col-group[data-group]`;
  - the header caption is `#columns-count`.

## 7. Qt side

### 7.1 Wiring (`ui_manager._create_tab2_analysis_results`)

The lambdas resolve `self.mw.actions_handler` at call time, the file's
existing pattern.
- `holdRequested` → `actions_handler.set_order_fulfillable(n, False)`
- `fulfillRequested` → `set_order_fulfillable(n, True)`
- `excludeRequested` → `remove_entire_order`
- `lineRemovalRequested` → `remove_line`
- `tagAddRequested` → `add_internal_tag`
- `tagRemovalRequested` → `remove_internal_tag`
- `columnSettingsChanged` → `mw.schedule_results_columns_save`

### 7.2 `ActionsHandler` additions (`gui/actions_handler.py`)

- **`set_order_fulfillable(order_number, fulfillable: bool)`:** reads the
  order's current status, comparing order numbers as stripped strings. It does
  nothing when the order is missing or its status already matches; otherwise
  it calls `toggle_fulfillment_status_for_order`. This makes a stale page
  harmless.
- **`remove_line(order_number, line_index, sku)`:** takes that order's rows
  in frame order.
  - If `line_index` is out of range, or that row's `SKU` (stripped string)
    differs from `sku`, it logs a warning and returns.
  - Otherwise it calls `remove_item_from_order(order_number, sku,
    df.index.get_loc(label))`.
- **`add_internal_tag(order_number, tag)` / `remove_internal_tag(order_number,
  tag)`:** restore the logic Bundle 12 deleted. Read it with
  `git show 056e3c2:gui/main_window_pyside.py`: `_apply_tag_operation`,
  `add_internal_tag_to_order`, `remove_internal_tag_from_order`.
  - They mask by stripped order number and apply `tag_manager.add_tag` /
    `remove_tag` over `Internal_Tags`. Add creates the column as `"[]"` when
    it is missing; remove does nothing when the column is missing.
  - A blank tag after stripping is ignored.
  - They record undo `add_internal_tag` / `remove_internal_tag` with params
    `{"order_number", "tag"}`.
  - Then they follow the handlers beside them: `data_changed.emit()`,
    `save_session_state()`, `_update_undo_button()`, and
    `log_activity("Internal Tag", …)`.
  - No toast, because the pane shows the change.

### 7.3 Column settings: load and save

- **Load:** `MainWindow._load_client_data` returns `(shopify_config,
  column_settings)`. The second item is
  `normalize_column_settings(client_config.get("ui_settings", {}).get("results_columns"))`,
  and it replaces the `table_config` load.
- **Apply:** `_on_client_data_loaded` calls
  `self.results_bridge.set_column_settings(column_settings)`.
- **Save:** `schedule_results_columns_save(settings)`:
  - It captures `current_client_id` now and restarts a 500ms single-shot
    `QTimer`.
  - On timeout it runs a `Worker`: `load_client_config`, then
    `setdefault("ui_settings", {})["results_columns"] = settings`, then
    `save_client_config`.
  - A failure is `logger.warning` only: this is a layout preference, and the
    next change retries.

### 7.4 Tag categories

Wherever `MainWindow` sets `active_profile_config` (`load_client_config`, and
after Settings saves, if that reloads it), it also calls
`results_bridge.set_tag_categories(_normalize_tag_categories(cfg.get("tag_categories", {})))`.

### 7.5 Settings › Mappings › Additional columns

`OrdersMappingPage` (`gui/settings/mappings.py`) gains a third `FormSection`,
placed after the column mapping and before Courier Mappings.
- **Title:** **"Additional columns"**.
- **Description:** **"Orders-file columns the analysis carries through under
  their own names. Load headers from CSV to list the file's unmapped
  columns."**
- **Rows:**
  - one per entry: a checkbox labelled with `csv_name`;
  - a checkbox **"Order-level"**, with the tooltip **"Filled down onto every
    line of a multi-line order"**;
  - a secondary caption **"Not in this file"** when `exists_in_df` is `False`.
  - Both checkboxes stay enabled, so a column the file lacks can still be
    switched off.
- **No entries:** the caption **"No additional columns yet. Load headers from
  CSV to list the file's unmapped columns."**
- **Source:** the page's entries are `column_mappings["additional_columns"]`
  when that key exists. Otherwise they come from a fallback list the window
  passes in, read from the client config's `ui_settings.table_view` (the
  window has `profile_manager` and `client_id`).
- **Loading headers:** after the Orders page's "Load headers from CSV…" reads
  the headers, it also runs
  `discover_additional_columns(pd.DataFrame(columns=headers), {"orders":
  self.mapping_widget.get_mappings()}, entries)` and re-renders the rows.
  The mappings passed are the current, possibly unsaved, ones.
- **`collect()`:** writes `self.column_mappings["additional_columns"] =
  entries` into the live dict, then returns as today.
  `StockMappingPage` writes only `stock`, so the key survives.
- **`snapshot()`:** includes the entries.

### 7.6 Deleted

- **Modules:** `gui/column_config_dialog.py` and `gui/table_config_manager.py`,
  whole.
- **Tests:** `tests/test_column_config_dialog.py` and
  `tests/test_table_config_manager.py`.
- **`MainWindow`:** the `TableConfigManager` construction (≈L164–166) and the
  `table_config` plumbing in `_load_client_data` / `_on_client_data_loaded`.
- **`tests/test_message_routes.py`:** the `("gui/column_config_dialog.py", "*")`
  entry.
- **Comments:** the ones citing `ColumnConfigPanel`, in
  `gui/settings/report_editor.py` ≈L138 and `gui/report_selection_dialog.py`
  ≈L205, are reworded so they don't point at a deleted file.
- **Kept:** `ProfileManager`'s `ui_settings.table_view` defaults and any
  stored `views`, both untouched.

**Done check:** no file under `gui/` or `tests/` contains
`ColumnConfigPanel`, `ColumnConfigDialog`, `TableConfigManager`,
`table_config_manager` or `column_config_dialog`. This is a plain file-scan
test, like Bundle 12's.

## 8. Tests — the seams

1. **Pure Python** (no Qt):
   - `order_verdict`, one case per row:
     - fulfillable with no note → ready;
     - insufficient plus out of stock → short, with both problems and their
       numbers;
     - a `Repeat; Cannot fulfill: …` prefix;
     - a ` [NO_SKU]` suffix stripped;
     - `Has_SKU` False → review with `no_sku`;
     - missing/invalid quantity → review;
     - fulfillable with a blocker note → review, `by_hand`;
     - not fulfillable with no note → review, `by_hand`;
     - a problem for an absent SKU is dropped;
     - "Unknown reason" → `other`.
   - `order_payload` carries `Verdict`, and each line carries `Short`;
     `json.dumps(allow_nan=False)` passes.
   - `normalize_column_settings`: junk input, removing duplicates, the bool.
   - `effective_additional_columns`: the key present (including `[]`) wins;
     absent falls back; both absent → `[]`.
2. **Bridge, Python side:**
   - Each slot emits its signal with its arguments.
   - Column slots update `columns` and emit `columnSettingsChanged` without
     `extras`.
   - `resetColumns` keeps `auto_hide_empty`.
   - `set_orders` fills `extras` from a frame with an order-level extra
     column.
   - `copyText` sets the clipboard.
3. **`ActionsHandler`** (Qt, no Chromium):
   - `set_order_fulfillable` is a no-op when the status matches, and toggles
     when it doesn't.
   - `remove_line` refuses an out-of-range index and a SKU mismatch, and
     removes the right one of two same-SKU lines.
   - The internal tag add and remove change every line of the order, record
     undo, and undo restores.
4. **Document through Chromium** (`tests/test_results_pane.py`,
   `tests/test_results_columns.py`): reuse `results_lines` and the fixture
   pattern from `tests/test_results_document.py`. Add a frame builder with
   reason-code notes, `Final_Stock`, a hand-toggled order and a no-SKU order.
   - At 1310×692: `.table-wrap` is 866 wide and `#pane` is 400×508, with
     `data-visible-rows == 17`.
   - Nothing selected → `#pane-empty` reads "No order selected".
   - Clicking a short order → the title reads `Cannot ship: 1 of 3 lines is
     short` (§6.3's `k == 1` form), the text contains its SKU and both numbers, and one `.line.short`.
   - Ready, review-by-run and review-by-hand → their titles, source lines
     and `data-by-hand`.
   - The actions each reach their signal (`qtbot.waitSignal`):
     - Hold → `holdRequested`, and Mark fulfillable → `fulfillRequested`;
     - Exclude from run → `excludeRequested`;
     - the line menu's Remove this line → `lineRemovalRequested(order, i,
       sku)`;
     - a tag chip's × → `tagRemovalRequested`;
     - a "+ Tag" item → `tagAddRequested`, and so does the "New tag" input
       with Enter.
   - Hide → `data-slot="strip"` and the table is 1242; Show → 866.
   - At 1100×692 → the strip shows by itself. Its button opens the pane, and
     the scroller's `scrollWidth > clientWidth`.
   - Columns → `data-slot="columns"`, the table is still 866, and
     `#columns-count` reads `8 shown · 10 hidden`. Scrolling the scroller to
     the bottom brings the last `.col-row` into view.
   - Toggling `type` → `setVisibleColumns` includes `type`, and the header
     gains **Type**.
   - Alt+↑ on `age` → `setColumnOrder` puts `age` before `units`. A
     synthetic `DragEvent` drop does the same.
   - `bridge.set_column_settings({...})` → the header follows the saved order
     and visibility. This is the page half of surviving a restart.
   - Auto-hide on, with a frame whose `Subtotal` is empty everywhere and
     `subtotal` visible → no Subtotal header, and its row says "empty".
5. **Main window:**
   - `schedule_results_columns_save` then `_load_client_data`, over a temp
     `ProfileManager`, round-trips the settings. This is the Python half of
     surviving a restart.
   - Emitting `results_bridge.holdRequested` reaches
     `actions_handler.set_order_fulfillable` (monkeypatched).
6. **Settings:**
   - `OrdersMappingPage` without the key shows the fallback entries.
   - "Load headers" (with `QFileDialog` and `read_csv_headers` monkeypatched)
     lists the unmapped columns.
   - `collect()` writes `column_mappings["additional_columns"]`, and toggling
     a box changes `snapshot()`.
7. **§7.6's done check.**
8. **Unchanged:** the style lint over `gui/web`, and every Bundle 11 and 12
   bridge and document test. At 1310 the table is 866 ≥ 780, so there is
   still no horizontal scroll. At 780 the strip shows and the table still
   scrolls.

## 9. Not in this bundle

- **Bundle 14:** the selection bar, bulk actions, the web toast, and the
  plural `addTag` / `removeTag` / `excludeOrders`.
- **Pane features with no backing code:**
  - adding notes;
  - Add product in the pane;
  - shipping ready lines or splitting a parcel;
  - label preview;
  - address, courier change or purchase-order data.
- **Pane width:** drag-resize, and persisting the pane's hidden state.
- **Column manager:** named column views.
- **Old data:** removing the stored `ui_settings.table_view.views` or its
  `additional_columns`.
- **Toasts:** whether the Qt toasts that `remove_item_from_order` and
  `remove_entire_order` raise sit above the web view is Bundle 14's.

## 10. Build

Two new files, `gui/web/columns.js` and `gui/web/pane.js`. The existing
`--add-data "gui/web;gui/web"` already collects them. No new dependency.

## 11. Departures from the brief and the canvas

| Brief / canvas | This design | Why |
|---|---|---|
| W4 actions: Print label preview · Exclude / Ship the 3 ready lines · Hold for PO / Fix the address · Change courier | Hold or Mark fulfillable · Exclude from run · ⋯ Copy order number | Only verbs that exist (owner) |
| Review = an address problem; "Held by Anna" | Review = detected by the run, or set by a person; no name | No review data, no user identity (owner) |
| "Ships today, complete" | "Ships complete" | The data has no ship date |
| "Cannot ship as one parcel" | "Cannot ship: k of n lines are short" | Splitting a parcel is not an action here |
| "Someone has to decide before this ships" | "Fix the data before this ships" / "Marked fulfillable by hand" / "On hold" | One title per review cause, so the pane says which |
| "The missing units are on PO-8841" | Absent | No purchase-order data |
| City and postcode | Country | No city data |
| Delivery address block | Absent | No address data |
| "SKU LINE WANT FREE" | SKU · Product · Want · Left | Left is `Final_Stock`, and "free" would overstate it; product name kept for pickers |
| Pane 360–480 resize | Fixed 400 | Owner |
| "23 columns" with email, phone, gross, discount, internal id | 18 real columns plus the client's extras | Those fields do not exist |
| Five groups | Five, plus Other when extras exist | Extras have no natural group |
| "9 shown · 14 hidden", "Reset to the 9 defaults", "Columns 9/23" | "8 shown · 10 hidden", "Reset to defaults", "Columns 8/18" | Select is not a managed column; totals depend on the data |
| W6 subtitle "360px side panel" | 400 | W6's own note and 9.16 say 400 |
| Drag reorders within a group | A drop on any row reorders the table's one sequence | The table has one order; groups are for finding |
| W7: "Add product to order" in the pane | Stays in the screen overflow | Its dialog takes no order |
| Right-click menu and double-click back "in B13/B14" (Bundle 12 §1) | Not restored | The pane holds every per-order verb (owner) |
| Bundle 11 `columns: list[{name, visible, pinned}]`, `setColumnVisible` | `columns: dict`, `setVisibleColumns` | The page owns defaults and pinning (§4) |
| — | Additional columns editor on Settings › Mappings | Its only home was deleted (owner); ADR 0006 |
