# Phase 5 — Table & Stats UX — Design

## Context

Phase 5 (Todoist `6h8v49wj4M3cFxJV`, light-epic) covers three independent UI/data-display
cleanups: Manage Table Columns window, Statistics tab, and Add Product to Order dialog. Per the
workflow guide, a light-epic gets "a small design per item... doesn't need the full multi-file
spec treatment" — this doc is that, one section per item, code-verified against current `main`
rather than assumed from the original 2026-07-28 backlog wording.

**Headline finding: two of the three items are substantially smaller than their Todoist wording
suggests**, because prior work already shipped fixes the backlog text doesn't reflect. Verifying
against code before scoping — not the original task text — is the main output of this doc.

Scope: design only. No code changes in this branch. Each item still needs a
`writing-plans` pass (or a quick decision + direct implementation for the smaller items) when
picked up.

## Item 1 — Manage Table Columns window

**Current state** (`gui/column_config_dialog.py`, `ColumnConfigPanel`, 936 lines +
`gui/table_config_manager.py`, `TableConfigManager`, 1116 lines): the complaint is accurate —
`self.column_list` is a flat `QListWidget`, one checkable `QListWidgetItem` per raw DataFrame
column name (`Order_Number`, `Order_Fulfillment_Status`, `Internal_Tags`, ...), no grouping, no
friendlier labels. Everything else around it — search filter, up/down reorder, show/hide all,
auto-hide-empty toggle, named views (save/delete/switch), an "Additional CSV Columns" section,
reset-to-default — is already there and reasonably capable. This is one panel used from **two
entry points**: a standalone popup (`ColumnConfigDialog`, opened via `main_window_pyside.py:624`
— this is the "window" in the screenshot) and an embedded tab inside the Settings window
(`settings_window_pyside.py:3368`). A layout fix to the panel benefits both automatically.

**Backend verification** (the task also asks to "verify the backend actually persists/applies
the configuration correctly"): `TableConfigManager.load_config`/`save_config` persist under
`client_config.json` → `ui_settings.table_view.views[view_name]`, with a debounce timer for
resize/move and explicit cleanup of a documented past bug (corrupted zero-width column entries).
No correctness bug found. One inefficiency, not a bug: `ColumnConfigPanel.apply_config()`
(`column_config_dialog.py:567`) calls `table_config_manager.save_config()` (one read-modify-write
of `client_config.json`) and then, for the "Additional CSV Columns" section, does a **second**,
separate read-modify-write of the same file (`column_config_dialog.py:589-598`). Over a UNC
share this is two network round-trips instead of one on every "Apply" click — worth folding into
a single write while this file is being touched anyway, not worth its own task.

**Proposal**: replace the flat list with grouped sections. Two ways to do it, pick one:

- **(a) `QTreeWidget` with category parent nodes** (Order info / Product info / Fulfillment /
  Tags & Lot / Additional CSV), checkable leaf items per column, parent checkbox tri-state
  reflects children. More natural "collapse a group I never touch" UX; requires rewriting
  `_load_columns`/`_on_item_changed`/reorder handlers against `QTreeWidgetItem` instead of
  `QListWidgetItem`.
- **(b) Keep `QListWidget`, insert non-checkable bold "category header" rows** between groups
  (skip them in checkable-item iteration). Smaller diff — same widget, same reorder/search logic,
  just an insertion-order and item-flag change in `_load_columns`.

Also: replace raw `col_name` labels (`Order_Fulfillment_Status`) with a small
display-name map for known columns, raw name in a tooltip. Category assignment for the ~20-30
known analysis columns needs a lookup table (doesn't exist yet — build it from
`shopify_tool/core.py`'s output columns, next task's job, not this doc's).

**Decision (made autonomously — no user present to ask, per runner guardrails):** going with
**(b)** — keep `QListWidget`, insert non-checkable bold category header rows. Smaller diff, same
widget/reorder/search logic, still resolves the "no grouping" complaint. Upgrade to (a)
(`QTreeWidget`) later only if users report it's still hard to navigate once grouped. This was the
doc's own first-pass recommendation, so taking it rather than blocking on a question nobody's
here to answer.

## Item 2 — Statistics tab

**Current state is materially different from the Todoist wording.** The backlog item
(`6h8v4VhWRJmCCVw3`, written 2026-07-28) asks for "better UI for stats: display by courier,
session totals, fulfillable vs non-fulfillable tag breakdowns, and a better SKU summary table" as
if none of this exists. It already does — `git log -S _create_statistics_subtab` shows this
landed in **PR #221** ("Statistics page redesign with stat cards"), well before the current
Phase 1-7 roadmap was written. `gui/ui_manager.py:1705` (`_create_statistics_subtab`, the
function actually wired to the tab via `ui_manager.py:431`) already builds: a Session Totals
card row, a horizontally-scrolling By Courier card row, side-by-side Fulfillable/Not-Fulfillable
Tags card rows, and a 6-column SKU Summary `QTableWidget` (#, SKU, Product, Total Qty,
Fulfillable, Not Fulfillable) — populated by `main_window_pyside.py:1249`
(`update_statistics_tab`). `shared/stats.py`, named in the Todoist description, doesn't exist —
the actual file is `shared/stats_manager.py` (server-side aggregate stats, a different thing
from this per-session tab; the Todoist file pointer is stale).

Also checked: a separate, not-yet-promoted backlog item (`6h8rg4FrqFfcqRQV`, "Refactor: Internal
tags... Statistic window") complains tag counts should be per-order, not per-line. Already fixed
— `shopify_tool/analysis.py:1598` (`_build_order_tag_counts`) explicitly dedupes `(Order_Number,
tag)` pairs before counting. Recommend closing/archiving that raw-backlog item as resolved; it's
not one of Phase 5's three official subtasks so it doesn't block anything here, but it's stale
and duplicative if left open.

**What's genuinely left**, verified against the code:

1. **Dead code**: `ui_manager.py:825` (`create_statistics_tab`, singular — a plainer, older
   `QGridLayout` version) has zero call sites anywhere in `gui/`. Superseded by
   `_create_statistics_subtab` since #221 and never deleted. Delete it — pure cleanup, not a
   design decision.
2. **SKU Summary table has no sort or filter.** It's a plain `QTableWidget` populated by manual
   `QTableWidgetItem` construction (`main_window_pyside.py:1304-1333`), no
   `setSortingEnabled(True)`, no search box — unlike the main Analysis Results table, which
   already has `PandasModel` + `QSortFilterProxyModel` (per this repo's own documented pattern
   in `CLAUDE.md`). For a client with a large catalog this is the one real "better SKU summary
   table" gap. Fix: `setSortingEnabled(True)` (near-free, click-to-sort already works on
   `QTableWidget` once enabled) + a `QLineEdit` search box above it filtering by SKU/product
   substring (same filter-text pattern already used elsewhere, e.g. `column_config_dialog.py`'s
   search input).
3. No other correctness issues found in courier-card or tag-card population.

**Proposal**: this item shrinks from "redesign" to "verify (done, findings above) + two small
fixes (delete dead code, add sort/filter to SKU table)." No open design decision — recommend
implementing directly rather than a further brainstorming pass.

## Item 3 — Add Product to Order dialog

**Current state** (`gui/add_product_dialog.py`, 418 lines): `AddProductDialog` — order number
input with autocomplete, SKU input with autocomplete + live stock/warning display, quantity
spinbox, a permanent info box (`_create_info_box`, `main_layout` line 82-83) explaining "Source:
Manual / recalculated for this order only / saved to session / no full re-analysis," and
Cancel/Add buttons.

**Backend verification** (task asks to "verify the backend logic it describes still holds"):
traced the full path in `gui/actions_handler.py:1259` (`_add_product_to_order`) and `:1358`
(`_recalculate_order_fulfillment`). All three claims in the info banner check out against
current code:
- `new_row["Source"] = "Manual"` — `actions_handler.py:1302`.
- Fulfillment is recalculated for the **single order only**, explicitly not touching others or
  re-running full analysis — `_recalculate_order_fulfillment`'s own docstring plus its
  implementation (rebuilds `live_stock` from the current `Final_Stock` column, doesn't call
  `core.run_full_analysis`).
- Saved to session — `_save_manual_addition(product_data)` call at `actions_handler.py:1338`.

No backend bug. The banner is accurate; it's just permanent, static UI real estate for something
that's true 100% of the time this dialog is ever used (it has exactly one workflow, no mode
switch) — the Todoist ask to remove it and document elsewhere (or let it be self-evident) is
sound. Recommend: drop the info box entirely; if the "no full re-analysis" guarantee needs to be
documented somewhere for future maintainers, that's a code comment on
`_add_product_to_order`, not runtime UI (arguably already adequately covered — the method's own
docstring already says this).

**Proposal for "better UI"**: current layout is three stacked `QGroupBox` sections (ORDER
NUMBER, PRODUCT SKU, QUANTITY), each with a redundant `QLabel` repeating what the group title
already says ("Enter order number:" under a group literally titled "ORDER NUMBER"). Consolidate
to a single `QFormLayout` (Order Number / SKU / Quantity as form rows) with the existing
inline status labels (`order_status_label`, `product_info_label`) kept as-is directly under
their field — those are genuinely useful (live existence/stock feedback) and shouldn't be
touched. Keep `warning_box` (low/zero-stock warning) — also genuinely useful, real-time. Net
result: same functionality, ~120 fewer lines of boilerplate `QGroupBox`/`QVBoxLayout` scaffolding,
shorter dialog (currently hardcoded to 500×500 — recompute after the layout change, likely
smaller).

**No open decision needed** — this is a straightforward mechanical simplification once the info
box is confirmed removable, which the backend trace above confirms.

## Testing

No existing test file covers any of the three areas (`tests/` has no `test_column_config*`,
`test_table_config*`, `test_add_product*`, or statistics-tab test). Whoever implements each item
should add a focused test: for Item 1, a `TableConfigManager` round-trip test if the
single-write refactor happens; for Item 2, none needed for the dead-code deletion, a lightweight
sort-enabled assertion for the SKU table fix; for Item 3, a `_validate()`/`_on_add_clicked()`
unit test using a stub `analysis_df`/`stock_df` (no full GUI needed, mirrors how
`test_actions_handler.py` likely already stubs `self.mw`).

## Recommended sequencing

Items 2 and 3 are small enough (verify-and-fix, not redesign) to implement directly without a
further `writing-plans` pass — quick-fix-sized once scoped, per the code findings above. Item 1
needs the (a)-vs-(b) decision above before a plan is worth writing, and is the only one of the
three with any real design surface left. None of the three block each other; any order works.

## Next steps

Get the Item 1 (a)/(b) call from the user, then this doc is ready to feed a `writing-plans` pass
(or, given how small each item nets out to, three short direct-implementation sessions instead of
a formal 3-file plan — light-epic, doesn't need the heavier ceremony a Phase 3/6/7 epic would).
