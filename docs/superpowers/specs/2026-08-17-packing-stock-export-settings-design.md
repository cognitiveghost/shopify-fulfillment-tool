# Packing List & Stock Export: filters, settings, and synchronised generation

Date: 2026-08-17
Roadmap item: Phase 6 — `6h8v4VxRHVq7MrGV` (orig: `6h8rpxwVr8rvR693`)
Branch: `worktree-packing-stock-export-settings`

## Why this exists

The roadmap item asks for three things: a fresh look at how packing-list
conditions are configured, control over what the packing list displays, and the
ability to generate a packing list and a stock export together.

Investigating the first of those turned up a data-correctness bug that changes
the shape of the work. **The filter vocabulary the settings UI offers is mostly
non-functional on the packing-list path, and fails silently.**

### Measured, 2026-08-17

Report filters are applied by two different implementations, one of which is
copy-pasted into both file writers:

| # | implementation | drives |
|---|---|---|
| 1 | `gui/actions_handler.py:_apply_filters` — explicit per-operator pandas ops | dialog **preview**, and the **JSON** handed to Packing Tool |
| 2 | pandas `.query()` string builder, duplicated verbatim in `packing_lists.py:104-126` and `stock_export.py:188-210` | packing-list **XLSX** and stock export **.xls** |

The two writers therefore share the same defects — the duplication is itself
part of the problem, and collapsing it is part of the fix.

Implementation 2 builds a query by string interpolation:

```python
query_parts.append(f"`{field}` {operator} {formatted_value}")
```

`pandas.query` only understands `==` and `!=` out of the five operators
`gui/settings/fields.py:FILTER_OPERATORS` offers. Behaviour of each, measured
against a 3-row fixture:

| operator | packing-list XLSX | stock export | severity |
|---|---|---|---|
| `==` | correct | correct | — |
| `!=` | correct | correct | — |
| `in` | **no file written**, no error surfaced | no file | silent no-op |
| `not in` | **all 3 rows written**, including both SKUs that should have been excluded | same builder, same defect | **silent wrong data** |
| `contains` | `SyntaxError: invalid syntax`, caught and logged, no file | no file | silent failure |

The `not in` case is the serious one: a warehouse worker is handed a picking
list containing items the configuration explicitly excluded, with nothing
anywhere indicating a problem.

Because implementations 1 and 2 differ, two further inconsistencies follow:

- The dialog preview can report "1 order" while the XLSX contains 3.
- The JSON handed to Packing Tool and the XLSX handed to the warehouse can
  contain different orders, generated from the same config in the same run.

### The consequence for this design

The "richer operators" half of the roadmap item and the bug fix are the same
change. `shopify_tool/rules.py` already contains a complete, tested operator
library — `OPERATOR_MAP`, 20 operators, each a `(series, value) -> bool Series`
function used by the rule engine. Routing report filters through it fixes the
correctness bug and delivers the richer vocabulary in one move, and deletes the
query-string builder rather than repairing it.

## Goals

1. One filter evaluator, shared by preview, XLSX, JSON and stock export, so all
   four always agree.
2. The richer rules-engine operator vocabulary in the report filter UI.
3. Filterable columns sourced from the analysis DataFrame rather than a
   hardcoded list, so `Internal_Tags` and additional CSV columns can be filtered.
4. Per-packing-list control over which columns the XLSX shows, and in what order.
5. One settings surface for both report kinds instead of two near-identical pages.
6. One generation dialog that produces any number of packing lists and stock
   exports in a single pass.

## Non-goals

- Changing the `.xls` stock export file format. The ERP contract is settled
  (integers, no zero-quantity rows) and is out of scope here.
- Reworking the write-off flow beyond carrying it across to the new dialog.
- Touching the rule engine itself. This design consumes `OPERATOR_MAP`; it does
  not modify it.
- Reconciling historical exports produced by the broken filters. Flagged
  separately; this design stops the bug, it does not correct past output.

## Design

### 1. `shopify_tool/report_filters.py` (new)

One public function, the single source of truth:

```python
def apply_report_filters(df, filters) -> pd.DataFrame
```

It builds a boolean mask per filter by looking the operator up in
`rules.OPERATOR_MAP`, AND-s them together, and returns the filtered frame.

**Legacy operator normalisation.** Client configs on the file server hold the
old symbols. Rather than a migration script and a config rewrite, the evaluator
normalises on read:

| stored | evaluated as |
|---|---|
| `==` | `equals` |
| `!=` | `does not equal` |
| `in` | `in list` |
| `not in` | `not in list` |
| `contains` | `contains` |

This keeps every existing config working untouched, needs no write path, and
means a config saved by an older build still evaluates correctly. New configs
written by the redesigned UI use the rules-engine names directly.

**`Internal_Tags`.** The column holds a serialized tag list — a JSON string in
production (`analysis.py` writes it that way), occasionally a native list. A
plain `contains` against the raw value is wrong: `contains "Gift"` would match
`["NoGift"]`. `shopify_tool/tag_manager.py` already solves this with
`parse_tags()` and `has_tag()`, both accepting either form. `apply_report_filters`
special-cases `Internal_Tags` to tag-membership semantics via `has_tag` rather
than substring matching.

**Unresolvable filters are an error, not a skip.** This follows the rule
engine's own reasoning (`rules.py:_resolve_condition`): silently dropping a
filter widens the result set, which is precisely the failure mode this design
exists to remove. An unknown operator or missing column produces a match of
nothing and a surfaced warning.

**Call sites collapse into it:** `create_packing_list`, `create_stock_export`,
and `actions_handler._apply_filters` all delegate. The query-string builder in
`packing_lists.py` is deleted.

### 2. Settings: one Reports page

`PackingListsPage` (127 lines) and `StockExportsPage` (117 lines) are ~90%
identical — same add button, scroll area, per-report group box of
name / output filename / filters / delete. Only `exclude_skus` differs.

They merge into a single `ReportsPage` backed by one shared report-editor
widget, parameterised by report kind. `collect()` returns both
`packing_list_configs` and `stock_export_configs`; the `SettingsPage` contract
already permits a page owning several keys.

The filter row editor gains:

- the `CONDITION_OPERATORS` combo already used by the rules page, so the
  vocabulary is consistent across the app;
- a field list built from the analysis DataFrame's columns, falling back to the
  current hardcoded list when no analysis has been run.

Packing-list editors additionally gain a **column picker**: which columns the
XLSX shows, and in what order.

### 3. Configurable packing-list columns

`create_packing_list` gains a `columns=None` parameter; `None` preserves
today's hardcoded default, so untouched configs render identically.

One obstruction has to be cleared first. The current writer smuggles metadata
into the sheet by renaming two specific columns
(`packing_lists.py:227`):

```python
rename_map = {"Shipping_Provider": generation_timestamp, "Warehouse_Name": output_filename}
```

That only works because those two columns are always present. With a
user-chosen column set they may not be, so the timestamp and filename must be
carried independently of which columns were selected. They move into the
existing custom header rows, which is where the docstring already says this
metadata belongs.

Two further behaviours are column-specific and must be conditional on the
column actually being selected: the `Destination_Country` first-item-only
blanking, and the per-column widths and formats.

### 4. Generation: one dialog, multi-select

`PackingListDialog` and `StockExportDialog` already share `_BaseReportDialog`
with its preview panel. They are replaced by a single `GenerateReportsDialog`:

- both report kinds listed under section headers, each row a checkbox;
- the existing preview panel updates on focus, unchanged;
- a footer showing the selected count;
- one `reportsSelected(list[dict])` signal replacing `reportSelected(dict)`.

`actions_handler._generate_single_report` already handles both kinds in one
function, so the generation side becomes a loop over the emitted list, with a
per-report try/except so one failure cannot abort the rest. The write-off-only
path carries across as-is.

The two main-window buttons collapse into one "Generate Reports".

## Data flow after the change

```
client config (packing_list_configs, stock_export_configs)
        |
        v
  ReportsPage  --------------------------------> saved config
        |
        v
GenerateReportsDialog  --preview-->  apply_report_filters
        |                                        ^
        | reportsSelected([cfg, cfg, ...])       |
        v                                        |
_generate_single_report (loop) ------------------+
        |
        +--> create_packing_list  --> apply_report_filters --> XLSX
        +--> _create_analysis_json --> apply_report_filters --> JSON
        +--> create_stock_export  --> apply_report_filters --> .xls
```

Every path reaches the same evaluator, which is the property the current code
lacks.

## Testing

The bug this fixes is silent, so the tests must assert on **content**, not on
"a file was produced".

1. **Operator correctness, per operator, against both writers.** For each
   supported operator, assert the exact set of rows in the written file. The
   `not in` case gets an explicit regression test pinning the measured bug:
   a 3-row fixture filtered by `SKU not in AB-01,CD-02` must write exactly one
   row. Today it writes three.
2. **The three implementations agree.** One test that runs the same config
   through preview, XLSX and JSON and asserts identical order sets. This is the
   invariant the whole design exists to establish.
3. **Legacy operator normalisation.** A config using `==` / `in` / `not in`
   evaluates identically to the same config using the new names.
4. **`Internal_Tags` membership.** `contains "Gift"` must match `["Gift"]` and
   must not match `["NoGift"]`, in both JSON-string and native-list forms.
5. **Column picker.** A chosen column set appears in the XLSX in the chosen
   order; `columns=None` reproduces today's output exactly; timestamp and
   filename survive a column set that excludes `Shipping_Provider` and
   `Warehouse_Name`.
6. **Settings round-trip.** `ReportsPage.collect()` round-trips both config
   keys, extending the existing `test_settings_page_packing_lists.py` and
   `test_settings_page_stock_exports.py`.
7. **Multi-select generation.** Selecting two packing lists and one stock
   export produces three files in one pass; a failure in one does not prevent
   the other two.

## Risks

- **Behaviour change on existing configs.** Any config using `in`, `not in` or
  `contains` produces different output after this change — that is the point,
  but output people may have grown used to will shift. Worth calling out in the
  PR body.
- **Packing-list writer surface.** The column work touches formatting, widths
  and the header hack in one function. Test 5's `columns=None` equivalence
  check is the guard against regressing the default rendering.
- **Single large PR.** Raised during design that the filter fix could ship
  ahead of the UI work; the decision was one PR for the whole epic. The risk is
  review size, not correctness.

## Decisions taken during design

- **Sync generation = one multi-select dialog**, not linked config pairs and
  not named bundles. It needs no new schema and no second place to keep in
  sync, and covers the pairing use case.
- **Reuse `OPERATOR_MAP` rather than write a filter evaluator.** It already
  exists, is already tested, and gives consistency with the rules engine for
  free.
- **Normalise legacy operators at evaluation time**, not via a config
  migration. No write path, no migration to get wrong, old configs keep working.
- **Column picker is in scope** for this cycle rather than deferred.
