# Tags & Lot Data Model — Design

## Problem

The Analysis Results table's tag and lot data was reported as six separate symptoms
across the Todoist "Phase 3 — Tags & Lot data model" epic and its subtasks (one of which,
the bulk add/remove bug, was found during Phase 2 undo-logic verification rather than
filed against the original screenshots), but they trace back to four distinct root
causes, not one:

- **RC-A — Inconsistent order-vs-line writes to `Internal_Tags`.** `Internal_Tags` is
  semantically an order-level concept (a tag applies to the whole order), but `final_df`
  has one row per order *line*, and four different code paths each pick a different
  subset of rows to write it to:
  - `gui/actions_handler.py` `bulk_add_tag()`/`bulk_remove_tag()` write only a single
    "representative" row per order (`order_rows[0]`).
  - `gui/main_window_pyside.py` `add_internal_tag_to_order()`/`remove_internal_tag_from_order()`
    (wired to the tag sidebar panel) correctly mask all rows of the order.
  - `gui/main_window_pyside.py` `_add_internal_tag()` (right-click "Internal Tags" submenu)
    masks only the single clicked `Order_Number` + `SKU` line.
  - `shopify_tool/rules.py` `_execute_actions()`, `ADD_INTERNAL_TAG` action, writes only to
    the rule's `matches` mask — whichever individual lines matched the rule's conditions,
    not necessarily every line of the affected orders.

  Additionally, the tag sidebar's "Current Tags" display
  (`gui/main_window_pyside.py` `on_selection_changed_for_tags()`) reads `Internal_Tags`
  off whichever single row happens to be selected in the table, rather than merging
  across all of the order's rows — so after any of the above inconsistent writes, the
  sidebar shows different "current tags" depending on which line of the same order is
  selected. This fully explains the reported "Tags Manager edit-tag logic is broken"
  symptom; there is no separate edit function to fix, the display is just reading stale/
  partial data.

  Verified *not* broken: the Statistics window's tag-breakdown counting
  (`shopify_tool/analysis.py:1560-1591`, `_build_order_tag_counts()`) already dedupes by
  `(Order_Number, tag)` before counting, so it already counts per unique order, not per
  line, despite the original ticket describing it as inflated. No fix needed there
  directly — but it depends on at least one row per order carrying the correct tag, which
  RC-A's inconsistent writes could still undermine for other consumers (CSV export,
  barcode/label rendering, SKU writeoff calculation, per-line filtering) that read
  `Internal_Tags` per-line rather than via the same order-level dedup.

- **RC-B — `Tags` column not forward-filled.** `Tags` (the raw Shopify orders-CSV `Tags`
  field, distinct from `Internal_Tags`) is one of the `base_columns` carried through from
  the raw orders DataFrame, but unlike `Order_Number`/`Shipping_Method`/`Total_Price`/
  `Subtotal` (`shopify_tool/analysis.py:238-247`), it is never `.ffill()`'d per order
  during `_clean_and_prepare_data`. Since Shopify order exports only populate `Tags` on
  an order's first CSV line, every subsequent line of a multi-line order ends up with a
  blank `Tags` value in `final_df`.

- **RC-C — `Lot_Details` has no renderer, a live crash bug, and inconsistent expiry
  strings.**
  - No GUI code references `Lot_Details` at all; it falls through to the generic cell
    renderer in `gui/pandas_model.py` `data()`, which does `str(value)` on the raw
    `list[dict]` (or `None`), producing dumps like
    `[{'expiry': '1', 'batch': None, 'qty_allocated': 1}]`.
  - That same generic renderer calls `pd.isna(value)` on the raw cell value
    (`gui/pandas_model.py:168`). For a scalar this is fine, but a `Lot_Details` cell
    holding a list of 2+ lot dicts makes `pd.isna()` return an array, and
    `if pd.isna(value):` on an array raises `ValueError: The truth value of an array
    with more than one element is ambiguous.` This is an unhandled, live crash risk in
    the Analysis Results table for any order with 2+ lots allocated to one SKU line.
  - `_build_fifo_lots()` (`shopify_tool/analysis.py:78-119`) stores the expiry as a raw,
    unvalidated string (`expiry_raw`) alongside a best-effort parsed `expiry_dt` (via
    `_parse_expiry_date()`, `analysis.py:17-46`, which currently only recognizes 6-digit
    YYMMDD and 8-digit YYYYMMDD, returning `None` — and silently swallowing the failure
    at `debug` log level — for anything else, including 4-digit codes and other stray
    formats). The raw string is what actually reaches `Lot_Details`, so inconsistent
    source formats (a stock CSV expiry cell read as a pandas float becoming e.g. `"2805"`
    via `str(int(raw_e))`) surface directly in the UI.

- **RC-D — Tag Categories dialog mutates the live config with no Save/Cancel
  isolation.** `TagCategoriesPanel.__init__` (`gui/tag_categories_dialog.py:53-63`) does
  `self.working_categories = tag_categories.copy()` — a *shallow* copy. Since the real
  config is already v2-shaped, `working_categories["categories"]` ends up being the same
  nested dict object as `active_profile_config["tag_categories"]["categories"]`.
  `_on_delete_category()`, `_on_new_category()`, and `_save_editor_to_working_copy()` all
  mutate this shared `categories` dict directly and immediately (on every keystroke/click,
  not just on Save). The dialog's `categories_updated` signal + Save/Apply/Cancel wiring
  (`gui/actions_handler.py` `open_tag_categories_dialog()`) is otherwise correct — it only
  persists on the signal, which only fires from Save/Apply — but because the "working
  copy" was never actually independent, edits are visible (and effectively already
  applied to the in-memory config, at risk of being persisted by an unrelated later save)
  even if the user clicks Cancel. This is the mechanism behind the reported "presets
  removed unexpectedly" symptom.

### Ticket-to-root-cause mapping

| # | Ticket | Root cause |
|---|---|---|
| 1 | Internal tag counting per-order not per-line | Verified already correct; no fix needed (see RC-A) |
| 2 | Tags column should only reflect original CSV tags | RC-B |
| 3 | Lot Details raw dict dump + verify allocation algorithm | RC-C |
| 4 | Tags Manager: fix edit-tag logic | RC-A (display fix) |
| 5 | Bulk add/remove writes only representative row | RC-A |
| 6 | Context-menu tag/preset bug | RC-A (right-click path) + RC-D (presets) |
| — | (found in review) pandas_model crash on multi-lot cells | RC-C |
| — | (found in review) rule engine ADD_INTERNAL_TAG line-only | RC-A |

## Goals

1. `Internal_Tags` writes and reads are consistent across every code path — always
   order-level, never split across an order's lines.
2. `Tags` reliably reflects the source CSV's tag value for every line of an order, not
   just the first.
3. `Lot_Details` renders as a short summary with full detail on hover, never raises, and
   expiry values parse correctly for YYMMDD/YYYYMMDD/DDMMYY/MMYY, with unparseable values
   visibly flagged (in the UI and in logs) rather than silently dropped.
4. Editing Tag Categories (add/remove/rename a category or its tags) only takes effect on
   Save/Apply; Cancel is a true no-op on the live config.

## Non-goals

- Restructuring `Internal_Tags` off the per-line DataFrame into a separate order-level
  store. A bigger architectural change (would touch session save/load, undo, CSV export,
  every existing reader) that the shared-masking-helper approach below makes unnecessary.
- Building a Stock CSV mapping UI for Expiry/Lot/Batch source columns. The backend
  mapping mechanism already supports this today (`column_mappings.stock` in client
  config, `shopify_tool/profile_manager.py:409-415`) — a client can already point
  arbitrary source CSV headers at `Expiry_Date`/`Batch`. The missing piece is a GUI to
  edit that mapping, which is already tracked as the Phase 6 "Mappings: better UI, add
  expiry/lot/position fields to Stock CSV mapping" ticket. Not duplicated here.
- A per-client configurable expiry date format. No evidence yet that the YYMMDD-priority
  heuristic (see RC-C design below) produces real ambiguity in live client data — revisit
  only if it does.
- Any change to `packing-tool` or `shared/` (this epic doesn't touch cross-tool session
  state).
- Deeper correctness audit of the FIFO allocation quantity math in
  `simulate_stock_allocation()` beyond what's needed to fix the expiry-string and
  rendering issues above — nothing in this review turned up an allocation-quantity bug,
  only formatting/parsing ones.

## Design

### RC-A: shared order-mask helper

New function in `shopify_tool/tag_manager.py`:

```python
def expand_to_order_rows(df: pd.DataFrame, mask: pd.Series) -> pd.Series:
    """Given a row mask, return a mask covering all rows of every order touched by it."""
    order_numbers = df.loc[mask, "Order_Number"].unique()
    return df["Order_Number"].isin(order_numbers)
```

Every `Internal_Tags` write is routed through this before assignment:

| Location | Current mask | Fix |
|---|---|---|
| `gui/actions_handler.py` `bulk_add_tag()`/`bulk_remove_tag()` | `order_rows[0]` per order (representative row only) | Mask on `Order_Number.isin(unique_orders)` directly — drop the representative-row narrowing |
| `gui/main_window_pyside.py` `_add_internal_tag()` (right-click) | `Order_Number == x & SKU == y` | Wrap through `expand_to_order_rows` |
| `shopify_tool/rules.py` `_execute_actions()`, `ADD_INTERNAL_TAG` | `matches` (rule-matched lines only) | Wrap `matches` through `expand_to_order_rows` before the `Internal_Tags` assignment |
| `gui/main_window_pyside.py` `add_internal_tag_to_order()`/`remove_internal_tag_from_order()` | Already masks all rows of the order | No change |

`add_tag()`/`remove_tag()` (`tag_manager.py`) are idempotent — re-applying to rows that
already have the correct value is a no-op — so no before/after diffing is needed at each
call site to avoid double-application artifacts.

**Display fix** — `gui/main_window_pyside.py` `on_selection_changed_for_tags()`: currently
reads `Internal_Tags` off the single selected row (`self.analysis_results_df.iloc[row]`).
Changes to select all rows matching that row's `Order_Number` and pass the result through
`tag_manager.merge_tags()` (already exists) before handing it to
`tag_management_panel.set_selected_order()`, so "Current Tags" always reflects the order's
true merged tag set regardless of which line is selected.

### RC-B: Tags forward-fill

`shopify_tool/analysis.py`, `_clean_and_prepare_data`, alongside the existing ffill block
(~line 238-247):

```python
if "Tags" in orders_df.columns:
    orders_df["Tags"] = orders_df["Tags"].ffill()
```

### RC-C: Lot_Details rendering, crash fix, expiry parsing

**Crash fix + rendering** — `gui/pandas_model.py`, `data()`: special-case list-valued
cells before the generic scalar `pd.isna(value)` path, for both `DisplayRole` (short
summary) and `Qt.ItemDataRole.ToolTipRole` (full breakdown, new — no tooltip role is
currently handled for any column):

```python
if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
    try:
        value = self._dataframe.iloc[row, col_index]
    except IndexError:
        return None
    if isinstance(value, list):
        if not value:
            return "" if role == Qt.ItemDataRole.DisplayRole else None
        if role == Qt.ItemDataRole.DisplayRole:
            return f"{len(value)} lot{'s' if len(value) != 1 else ''}"
        return "\n".join(_format_lot(lot) for lot in value)
    if pd.isna(value):
        return "" if role == Qt.ItemDataRole.DisplayRole else None
    return str(value) if role == Qt.ItemDataRole.DisplayRole else None
```

`_format_lot(lot: dict) -> str` renders one lot dict as e.g.
`"2x, exp 2026-12-30, Batch B1"`, using `lot["expiry_dt"]` when parseable and falling
back to `f"exp unparsed ({lot['expiry']!r})"` when `expiry_dt` is `None`. This handles any
future list-valued column generically, not just `Lot_Details`.

Note: `lot_allocations` (built in `simulate_stock_allocation()`) currently stores only
`expiry`/`batch`/`qty_allocated` per lot (`shopify_tool/analysis.py:640-660`) — it needs
`expiry_dt` carried through alongside `expiry` so the renderer can use the already-parsed
date instead of re-parsing the raw string.

**Expiry parsing** — `shopify_tool/analysis.py`, `_parse_expiry_date()`: extend to try
candidate formats in priority order, keeping the first calendar-valid result, logging when
a value is unparseable or ambiguous across formats:

```python
def _parse_expiry_date(raw) -> date | None:
    s = str(raw).strip()
    if not s or s == "1":
        return None

    # ponytail: format priority (YYMMDD > DDMMYY > MMYY) is a heuristic, not a
    # guaranteed-correct disambiguation for 6-digit values that are valid under more
    # than one format — add a per-client date-format setting if that turns out to be
    # common in practice.
    candidates = []
    if len(s) == 6:
        candidates = [
            ("YYMMDD", 2000 + int(s[0:2]), int(s[2:4]), int(s[4:6])),
            ("DDMMYY", 2000 + int(s[4:6]), int(s[2:4]), int(s[0:2])),
        ]
    elif len(s) == 8:
        candidates = [("YYYYMMDD", int(s[0:4]), int(s[4:6]), int(s[6:8]))]
    elif len(s) == 4:
        candidates = [("MMYY", 2000 + int(s[2:4]), int(s[0:2]), 1)]

    valid = []
    for fmt, y, m, d in candidates:
        try:
            valid.append((fmt, date(y, m, d)))
        except (ValueError, OverflowError):
            continue

    if not valid:
        logger.warning(f"Could not parse expiry date: {s!r}")
        return None
    if len(valid) > 1:
        logger.warning(
            f"Ambiguous expiry {s!r}: valid as {[v[0] for v in valid]}, using {valid[0][0]}"
        )
    return valid[0][1]
```

(Replaces the current manual field-range validation with `date()`'s own `ValueError` on an
invalid calendar date — simpler and equally strict. Swallowed-failure log level goes from
`debug` to `warning` so bad source data is visible in production logs, per Goal 3.)

### RC-D: Tag Categories isolation

`gui/tag_categories_dialog.py`, `TagCategoriesPanel.__init__`:

```python
import copy
self.working_categories = copy.deepcopy(tag_categories)
```

(Replaces the shallow `tag_categories.copy()`.) No other changes needed — the
`categories_updated` signal and Save/Apply/Cancel wiring in
`gui/actions_handler.py` `open_tag_categories_dialog()` already only persists on
Save/Apply; it was only unsafe because the working copy wasn't actually independent from
the live config.

## Testing

Per `AGENTS.md`/`CLAUDE.md`: `QT_QPA_PLATFORM=offscreen python -m pytest` and
`ruff check . --exclude shared` must pass before merge.

- `tag_manager.expand_to_order_rows`: unit tests — single-line mask expands to all lines
  of that order; multi-order mask expands correctly; mask matching zero rows returns
  all-False.
- RC-A call sites: extend/add tests for `bulk_add_tag`/`bulk_remove_tag`,
  `_add_internal_tag`, and `rules.py` `ADD_INTERNAL_TAG` asserting *all* rows of a
  multi-line order receive the tag, not just one.
- Tag sidebar display: test `on_selection_changed_for_tags` returns the merged tag set
  regardless of which line of a multi-line order is selected.
- RC-B: test `Tags` survives `ffill()` across a multi-line order in
  `_clean_and_prepare_data`.
- RC-C:
  - `_parse_expiry_date`: table-driven test over YYMMDD, YYYYMMDD, DDMMYY, MMYY, the
    ambiguous-6-digit case (asserts YYMMDD wins and a warning is logged), and
    unparseable input (asserts `None` + warning logged).
  - `pandas_model.data()`: test a `Lot_Details` cell with 0, 1, and 2+ lots doesn't raise
    and returns the expected `DisplayRole` summary and `ToolTipRole` detail text — this is
    the regression test for the crash bug.
- RC-D: test that mutating `TagCategoriesPanel.working_categories` (add/remove/edit a
  category) does not mutate the original `tag_categories` dict passed to `__init__`.

This is a bug-fix epic, not new user-facing features — no new manual QA beyond running the
app and re-checking the original six screenshot scenarios resolve correctly.

## Files touched

- `shopify_tool/tag_manager.py` — new `expand_to_order_rows()`
- `shopify_tool/analysis.py` — `Tags` ffill, `_parse_expiry_date()` extension,
  `simulate_stock_allocation()`/lot allocation dict carries `expiry_dt`
- `gui/actions_handler.py` — `bulk_add_tag()`, `bulk_remove_tag()`
- `gui/main_window_pyside.py` — `_add_internal_tag()`, `on_selection_changed_for_tags()`
- `shopify_tool/rules.py` — `_execute_actions()`, `ADD_INTERNAL_TAG` branch
- `gui/pandas_model.py` — `data()` list-value handling, new `_format_lot()` helper
- `gui/tag_categories_dialog.py` — `TagCategoriesPanel.__init__()`

## Follow-ups (not in this epic's scope)

- Phase 6: Stock CSV mapping UI for Expiry/Lot/Batch/Position fields.
- Per-client configurable expiry date format, if ambiguous 6-digit values turn out to be
  common in practice (heuristic priority logs a warning so this is discoverable).
