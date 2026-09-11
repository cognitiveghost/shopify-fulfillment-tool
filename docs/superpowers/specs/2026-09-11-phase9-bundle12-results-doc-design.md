# Phase 9 Bundle 12 — The results document and its numbers (9.13 + 9.15)

- **Todoist:** bundle `6hQXj74V4RpmrcCV`; items 9.13 `6hQVj5Vq4PR3mHV3`, 9.15 `6hQVj5pmFv9m9QPV`
- **Contract:** roadmap § Track W 9.13 and 9.15
  (`docs/superpowers/plans/2026-09-03-phase9-roadmap.md`), ADR 0001, the
  Bundle 11 seam spec (`2026-09-11-phase9-bundle11-seam-design.md`), ADR 0005.
- **Artboards:** W3, W3b, W5, W5b. **Read from the canvas this time.** The
  Claude Design project is `75385f2c-4be2-446c-8e9d-bf90ee063ff7`, file
  `W Setup and Results.dc.html`, reached through DesignSync. §11 lists every
  departure from it.
- **Classification:** architectural. It replaces the Qt Analysis Results
  screen with a web document and adds two orders-file fields.
- **Repo:** shopify only. `display_xl` is already in `TYPE_SCALE`, so
  `shared/` does not change.

## 1. What this bundle delivers

The Analysis Results page becomes one `QWebEngineView` holding the
**results document**: a KPI strip, a filter bar, and the order table. The Qt
table, its filter row, the Qt KPI strip, the Qt detail pane, the selection bar
and the footer are deleted, not hidden.

**Bundle done when:**
- The document renders 312 orders in a page area of 1310×692 (the page at
  1366×768) with exactly **17** visible rows, and **28** at 1864×1004 (1920×1080).
- No horizontal scroll at 1310. The table scrolls horizontally only when the
  page is narrower than 812px (a window narrower than 868px).
- A search, a chip, a sort and a selection each work, and the selection
  reaches `SelectionHelper`.
- CUSTOMER and AGE show data for a profile that maps `Customer` and `Created_At`.
- A screenshot of the Results screen in which the Qt/web seam cannot be
  located. This is a manual check at Stage C on the dev box.

### The regression window (repo owner's decision, 2026-09-11)

The Qt screen is replaced now, and the pane slot stays empty. The following
leave `main` until Bundles 13 and 14 bring them back on the web tier:
- the order detail pane and its line table
- the tag panel
- the row context menu and the double-click status toggle
- the selection bar and its bulk actions
- Configure Columns and the hidden-columns indicator

Release builds ship only on a manual GitHub `release` event, so none of this
reaches a warehouse unless a release is cut. **Do not cut one until Bundle 14
merges.**

## 2. Premises the code disproved, and what was decided

| Premise (brief or canvas) | What the code says | Decision |
|---|---|---|
| CUSTOMER, AGE and ADDRESS columns | The analysis output (`analysis.py:1119`) has no customer, date, address or city. | Add optional `Customer` and `Created_At` orders-file fields (§3). **ADDRESS is dropped**, along with the ≥1600 column (owner). Existing profiles are **not** migrated and get no fallback: they show "—" until mapped in Settings › Mappings (owner). |
| NEEDS REVIEW card, "address, courier or price" | Nothing in the data marks an order for review. | The card is replaced by **Labels**: the courier label count, split by courier (owner). |
| "Ready" rows, "Ship complete" card | The stored value, the reports and today's screen all say Fulfillable. | **Fulfillable** everywhere (owner). "Short on stock" was already retired for **Blocked** (CONTEXT.md). |
| "Held by Anna" / solid mark | No person-set order status exists. The row status is `Order_Fulfillment_Status` plus the repeat flag. | Every status chip here has a hollow mark (system-derived). Hold is Bundle 13's. |
| Stock-file age chip "beside the Analysed chip" | Neither chip is set today (`CommandBar.set_status` has no caller). `analysis_completed_at` is in `session_info`, and the stock file is copied with `shutil.copy2`, which keeps its mtime. | Both chips are built (§7.2). |
| Re-run "secondary in the command bar" | `CommandBar` has one action slot, and it is styled primary. | `bind_action` gains a role; Results binds `run_analysis_button` as secondary (§7.2). |
| Export "is the Qt command bar's primary" (Bundle 11 §5.2) | The canvas draws "Export 268 orders" in the document's filter row, with Re-run in the bar. | The canvas wins. Export moves onto the bridge (§5). |
| Bridge slots `setSort` / `setFilterText` / `setFilterChips` (Bundle 11 §5.2) | No Python code reads sort or filter state. Reports and exports ignore the view. | **Removed.** The page owns its view state (ADR 0005). |
| "Virtualised" table | 312 rows × 9 cells is small, but the canvas pins 17 whole rows and no partial rows. | Windowed rendering at a fixed row height, in plain JS, with no library (§6.4). |

## 3. Data: `Customer` and `Created_At`

Two optional orders-file fields, carried exactly like `Total_Price`:

1. `gui/settings/mappings.py` — `OrdersMappingPage.OPTIONAL_FIELDS` gains
   `"Customer"` and `"Created_At"`.
2. `shopify_tool/profile_manager.py` — the new-profile `column_mappings.orders`
   defaults gain `"Shipping Name": "Customer"` and `"Created at": "Created_At"`.
   These are Shopify's export headers. So does `run_analysis`'s
   `column_mappings is None` fallback in `analysis.py`, which writes no profile.
   `profile_migrations.py` is **not** touched: there is no migration.
3. `shopify_tool/analysis.py`:
   - forward-fill both, beside the `Total_Price`/`Tags` forward-fills. A Shopify
     export writes them on an order's first line only.
   - add both to `base_columns`.
   - append both to the `output_columns` literal **after `"Lot_Details"`**, so
     the positional inserts at 3, 6 and 7 do not move. The existing
     `final_output_columns` filter drops them when absent.
4. `gui/orders_view.py` — `ORDER_LEVEL_COLUMNS` gains both.

`Created_At` stays the raw CSV string in the analysis frame. Only the payload
normalises it (§4). Reports and the packing-tool handoff read columns by name,
so additive columns do not reach them.

## 4. Python seams: the payload and the summary

Both functions live in `gui/orders_view.py`, which keeps all order folding in
one module. Both are pure and run without Chromium.

### 4.1 `order_payload(df)` gains derived per-order keys

These are added beside the existing keys. The Bundle 11 contract is otherwise
unchanged.

| Key | Value |
|---|---|
| `Units` | `int`, the sum of the order's line `Quantity` (`pd.to_numeric(errors="coerce")`, NaN → 0). `0` with no `Quantity` column. |
| `Created_At` | Replaced in place. An ISO 8601 string with offset when `pd.to_datetime(value, utc=True, errors="coerce")` parses it, else `None`. |
| `Tag_List` | `shopify_tool.tag_manager.parse_tags(Internal_Tags)`, a `list[str]`; `[]` without the column. |
| `Unknown_SKU` | `bool`: any line has `Has_SKU` exactly `False`. `False` without the column. |
| `Low_Stock` | `bool`: any line has a non-empty `Stock_Alert`. That column holds `"Low Stock"` or `""`. |

`Items` is LINES. `_repeat` (`REPEAT_COLUMN`) is the Repeat flag.
`Order_Fulfillment_Status == "Fulfillable"` is the status; anything else is
Blocked.

### 4.2 `results_summary(df) -> dict`

The KPI numbers, computed from the **line** frame as `update_kpi_strip` did.
`{}` for a `None` or empty frame, or a frame without `Order_Number`. Keys are
snake_case; every value is JSON-native.

| Key | Meaning |
|---|---|
| `orders` | `Order_Number.nunique()` |
| `lines` | row count |
| `skus` | `SKU.nunique()` (0 without SKU) |
| `fulfillable` | orders whose status is `"Fulfillable"` |
| `blocked` | `orders - fulfillable` |
| `blocked_lines`, `blocked_skus` | lines and distinct SKUs of blocked orders |
| `labels_by_courier` | `[[courier, count], …]` over fulfillable orders by `Shipping_Provider`, count descending then name. A blank courier counts as `"No courier"`. |
| `value_ready`, `value_total` | the sum of each order's first `Total_Price`, over fulfillable and over all orders. `None` without the column. |
| `oldest` | `{"order_number", "created_at"}` for the earliest parseable `Created_At`, else `None` |

## 5. The bridge — catalogue amendments

Bundle 11 §5.2 lets the owning bundle amend its catalogue with a recorded
reason. **Stage B edits that table** so it stays the single catalogue. It marks
the rows below as Bundle 12 and strikes the three removed rows, citing ADR 0005.

| Dir | Member | Kind | Why |
|---|---|---|---|
| out | `summary: dict` | notify property | KPIs are computed in Python over the line frame (§4.2). |
| out | `exportEnabled: bool` | notify property | Mirrors the generate-reports button, which stays the guard. |
| out | `focusSearchRequested()` | signal | Ctrl+F reaches the page's search field. |
| in | `openExport()` | slot → Python-facing `exportRequested` | The canvas puts Export in the document. |
| in | `openScreenMenu()` | slot → Python-facing `screenMenuRequested` | The Qt filter row that held the screen overflow is gone. A `QMenu` is a top-level popup, so it paints above the view. |
| ~~in~~ | ~~`setSort`, `setFilterText`, `setFilterChips`~~ | removed | No Python consumer (ADR 0005). |

Python-facing API changes:
- `set_orders(df)` now sets `orders` **and** `summary`, emitting both notifies.
- `set_export_enabled(enabled: bool)` is new.

`selectionChanged` gets its first consumer:
`bridge.selectionChanged.connect(mw.selection_helper.set_selected_orders)`.

## 6. The document

Every value is a token from `theme_css_vars`. The banned list and the linter
from Bundle 11 apply unchanged: no hex, no shadow, gradient, transition,
transform or opacity, and no px font size. Position windowed rows with `top`,
never `transform`.

### 6.1 Page geometry (desk density)

`<main id="results">` fills the view and paints `--surface` to its edges,
with no border and no inset. Its padding is `--spacing-lg` (16) on all sides.

It is a single-column grid: KPI strip (88px), filter bar (40px), then the table
area (`1fr`), with a `--spacing-md` (12) row gap. It also declares
`container-type: inline-size`.

**One container query, at page width ≥ 1544px** (a window of 1600 minus the
56px rail), shows the sixth KPI card. Nothing else responds to width.

The pane slot is not rendered. Bundle 13 adds a second grid column to the
table area.

Vertical arithmetic: table area = page height − 32 − 88 − 40 − 24.
- 692 → 508, and (508 − 28) / 28 = 17.1 → **17 rows**
- 1004 → 820, and 792 / 28 = 28.3 → **28 rows**

### 6.2 KPI strip

Five equal cards (`grid-template-columns: repeat(5, 1fr)`) with an 8px gap,
the gap `KpiStrip` used. The sixth card is shown only by the container query,
and only when `summary.oldest` is not null.

Card anatomy is copied from `StatCard`, with a label added above the numeral:
- **Label:** caption size, bold, uppercase, `letter-spacing: 0.06em`, `--text-secondary`.
- **Numeral:** `--type-display-xl-size`, bold, tabular.
- **Sub-line:** caption, `--text-secondary`, one line, ellipsis.

The card's background and radius match the `Card` rule in `build_stylesheet`.
Read it; do not invent a plane. Everything fits in 88px with `overflow: hidden`.

| # | Label | Numeral | Sub-line |
|---|---|---|---|
| 1 | ORDERS | `orders` | `{lines} lines · {skus} SKUs touched` |
| 2 | FULFILLABLE | `fulfillable` | `{pct}% of orders` (rounded) |
| 3 | BLOCKED | `blocked` | `{blocked_lines} lines, {blocked_skus} SKUs` |
| 4 | LABELS | `fulfillable` | `DHL 120 · DPD 98 · Packeta 50` from `labels_by_courier` |
| 5 | VALUE READY | compact `value_ready` | `of {compact value_total} analysed`; "No price column mapped" when `None` |
| 6 | OLDEST WAITING | age of `oldest.created_at` | `order {oldest.order_number}` |

- **Integers:** thousands separators (`1,842`).
- **Compact values:** `41.2k`, `1.2M`, or a plain integer below 1,000. No
  currency symbol: the data carries none.
- **Before any analysis:** every numeral reads "—", as today.

### 6.3 Filter bar

A 40px flex row with an 8px gap, items centred, left to right:

1. **Search:**
   - Look: `<input type="search">`, 280px wide, `--control-height` tall,
     1px `--border`, `--radius`, `--surface` background. Focus is a 2px
     `--focus-ring` outline.
   - Placeholder: **"Order, customer or SKU"**.
   - Matching: case-insensitive substring over `Order_Number`, `Customer`,
     `Shipping_Provider`, `Tag_List`, and every line's `SKU` and
     `Product_Name`. The search text is precomputed once per `orders` push.
2. **Applied chips:**
   - Look: an outlined pill with 1px `--border`, `--radius-lg`, padding
     3px 8px, caption size.
   - Label and dismissal: the text is `"<label> ×"`, and a click anywhere on
     it removes the chip (parity with the Qt `_FilterChip`).
   - Overflow: the chip container shrinks and clips.
3. **"Add filter"** — a ghost button opening an in-page menu (`role="menu"`,
   `--surface-overlay`, 1px `--border`, `--radius-md`, no shadow).
   - **Groups, in order:**
     - **Status:** Fulfillable, Blocked
     - **Flags:** Repeat, Unknown SKU, Low stock, 3 or more lines
     - **Courier:** one item per courier present, labelled `Courier: DPD`
     - **Tags:** one item per tag present, labelled `Tag: <tag>`
   - Applied items show a check, and choosing one removes it.
   - Esc, an outside click or a choice closes the menu.
4. **"Clear all"** — a ghost button, shown only while a chip or search text exists.
5. A flexible spacer.
6. **Count** — caption, `--text-secondary`: `312 orders`, or `44 of 312 orders`
   while anything narrows. This is today's copy.
7. **"⋯"** — a 32×32 ghost button labelled "More actions for this screen".
   It calls `openScreenMenu()`.
8. **Export** — the screen's one primary.
   - **Look:** `--control-height` tall, padding 0 12px, `--accent-fill`,
     `--on-accent`, `--radius`, body size bold. Hover uses
     `--accent-fill-hover`, active `--accent-fill-active`. Disabled matches
     `QPushButton[role="primary"]:disabled` in `build_stylesheet`.
   - **Label:** `Export {fulfillable} orders`.
   - **Enabled:** only while `exportEnabled` is true and `fulfillable > 0`.
   - **Click:** calls `openExport()`.

**Filter semantics:**
- Search AND every group.
- Status is exclusive: adding one replaces the other.
- Each flag is its own group, so flags AND together.
- Courier chips OR together, and tag chips OR together.
- "3 or more lines" means `Items >= 3`.

### 6.4 The order table

**Columns** (`grid-template-columns` from a `--cols` custom property that JS
sets):

| Column | Width | Cell |
|---|---|---|
| select | 32 | checkbox |
| Status | 132 | status chip (§6.5) |
| Order | 84 | `Order_Number`, `--font-family-mono` |
| Customer | `minmax(<min>px, 1fr)` | `Customer`, ellipsis |
| Lines | 56 | `Items`, right, tabular |
| Units | 56 | `Units`, right, tabular |
| Value | 84 | `Total_Price` to 2 decimals, right, tabular |
| Courier | 76 | `Shipping_Provider` |
| Age | 56 | from `Created_At`, right, `--text-secondary` |

Sizing and scrolling:
- **Fixed columns:** each is `max(canvas width, widest measured cell text + 16)`,
  measured once per `orders` push with a 2D canvas `measureText` in the cell's
  font. Columns never reflow after that.
- **Customer:** its minimum is `max(120, 780 − sum of the others)`, so the
  table's minimum width is 780.
- **Missing values:** "—" in `--text-secondary`.
- **Age format:** `N min` under 1h, `N h` under 48h, else `N d`.
- **Horizontal scroll:** the table scroller is `overflow: auto`. The select and
  Status cells are `position: sticky; left` on a `--surface` ground, so they
  stay pinned when it scrolls.

**Header:**
- 28px, sticky top, `--surface`, with a 1px `--border-subtle` bottom border
  inside the 28px.
- Caption size, bold, `--text-secondary`, **title case**; numeric headers
  right-aligned.
- Clicking a header sorts ascending, then descending, then back to frame order.
  - Numbers compare numerically.
  - Text compares with `localeCompare`.
  - Empty values sort last.
- A chevron (inline SVG path, `stroke: currentColor`) shows on the sorted
  column, and at `--text-secondary` on a hovered one.
- The select header is a tri-state checkbox over the visible rows.

**Rows:**
- `--row-height` (28 at desk density). JS reads it from computed style, so a
  density change re-lays the table.
- Cell padding is 0 8px, body size, one line.
- **Hover:** `--hover`.
- **Selected:** `--selection-bg` with `outline: 2px solid var(--selection-border);
  outline-offset: -2px`, a closed ring.
- **No status edge:** the canvas draws none on rows; the chip carries status.
- **No partial rows:** the body viewport's height is
  `floor((table area − 28) / rowH) × rowH`. The leftover pixels stay page
  surface below the table.
- **Windowing:** only rows in `[first − 4, last + 4]` exist in the DOM, placed
  with `top` inside a spacer of `n × rowH`.
- **Test hooks:**
  - the table element carries `data-visible-rows`
  - each row carries `data-order="<Order_Number>"`
  - the empty and no-match states are addressable by id

### 6.5 Status chip

This is the web rendering of `shared.theme.StatusChip`'s `chip` variant, at
**its** geometry, not the canvas pill's. Two renderers get one appearance
(ADR 0001):
- a 1px border in the role colour, `--radius` (4)
- padding 2px 8px 2px 20px (`MARK_LEFT_PX + MARK_PX + 4`), caption size
- an 8px hollow ring (`MARK_PX`, stroke `MARK_RING_WIDTH` 1.5) at 8px from the
  left, vertically centred

| Status | Role | Live? | Fill |
|---|---|---|---|
| Fulfillable | `status_success` | resting | none |
| Blocked | `status_danger` | live | `--status-danger-bg` |

A repeat order is not a status: it is a filter flag, and Bundle 13 shows it as
a pane tag. W3's "WENT WHERE" table puts repeat there. Today's warning edge
for repeats goes with the Qt table.

### 6.6 Selection and keyboard

- Click selects only that row.
- Ctrl-click toggles a row, and so does the row's checkbox.
- Shift-click selects a range from the anchor, in display order.
- The table is focusable (`tabindex="0"`, 2px `--focus-ring` on `:focus-visible`):
  - Ctrl+A selects every visible row.
  - Esc clears the selection.
  - ↑/↓ move a single selection, and Shift extends it. The moved row scrolls
    into view.
- A search or chip that hides a selected order deselects it, as the Qt proxy
  did.
- An `orders` push keeps the selected orders that are still present and visible.
- Every change calls `setSelection(orderNumbers)` in display order. The bridge
  already drops repeats.
- `focusSearchRequested` focuses the search field.

### 6.7 States

- **Nothing analysed** (`orders` empty):
  - KPI numerals read "—".
  - Search, Add filter and Export are disabled.
  - The table area shows:
    - title (body, bold): **"Nothing analysed yet"**
    - text: **"Load the orders and stock files in Setup, then run the analysis.
      Every order it finds lands here."**
- **No match:**
  - Count reads `0 of 312 orders`.
  - The table area shows **"No orders match"**, with the text
    **"Remove a filter or clear the search."** and a **Clear all** button.
- Both states sit centred in the table area, on `--surface`.

## 7. Qt side

### 7.1 Mounting and data flow

`ui_manager._create_tab2_analysis_results` becomes:
- a `QWebEngineView` filling the tab, with 0 margins
- `mw.results_view` for that view
- `mw.results_bridge = mount_results_page(view)`

Then:
- **Connections:**
  - `selectionChanged` → `mw.selection_helper.set_selected_orders`
  - `exportRequested` → `mw.generate_reports_button_tab2.click()`. A disabled
    button ignores the click, so it stays the guard.
  - `screenMenuRequested` → `mw.results_menu.popup(QCursor.pos())`
- **Export enabled state:** every `generate_reports_button_tab2.setEnabled(x)`
  call site also calls `mw.results_bridge.set_export_enabled(x)`.
- **The generate-reports button** stays a hidden `QPushButton`, created in the
  tab builder, but is no longer bound to the command bar.
- **`_update_all_views`:** the table, KPI and filter-scope block is replaced by
  `self.results_bridge.set_orders(df)`, with an empty frame when there is no
  analysis, plus `self.ui_manager.update_session_chips()`.
- **Ctrl+F** (`main_window_pyside.py:425`):
  `results_bridge.focusSearchRequested.emit()` and `results_view.setFocus()`.

### 7.2 Command bar

- `_SCREEN_ACTIONS` values gain a role:
  - `0: ("run_analysis_button", True, "primary")`
  - `1: ("run_analysis_button", True, "secondary")`
- `CommandBar.bind_action(button, role="primary")` applies the role to
  `action_button` with `set_button_role`. `_bind_screen_action` passes it.
- The label stays **"Run analysis"**, the button's own text, so the action
  keeps one name across Setup and Results (§11).
- **Session chips:**
  - `CommandBar` gains `stock_chip` (a `StatusChip("text_secondary", …)`
    beside `status_chip`) and `set_stock_age(text)`, mirroring `set_status`.
    `_refresh` applies the same visibility rule to both.
  - `ui_manager.update_session_chips()` reads
    `session_manager.get_session_info(mw.session_path)`:
    - `analysis_completed_at` gives `set_status("text_secondary",
      "Analysed HH:MM")` in local time.
    - The stock age is `analysis_completed_at` minus the mtime of
      `<session>/input/inventory.csv`, which gives `set_stock_age("Stock file
      19 h old")` (`N min` / `N h` / `N d`).
  - A missing value blanks its chip.
  - It is called from `_update_all_views` and after a session opens.

### 7.3 Screen overflow

`_create_results_overflow` keeps its `QMenu` as `mw.results_menu`. Its
`QToolButton` and `_style_results_overflow` are deleted.

**"Configure Columns" is removed** (Bundle 13), along with
`configure_columns_button_tab2` and its call sites. "Add Product to Order"
and "Undo" stay under their attribute names.

### 7.4 Deleted

**Rule:** delete what only the Qt results screen reached. Keep a module that
another live screen, or a Bundle 13/14 brief, still needs.

**`gui/ui_manager.py`** — these methods go:
- `_create_selection_bar`, `_create_kpi_strip`, `update_results_table`
- `_selected_order_numbers`, `_reselect_orders`, `results_view_frame`
- `_populate_tag_filter`, `_extract_unique_tags_from_dataframe`,
  `_group_tags_by_category` (grep for other callers first)
- `_create_filter_controls` (its generate-reports button moves to the tab
  builder), `update_filter_count`
- `_create_results_table`, `_setup_header_context_menu`,
  `_show_header_context_menu`, `_create_footer`, `update_kpi_strip`
- `update_hidden_columns_indicator`, `_show_hidden_columns_popup`,
  `_restore_hidden_column`, `_restore_all_hidden_columns`
- `_style_results_overflow`

**`gui/main_window_pyside.py`** — these go:
- **Setup:** `FulfillmentFilterProxy` and `proxy_model`; `SelectionHelper` is
  built with `table_view=None, proxy_model=None`.
- **Table hookups:** the table, pane and filter connections (385–403) and
  `_filter_debounce`.
- **Methods:** `on_results_selection_changed`, `_pane_lines`,
  `open_column_config_dialog`, `_update_selection_bar_state`, `filter_table`,
  `on_table_double_clicked`, `show_context_menu`, `show_line_context_menu`.
- **Tag panel:** `add_internal_tag_to_order` and
  `remove_internal_tag_from_order`, if only the tag panel calls them.
- **State:** `orders_df`, once nothing reads it.

**Other code:**
- `gui/actions_handler.py` — the three `hasattr(self.mw, "_update_selection_bar_state")` calls.
- `gui/column_config_dialog.py` — the `tableView` branch (≈750–756).
- **Modules:** `gui/order_detail_pane.py`, `gui/tag_management_panel.py`,
  `gui/tag_delegate.py`, `gui/components/statcard.py` (and its export in
  `gui/components/__init__.py`), and the `FulfillmentFilterProxy` class in
  `gui/pandas_model.py`.

**Tests:**
- deleted whole: `tests/test_analysis_results_1b_chrome.py`,
  `tests/test_main_window_tags.py`, `tests/test_components_statcard.py`
- from `tests/test_analysis_results_1b.py`: every test touching a deleted symbol
- from `tests/test_pandas_model.py`: the `FulfillmentFilterProxy` tests
- from `tests/test_selection_ring_renders.py`: the `TagDelegate` case

**Kept:**
- `PandasModel` (a fixture for live `StatusEdgeDelegate`/ring tests) and
  `StatusEdgeDelegate` (Logs)
- `selection_ring`, `SelectionHelper`, and the `actions_handler.bulk_*` handlers (Bundle 14)
- `TableConfigManager` and `column_config_dialog` (Settings; Bundle 13)
- `FilterBar` and `ContextualSelectionBar` (Session Browser)

**Done check:** this returns nothing:

```
git grep -n -E "tableView|proxy_model|order_detail_pane|tag_management_panel|filter_input|filter_column_selector|case_sensitive_checkbox|tag_filter_combo|kpi_cards|kpi_strip|update_results_table|update_kpi_strip|update_filter_count|hidden_columns_indicator|configure_columns_button_tab2|_update_selection_bar_state" -- gui ':!gui/session_browser_widget.py'
```

## 8. Tests — the seams

1. **Pure Python** (no Chromium):
   - `results_summary`: counts, `labels_by_courier` order and the blank
     courier, both values and `None`, `oldest`.
   - The new `order_payload` keys: `Units` coercion, `Created_At` from the
     Shopify format, and `None` when unparseable. `json.dumps(allow_nan=False)`
     still passes.
   - `analysis` carries and forward-fills `Customer`/`Created_At` when mapped,
     and omits them when not.
   - `OPTIONAL_FIELDS` and the new-profile defaults.
2. **Bridge, Python side:**
   - `set_orders` sets `summary`.
   - `openExport` emits `exportRequested`.
   - `set_export_enabled` notifies.
   - `openScreenMenu` emits `screenMenuRequested`.
3. **Document, through Chromium:** the existing `tests/test_results_bridge.py`
   helpers `_eval`/`_until_js`/`page` move to a shared test helper, with a
   deterministic 312-order line frame built in code.
   - `view.resize(1310, 692)` gives `data-visible-rows == 17`, and
     `(1864, 1004)` gives 28.
   - At 1310 the scroller's `scrollWidth <= clientWidth`; at 780 it is greater.
   - Rendered rows are ≤ visible + 8.
   - The header text order matches §6.4.
   - A search for one order's SKU narrows the count to `1 of 312 orders`.
   - Chips follow the AND/OR rules, and Clear all resets.
   - A row click reaches `selectionChanged` as `[order]`, and a chip hiding that
     order sends `[]`.
   - Sorting Value twice gives descending order.
   - Export reaches `exportRequested`.
   - The sixth KPI card is visible at 1864 and hidden at 1310.
   - An empty push shows `#results-empty`.
4. **Main window:**
   - The Results tab holds a `QWebEngineView`.
   - `_update_all_views` pushes orders and a summary.
   - Screen 1 binds `run_analysis_button` with the secondary role.
   - `update_session_chips` writes both chips from a temp session.
   - The §7.4 done-check passes: a test reads every `gui/**/*.py` except
     `gui/session_browser_widget.py` and asserts that none contains those
     names. It is a plain file scan, not `git grep`.
5. **Unchanged:** the style lint over `gui/web` still passes, and the Bundle 11
   bridge tests still pass.

## 9. Not in this bundle

- The order detail pane and its slot (Bundle 13, 9.14).
- The column manager and "Columns 9/23" (Bundle 13, 9.16).
- The selection bar, bulk actions and the web toast (Bundle 14, 9.17).
- Numeric filter chips such as "Value over €100".
- ADDRESS, and city in the table.
- A migration or fallback for existing profiles.
- Deleting `gui/webengine_gate.py` and `PandasModel`.

## 10. Build

No new files outside `gui/web/`, which is already collected
(`--add-data "gui/web;gui/web"`). No new dependency.

## 11. Departures from the brief and the canvas

| Brief / canvas | This design | Why |
|---|---|---|
| NEEDS REVIEW card | LABELS card with courier split | No review data; owner's call |
| "Ready" / "Ship complete" / "Short on stock" | Fulfillable / Blocked | Owner's call; CONTEXT.md |
| ADDRESS column ≥1600, 220px | Dropped; CUSTOMER takes all growth | Owner's call |
| Container query adds a column | Container query adds the sixth KPI card only | ADDRESS dropped |
| Pane 400 / reopen strip 36 | No pane, no strip; the table takes the content width | Pane slot empty until Bundle 13 (owner) |
| "Re-run" label | "Run analysis", styled secondary | One name for one action across two screens |
| Export on the Qt command bar (Bundle 11) | Export in the document, via `openExport()` | Canvas W3 |
| Bridge sort/filter slots | Removed | ADR 0005 |
| Headers in caps | Title case | Bundle 6 precedent: this app's tables are title case |
| "B. Fischer" abbreviated names | The customer name as mapped, ellipsised | No reliable abbreviation for company names; CUSTOMER stretches |
| "€41.2k" | "41.2k" | No currency in the data |
| Chip set: status, courier, 3+ lines, value threshold | Status, Repeat, Unknown SKU, Low stock, 3 or more lines, courier, tags | Owner picked status, flags, tags and courier; 3+ lines is the canvas's own flag |
| "Columns 9/23" button | Absent | Bundle 13 |
| Rows 17 @1366 measured with a pane | Same count, no pane | Row count does not depend on the pane |
