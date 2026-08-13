# Settings structural split (Phase 6 "Track C") — design

**Date**: 2026-08-12
**Todoist**: `6h8v4VhrcGgHJpcV` — "Profile manager: review logic/backend, resolve duplicate
client-settings windows" (Phase 6 epic `6h8v4C2c9xgR7gfV`)
**Prerequisite for**: UI Design System Track 4 — Settings Hub (`6hG88cmcgF282MwV`)
**Related**: `2026-08-09-packaging-unlock-and-perf-audit-design.md` (Track C),
`2026-08-11-ui-design-system-vision-design.md` (Track 4)

## Problem

Three settings surfaces exist. Their names and their entry points do not line up.

| Surface | Lines | Edits | Opened by | Window title |
|---|---|---|---|---|
| `SettingsWindow` (`gui/settings_window_pyside.py`) | 3593 | `shopify_config.json` | buttons labeled **"Client Settings"** (`ui_manager.py:821`, `:1177`) | *Settings - CLIENT_x* |
| `ClientSettingsDialog` (`gui/client_settings_dialog.py:336`) | 671 (file) | `client_config.json` | sidebar context menu → "Edit Client…" (`client_sidebar.py:725`) | *Client Settings - CLIENT_x* |
| `ProfileManagerDialog` (`gui/profile_manager_dialog.py`) | 121 | — | **nothing** | *Manage Profiles* |

The Phase 6 task calls these "duplicate client-settings windows". They are not duplicates in
data terms — they edit two different JSON files through two different save paths. The actual
defects are:

1. **The names are swapped relative to the entry points.** The button labeled "Client
   Settings" opens the window titled "Settings"; the window titled "Client Settings" is
   reached from somewhere else entirely.
2. **`ProfileManagerDialog` is dead and broken.** Nothing constructs it, and it calls
   `self.parent.create_profile()` / `self.parent.active_profile_name`, neither of which
   exists on `MainWindow`. It would raise `AttributeError` on open.
3. **`ClientSettingsDialog`'s "Advanced" tab is an empty placeholder** whose entire content is
   a label telling the user to go use the other window.
4. **`SettingsWindow` cannot be worked on safely.** At 3593 lines it is the largest file in
   the repo, and Track 4 must build a Settings Hub on top of it.

## Scope decision

Track C **splits**; Track 4 **merges**. Confirmed with the user on 2026-08-12.

This matches what both prior design docs already assume: the 2026-08-09 audit scopes Track C
as "structural split ahead of Phase 6's UI pass", and the 2026-08-11 vision doc scopes Track 4
as the Hub that "directly resolves Phase 6's flagged 'two competing client-settings windows'".
The Todoist task's wording predates both.

Folding `ClientSettingsDialog` into `SettingsWindow` now would mean orchestrating two config
files, two save paths and two locks *while* the 3593-line file is being taken apart. Once the
panel contract below exists, Track 4 folds it in as one more nav page.

## Design

### 1. Pages become panel objects

All nine pages are currently `create_*_tab()` methods on `SettingsWindow`. They stash widget
references on `self` (`self.rule_widgets`, `self.stock_delimiter_edit`,
`self.courier_mapping_widgets`, …) and `save_settings()` (lines 3034–3283) reaches back into
every one of them. Moving the methods to mixins would move the line count without removing any
of that coupling, and would give Track 4 nothing to build on.

Each page becomes a `QWidget` subclass in its own module, with a three-method contract:

```python
# gui/settings/base.py
class SettingsPage(QWidget):
    """A single settings page. The window shell owns nav, stacking and saving."""

    def collect(self) -> dict:
        """Config keys this page owns, merged into config_data by the shell."""
        return {}

    def validate(self) -> tuple[bool, list[str]]:
        """(ok, error messages). Blocks the save when not ok."""
        return True, []
```

This is not a new invention. It is the shape two collaborators in this file already use —
`TagCategoriesPanel.validate_categories()`/`.get_categories()` and
`ColumnMappingWidget.validate_mappings()`/`.get_mappings()` — and it is precisely the sequence
`save_settings()` performs inline today: validate mappings, validate tag categories, collect
every section, then one write.

`SettingsWindow.save_settings()` collapses to: validate each page (first failure shows its
message and aborts, as today), merge each page's `collect()` into `config_data`, then the
**single existing** `profile_manager.save_shopify_config` background write. The write path,
the `Worker` strong-reference handling, and the save-button state machine are unchanged.

Pages fall into two kinds and the default methods cover both:

- **Config-contributing** — General, Rules, Packing Lists, Stock Exports, Mappings, Weight,
  Tag Categories. These return their keys from `collect()`.
- **Self-saving** — Sets and Column Config already persist immediately through
  `profile_manager.add_set`/`delete_set` and `table_config_manager`, and contribute nothing to
  `save_settings()` today. They inherit the `{}` default; the shell needs no special case.

### 2. Module layout

Flat under `gui/settings/`, with no `pages/` sub-level:

```
gui/settings/
    __init__.py          re-exports SettingsWindow
    window.py            the shell: nav groups, QStackedWidget, save orchestration
    base.py              SettingsPage
    fields.py            FILTERABLE_COLUMNS, FILTER_OPERATORS, CONDITION_FIELDS,
                         CONDITION_OPERATORS, ACTION_TYPES + the shared filter-row builder
    general.py           ~85 lines today
    rules.py             ~990 lines today (rule / step / condition / action builders)
    packing_lists.py     ~160
    stock_exports.py     ~60
    mappings.py          ~165
    sets.py              ~290 + SetEditorDialog
    weight.py            ~850
```

`fields.py` exists because `add_filter_row` and the field/operator constants are shared by
Packing Lists and Stock Exports; without it the two modules would duplicate them.

`gui/settings_window_pyside.py` is **deleted, not shimmed**. It has two importers
(`gui/actions_handler.py:9` and `tests/test_settings_window_weight_quick_add.py`) plus its own
`__main__` block; all are updated. A compatibility shim would be one more file to explain and
delete later.

### 3. Safety net, written first

3593 lines move with zero intended behavior change, and existing coverage of this file is a
single test for weight quick-add. Before anything moves:

A **config round-trip characterization test** — construct `SettingsWindow` from a fixture
config that populates every section (settings, rules with steps/conditions/actions, packing
list configs, stock export configs, column mappings v2, courier mappings, weight config, tag
categories), call `save_settings()` with the background save stubbed, and assert the collected
`config_data` equals the input.

One test covering all seven config-contributing pages. If the split drops or renames a field,
it fails. This test must pass on the pre-split code first — a characterization test that has
never been green against the old implementation proves nothing.

**Feasibility verified on 2026-08-12** against the pre-split code, because
`tests/test_settings_window_weight_quick_add.py`'s docstring asserts the opposite:

> *its full `__init__` builds every settings tab and hangs under the offscreen QPA platform
> (no way to dismiss real dialogs headlessly)*

**That claim is false.** `SettingsWindow(client_id=..., client_config=..., profile_manager=None)`
constructs cleanly under `QT_QPA_PLATFORM=offscreen` and registers all nine pages. The
docstring's rationale should be corrected as part of this work, or it will keep steering tests
away from the real class. (The test's own approach — building an instance via `__new__` — can
stay; only the justification is wrong.)

Four conditions the test must satisfy, each found by probing rather than assumed:

1. **Stub `QMessageBox`'s static methods.** This is the trap. `save_settings()` validates
   column mappings at lines 3184–3200 and returns early via a *modal* `QMessageBox.warning`
   on failure. A headless test that trips this blocks forever rather than failing — which is
   the most plausible origin of the "hangs" folklore above.
2. **Pass a `Mock` profile_manager.** `save_settings()` ends by constructing
   `Worker(self.profile_manager.save_shopify_config, ...)`; `None` raises `AttributeError`
   inside the broad `except Exception`, which surfaces only as another modal.
3. **Satisfy required mappings or validation aborts before six of the seven pages are ever
   collected.** On-disk v2 format is `{csv_column: internal_name}` (the widget inverts it
   internally). Orders requires `Order_Number`, `SKU`, `Quantity`, `Shipping_Method`; stock
   requires `SKU`, `Stock`.
4. **Use the real `weight_config` schema** — `length_cm` / `width_cm` / `height_cm`, not
   `l`/`w`/`h`. Read `_weight_collect_config()` and `_weight_populate_products()` when writing
   the fixture. Note also that an empty `weight_config` is normalized on collect to
   `{"volumetric_divisor": 6000, "products": {}, "boxes": []}`, so the fixture must be
   populated or the assertion must expect the normalized form.

With those four in place, the remaining eight sections round-trip byte-identical on the
pre-split code, confirming the net works before it is relied on.

### 4. Dead code and naming

- **Delete `gui/profile_manager_dialog.py`** (121 lines) — unreachable, and broken if reached.
- **Delete `ClientSettingsDialog`'s "Advanced" tab** (`_create_advanced_tab`, lines 524–539) —
  a placeholder pointing at the other window.
- **Rename, per the user's decision:**
  - `ui_manager.py:821` and `:1177` — "Client Settings" → **"Settings"** (both buttons, and
    their tooltips).
  - `ClientSettingsDialog` window title — "Client Settings - CLIENT_x" → **"Client Profile -
    CLIENT_x"**. "Client Profile" is also the nav-page name Track 4 will use when it folds
    this dialog into the Hub.

  Class names stay as they are; renaming `ClientSettingsDialog` itself is churn Track 4 will
  redo.

### 5. `profile_manager.py` review

The Todoist task's second half. Four bounded items, not a rewrite.

1. **Extract migrations.** The six `_migrate_*` methods (lines 347–745, ~400 lines) move to
   `shopify_tool/profile_migrations.py` as functions taking `(client_id, config)` and
   returning `bool`. `ProfileManager` calls them from `load_client_config` /
   `load_shopify_config` exactly as now. 1872 → ~1470 lines on a clean seam.
2. **Drop an unused network read.** `ClientSettingsDialog:383` assigns
   `self.shopify_config = profile_manager.load_shopify_config(client_id)` and never reads it
   again. On the production Windows file server that is a wasted round-trip on every open.
3. **Fix a lost update (real bug).** `ClientSettingsDialog` loads the whole
   `client_config.json` at open and writes the whole thing at save. Any
   `update_ui_settings()` that lands in between — the sidebar's pin toggle
   (`client_sidebar.py:_toggle_pin`) or group move (`_move_to_group`), both of which write the
   same file — is silently reverted when the dialog saves.

   Root-cause fix in the one place all these callers route through: a new
   `ProfileManager.update_client_profile(client_id, name=None, ui_settings=None)` that
   loads, merges only the supplied keys, and saves inside the existing lock — the same
   load-merge-save shape as `update_ui_settings` (lines 1578–1619), still a single write. The
   dialog calls it with the five fields it actually owns (`client_name` plus `is_pinned`,
   `group_id`, `custom_color`, `custom_badges`) instead of writing back a whole stale config.
4. **Repopulate the cache after a migration.** `load_shopify_config` returns at line 1002
   after a migration without writing `_config_cache`, so the next call re-reads from the
   share. `load_client_config` (lines 913–921) already handles this correctly by re-stat'ing;
   apply the same treatment.

## Testing

| What | How |
|---|---|
| Split loses no config | The round-trip characterization test above — green pre-split, green post-split |
| Every page still builds | New: construct `SettingsWindow` headlessly and assert all nine nav pages register. No such test exists today; the round-trip test's fixture gives it to us for free |
| Weight quick-add | `tests/test_settings_window_weight_quick_add.py`, import path updated and its false "hangs under offscreen QPA" docstring corrected |
| Panel contract | Each page's `collect()`/`validate()` exercised through the round-trip test |
| Lost update fixed | New test: open-dialog state + interleaved `update_ui_settings()` + dialog save → both survive |
| Migrations still run | Existing `tests/test_profile_manager.py` covers the migration paths |
| Dead code gone | `test_dialog_button_guard.py`-style guard is unnecessary; deletion is verified by the suite still passing |

Gate: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest` (455 + 13 = 468 baseline) and
`.venv/bin/ruff check . --exclude shared`.

## Non-goals

- **Merging the two windows** — Track 4 (Settings Hub).
- **Any visual redesign** — no layout, spacing, color or component changes. Track 4/5.
- **Splitting `gui/actions_handler.py`** (2171 lines) — named by the 2026-08-09 audit, but the
  Hub does not depend on it. Deferred until something actually needs it.
- **Anything under `shared/`** — one-way synced from `packing-tool`.
- **Renaming `ClientSettingsDialog` the class**, or restructuring `client_config.json` /
  `shopify_config.json` on disk.

## Risks

- **Silent field loss during the move** is the main risk; the characterization test exists
  specifically for it, and must be green against the pre-split code before any page moves.
- **`create_column_config_tab` reaches for `self.parent()` and `main_window.table_config_manager`**
  (lines 3341–3347), with a fallback page when unavailable. The panel must keep receiving the
  main window, so it takes it as an explicit constructor argument rather than walking
  `parent()` from inside a package module.
- **Import cycles** — pages must not import `window.py`. Shared constants live in `fields.py`,
  which imports nothing from the package.
- **Windows-only visual verification** remains outstanding from Tracks 1–3 (see PR #270). This
  track changes two button labels and one window title; it adds to that pending check rather
  than needing its own.
