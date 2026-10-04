# UI refresh phase 9: Sets, Weight, Reports and Tag categories on the web tier. Implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the last four Qt settings pages (Sets, Weight, Reports, Tag categories) with pages of the
Client settings web document, so that no Qt page is left in the dialog.

**Architecture:** Each page becomes a *draft* beside the four phases 7 and 8 built: a class with no widget
that holds the page's values, takes every edit through `apply(action, args)`, words everything the page
shows in `view()`, and meets `PageContract`, so `SettingsWindow` saves and marks it like any other page. One
script per page (`gui/web/settings_<page>.js`) draws that view inside the settings document and reports each
edit through `SettingsBridge.edit`. CSV import and export go through three new bridge slots: the host opens
the native file dialog and hands the path to the draft.

**Tech Stack:** Python 3.14, PySide6 (Qt widgets, QtWebEngine, QWebChannel), pandas, plain CSS and
JavaScript (no build step, no framework), pytest + pytest-qt driving a real Chromium offscreen.

**Spec:** `docs/superpowers/specs/2026-10-04-ui-refresh-phase9-settings-lists-design.md`. Read it whole
before starting; this plan argues from it. Every label, sentence and empty state is in spec §4 to §8 and is
verbatim in the code.

## How this plan carries its code

**The code is in patch files, not in this document.** The folder
`docs/superpowers/plans/2026-10-04-ui-refresh-phase9-settings-lists/` holds two patches per task: the
task's tests, and the task's implementation. You apply them with `/usr/bin/git apply <path>`; you do not
retype anything.

**Every patch was run before this plan was written.** The patches were generated from a working tree on this
branch (code identical to `origin/main` at 7002882). There, each draft's tests passed, the four pages were
driven in a real Chromium, the dialog was rendered and looked at, `ruff check .` passed, and the whole suite
passed but for the baseline failures below. The patches were then applied, in this plan's order, to a clean
tree, and rebuilt that working tree byte for byte.

So your job in each task is: apply the tests, see them fail for the reason given, apply the implementation,
see them pass, **read what you applied against the spec section the task names**, and commit. If a patch
does not apply, `main` has moved under it: run `/usr/bin/git apply --3way <path>`, resolve what it marks,
and say what differed in your handoff. If a test fails after its implementation is applied, suspect a
change on `main` since 7002882 before you suspect the design, and say what differed.

**Baseline failures** (they fail on `main` too, and are not this task's):
`tests/test_label_printing.py::TestImageToZpl::test_black_pixels_become_set_bits`,
`::test_invert_flips_the_polarity` and `::test_rotate_and_invert_compose`.

## Global Constraints

- Work in `/home/gloopy/Desktop/Projects/shopify-fulfillment-tool/.claude/worktrees/dr-21` on branch
  `dr/21-ui-refresh-phase-9-client-settings-on-th`. Never `cd` anywhere else. If `.venv` is missing, run
  `./scripts/setup_venv.sh`.
- Run tests only as `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q <paths>`. A hook blocks any
  other Bash text containing the word "pytest", so write or change test files with Write/Edit, never with
  heredocs.
- Git: `/usr/bin/git`, one plain command per Bash call, with no `;`, `&&` or `$VAR`. Commit with
  `/usr/bin/git commit -F <absolute path to a message file>`; write the message file under your job's tmp
  dir. End every message with the attribution lines your session is given. The post-commit hook refreshes
  the graphify graph; there is nothing to run by hand.
- No hex, colour name, `rgb()`, px font size, `transition`, `transform`, gradient or `opacity` in any file
  under `gui/` (`shared/style_lint.py`, enforced by `tests/test_style_literals_guard.py`). The one hex this
  phase has, `DEFAULT_TAG_COLOR` in `gui/settings/tags_state.py`, carries `# style-lint: allow`: it is
  stored data, not a theme value.
- `shared/` does not change in this phase. Packing Tool needs no work.
- Python owns every value and every sentence. A page script computes nothing and validates nothing.
- The page sends strings and booleans only. A draft drops an edit of any other shape and returns `False`.
- `collect()` never raises: a value that blocks Save is written as typed.
- A value a draft does not draw is kept: each entry holds its stored dict, and `collect()` writes the drawn
  keys over it.

## Review Focus

The inputs a person is most likely to hit that the spec only implies. Each has its test in the task that
owns the code:

1. **A profile with malformed stored values** (a set whose components are not a list, a category that is
   not a dict, a report whose `columns` is a string). The page opens and saves; nothing raises. Tests named
   `test_odd_stored_values_load_without_raising` in Tasks 2, 4 and 5, and
   `test_an_empty_config_loads_as_the_defaults` in Task 3.
2. **A stock CSV with thousands of SKUs imported into Weight.** The list shows 200 rows, says so, and the
   footer's link can still reach a row past the limit.
   `test_the_list_stops_at_the_limit_and_reveal_lists_a_row_past_it` in Task 3.
3. **Save pressed, or the unsaved check running, while a value is half typed.** `collect()` writes it as
   typed and does not raise. `test_a_quantity_that_is_not_a_whole_number_in_range_blocks` (Task 2),
   `test_a_divisor_that_is_not_a_whole_number_in_range_blocks` (Task 3),
   `test_a_write_off_quantity_out_of_range_blocks` (Task 5).
4. **The wrong file picked for an import.** The draft is unchanged and the operator is told what to do, or
   pointed to Logs. `test_a_file_with_the_wrong_columns_raises_and_changes_nothing` (Task 2),
   `test_a_file_problem_is_shown_as_it_is` and `test_any_other_import_failure_points_to_logs` (Task 6).
5. **Something sent by the page that is not one of the draft's own imports** (another page's kind, a path).
   No dialog opens and no file is read.
   `test_a_kind_the_showing_draft_does_not_have_opens_no_dialog` in Task 6.

## File Structure

| File | Task | What it is |
|---|---|---|
| `gui/settings/contract.py` | 1 | Gains `FileProblem` |
| `gui/settings/bridge.py` | 1 | Gains `importFile`, `exportFile`, `toastAction` |
| `gui/settings/sets_state.py` (new) | 2 | `SetsDraft` |
| `gui/settings/weight_state.py` (new) | 3 | `WeightDraft` and its CSV imports |
| `gui/settings/rules_state.py` | 4 | `iso_date` becomes a module function |
| `gui/settings/reports_state.py` (new) | 4 | `ReportsDraft`, `match_text` |
| `gui/settings/tags_state.py` (new) | 5 | `TagsDraft`, `DEFAULT_TAG_COLOR` |
| `gui/settings/web_host.py` | 6 | Runs imports and exports; raises the toast |
| `gui/web/settings_sets.js`, `settings_weight.js`, `settings_reports.js`, `settings_tags.js` (new) | 7 | One page each |
| `gui/web/settings_rules.js` | 7 | `conditionRow` takes its key, its data and its action names |
| `gui/web/settings.js`, `settings.html`, `settings.css` | 7 | Routing, the toast, Enter in a `data-enter` field, the pages' styles |
| `gui/settings/window.py` | 8 | Every page is a draft; the poll goes |
| `gui/settings/fields.py`, `gui/settings/__init__.py`, `gui/actions_handler.py` | 8 | The Qt helpers and the dead dialog entry point go |
| Deleted | 8 | `gui/settings/sets.py`, `weight.py`, `reports.py`, `report_editor.py`, `base.py`, `gui/tag_categories_dialog.py`, and six test files |
| `docs/design/ui-refresh/roadmap.md`, `CONTEXT.md`, renders | 9 | Docs |

Below, `PLAN/` stands for `docs/superpowers/plans/2026-10-04-ui-refresh-phase9-settings-lists/`. Write the
path in full in every command.

---

### Task 1: `FileProblem` and the bridge's three slots

**Spec:** §3.2, §8.1.

**Files:**
- Modify: `gui/settings/contract.py`, `gui/settings/bridge.py`
- Test: `tests/test_settings_bridge.py`

**Interfaces:**
- Produces: `gui.settings.contract.FileProblem(headline: str, detail: str)`, an `Exception` with
  `.headline` and `.detail`.
- Produces on `SettingsBridge`: slots `importFile(kind: str)`, `exportFile(kind: str)`, `toastAction()`;
  Python-facing signals `importRequested(str)`, `exportRequested(str)`, `toastActionRequested()`.
- The toast itself is `PageBridge`'s existing `raise_toast(message, flag=False)` and `toastRaised(str,
  bool)` (`gui/web_page.py`). Do **not** declare a second `toastRaised` on `SettingsBridge`: a signal of
  that name with another signature never reaches the page.

- [ ] **Step 1: Apply the test**

Run: `/usr/bin/git apply docs/superpowers/plans/2026-10-04-ui-refresh-phase9-settings-lists/01-bridge-tests.patch`

- [ ] **Step 2: Run it to see it fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_settings_bridge.py`
Expected: 1 failed, with `AttributeError: 'SettingsBridge' object has no attribute 'importRequested'`.

- [ ] **Step 3: Apply the implementation**

Run: `/usr/bin/git apply docs/superpowers/plans/2026-10-04-ui-refresh-phase9-settings-lists/01-bridge.patch`

- [ ] **Step 4: Run the tests to see them pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_settings_bridge.py`
Expected: all pass.

- [ ] **Step 5: Commit**

`/usr/bin/git add gui/settings/contract.py gui/settings/bridge.py tests/test_settings_bridge.py`, then
commit with the message `Settings bridge: import, export and the toast's action`.

---

### Task 2: `SetsDraft`

**Spec:** §4 (all of it), §8.1.

**Files:**
- Create: `gui/settings/sets_state.py`
- Test: `tests/test_settings_draft_sets.py`

**Interfaces:**
- Consumes: `FileProblem`, `PageContract` (Task 1); `gui.settings.page_state._shaped`;
  `shopify_tool.set_decoder.import_sets_from_csv`, `export_sets_to_csv`.
- Produces: `SetsDraft(set_decoders: dict)` with `apply(action, args) -> bool`, `view() -> dict`,
  `collect() -> {"set_decoders": dict}`, `blocker()`, `blocker_key()`, `validate()`,
  `stored() -> dict`.
- Produces the file interface Task 6 relies on, as class attributes and methods:
  `imports: dict[kind, dialog title]`, `exports: dict[kind, (dialog title, default name)]`,
  `import_failed: dict[kind, headline]`, `export_failed: dict[kind, headline]`,
  `import_csv(kind, path, update=False) -> (text, can_update)`, `export_csv(kind, path) -> text`.
  Kinds: imports `sets-merge` and `sets-replace`; export `sets`.
- Produces helpers Task 3 imports: `whole_text(value) -> str`, `_plural(count, word) -> str`,
  `_text(value) -> str`.
- `view()["sets"]` is the shape in spec §4.6. A row's uid is a string counting from `"1"` in load order.

- [ ] **Step 1: Apply the tests**

Run: `/usr/bin/git apply docs/superpowers/plans/2026-10-04-ui-refresh-phase9-settings-lists/02-sets-draft-tests.patch`

- [ ] **Step 2: Run them to see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_settings_draft_sets.py`
Expected: a collection error, `ModuleNotFoundError: No module named 'gui.settings.sets_state'`.

- [ ] **Step 3: Apply the implementation**

Run: `/usr/bin/git apply docs/superpowers/plans/2026-10-04-ui-refresh-phase9-settings-lists/02-sets-draft.patch`

- [ ] **Step 4: Run the tests to see them pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_settings_draft_sets.py`
Expected: 38 passed.

- [ ] **Step 5: Read `gui/settings/sets_state.py` against spec §4.2 to §4.6**

Check each action of §4.2 has a branch in `apply`, each line of §4.3 is in `_problems`, and every sentence
of §4.6 is a constant at the top of the file.

- [ ] **Step 6: Commit**

`/usr/bin/git add gui/settings/sets_state.py tests/test_settings_draft_sets.py`, then commit with the
message `Sets draft: the Sets page's values with no widget`.

---

### Task 3: `WeightDraft`

**Spec:** §5 (all of it), §8.1.

**Files:**
- Create: `gui/settings/weight_state.py`
- Test: `tests/test_settings_draft_weight.py`

**Interfaces:**
- Consumes: `FileProblem`, `PageContract`; `whole_text`, `_plural`, `_text` from
  `gui.settings.sets_state` (Task 2); `shopify_tool.csv_utils.detect_csv_delimiter`, `resolve_delimiter`.
- Produces: `WeightDraft(weight_config: dict, column_mappings: dict, stock_csv_delimiter: str)` with the
  same page methods as `SetsDraft`, and the same file interface. Kinds: imports `products-stock`,
  `products-dims`, `boxes`; exports `products`, `boxes`.
- Produces: `number_text(value) -> str` and `parse_number(text) -> float | None`.
- `view()["weight"]` is the shape in spec §5.7. Products and boxes share one uid counter: products first,
  in stored order, then boxes.

- [ ] **Step 1: Apply the tests**

Run: `/usr/bin/git apply docs/superpowers/plans/2026-10-04-ui-refresh-phase9-settings-lists/03-weight-draft-tests.patch`

- [ ] **Step 2: Run them to see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_settings_draft_weight.py`
Expected: a collection error, `ModuleNotFoundError: No module named 'gui.settings.weight_state'`.

- [ ] **Step 3: Apply the implementation**

Run: `/usr/bin/git apply docs/superpowers/plans/2026-10-04-ui-refresh-phase9-settings-lists/03-weight-draft.patch`

- [ ] **Step 4: Run the tests to see them pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_settings_draft_weight.py`
Expected: 50 passed.

- [ ] **Step 5: Read `gui/settings/weight_state.py` against spec §5.3 and §5.6**

The three imports must keep today's rules: compare `_import_stock`, `_import_dimensions` and
`_import_boxes` with `_weight_import_skus_from_stock_csv`, `_weight_import_products_from_csv` and
`_weight_import_boxes_from_csv` in `gui/settings/weight.py`, which is still in the tree until Task 8.

- [ ] **Step 6: Commit**

`/usr/bin/git add gui/settings/weight_state.py tests/test_settings_draft_weight.py`, then commit with the
message `Weight draft: divisor, products, boxes and their CSV imports`.

---

### Task 4: `ReportsDraft`

**Spec:** §6 (all of it), §3.1 (the `iso_date` row).

**Files:**
- Create: `gui/settings/reports_state.py`
- Modify: `gui/settings/rules_state.py`
- Test: `tests/test_settings_draft_reports.py`

**Interfaces:**
- Consumes: `REPORT_FILTER_OPERATORS`, `report_filter_fields` from `gui.settings.fields`;
  `count_matches`, `normalize_operator`, `parse_sku_list` from `shopify_tool.report_filters`;
  `get_unique_column_values` from `shopify_tool.core`.
- Produces in `gui/settings/rules_state.py`: `iso_date(text: str) -> str`, a module function
  (`RulesDraft._iso_date` now calls it, and `RulesDraft._dates` is gone).
- Produces: `ReportsDraft(packing_configs, stock_configs, analysis_df=None)` with the page methods, and
  `match_text(counts) -> str`. It has no file interface.
- `view()["reports"]["groups"]` is the shape in spec §6.7. An open report's `editor["filters"]` entries
  have exactly the keys of a rule condition's view (phase 8 spec §4.7): Task 7 draws them with the same
  function. Uids count packing lists first, then stock exports.

- [ ] **Step 1: Apply the tests**

Run: `/usr/bin/git apply docs/superpowers/plans/2026-10-04-ui-refresh-phase9-settings-lists/04-reports-draft-tests.patch`

- [ ] **Step 2: Run them to see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_settings_draft_reports.py`
Expected: a collection error, `ModuleNotFoundError: No module named 'gui.settings.reports_state'`.

- [ ] **Step 3: Apply the implementation**

Run: `/usr/bin/git apply docs/superpowers/plans/2026-10-04-ui-refresh-phase9-settings-lists/04-reports-draft.patch`

- [ ] **Step 4: Run the tests to see them pass, with the Rules draft's**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_settings_draft_reports.py tests/test_settings_draft_rules.py`
Expected: all pass (204 at the time of writing). The Rules draft's tests prove the `iso_date` move changed
nothing.

- [ ] **Step 5: Commit**

`/usr/bin/git add gui/settings/reports_state.py gui/settings/rules_state.py tests/test_settings_draft_reports.py`,
then commit with the message `Reports draft: packing lists and stock exports`.

---

### Task 5: `TagsDraft`

**Spec:** §7 (all of it).

**Files:**
- Create: `gui/settings/tags_state.py`
- Test: `tests/test_settings_draft_tags.py`

**Interfaces:**
- Consumes: `PageContract`, `_shaped`; `shopify_tool.tag_manager.validate_tag_categories_v2`.
- Produces: `TagsDraft(tag_categories: dict)` with the page methods, `stored() -> dict` (the categories in
  list order), and an overridden `mark_clean(snapshot=None)` that fixes each new category's ID when it is
  given a snapshot. It has no file interface.
- Produces: `DEFAULT_TAG_COLOR`.
- `view()["tags"]` is the shape in spec §7.6. Uids count from `"1"` in the order the list shows.

- [ ] **Step 1: Apply the tests**

Run: `/usr/bin/git apply docs/superpowers/plans/2026-10-04-ui-refresh-phase9-settings-lists/05-tags-draft-tests.patch`

- [ ] **Step 2: Run them to see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_settings_draft_tags.py`
Expected: a collection error, `ModuleNotFoundError: No module named 'gui.settings.tags_state'`.

- [ ] **Step 3: Apply the implementation**

Run: `/usr/bin/git apply docs/superpowers/plans/2026-10-04-ui-refresh-phase9-settings-lists/05-tags-draft.patch`

- [ ] **Step 4: Run the tests to see them pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_settings_draft_tags.py`
Expected: 34 passed.

- [ ] **Step 5: Read `gui/settings/tags_state.py` against spec §7.3 to §7.5**

Two things are easy to break later, and both have tests: `open` does not clear a refused tag's sentence
(opening a row is not an edit), and a category with no stored `sku_writeoff` and no write-off gets no such
key on save, so an untouched profile round-trips.

- [ ] **Step 6: Commit**

`/usr/bin/git add gui/settings/tags_state.py tests/test_settings_draft_tags.py`, then commit with the
message `Tag categories draft: names, tags and packaging write-offs`.

---

### Task 6: The host runs imports and exports

**Spec:** §8.2.

**Files:**
- Modify: `gui/settings/web_host.py`
- Test: `tests/test_settings_web_host.py`

**Interfaces:**
- Consumes: the bridge signals of Task 1; the file interface of Tasks 2 and 3; `FileProblem`;
  `PageBridge.raise_toast(message, flag)`.
- Produces on `SettingsWebHost`: `_import(kind, path=None, update=False)`, `_update_import()`,
  `_export(kind)`, connected to `importRequested`, `toastActionRequested` and `exportRequested`.
  `show_page` forgets the pending "Update them".
- The toast's flag is `True` when the import skipped rows it could update: the page then shows "Update
  them".

- [ ] **Step 1: Apply the tests**

Run: `/usr/bin/git apply docs/superpowers/plans/2026-10-04-ui-refresh-phase9-settings-lists/06-host-tests.patch`

- [ ] **Step 2: Run them to see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_settings_web_host.py`
Expected: the tests under "import, export and the toast" fail on their assertions (no dialog was asked
for, no toast was raised); the others pass.

- [ ] **Step 3: Apply the implementation**

Run: `/usr/bin/git apply docs/superpowers/plans/2026-10-04-ui-refresh-phase9-settings-lists/06-host.patch`

- [ ] **Step 4: Run the tests to see them pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_settings_web_host.py tests/test_settings_bridge.py`
Expected: all pass (44 at the time of writing).

- [ ] **Step 5: Commit**

`/usr/bin/git add gui/settings/web_host.py tests/test_settings_web_host.py`, then commit with the message
`Settings host: CSV import and export with a toast`.

---

### Task 7: The four pages

**Spec:** §3.3, §3.4, §4.7, §5.8, §6.8, §7.7, §8.3.

**Files:**
- Create: `gui/web/settings_sets.js`, `gui/web/settings_weight.js`, `gui/web/settings_reports.js`,
  `gui/web/settings_tags.js`
- Modify: `gui/web/settings.js`, `gui/web/settings.html`, `gui/web/settings.css`,
  `gui/web/settings_rules.js`
- Test: `tests/test_settings_lists_page.py`

**Interfaces:**
- Consumes: the four drafts' `view()` shapes; the bridge slots of Task 1.
- Each page script defines three globals that `settings.js` lists in `LIST_PAGES`:
  `setsPage(view)`, `setsClick(data, el, bridge)`, `setsInput(data, el, bridge)`, and the same for
  `weight`, `reports` and `tags`. A click or input handler returns `true` when the event was its own.
- `data-act` names are unique across pages, because every handler is tried in turn: `set-*`, `comp-*`,
  `sets-*`; `product-*`, `box-*`, `weight-*`; `report-*`, `filter-*`; `cat-*`, `tag-*`, `map-*`.
- `settings_rules.js`: `conditionRow(e, key, at, acts, cond)` and the constant `RULE_CONDITION`.
  `settings_reports.js` calls it with its own `REPORT_FILTER`.
- `settings.js`: `view.pending` accepts three new requests: `@css:<selector>` (focus the first match),
  `@css-select:<selector>` (and select its text), `@keys:<key>|<key>` (the first of these keys that can
  take focus). `settings_sets.js` defines `OPEN_NAME`, the `@css:` request for the open row's name field,
  which the Reports and Tag categories scripts reuse.
- The Sets list's filter is a `data-input="filter"` field: `rulesInput` already reports that as
  `edit("filter", [text])`, which is `SetsDraft`'s action too.
- Script order in `settings.html`: `settings_rules.js`, `settings_sets.js`, `settings_weight.js`,
  `settings_reports.js`, `settings_tags.js`, `settings.js`.

- [ ] **Step 1: Apply the tests**

Run: `/usr/bin/git apply docs/superpowers/plans/2026-10-04-ui-refresh-phase9-settings-lists/07-pages-tests.patch`

- [ ] **Step 2: Run them to see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_settings_lists_page.py`
Expected: every test fails (the page draws nothing for these views, so each test's first read of the DOM
raises, or its wait times out). This run is slow, a few minutes: the waits run to their timeouts.

- [ ] **Step 3: Apply the implementation**

Run: `/usr/bin/git apply docs/superpowers/plans/2026-10-04-ui-refresh-phase9-settings-lists/07-pages.patch`

- [ ] **Step 4: Run the tests to see them pass, with the pages that were there before**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_settings_lists_page.py tests/test_settings_rules_page.py tests/test_settings_web_page.py tests/test_style_literals_guard.py`
Expected: all pass. `test_settings_rules_page.py` passing unchanged is the proof that the shared condition
row draws the same DOM for Rules.

- [ ] **Step 5: Commit**

`/usr/bin/git add gui/web tests/test_settings_lists_page.py`, then commit with the message
`Settings pages: Sets, Weight, Reports and Tag categories on the web tier`.

---

### Task 8: The window, and the Qt pages go

**Spec:** §9, §1 (the deletions), §13.

**Files:**
- Modify: `gui/settings/window.py`, `gui/settings/fields.py`, `gui/settings/__init__.py`,
  `gui/actions_handler.py`
- Delete: `gui/settings/sets.py`, `gui/settings/weight.py`, `gui/settings/reports.py`,
  `gui/settings/report_editor.py`, `gui/settings/base.py`, `gui/tag_categories_dialog.py`
- Test: `tests/test_settings_lists_window.py` (new); modify `tests/test_settings_footer.py`,
  `tests/test_settings_nav.py`, `tests/test_settings_page_contract.py`, `tests/test_settings_roundtrip.py`,
  `tests/test_settings_unsaved.py`, `tests/test_icon_usage_guard.py`
- Delete tests: `tests/test_settings_page_sets.py`, `tests/test_settings_page_weight.py`,
  `tests/test_settings_window_weight_quick_add.py`, `tests/test_settings_page_reports.py`,
  `tests/test_settings_report_editor.py`, `tests/test_tag_categories_dialog.py`

**Interfaces:**
- Consumes: the four drafts and the host as Tasks 2 to 6 left them.
- Produces: `WEB_PAGE_KEYS` names all eight pages (`"Sets": "sets"`, `"Weight": "weight"`, `"Reports":
  "reports"`, `"Tag categories": "tags"`). `SettingsWindow._add_page(page, name)` takes no widget.
  `_dirty_poll`, `_poll_current_page`, `_poll_page`, `DIRTY_POLL_MS`, `PAGE_MARGIN_PX`,
  `_TagCategoriesPage` and the window's `done()` override are gone.
- `gui/settings/fields.py` keeps `FILTERABLE_COLUMNS`, `CONDITION_OPERATORS`, `ACTION_TYPES`,
  `LEGACY_ACTION_TYPES`, `REPORT_FILTER_OPERATORS` and `report_filter_fields`, and imports no Qt.
- `ActionsHandler.open_tag_categories_dialog` is gone. It had no caller.

What the modified tests change, so you can check the patch says the same:
- `test_settings_unsaved.py`, `test_settings_footer.py`: `_edit_sets` adds a set through the bridge
  (`set_add`, `set_sku`, `comp_sku`) in place of writing into the Qt page's dict. The two poll tests become
  one, `test_an_edit_is_marked_at_once_with_no_poll`. The import test picks a real CSV through the patched
  file dialog and calls `bridge.importFile("sets-replace")`. `test_ctrl_s_saves_an_edit` asserts Save is
  live at once.
- `test_settings_roundtrip.py`: `test_every_page_shares_one_widget_in_the_stack` replaces the test that
  expected Sets to be its own widget.
- `test_settings_nav.py`: the margins test no longer reads a Qt page's margin.
- `test_settings_page_contract.py`: against `PageContract`, with no `QApplication`.
- `test_icon_usage_guard.py`: the guard's known call sites are `plus` and `circle-alert`; `trash-2` was
  used only by the deleted filter row.

- [ ] **Step 1: Apply the tests and delete the Qt pages' tests**

Run: `/usr/bin/git apply docs/superpowers/plans/2026-10-04-ui-refresh-phase9-settings-lists/08-window-tests.patch`

Then: `/usr/bin/git rm tests/test_settings_page_sets.py tests/test_settings_page_weight.py tests/test_settings_window_weight_quick_add.py tests/test_settings_page_reports.py tests/test_settings_report_editor.py tests/test_tag_categories_dialog.py`

- [ ] **Step 2: Run them to see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_settings_lists_window.py tests/test_settings_unsaved.py tests/test_settings_roundtrip.py`
Expected: failures. `test_each_page_is_a_draft_the_web_host_draws` fails on `isinstance` (the pages are
still Qt widgets), and the tests that edit Sets through the bridge fail with `KeyError: 'sets'`.

- [ ] **Step 3: Apply the implementation and delete the Qt pages**

Run: `/usr/bin/git apply docs/superpowers/plans/2026-10-04-ui-refresh-phase9-settings-lists/08-window.patch`

Then: `/usr/bin/git rm gui/settings/sets.py gui/settings/weight.py gui/settings/reports.py gui/settings/report_editor.py gui/settings/base.py gui/tag_categories_dialog.py`

- [ ] **Step 4: Check nothing still names what was deleted**

Run: `rg -n "SetsPage|WeightPage|ReportsPage|ReportEditor|TagCategoriesPanel|TagCategoriesDialog|open_tag_categories_dialog|settings/base|settings\.base|add_filter_row" gui tests gui_main.py`
Expected: one match, the docstring at the top of `gui/settings/contract.py`. Fix it with one Edit.

Find exactly:

```python
A Qt page is a QWidget that meets this (gui/settings/base.py). A draft meets
it with no widget at all (gui/settings/page_state.py): its values are drawn
by the web page. The window saves and marks both the same way. No Qt import.
```

Replace with:

```python
Every page is a draft: it meets this with no widget (gui/settings/
page_state.py and the *_state.py modules beside it), and its values are drawn
by the web page. No Qt import.
```

Run the `rg` command again. Expected: no match.

- [ ] **Step 5: Run the settings tests to see them pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_settings_lists_window.py tests/test_settings_unsaved.py tests/test_settings_roundtrip.py tests/test_settings_footer.py tests/test_settings_nav.py tests/test_settings_page_contract.py tests/test_settings_entry_points.py tests/test_settings_button_roles.py tests/test_settings_rules_window.py tests/test_actions_handler.py tests/test_icon_usage_guard.py`
Expected: all pass.

- [ ] **Step 6: Lint**

Run: `.venv/bin/ruff check .`
Expected: `All checks passed!`

- [ ] **Step 7: Commit**

`/usr/bin/git add gui tests`, then commit with the message
`Settings window: every page is a draft, and the Qt pages are deleted`.

---

### Task 9: Renders, docs and the gate

**Spec:** §13 (the renders), §14, §16.

**Files:**
- Create: PNGs under `docs/design/ui-refresh/renders/phase9/`
- Modify: `docs/design/ui-refresh/roadmap.md`, `CONTEXT.md`
- Delete: `docs/superpowers/plans/2026-10-04-ui-refresh-phase9-settings-lists/` (the patches and the render
  script; this document stays)

- [ ] **Step 1: Render the dialog**

Run: `QT_QPA_PLATFORM=offscreen PYTHONPATH=. .venv/bin/python docs/superpowers/plans/2026-10-04-ui-refresh-phase9-settings-lists/render_settings.py docs/design/ui-refresh/renders/phase9`
Expected: 14 lines starting `wrote`. The repeated log line "The client config's additional columns
couldn't be read" is the mocked profile manager, not a failure.

- [ ] **Step 2: Look at every PNG**

Read each file under `docs/design/ui-refresh/renders/phase9/` with the Read tool and check it against the
spec's drawing for its page (§4.7, §5.8, §6.8, §7.7):

| File | What it must show |
|---|---|
| `light-sets.png`, `dark-sets.png` | Three sets as rows with component chips; "+3 more" on the nine-part set; the bar with the filter, "3 sets", Import and Export |
| `light-sets-open-problem.png` | SET-GIFT open, its second quantity field marked, "Type a whole number from 1 to 9999." under it, the footer's "Fix set “SET-GIFT” in Sets to save." |
| `light-sets-empty.png` | "No sets yet", Add set and Import from CSV…, no action in the page head |
| `light-weight.png`, `dark-weight.png` | Three cards: Volumetric weight, Products, Boxes; a row of fields per product; "0.2 kg" on TEE-01 |
| `light-weight-problem.png` | A new empty row first with "Type a SKU, or this row isn't saved."; TEE-01's W marked with "Type a number, 0 or more." |
| `light-reports.png` | Two cards; DHL's summary and "Matches 2 orders · 3 rows"; DPD's "No file name yet…" line |
| `light-reports-open.png`, `dark-reports-open.png` | DHL open: File name, Filters (one row), Exclude SKUs, Columns (three chips), Done |
| `light-tags.png` | Three categories; chips; the "Write-off" badge on Packaging; "No tags yet." on Returns |
| `light-tags-open.png`, `dark-tags-open.png` | Packaging open: tag chips and the Add tag field; the switch on; two write-off rows |
| `light-tags-refused.png` | "VIP is already in Priority. A tag belongs to one category." under the tags; a third write-off row marked "Type the SKU to write off." |

In the dark renders, check that no control is drawn in a light colour. If a render is wrong, fix the page
(`gui/web/settings.css` or the page's script), rerun its test file from Task 7, render again, and say what
you changed in the commit message.

- [ ] **Step 3: Update `docs/design/ui-refresh/roadmap.md`**

Find exactly:

```markdown
### 9. Client settings on the web tier: Sets, Weight, Reports, Tag categories

The mockup has no drawing of these pages. They follow the page anatomy from Phase 7, and the spec names each
place where it had to decide something the mockup does not show.
```

Replace with:

```markdown
### 9. Client settings on the web tier: Sets, Weight, Reports, Tag categories (built in run 59)

Spec: `docs/superpowers/specs/2026-10-04-ui-refresh-phase9-settings-lists-design.md`.
Plan: `docs/superpowers/plans/2026-10-04-ui-refresh-phase9-settings-lists.md`.

Built as listed below, with these differences. It fitted one PR. Sets, Reports and Tag categories are
lists whose row opens in place, as Rules is; Weight is three cards, with products edited in the table, 200
rows at a time. A tag category's colour, order number and ID are no longer drawn: the colour is kept as
stored, the order is the list's (set by up and down, and Results' "+ Tag" menu now follows it), and a new
category's ID is made from its name. Reports reorder by up and down, not by dragging. Packing-list columns
are chips and print in the order they were added. CSV import and export go through the settings bridge to
a native file dialog, and the page has a toast. Several quiet data losses are now blocked and said: a set
renamed onto another set's SKU, a dimension that is not a number, a product SKU typed twice. The unsaved
poll is gone: every page reports its own edits. The standalone Tag Categories dialog, which had no caller,
is deleted. Renders: `renders/phase9/`.

The mockup has no drawing of these pages. They follow the page anatomy from Phase 7, and the spec names each
place where it had to decide something the mockup does not show.
```

- [ ] **Step 4: Update `CONTEXT.md`**

Find exactly:

```markdown
**Generate order** — the order reports are listed in Settings › Reports,
which is the order they are offered and generated in. Set by dragging within
one kind; packing lists and stock exports never mix.
```

Replace with:

```markdown
**Generate order** — the order reports are listed in Settings › Reports,
which is the order they are offered and generated in. Set by the up and down
buttons within one kind; packing lists and stock exports never mix.

**Set** / **Component** — a set is a SKU on an order that the analysis
replaces with other SKUs before stock is allocated; a component is one of
those SKUs and how many of it one set holds. Stored under `set_decoders`.

**Tag category** — a named group of internal tags. A tag belongs to one
category. Its place in Settings › Tag categories is the order Results' "+ Tag"
menu lists it in. Its colour and its ID are stored and drawn nowhere.
```

- [ ] **Step 5: Remove the patch folder**

Run: `/usr/bin/git rm -r docs/superpowers/plans/2026-10-04-ui-refresh-phase9-settings-lists`

The plan document itself, `docs/superpowers/plans/2026-10-04-ui-refresh-phase9-settings-lists.md`, stays.

- [ ] **Step 6: The gate**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
Expected: everything passes but the three baseline failures named at the top of this plan.

Run: `.venv/bin/ruff check .`
Expected: `All checks passed!`

- [ ] **Step 7: Commit**

`/usr/bin/git add docs CONTEXT.md`, then commit with the message
`Phase 9 renders and docs: roadmap as built, glossary`.

The PR description says: `shared/` does not change and Packing Tool needs no work; which mockup was
followed (anatomy only) and the departures (spec §11 and §12); and the three baseline failures.
