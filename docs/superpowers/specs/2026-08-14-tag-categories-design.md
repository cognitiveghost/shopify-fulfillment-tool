# Tag categories: remove Ukrainian localization defaults, audit the dialog

**Date:** 2026-08-14
**Phase:** 6
**Todoist:** `6h8v4VqPQCGfGF3V`

## Problem

Two separate problems share one file set.

**1. The shipped tag-category defaults are Ukrainian-localized.** Seven category
labels (`Пакетаж`, `Пріоритет`, `Статус`, `Тип замовлення`, `Додатки`,
`Кур'єр/Доставка`, `Інші`) and three Ukrainian-carrier tags (`NOVA_POSHTA`,
`UKRPOSHTA`, `SELF_PICKUP`) are hardcoded into new profiles. The entire dialog UI
around them is English, so the labels are the outlier. The block is duplicated in
three places, which is why it has drifted before:

| site | what |
|---|---|
| `shopify_tool/profile_manager.py:416-469` | full default block, inside `_default_client_config()` |
| `shopify_tool/profile_migrations.py:134-187` | full default block, inside `migrate_add_tag_categories()` |
| `shopify_tool/profile_migrations.py:274-305` | partial — `order_type`, `accessories`, `delivery` backfill inside `migrate_tag_categories_v1_to_v2()` |

**2. `gui/tag_categories_dialog.py` has real defects.** A full audit of all 798
lines found one silent data-loss bug and several smaller ones (below).

### Out of scope

The Bulgarian stock-export column names (`Артикул`, `Мярка`, `Брой`, `Годност`,
`Партида` in `stock_export.py`, `analysis.py`, `sku_writeoff.py`) are a real
external CSV format, not localization. They are not touched.

`shopify_tool/groups_manager.py` manages **client groups**, not tags. The Todoist
task's file list (`tag_manager.py`/`groups_manager.py`) is stale and does not
describe where this code actually lives.

## Decisions

Confirmed with the user before design:

1. **Existing configs get a migration, exact-match guarded.** A label is rewritten
   only when it still exactly equals the old Ukrainian default for that category
   id. A label the user renamed themselves is left alone. Tags are never removed
   by the migration — relabel only, so nothing already applied to an order breaks.
2. **`delivery` seeds no tags.** Couriers are configured separately in
   `courier_mappings` (DHL/DPD/Speedy); seeding the wrong carriers is worse than
   seeding none. Existing configs keep their carrier tags — see decision 1.
3. **Full dialog audit**, not just the defaults change.

## Part 1 — One source of truth for the defaults

Add `DEFAULT_TAG_CATEGORIES` to `shopify_tool/tag_manager.py`. That module is the
natural home (it already owns `validate_tag_categories_v2` and the v1/v2
normalization) and imports only `json`/`hashlib`/`pandas`, so neither
`profile_manager` nor `profile_migrations` gains a circular import.

```python
DEFAULT_TAG_CATEGORIES = {
    "version": 2,
    "categories": {
        "packaging":   {"label": "Packaging",   "color": "#4CAF50", "order": 1, ...},
        "priority":    {"label": "Priority",    "color": "#FF9800", "order": 2, ...},
        "status":      {"label": "Status",      "color": "#2196F3", "order": 3, ...},
        "order_type":  {"label": "Order Type",  "color": "#9C27B0", "order": 4, ...},
        "accessories": {"label": "Accessories", "color": "#E91E63", "order": 5, ...},
        "delivery":    {"label": "Delivery",    "color": "#FF5722", "order": 6, "tags": []},
        "custom":      {"label": "Other",       "color": "#9E9E9E", "order": 999, "tags": []},
    },
}
```

Colors, orders, ids and every non-delivery tag list are unchanged — only the seven
labels and `delivery`'s tag list change. All three sites read from the constant.

**Callers must deep-copy it.** Both consuming sites write the result into a config
dict that later gets mutated and saved; handing out the module-level object would
let one client's edits leak into the next. `migrate_add_tag_categories` and
`_default_client_config` each take `copy.deepcopy(DEFAULT_TAG_CATEGORIES)`. The
partial backfill in `migrate_tag_categories_v1_to_v2` deep-copies the individual
category dicts it pulls out.

## Part 2 — Relabel migration

New in `profile_migrations.py`:

```python
_UKRAINIAN_DEFAULT_LABELS = {
    "packaging": "Пакетаж",
    "priority": "Пріоритет",
    "status": "Статус",
    "order_type": "Тип замовлення",
    "accessories": "Додатки",
    "delivery": "Кур'єр/Доставка",
    "custom": "Інші",
}

def migrate_tag_category_labels_to_english(client_id: str, config: dict) -> bool:
```

Walks `config["tag_categories"]["categories"]`; for each id in the map, rewrites
`label` to the English default **only if** it currently equals the Ukrainian
string exactly. Returns True if anything changed.

Properties this must have:

- **Idempotent.** A second run changes nothing and returns False (so the caller
  does not re-save on every load).
- **Non-destructive.** Never touches `tags`, `color`, `order`, or `sku_writeoff`.
  A user-renamed label is left as-is.
- **Shape-tolerant.** Handles a missing `tag_categories`, a v1-shaped dict, and a
  `categories` value that is not a dict, without raising. It runs after
  `migrate_tag_categories_v1_to_v2` in the chain, so it can assume v2 in the happy
  path but must not crash on a malformed config.

Registered in `profile_manager.py` at the existing migration site (~line 589),
after the v1→v2 tag-categories migration, and OR-ed into the same "did anything
change, therefore save" flag as its neighbours.

## Part 3 — Dialog audit findings

Ordered by severity. All line numbers are pre-change.

### A. Every list rebuild blanks a category's label (data loss)

**Verified by running it** (`_load_categories()` on a 3-category panel), not by
reading — the first reading of this chain was wrong in two ways, both recorded
below because they are easy to re-derive incorrectly.

`_load_categories()` starts with `self.categories_list.clear()`. Qt does not emit
a single `currentItemChanged(None, previous)` for that — it walks the current
item down the list as rows are removed, emitting repeatedly, and only the final
emission has `current is None`. Each non-None emission reaches
`_on_category_selected`, which **reassigns `self.current_category_id`**. The final
`current is None` emission then calls `_set_editor_enabled(False)` at :299
*before* clearing `current_category_id` at :300, and
`_set_editor_enabled(False)` calls `category_id_input.clear()` (:398) and
`label_input.clear()` (:399) with signals unblocked. Both fire `textChanged` →
`_on_editor_changed` → `_save_editor_to_working_copy()`, and the second one writes
`label = ""` into whichever category `current_category_id` was last reassigned to.

Two consequences that a code-reading misses:

- **The victim is not the selected category.** It is the penultimate category in
  sorted order — the last one Qt promotes to current while draining the list.
  Observed identically for a selection on row 0, row 1 and row 2 of three.
- **The delete path does not escape.** `_on_delete_category` nulls
  `current_category_id` at :712 before rebuilding, but the rebuild's own
  `currentItemChanged` emissions set it right back. Deleting any category today
  blanks another category's label.

So this fires on **both** mutation paths in the dialog — `+ New` and `Delete` —
every time. `validate_tag_categories_v2` accepts an empty label, so it saves
silently and the category renders as a blank row.

Scope of the corruption is `label` only: the two spurious saves both land before
`tags_list.clear()` (:400) and the mappings-table reset (:401), and the
intermediate `currentItemChanged` emissions reload the editor for each category
they pass through, so `tags`, `color`, `order` and `sku_writeoff` are written back
with correct values. Confirmed against a category carrying a live writeoff
mapping.

**Fix at the root, not the call site.** `_load_categories()` guards the whole
rebuild with `QSignalBlocker(self.categories_list)` (or explicit `blockSignals`
around it), so no `currentItemChanged` escapes during a rebuild. Reordering the
two lines in `_on_category_selected` would not be enough — the reassignment
happens in the non-None emissions, which that reorder does not touch.

### B. Theme change leaves list-row colors blended against the old background

`_load_categories()` blends each category color 45/55 against
`theme.background`. `_on_theme_changed` refreshes `self.theme` and the color
swatch but never re-blends the rows, so after a light/dark switch every row keeps
a background mixed against the previous theme. Fix: re-run the row rebuild from
`_on_theme_changed`. This depends on A being fixed first — without the signal
guard, a theme switch would trigger the label wipe.

### C. Removing a tag orphans its writeoff mappings

`_on_remove_tag` takes the item out of `tags_list`, but
`_save_editor_to_working_copy` rebuilds `mappings` from
`writeoff_mappings_table`, whose rows for the removed tag are still there. The
saved config keeps a mapping keyed by a tag the category no longer contains; it
can never fire again and no validation reports it. Fix: drop the matching table
rows in `_on_remove_tag` before saving.

### D. Category ID validation accepts non-ASCII

`_on_new_category:651` uses `category_id.replace("_", "").isalnum()`.
`str.isalnum()` is True for any Unicode letter, so `категорія` and `café` pass a
check whose message promises "lowercase letters, numbers, and underscores".
Fitting, given the rest of this task. Fix: an explicit ASCII
lowercase/digit/underscore check.

### E. New-category `order` collides after a deletion

`_on_new_category:672` sets `"order": len(categories) + 1`. Delete two categories
from the seven defaults and the next new one gets an order already in use; sort
order between the two then depends on dict insertion order. Fix: next unused
order, computed from the existing values rather than from the count.
`custom`'s sentinel `999` and the spinbox maximum of `999` both have to survive
this — a naive `max(...) + 1` yields 1000, which the spinbox cannot represent.

### F. Editor color swatch is stale after deselection

`_set_editor_enabled(False)` clears the label, tags and mappings table but leaves
`self.current_color` and the swatch showing the last category's color. Cosmetic.
Fix alongside the other clears.

### G. Quantity cells accept free text and silently fall back to 1.0

Writeoff table cells are editable. `_save_editor_to_working_copy:443-447` catches
`ValueError` on `float(quantity_str)` and substitutes `1.0` with only a log line,
so typing `abc` into Quantity silently writes a quantity of 1. The table is only
ever populated through the Add Mapping dialog, which already uses a
`QDoubleSpinBox` — so make the cells read-only and the fallback becomes
unreachable rather than silent.

### H. Duplicate (tag, SKU) mapping rows

`_on_add_mapping` does not check for an existing row with the same tag and SKU.
Two identical rows produce two entries in `mappings[tag]`, doubling the
deduction. Multiple *different* SKUs per tag are the intended feature and stay
allowed; only the exact duplicate is rejected.

### I. `validate_tag_categories_v2` accepts an empty label

Defense in depth against A, and worth having independently: a category with
`label: ""` renders as a blank row that cannot be identified in the list. Add an
empty/whitespace-only label error to the validator in `tag_manager.py`.

### Considered and deliberately not changed

- `TagCategoriesDialog.__getattr__` proxying to the panel is a smell but is
  load-bearing backwards compatibility with an existing test and `actions_handler`.
- `_on_apply` shows a "Saved" info box and `_on_save` does not. Inconsistent, but
  changing dialog confirmation behavior is a UX decision outside this task.
- `_on_writeoff_enabled_changed` compares an `int` state to `Qt.Checked`. It works
  under PySide6's IntEnum semantics; the implementation adds a test pinning that
  behavior rather than rewriting the signal.

## Testing

`tests/test_tag_categories_dialog.py` currently holds exactly one test. Each
finding above gets a regression test that is confirmed to fail before its fix.

Defaults and migration (`tests/test_profile_manager.py` or a new
`tests/test_tag_category_labels_migration.py`):

- A config with untouched Ukrainian labels is fully relabeled.
- A config whose `packaging` label was renamed by the user keeps the rename while
  its siblings are relabeled.
- Running the migration twice returns False the second time and changes nothing.
- `tags`, `color`, `order` and `sku_writeoff` are byte-identical before/after,
  including a config that still has `NOVA_POSHTA`/`UKRPOSHTA`.
- Missing / v1-shaped / malformed `tag_categories` does not raise.
- A new profile from `_default_client_config()` has English labels, an empty
  `delivery` tag list, and no Cyrillic anywhere in `tag_categories`.
- Two profiles created in sequence do not share mutable state (deep-copy check).

Dialog (`tests/test_tag_categories_dialog.py`), all headless under
`QT_QPA_PLATFORM=offscreen`:

- **A:** assert **every** label is unchanged after a rebuild — do not assert
  against a named victim, since which category gets blanked is a Qt
  list-draining detail. Cover both mutation paths: add a category, and delete a
  category. Both must fail on today's code. A third case asserts `tags`, `color`,
  `order` and `sku_writeoff` also survive, pinning the corruption scope.
- **B:** emit `theme_changed`, assert row backgrounds re-blend and no label is
  wiped.
- **C:** remove a tag that has a writeoff mapping, assert the mapping is gone from
  the saved config.
- **D:** `категорія` is rejected; `my_category_2` is accepted.
- **E:** delete two of seven defaults, add a category, assert its order is unused
  and ≤ 999.
- **F:** deselect, assert the swatch resets.
- **G:** quantity cells are read-only.
- **H:** adding the same tag+SKU twice is rejected; same tag with a different SKU
  is accepted.
- **I:** validator rejects an empty label.

Gate before finishing: `QT_QPA_PLATFORM=offscreen python -m pytest` and
`ruff check . --exclude shared`.

## Risk

The migration writes to live warehouse client configs. Its guard is exact string
equality against seven known constants, and it only ever replaces one string
field — so the worst case for a config it misjudges is an English label where the
user wanted Ukrainian, recoverable by typing the old name back into the dialog.
No tag, color, order or writeoff data is reachable from this code path.

Fix A changes behavior users may have unknowingly worked around (a blanked label
they retyped). That is strictly an improvement, but it is the one change in this
set that alters what the dialog does rather than what it stores.
