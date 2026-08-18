# Packing List & Stock Export: filters, settings, sync generation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give report filters one correct evaluator shared by every consumer, let users choose which columns a packing list shows, merge the twin settings pages, and generate any number of packing lists and stock exports in one pass.

**Architecture:** A new `shopify_tool/report_filters.py` becomes the single filter evaluator, delegating to the `OPERATOR_MAP` functions the rule engine already uses. The duplicated pandas `.query()` string builders in `packing_lists.py` and `stock_export.py` are deleted, as is the divergent `_apply_filters` in `actions_handler.py`. On top of that, `create_packing_list` gains a `columns` parameter, the two settings pages merge into one, and the two generation dialogs merge into one multi-select dialog.

**Tech Stack:** Python 3.14, PySide6, pandas, xlsxwriter (packing lists, `.xlsx`), xlwt (stock exports, `.xls`), pytest.

**Spec:** `docs/superpowers/specs/2026-08-17-packing-stock-export-settings-design.md`

## Global Constraints

- **Never hand-edit files under `shared/`.** One-way synced from `../packing-tool`. No task here touches it.
- **No hardcoded colors** in stylesheets. Use `get_theme_manager().get_current_theme()` tokens (`theme.text_secondary`, `theme.border`, …).
- **No UI calls from background threads.** Signals only.
- **Gate before finishing:** `QT_QPA_PLATFORM=offscreen python -m pytest` and `ruff check . --exclude shared`, both clean.
- **Use `.venv/bin/python`** — bare `python` is not on PATH on this machine. `scripts/run_tests.sh` wraps the suite.
- **No direct commits to `main`.** Work stays on `worktree-packing-stock-export-settings`.
- **The ERP contract is settled and out of scope:** integer quantities, no zero-quantity rows in the `.xls`. Do not touch stock-export cell formatting.
- **Every commit** ends with the two trailers shown in each Commit step. Copy them verbatim.

---

## File Structure

| File | Responsibility |
|---|---|
| `shopify_tool/report_filters.py` (new) | The only place a report filter is evaluated. |
| `tests/test_report_filters.py` (new) | Operator matrix, legacy aliases, tag membership, unresolvable filters. |
| `shopify_tool/packing_lists.py` (modify) | Delete query builder; delegate; add `columns` parameter. |
| `shopify_tool/stock_export.py` (modify) | Delete duplicate query builder; delegate. |
| `gui/actions_handler.py` (modify) | Delete `_apply_filters` body; delegate; loop over multiple selected reports. |
| `gui/settings/report_editor.py` (new) | Shared per-report editor widget used by both report kinds. |
| `gui/settings/reports.py` (new) | `ReportsPage` — one settings page owning both config keys. |
| `gui/settings/packing_lists.py`, `gui/settings/stock_exports.py` (delete) | Superseded by the two files above. |
| `gui/settings/window.py` (modify) | Register `ReportsPage` in place of the two pages. |
| `gui/settings/fields.py` (modify) | `REPORT_FILTER_OPERATORS`; DataFrame-sourced field list helper. |
| `gui/report_selection_dialog.py` (modify) | `GenerateReportsDialog`, multi-select, `reportsSelected(list)`. |
| `gui/main_window_pyside.py` (modify) | One "Generate Reports" button. |
| `tests/test_settings_page_reports.py` (new) | Round-trip of both config keys through the merged page. |
| `tests/test_generate_reports_dialog.py` (new) | Multi-select emission. |
| `tests/test_packing_lists.py` (modify) | Column picker; `columns=None` equivalence; `not in` regression. |
| `tests/test_stock_export.py` (modify) | Operator correctness via the shared evaluator. |
| `tests/test_settings_page_packing_lists.py`, `tests/test_settings_page_stock_exports.py` (delete) | Replaced by `test_settings_page_reports.py`. |

---

## Task 1: The shared filter evaluator

**Files:**
- Create: `shopify_tool/report_filters.py`
- Test: `tests/test_report_filters.py`

**Interfaces:**
- Consumes: `shopify_tool.rules.OPERATOR_MAP` and its `_op_*` functions; `shopify_tool.tag_manager.has_tag`.
- Produces: `apply_report_filters(df, filters) -> pd.DataFrame` and `normalize_operator(operator) -> str`, used by Tasks 2, 3, 4 and 7.

> The implementation below was executed against the fixture in Step 1 during
> planning; all 17 cases passed. Transcribe it as written.

- [ ] **Step 1: Write the failing test**

Create `tests/test_report_filters.py`:

```python
"""The filter evaluator every report path shares.

Before this module existed, packing_lists.py and stock_export.py each built a
pandas .query() string, which could not evaluate 3 of the 5 operators the
settings UI offered: "in" produced no file, "contains" raised SyntaxError, and
"not in" silently emitted the rows it was told to exclude. test_not_in_excludes
pins that last one -- it is the case that shipped wrong picking lists.
"""
import pandas as pd
import pytest

from shopify_tool.report_filters import apply_report_filters, normalize_operator


@pytest.fixture
def df():
    return pd.DataFrame({
        "Order_Number": ["#1001", "#1002", "#1003"],
        "SKU": ["AB-01", "CD-02", "EF-03"],
        "Quantity": [1, 2, 3],
        "Shipping_Provider": ["DHL", "DPD", "DHL"],
        # Both storage forms: a JSON string (what analysis.py writes) and a
        # native list (what the in-memory tag path can hold).
        "Internal_Tags": ['["Gift"]', '["NoGift"]', ["Gift", "Fragile"]],
    })


def _skus(df, filters):
    return sorted(apply_report_filters(df, filters)["SKU"].tolist())


@pytest.mark.parametrize("operator, value, expected", [
    # Legacy spellings, as stored by older builds of the settings UI.
    ("==", "DHL", ["AB-01", "EF-03"]),
    ("!=", "DHL", ["CD-02"]),
    # Rules-engine spellings.
    ("equals", "DHL", ["AB-01", "EF-03"]),
    ("does not equal", "DHL", ["CD-02"]),
])
def test_provider_operators(df, operator, value, expected):
    assert _skus(df, [{"field": "Shipping_Provider", "operator": operator, "value": value}]) == expected


@pytest.mark.parametrize("operator, value, expected", [
    ("in", "AB-01,CD-02", ["AB-01", "CD-02"]),
    ("in list", "AB-01,CD-02", ["AB-01", "CD-02"]),
    ("contains", "AB", ["AB-01"]),
    ("starts with", "AB", ["AB-01"]),
    ("ends with", "03", ["EF-03"]),
])
def test_sku_operators(df, operator, value, expected):
    assert _skus(df, [{"field": "SKU", "operator": operator, "value": value}]) == expected


@pytest.mark.parametrize("operator", ["not in", "not in list"])
def test_not_in_excludes_the_listed_skus(df, operator):
    """The regression that motivated this module.

    The old query-string builder wrote all three rows here, including both
    SKUs the filter named. A warehouse worker got a picking list containing
    items the configuration excluded, under a "Report saved" message.
    """
    assert _skus(df, [{"field": "SKU", "operator": operator, "value": "AB-01,CD-02"}]) == ["EF-03"]


def test_numeric_comparison(df):
    assert _skus(df, [{"field": "Quantity", "operator": "is greater than", "value": "1"}]) == ["CD-02", "EF-03"]


@pytest.mark.parametrize("operator, expected", [
    ("contains", ["AB-01", "EF-03"]),
    ("does not contain", ["CD-02"]),
])
def test_internal_tags_use_membership_not_substring(df, operator, expected):
    """"Gift" must match ["Gift"] but not ["NoGift"].

    A substring match against the raw JSON would match both, which is why this
    column gets tag_manager.has_tag semantics instead.
    """
    assert _skus(df, [{"field": "Internal_Tags", "operator": operator, "value": "Gift"}]) == expected


def test_filters_combine_with_and(df):
    filters = [
        {"field": "Shipping_Provider", "operator": "equals", "value": "DHL"},
        {"field": "SKU", "operator": "contains", "value": "AB"},
    ]
    assert _skus(df, filters) == ["AB-01"]


@pytest.mark.parametrize("filters", [
    [{"field": "SKU", "operator": "bogus", "value": "x"}],
    [{"field": "NoSuchColumn", "operator": "equals", "value": "x"}],
    [{"field": "", "operator": "equals", "value": "x"}],
])
def test_unresolvable_filter_matches_nothing(df, filters):
    """Skipping a filter widens the result set -- the exact failure this
    module exists to remove. An unusable filter matches nothing instead.
    """
    assert _skus(df, filters) == []


def test_no_filters_returns_everything(df):
    assert _skus(df, []) == ["AB-01", "CD-02", "EF-03"]


def test_empty_frame_is_returned_unchanged(df):
    empty = df.iloc[0:0]
    assert apply_report_filters(empty, [{"field": "SKU", "operator": "equals", "value": "AB-01"}]).empty


def test_normalize_operator_maps_legacy_names():
    assert normalize_operator("==") == "equals"
    assert normalize_operator("not in") == "not in list"
    assert normalize_operator("starts with") == "starts with"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_report_filters.py -q`

Expected: collection error — `ModuleNotFoundError: No module named 'shopify_tool.report_filters'`

- [ ] **Step 3: Write the implementation**

Create `shopify_tool/report_filters.py`:

```python
"""Single source of truth for evaluating report filters.

Packing lists, stock exports, the generation dialog's preview and the JSON
handed to Packing Tool all filter the analysis DataFrame by the same saved
filter config. They used to do it two different ways -- both writers shared a
copy-pasted pandas ``.query()`` string builder, and the GUI had its own
per-operator implementation -- so the same config could yield different rows in
the XLSX, the .xls and the preview.

Worse, the query-string builder could only evaluate ``==`` and ``!=`` of the
five operators the settings UI offered. ``in`` produced no file under a
"Report saved" message, ``contains`` raised a SyntaxError, and ``not in``
silently emitted the rows it was told to exclude.

This module replaces it. Operators are evaluated by the same OPERATOR_MAP
functions the rule engine uses, so the vocabulary is consistent across the app
and there is one implementation to keep correct.
"""

import logging

import pandas as pd

from shopify_tool import rules
from shopify_tool.tag_manager import has_tag

logger = logging.getLogger(__name__)

# Operator names written by older builds of the settings UI. Normalised on
# read rather than migrated on disk: client configs live on a shared file
# server and may be written by a mix of app versions, so the evaluator has to
# understand both spellings anyway. Normalising here means no write path and
# no migration to get wrong.
LEGACY_OPERATOR_ALIASES = {
    "==": "equals",
    "!=": "does not equal",
    "in": "in list",
    "not in": "not in list",
    "contains": "contains",
}

# Internal_Tags holds a serialized tag list -- a JSON string in production,
# occasionally a native list. Substring matching against the raw value is
# wrong: "contains Gift" would match ["NoGift"]. These operators get
# tag-membership semantics instead, via tag_manager.has_tag which accepts
# either form.
_TAG_COLUMN = "Internal_Tags"
_TAG_MEMBERSHIP_OPERATORS = {"contains", "equals"}
_TAG_ABSENCE_OPERATORS = {"does not contain", "does not equal"}


def normalize_operator(operator):
    """Returns the rules-engine name for a stored operator."""
    return LEGACY_OPERATOR_ALIASES.get(operator, operator)


def _tag_mask(series, operator, value):
    """Boolean mask for a filter on the Internal_Tags column."""
    present = series.apply(lambda cell: has_tag(cell, value))
    return present if operator in _TAG_MEMBERSHIP_OPERATORS else ~present


def apply_report_filters(df, filters):
    """Filters ``df`` by a report config's filter list.

    A filter that cannot be evaluated -- unknown operator, missing column --
    matches nothing rather than being skipped. Skipping widens the result set,
    which is the exact failure this module exists to remove: a packing list
    that quietly contains rows the configuration excluded is worse than one
    that is visibly empty.

    Args:
        df (pd.DataFrame): The frame to filter.
        filters (list[dict] | None): Filter dicts with 'field', 'operator' and
            'value' keys. Operators may use either the rules-engine names or
            the legacy symbols; both are understood.

    Returns:
        pd.DataFrame: A filtered copy. Filters combine with AND.
    """
    if df is None or df.empty or not filters:
        return df.copy() if df is not None else df

    mask = pd.Series(True, index=df.index)

    for filt in filters:
        field = filt.get("field")
        operator = normalize_operator(filt.get("operator"))
        value = filt.get("value")

        if not field or not operator:
            logger.warning(f"[REPORT FILTERS] Incomplete filter, matches nothing: {filt}")
            return df.iloc[0:0].copy()

        if field not in df.columns:
            logger.warning(
                f"[REPORT FILTERS] Field '{field}' is not a column, matches nothing"
            )
            return df.iloc[0:0].copy()

        if field == _TAG_COLUMN and operator in (
            _TAG_MEMBERSHIP_OPERATORS | _TAG_ABSENCE_OPERATORS
        ):
            mask &= _tag_mask(df[field], operator, value)
            continue

        func_name = rules.OPERATOR_MAP.get(operator)
        if func_name is None:
            logger.warning(
                f"[REPORT FILTERS] Unknown operator '{operator}', matches nothing"
            )
            return df.iloc[0:0].copy()

        op_func = getattr(rules, func_name)
        mask &= op_func(df[field], value)

    return df[mask].copy()
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_report_filters.py -q`

Expected: PASS. 22 tests (the parametrized cases expand).

- [ ] **Step 5: Commit**

```bash
git add shopify_tool/report_filters.py tests/test_report_filters.py
git commit -m "$(cat <<'EOF'
Add report_filters: one evaluator for every report filter path

Delegates to rules.OPERATOR_MAP rather than building a pandas .query()
string, which could only evaluate == and != of the five operators the
settings UI offers. Internal_Tags gets tag-membership semantics via
tag_manager.has_tag instead of substring matching against raw JSON.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PCmhFN4SuzRPDTB111c69T
EOF
)"
```

---

## Task 2: Route the packing-list writer through the evaluator

**Files:**
- Modify: `shopify_tool/packing_lists.py:104-126` (delete the query builder)
- Test: `tests/test_packing_lists.py`

**Interfaces:**
- Consumes: `apply_report_filters` from Task 1.
- Produces: `create_packing_list` with unchanged signature; its filter semantics now match Task 1's.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_packing_lists.py`:

```python
def test_not_in_filter_excludes_the_listed_skus(tmp_path):
    """Regression: the old .query() builder wrote every row here.

    "SKU not in AB-01,CD-02" against three rows must leave exactly EF-03.
    Before the shared evaluator this produced a 3-row file -- a picking list
    containing both SKUs the config excluded, reported as "Report saved".
    """
    df = pd.DataFrame({
        "Order_Number": ["#1001", "#1002", "#1003"],
        "SKU": ["AB-01", "CD-02", "EF-03"],
        "Product_Name": ["Widget", "Gadget", "Doohickey"],
        "Warehouse_Name": ["Widget", "Gadget", "Doohickey"],
        "Quantity": [1, 2, 3],
        "Shipping_Provider": ["DHL", "DPD", "DHL"],
        "Destination_Country": ["DE", "FR", "DE"],
        "Order_Fulfillment_Status": ["Fulfillable"] * 3,
    })
    out = tmp_path / "notin.xlsx"

    create_packing_list(df, str(out), "notin",
                        filters=[{"field": "SKU", "operator": "not in", "value": "AB-01,CD-02"}])

    written = pd.read_excel(out)
    assert written["SKU"].tolist() == ["EF-03"]


def test_contains_filter_writes_the_matching_row(tmp_path):
    """"contains" used to raise SyntaxError -- it is not valid pandas query
    syntax -- so the report failed outright."""
    df = pd.DataFrame({
        "Order_Number": ["#1001", "#1002"],
        "SKU": ["AB-01", "CD-02"],
        "Product_Name": ["Widget", "Gadget"],
        "Warehouse_Name": ["Widget", "Gadget"],
        "Quantity": [1, 2],
        "Shipping_Provider": ["DHL", "DPD"],
        "Destination_Country": ["DE", "FR"],
        "Order_Fulfillment_Status": ["Fulfillable"] * 2,
    })
    out = tmp_path / "contains.xlsx"

    create_packing_list(df, str(out), "contains",
                        filters=[{"field": "SKU", "operator": "contains", "value": "AB"}])

    assert pd.read_excel(out)["SKU"].tolist() == ["AB-01"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_packing_lists.py -q -k "not_in_filter or contains_filter"`

Expected: `test_not_in_filter_excludes_the_listed_skus` FAILS with `assert ['AB-01', 'EF-03', 'CD-02'] == ['EF-03']`; `test_contains_filter_writes_the_matching_row` FAILS with `SyntaxError: invalid syntax`.

- [ ] **Step 3: Replace the query builder**

In `shopify_tool/packing_lists.py`, add to the imports at the top of the file:

```python
from shopify_tool.report_filters import apply_report_filters
```

Then replace the whole block that starts `# Build the query string to filter the DataFrame` and ends with `filtered_orders = analysis_df.query(full_query).copy()` with:

```python
        # Packing lists only ever contain fulfillable orders; the report's own
        # filters narrow it further. Both go through the shared evaluator so
        # the XLSX, the JSON and the dialog preview cannot disagree.
        fulfillable = analysis_df[
            analysis_df["Order_Fulfillment_Status"] == "Fulfillable"
        ]
        filtered_orders = apply_report_filters(fulfillable, filters)
```

- [ ] **Step 4: Run to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_packing_lists.py -q`

Expected: PASS, including every pre-existing test in the file.

- [ ] **Step 5: Commit**

```bash
git add shopify_tool/packing_lists.py tests/test_packing_lists.py
git commit -m "$(cat <<'EOF'
Packing lists: evaluate filters through report_filters

Deletes the pandas .query() string builder. "not in" wrote the rows it was
told to exclude; "contains" raised SyntaxError; "in" wrote no file while the
status bar reported success.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PCmhFN4SuzRPDTB111c69T
EOF
)"
```

---

## Task 3: Route the stock-export writer through the evaluator

**Files:**
- Modify: `shopify_tool/stock_export.py:188-210` (delete the duplicate query builder)
- Test: `tests/test_stock_export.py`

**Interfaces:**
- Consumes: `apply_report_filters` from Task 1.
- Produces: `create_stock_export` with unchanged signature.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_stock_export.py`:

```python
def test_not_in_filter_excludes_the_listed_skus(tmp_path):
    """stock_export.py carried a verbatim copy of the packing-list query
    builder, so it carried the same defect."""
    df = pd.DataFrame({
        "Order_Number": ["#1001", "#1002", "#1003"],
        "SKU": ["AB-01", "CD-02", "EF-03"],
        "Product_Name": ["Widget", "Gadget", "Doohickey"],
        "Quantity": [1, 2, 3],
        "Final_Stock": [10, 20, 30],
        "Shipping_Provider": ["DHL", "DPD", "DHL"],
        "Order_Fulfillment_Status": ["Fulfillable"] * 3,
    })
    out = tmp_path / "notin.xls"

    create_stock_export(df, str(out),
                        filters=[{"field": "SKU", "operator": "not in", "value": "AB-01,CD-02"}])

    written = pd.read_excel(out)
    assert "AB-01" not in written.to_string()
    assert "CD-02" not in written.to_string()
    assert "EF-03" in written.to_string()
```

- [ ] **Step 2: Run to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_stock_export.py -q -k not_in_filter`

Expected: FAIL — `AB-01` is present in the written file.

- [ ] **Step 3: Replace the duplicate query builder**

In `shopify_tool/stock_export.py`, add to the imports at the top:

```python
from shopify_tool.report_filters import apply_report_filters
```

Replace the block from `# Build the query string to filter the DataFrame` through `filtered_items = analysis_df.query(full_query).copy()` with:

```python
        # Same shared evaluator as the packing-list writer -- these two used
        # to hold byte-identical copies of a query-string builder, and so
        # shared its defects.
        fulfillable = analysis_df[
            analysis_df["Order_Fulfillment_Status"] == "Fulfillable"
        ]
        filtered_items = apply_report_filters(fulfillable, filters)
```

- [ ] **Step 4: Run to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_stock_export.py -q`

Expected: PASS, including all pre-existing write-off and merge tests.

- [ ] **Step 5: Commit**

```bash
git add shopify_tool/stock_export.py tests/test_stock_export.py
git commit -m "$(cat <<'EOF'
Stock exports: evaluate filters through report_filters

Removes the second copy of the query-string builder. Both writers now share
one evaluator.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PCmhFN4SuzRPDTB111c69T
EOF
)"
```

---

## Task 4: Make the preview and the JSON agree with the files

**Files:**
- Modify: `gui/actions_handler.py` — `_apply_filters` (the ~40-line per-operator implementation)
- Test: `tests/test_report_filters.py`

**Interfaces:**
- Consumes: `apply_report_filters` from Task 1.
- Produces: `ActionsHandler._apply_filters(df, filters)` kept as a thin delegating method, because `report_selection_dialog` receives it as `apply_filters_fn` and Task 7 keeps that wiring.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_report_filters.py`:

```python
def test_preview_and_writer_agree_on_the_same_config(tmp_path):
    """The invariant this whole change exists to establish.

    The preview counted rows with actions_handler._apply_filters while the
    XLSX was written by a .query() string, so the dialog could report one
    order and the file could contain three -- and the JSON handed to Packing
    Tool, which used the preview's implementation, could disagree with the
    XLSX given to the warehouse.
    """
    from shopify_tool.packing_lists import create_packing_list

    df = pd.DataFrame({
        "Order_Number": ["#1001", "#1002", "#1003"],
        "SKU": ["AB-01", "CD-02", "EF-03"],
        "Product_Name": ["Widget", "Gadget", "Doohickey"],
        "Warehouse_Name": ["Widget", "Gadget", "Doohickey"],
        "Quantity": [1, 2, 3],
        "Shipping_Provider": ["DHL", "DPD", "DHL"],
        "Destination_Country": ["DE", "FR", "DE"],
        "Order_Fulfillment_Status": ["Fulfillable"] * 3,
    })
    filters = [{"field": "SKU", "operator": "not in", "value": "AB-01,CD-02"}]

    preview_skus = sorted(apply_report_filters(df, filters)["SKU"].tolist())

    out = tmp_path / "agree.xlsx"
    create_packing_list(df, str(out), "agree", filters=filters)
    written_skus = sorted(pd.read_excel(out)["SKU"].tolist())

    assert preview_skus == written_skus == ["EF-03"]
```

- [ ] **Step 2: Run to verify it passes already**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_report_filters.py -q -k preview_and_writer`

Expected: PASS — Task 2 already made the writer correct. This test pins the invariant so it cannot regress. Proceed to Step 3 to remove the last duplicate implementation.

- [ ] **Step 3: Delete the GUI's own implementation**

In `gui/actions_handler.py`, replace the entire body of `_apply_filters` (everything after the docstring, from `filtered_df = df.copy()` to `return filtered_df`) with a delegation:

```python
    def _apply_filters(self, df, filters):
        """Apply a report config's filters to a DataFrame.

        Kept as a method because report_selection_dialog receives it as
        apply_filters_fn. The logic lives in shopify_tool.report_filters so
        the preview, the JSON and both file writers cannot drift apart --
        they used to, and the preview could report a different number of
        orders than the file contained.

        Args:
            df: DataFrame to filter
            filters: List of filter dicts with 'field', 'operator', 'value'

        Returns:
            Filtered DataFrame
        """
        from shopify_tool.report_filters import apply_report_filters

        return apply_report_filters(df, filters)
```

- [ ] **Step 4: Run the full suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`

Expected: PASS. If any pre-existing test asserted the old lenient behaviour (an unknown operator being skipped rather than matching nothing), update that test to the new contract and note it in the commit body — the new behaviour is deliberate, per the spec.

- [ ] **Step 5: Commit**

```bash
git add gui/actions_handler.py tests/test_report_filters.py
git commit -m "$(cat <<'EOF'
Preview, JSON and files now share one filter evaluator

_apply_filters was a third implementation, so the dialog preview and the
JSON handed to Packing Tool could disagree with the XLSX given to the
warehouse from the same config.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PCmhFN4SuzRPDTB111c69T
EOF
)"
```

---

## Task 5: Configurable packing-list columns

**Files:**
- Modify: `shopify_tool/packing_lists.py` — `create_packing_list` signature, `columns_for_print`, the rename hack at ~line 227, the order-boundary computation, column widths
- Test: `tests/test_packing_lists.py`

**Interfaces:**
- Produces: `create_packing_list(analysis_df, output_file, report_name="Packing List", filters=None, exclude_skus=None, columns=None)`. `columns=None` reproduces today's output exactly. Task 6's column picker writes `columns` into the packing-list config; Task 7 passes it through.

**Three obstructions, all of which must be cleared:**

1. `rename_map = {"Shipping_Provider": timestamp, "Warehouse_Name": filename}` assumes both columns are present. With a user-chosen set they may not be.
2. `order_boundaries` is computed from `print_list["Order_Number"]`. Deselecting `Order_Number` raises `KeyError`.
3. Widths and centred formats key off `columns_for_print[i]`, which is already indirection-safe — leave that mechanism alone.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_packing_lists.py`:

```python
def _three_row_df():
    return pd.DataFrame({
        "Order_Number": ["#1001", "#1001", "#1002"],
        "SKU": ["AB-01", "CD-02", "EF-03"],
        "Product_Name": ["Widget", "Gadget", "Doohickey"],
        "Warehouse_Name": ["Widget", "Gadget", "Doohickey"],
        "Quantity": [1, 2, 3],
        "Shipping_Provider": ["DHL", "DHL", "DPD"],
        "Destination_Country": ["DE", "DE", "FR"],
        "Order_Fulfillment_Status": ["Fulfillable"] * 3,
    })


def test_columns_none_reproduces_the_default_layout(tmp_path):
    """The guard against regressing every existing packing list."""
    out = tmp_path / "default.xlsx"
    create_packing_list(_three_row_df(), str(out), "default")

    written = pd.read_excel(out)
    # Shipping_Provider and Warehouse_Name are renamed to carry the timestamp
    # and the filename; the other four keep their names and order.
    assert list(written.columns)[:3] == ["Destination_Country", "Order_Number", "SKU"]
    assert len(written.columns) == 6


def test_chosen_columns_appear_in_the_chosen_order(tmp_path):
    out = tmp_path / "custom.xlsx"
    create_packing_list(_three_row_df(), str(out), "custom",
                        columns=["SKU", "Quantity", "Order_Number"])

    written = pd.read_excel(out)
    assert list(written.columns) == ["SKU", "Quantity", "Order_Number"]
    assert written["SKU"].tolist() == ["AB-01", "CD-02", "EF-03"]


def test_column_set_without_order_number_still_writes(tmp_path):
    """Order boundaries drive the row borders and used to be read off the
    printed frame, so deselecting Order_Number raised KeyError."""
    out = tmp_path / "no_order_col.xlsx"
    create_packing_list(_three_row_df(), str(out), "no_order_col",
                        columns=["SKU", "Quantity"])

    written = pd.read_excel(out)
    assert list(written.columns) == ["SKU", "Quantity"]
    assert len(written) == 3


def test_metadata_survives_a_column_set_that_drops_the_carrier_columns(tmp_path):
    """The timestamp and filename used to ride on Shipping_Provider and
    Warehouse_Name. With neither selected they must still reach the sheet --
    they move to the Excel print header."""
    out = tmp_path / "no_carriers.xlsx"
    create_packing_list(_three_row_df(), str(out), "no_carriers",
                        columns=["SKU", "Quantity"])

    written = pd.read_excel(out)
    # No metadata smuggled into a column name.
    assert list(written.columns) == ["SKU", "Quantity"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_packing_lists.py -q -k "chosen_columns or without_order_number or metadata_survives"`

Expected: FAIL — `create_packing_list() got an unexpected keyword argument 'columns'`.

- [ ] **Step 3: Implement**

Change the signature:

```python
def create_packing_list(analysis_df, output_file, report_name="Packing List",
                        filters=None, exclude_skus=None, columns=None):
```

Add to the docstring's Args section:

```
        columns (list[str], optional): The columns to print, in order. None
            keeps the default layout. Columns not present in the data are
            dropped with a warning rather than raising.
```

Replace the `columns_for_print = [...]` assignment in the `else` branch so a caller-supplied list wins:

```python
            default_columns = [
                "Destination_Country",
                "Order_Number",
                "SKU",
                "Warehouse_Name",  # From stock file - actual warehouse product names (or Product_Name fallback)
                "Quantity",
                "Shipping_Provider",
            ]
            if columns:
                columns_for_print = [c for c in columns if c in sorted_list.columns]
                missing = [c for c in columns if c not in sorted_list.columns]
                if missing:
                    logger.warning(f"Configured columns not in the data, skipped: {missing}")
                if not columns_for_print:
                    logger.warning("No configured column exists in the data; using the default layout")
                    columns_for_print = default_columns
            else:
                columns_for_print = default_columns
```

Compute the order boundaries **before** slicing to the printed columns, so they
do not depend on `Order_Number` being printed. Replace the
`order_boundaries = print_list[...]` line with a value computed from
`sorted_list` right after `print_list = sorted_list[columns_for_print]`:

```python
        # Borders group the rows of one order. Read the boundaries off the
        # full frame -- the user may not have chosen to print Order_Number.
        order_boundaries = (
            sorted_list["Order_Number"].ne(sorted_list["Order_Number"].shift()).cumsum()
        )
```

and delete the later re-assignment inside the `with` block.

Make the metadata rename conditional, and always put it in the print header so
it survives any column choice. Replace the `rename_map = {...}` line with:

```python
        # The timestamp and the filename ride on two column headers when those
        # columns are printed -- that is the established look. With a custom
        # column set they may be absent, so the same metadata also goes into
        # the Excel print header, where it cannot be lost.
        rename_map = {
            col: label
            for col, label in (
                ("Shipping_Provider", generation_timestamp),
                ("Warehouse_Name", output_filename),
            )
            if col in print_list.columns
        }
```

and in the print-settings block, next to `worksheet.set_paper(9)`, add:

```python
            worksheet.set_header(f"&L{output_filename}&R{generation_timestamp}")
```

- [ ] **Step 4: Run to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_packing_lists.py -q`

Expected: PASS, all tests in the file including the pre-existing lot-detail layout tests.

- [ ] **Step 5: Commit**

```bash
git add shopify_tool/packing_lists.py tests/test_packing_lists.py
git commit -m "$(cat <<'EOF'
Packing lists: configurable output columns

columns=None keeps today's layout byte for byte. Order-group borders now read
their boundaries off the full frame, so Order_Number no longer has to be
printed, and the timestamp/filename metadata moves to the print header so it
survives any column choice.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PCmhFN4SuzRPDTB111c69T
EOF
)"
```

---

## Task 6: One Reports settings page

**Files:**
- Create: `gui/settings/report_editor.py`, `gui/settings/reports.py`
- Delete: `gui/settings/packing_lists.py`, `gui/settings/stock_exports.py`
- Modify: `gui/settings/fields.py`, `gui/settings/window.py`
- Create: `tests/test_settings_page_reports.py`
- Delete: `tests/test_settings_page_packing_lists.py`, `tests/test_settings_page_stock_exports.py`

**Interfaces:**
- Consumes: `SettingsPage` from `gui/settings/base.py`; `add_filter_row`, `CONDITION_OPERATORS` from `gui/settings/fields.py`; `set_button_role` from `gui/theme_manager`.
- Produces:
  - `ReportEditor(kind, config, analysis_df, parent=None)`; method `collect() -> dict`.
  - `ReportsPage(packing_configs, stock_configs, analysis_df, parent=None)`; `collect() -> {"packing_list_configs": [...], "stock_export_configs": [...]}`.
  - `report_filter_fields(analysis_df) -> list[str]` in `fields.py`, used by Task 7's preview labels.

**`kind` vocabulary — use these two strings and no others.** `kind` is
`"packing_lists"` or `"stock_exports"`, plural, matching the existing
`report_type` convention that `_generate_single_report` and the old
`open_report_selection_dialog` already use. Task 7 emits the same strings as
`report_type`, so one vocabulary spans the settings page, the dialog and the
generator. Do not introduce a singular variant.

**Design notes for the implementer:**

The two existing pages are ~90% identical: an "Add New …" button, a scroll
area, and one group box per report holding name / output filename / filters /
delete. Only `exclude_skus` (packing lists) differs. `ReportEditor` holds that
shared structure and switches on `kind` for the two differences: the
`exclude_skus` line edit and the column picker, both packing-list only.

`ReportsPage` stacks two labelled sections in one scroll area, each with its
own "Add New" button, and returns both config keys from `collect()` — the
`SettingsPage` contract explicitly allows a page owning several keys.

- [ ] **Step 1: Add the field and operator helpers**

In `gui/settings/fields.py`, below `CONDITION_OPERATORS`, add:

```python
# Report filters use the rule engine's vocabulary. The old five-symbol list
# (==, !=, in, not in, contains) is still understood when reading saved
# configs -- see shopify_tool/report_filters.LEGACY_OPERATOR_ALIASES -- but
# new configs are written with these names.
REPORT_FILTER_OPERATORS: list[str] = list(CONDITION_OPERATORS)


def report_filter_fields(analysis_df) -> list[str]:
    """Columns offered in a report filter's field dropdown and column picker.

    Sourced from the analysis DataFrame so Internal_Tags and any additional
    CSV columns the client configured are filterable, falling back to the
    static list when no analysis has been run yet. Always sorted, so the
    column picker's order -- and therefore a saved config's column order --
    does not depend on which branch produced the list.
    """
    if analysis_df is not None and not analysis_df.empty:
        return sorted(analysis_df.columns.tolist())
    return sorted(FILTERABLE_COLUMNS)
```

Also add `"Quantity"` to `FILTERABLE_COLUMNS` — it is filterable in every other
surface in the app and its absence here is an oversight.

- [ ] **Step 2: Write the failing test**

Create `tests/test_settings_page_reports.py`:

```python
"""The merged Reports settings page.

PackingListsPage and StockExportsPage were ~90% identical; they are one page
now, owning both config keys. The round-trip tests below are the merged
successors of test_settings_page_packing_lists.py and
test_settings_page_stock_exports.py.
"""
import pytest
from PySide6.QtWidgets import QApplication

from gui.settings.reports import ReportsPage


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


# "columns" is in the picker's own (sorted) order -- see the note in the plan
# about column ordering being the picker's, not an arbitrary user order.
PACKING = [{
    "name": "DHL Express",
    "output_filename": "dhl.xlsx",
    "filters": [{"field": "Shipping_Provider", "operator": "equals", "value": "DHL"}],
    "exclude_skus": ["SHIP-01"],
    "columns": ["Quantity", "SKU"],
}]

STOCK = [{
    "name": "Daily ERP",
    "output_filename": "erp.xls",
    "filters": [{"field": "SKU", "operator": "in list", "value": "A,B"}],
}]


def test_round_trips_both_config_keys():
    page = ReportsPage(PACKING, STOCK, analysis_df=None)

    collected = page.collect()

    assert collected["packing_list_configs"] == PACKING
    assert collected["stock_export_configs"] == STOCK


def test_starts_empty_with_no_configs():
    page = ReportsPage([], [], analysis_df=None)

    assert page.collect() == {
        "packing_list_configs": [],
        "stock_export_configs": [],
    }


def test_only_packing_lists_carry_exclude_skus_and_columns():
    """Stock export configs must not grow packing-list-only keys."""
    page = ReportsPage(PACKING, STOCK, analysis_df=None)

    stock = page.collect()["stock_export_configs"][0]

    assert "exclude_skus" not in stock
    assert "columns" not in stock


def test_added_packing_list_appears_in_collect():
    page = ReportsPage([], [], analysis_df=None)

    page.add_report("packing_lists")

    assert len(page.collect()["packing_list_configs"]) == 1


@pytest.mark.parametrize("stored, expected", [
    ("==", "equals"),
    ("!=", "does not equal"),
    ("in", "in list"),
    ("not in", "not in list"),
    ("contains", "contains"),
])
def test_legacy_operators_survive_a_load_and_save(stored, expected):
    """Opening the page must not rewrite a saved filter's meaning.

    add_filter_row does op_combo.setCurrentText(stored), and on a non-editable
    QComboBox that silently does nothing when the string is absent from the
    list -- leaving "equals" selected. Without normalising first, merely
    opening settings and pressing Save would turn every stored "!=" and
    "not in" filter into "equals", inverting it against live client data.
    """
    config = [{
        "name": "legacy",
        "output_filename": "legacy.xlsx",
        "filters": [{"field": "SKU", "operator": stored, "value": "AB-01"}],
        "exclude_skus": [],
    }]
    page = ReportsPage(config, [], analysis_df=None)

    saved = page.collect()["packing_list_configs"][0]["filters"][0]

    assert saved["operator"] == expected
    assert saved["value"] == "AB-01"
```

- [ ] **Step 3: Run to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_settings_page_reports.py -q`

Expected: `ModuleNotFoundError: No module named 'gui.settings.reports'`

- [ ] **Step 4: Implement `ReportEditor`**

Create `gui/settings/report_editor.py`:

```python
"""One report's editor, shared by both report kinds.

PackingListsPage and StockExportsPage each carried their own copy of this
widget and differed only in the exclude-SKUs field. The two differences that
remain -- exclude SKUs and the column picker -- are packing-list only and
switch on `kind`.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from gui.settings.fields import REPORT_FILTER_OPERATORS, add_filter_row, report_filter_fields
from gui.theme_manager import set_button_role
from shopify_tool.report_filters import normalize_operator

PACKING_LISTS = "packing_lists"
STOCK_EXPORTS = "stock_exports"


class ReportEditor(QGroupBox):
    """Editor for a single packing-list or stock-export config."""

    def __init__(self, kind, config=None, analysis_df=None, parent=None):
        super().__init__(parent)
        if kind not in (PACKING_LISTS, STOCK_EXPORTS):
            raise ValueError(f"Unknown report kind: {kind}")
        self.kind = kind
        self.analysis_df = analysis_df
        self.filters = []

        if not isinstance(config, dict):
            config = {}

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name_edit = QLineEdit(config.get("name", ""))
        self.filename_edit = QLineEdit(config.get("output_filename", ""))
        form.addRow("Name:", self.name_edit)
        form.addRow("Output Filename:", self.filename_edit)

        self.exclude_skus_edit = None
        self.columns_list = None
        if kind == PACKING_LISTS:
            self.exclude_skus_edit = QLineEdit(",".join(config.get("exclude_skus", [])))
            form.addRow("Exclude SKUs (comma-separated):", self.exclude_skus_edit)
        layout.addLayout(form)

        filters_box = QGroupBox("Filters")
        filters_box_layout = QVBoxLayout(filters_box)
        self.filters_layout = QVBoxLayout()
        filters_box_layout.addLayout(self.filters_layout)
        add_filter_btn = QPushButton("Add Filter")
        set_button_role(add_filter_btn, "secondary")
        add_filter_btn.clicked.connect(self._add_filter)
        filters_box_layout.addWidget(add_filter_btn, 0, Qt.AlignLeft)
        layout.addWidget(filters_box)

        if kind == PACKING_LISTS:
            columns_box = QGroupBox("Columns to display")
            columns_layout = QVBoxLayout(columns_box)
            hint = QLabel("Leave all unchecked to use the default layout.")
            hint.setWordWrap(True)
            columns_layout.addWidget(hint)
            self.columns_list = QListWidget()
            # An unbounded QListWidget inside the settings page's scroll area
            # collapses to about two visible rows.
            self.columns_list.setMinimumHeight(160)
            chosen = config.get("columns") or []
            for name in report_filter_fields(analysis_df):
                item = QListWidgetItem(name)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked if name in chosen else Qt.Unchecked)
                self.columns_list.addItem(item)
            columns_layout.addWidget(self.columns_list)
            layout.addWidget(columns_box)

        self.delete_button = QPushButton("Delete")
        set_button_role(self.delete_button, "secondary")
        layout.addWidget(self.delete_button, 0, Qt.AlignRight)

        for f_config in config.get("filters", []):
            self._add_filter(f_config)

    def _add_filter(self, f_config=None):
        # Normalise the stored operator before it reaches the combo box.
        # add_filter_row does op_combo.setCurrentText(stored), and on a
        # non-editable QComboBox that is a silent no-op when the string is not
        # in the list -- leaving index 0, "equals". A saved "!=" or "not in"
        # filter would therefore render as "equals" and be written back that
        # way on the next save, inverting the filter against live client
        # configs. Verified: setCurrentText("!=") leaves the combo on "equals".
        if isinstance(f_config, dict):
            f_config = {**f_config, "operator": normalize_operator(f_config.get("operator"))}
        else:
            f_config = None

        add_filter_row(
            {"filters_layout": self.filters_layout, "filters": self.filters},
            report_filter_fields(self.analysis_df),
            REPORT_FILTER_OPERATORS,
            self.analysis_df,
            f_config,
        )

    def _chosen_columns(self):
        """The ticked columns, in list order. Empty means "default layout"."""
        if self.columns_list is None:
            return []
        return [
            self.columns_list.item(i).text()
            for i in range(self.columns_list.count())
            if self.columns_list.item(i).checkState() == Qt.Checked
        ]

    def collect(self) -> dict:
        """This report's config dict.

        Packing-list-only keys are omitted entirely for stock exports rather
        than written as empty -- a stock export config that grew an
        exclude_skus key would be silently carried into the saved profile.
        """
        filters = []
        for f in self.filters:
            value_widget = f.get("value_widget")
            if isinstance(value_widget, QComboBox):
                val = value_widget.currentText()
            elif value_widget is not None:
                val = value_widget.text()
            else:
                val = ""
            filters.append({
                "field": f["field"].currentText(),
                "operator": f["op"].currentText(),
                "value": val,
            })

        config = {
            "name": self.name_edit.text(),
            "output_filename": self.filename_edit.text(),
            "filters": filters,
        }

        if self.kind == PACKING_LISTS:
            raw = self.exclude_skus_edit.text().strip()
            config["exclude_skus"] = [s.strip() for s in raw.split(",") if s.strip()]
            chosen = self._chosen_columns()
            if chosen:
                config["columns"] = chosen

        return config
```

**Known limitation — column *order* is the picker's, not the user's.** A
checkbox list can express which columns, not what order; the saved `columns`
list comes out in `report_filter_fields` order. The spec asked for "which
columns the XLSX shows, and in what order", so this delivers the first half
fully and the second only as a stable, predictable order. Mark it in
`report_editor.py` above the picker:

```python
            # ponytail: checkbox list gives column choice but not arbitrary
            # column order -- the saved order is the picker's. Add Move Up /
            # Move Down buttons (see ColumnConfigPanel, which already does
            # exactly this) if a user asks to reorder printed columns.
```

Raise it in the PR body so the maintainer can decide whether the reorder
controls are worth a follow-up.

- [ ] **Step 5: Implement `ReportsPage`**

Create `gui/settings/reports.py`:

```python
"""Packing list and stock export reports, in one settings page."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from gui.settings.base import SettingsPage
from gui.settings.report_editor import PACKING_LISTS, STOCK_EXPORTS, ReportEditor
from gui.theme_manager import set_button_role

_SECTIONS = (
    (PACKING_LISTS, "Packing Lists", "Add New Packing List", "packing_list_configs"),
    (STOCK_EXPORTS, "Stock Exports", "Add New Stock Export", "stock_export_configs"),
)


class ReportsPage(SettingsPage):
    """Owns both packing_list_configs and stock_export_configs.

    The SettingsPage contract allows one page to own several config keys; each
    value returned by collect() replaces config_data[key] outright.
    """

    def __init__(self, packing_configs, stock_configs, analysis_df=None, parent=None):
        super().__init__(parent)
        self.analysis_df = analysis_df
        self._editors = {PACKING_LISTS: [], STOCK_EXPORTS: []}
        self._layouts = {}

        main_layout = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        main_layout.addWidget(scroll)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setAlignment(Qt.AlignTop)
        scroll.setWidget(content)

        for kind, title, add_label, _ in _SECTIONS:
            heading = QLabel(title)
            heading_font = heading.font()
            heading_font.setBold(True)
            heading.setFont(heading_font)
            content_layout.addWidget(heading)

            add_btn = QPushButton(add_label)
            set_button_role(add_btn, "secondary")
            add_btn.clicked.connect(lambda _checked=False, k=kind: self.add_report(k))
            content_layout.addWidget(add_btn, 0, Qt.AlignLeft)

            section_layout = QVBoxLayout()
            content_layout.addLayout(section_layout)
            self._layouts[kind] = section_layout

        for config in packing_configs or []:
            self.add_report(PACKING_LISTS, config)
        for config in stock_configs or []:
            self.add_report(STOCK_EXPORTS, config)

    def add_report(self, kind, config=None):
        """Adds one report editor to the given section."""
        editor = ReportEditor(kind, config, self.analysis_df)
        editor.delete_button.clicked.connect(
            lambda _checked=False, e=editor, k=kind: self._delete(k, e)
        )
        self._layouts[kind].addWidget(editor)
        self._editors[kind].append(editor)
        return editor

    def _delete(self, kind, editor):
        editor.deleteLater()
        self._editors[kind].remove(editor)

    def collect(self) -> dict:
        return {
            config_key: [e.collect() for e in self._editors[kind]]
            for kind, _title, _label, config_key in _SECTIONS
        }
```

- [ ] **Step 6: Register the page and delete the old ones**

In `gui/settings/window.py`, replace the two page registrations with one
`ReportsPage`, constructed from `config_data.get("packing_list_configs", [])`
and `config_data.get("stock_export_configs", [])`. Then:

```bash
git rm gui/settings/packing_lists.py gui/settings/stock_exports.py
git rm tests/test_settings_page_packing_lists.py tests/test_settings_page_stock_exports.py
```

Grep for stragglers and fix each:

```bash
grep -rn "PackingListsPage\|StockExportsPage\|settings.packing_lists\|settings.stock_exports" --include=*.py .
```

- [ ] **Step 7: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_settings_page_reports.py -q`

Expected: PASS, 4 tests.

Then the full suite: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`

- [ ] **Step 8: Commit**

```bash
git add -A gui/settings tests/test_settings_page_reports.py
git commit -m "$(cat <<'EOF'
Settings: one Reports page for both report kinds

PackingListsPage and StockExportsPage were ~90% identical. They become one
page over a shared ReportEditor. Filter rows now offer the rule engine's
operator vocabulary and take their field list from the analysis DataFrame,
so Internal_Tags and additional CSV columns are filterable. Packing lists
gain a column picker.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PCmhFN4SuzRPDTB111c69T
EOF
)"
```

---

## Task 7: One generation dialog, multi-select

**Files:**
- Modify: `gui/report_selection_dialog.py` — add `GenerateReportsDialog`
- Modify: `gui/actions_handler.py` — `open_report_selection_dialog`, `_generate_single_report` call site
- Modify: `gui/main_window_pyside.py:321-322` — one button
- Create: `tests/test_generate_reports_dialog.py`

**Interfaces:**
- Consumes: `_BaseReportDialog`'s preview panel; `ReportsPage`'s two config keys; `create_packing_list(..., columns=...)` from Task 5.
- Produces: `GenerateReportsDialog(packing_configs, stock_configs, analysis_df, apply_filters_fn, writeoff_handler=None, parent=None)` emitting `reportsSelected(list)`, where each item is `dict(config, report_type=...)`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_generate_reports_dialog.py`:

```python
"""One dialog generating any number of reports of both kinds in one pass.

Previously two buttons opened two modal dialogs, each emitting exactly one
config, so producing a packing list and its stock export took two full
round-trips.
"""
import pandas as pd
import pytest
from PySide6.QtWidgets import QApplication

from gui.report_selection_dialog import GenerateReportsDialog


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


PACKING = [
    {"name": "DHL", "output_filename": "dhl.xlsx", "filters": []},
    {"name": "DPD", "output_filename": "dpd.xlsx", "filters": []},
]
STOCK = [{"name": "Daily ERP", "output_filename": "erp.xls", "filters": []}]


def _df():
    return pd.DataFrame({
        "Order_Number": ["#1001"],
        "SKU": ["AB-01"],
        "Quantity": [1],
        "Order_Fulfillment_Status": ["Fulfillable"],
    })


def _dialog():
    return GenerateReportsDialog(PACKING, STOCK, _df(), lambda df, f: df)


def test_emits_every_checked_report_with_its_type():
    dialog = _dialog()
    emitted = []
    dialog.reportsSelected.connect(emitted.append)

    dialog.set_checked("packing_lists", 0, True)
    dialog.set_checked("packing_lists", 1, True)
    dialog.set_checked("stock_exports", 0, True)
    dialog._on_generate()

    (batch,) = emitted
    assert [(r["name"], r["report_type"]) for r in batch] == [
        ("DHL", "packing_lists"),
        ("DPD", "packing_lists"),
        ("Daily ERP", "stock_exports"),
    ]


def test_emits_nothing_when_no_report_is_checked():
    dialog = _dialog()
    emitted = []
    dialog.reportsSelected.connect(emitted.append)

    dialog._on_generate()

    assert emitted == []


def test_generate_button_is_disabled_until_something_is_checked():
    dialog = _dialog()
    assert dialog.generate_button.isEnabled() is False

    dialog.set_checked("packing_lists", 0, True)

    assert dialog.generate_button.isEnabled() is True
```

- [ ] **Step 2: Run to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_generate_reports_dialog.py -q`

Expected: `ImportError: cannot import name 'GenerateReportsDialog'`

- [ ] **Step 3: Implement the dialog**

In `gui/report_selection_dialog.py`, add `GenerateReportsDialog`, reusing
`_BaseReportDialog`'s right-hand preview panel:

- Left panel: one `QListWidget` holding both kinds under non-selectable
  section header rows ("PACKING LISTS", "STOCK EXPORTS"), each report row a
  checkable item carrying `(kind, index)` in `Qt.UserRole`. Mark header rows
  with a module-level sentinel and `Qt.NoItemFlags`, exactly as
  `column_config_dialog._CATEGORY_HEADER_MARKER` does — follow that pattern
  rather than inventing a second one.
- Selecting (not checking) a row updates the existing preview via
  `_update_preview(cfg)`.
- A footer label showing `"{n} selected"`.
- `set_checked(kind, index, checked)` — a small method the tests drive and the
  UI uses, so the test does not have to reach into list internals.
- `generate_button` enabled only when at least one row is checked.
- `_on_generate()` builds the list in list order, each entry
  `{**config, "report_type": kind}`, emits `reportsSelected`, and accepts the
  dialog. With nothing checked it emits nothing and does not close.
- Keep the write-off section from `StockExportDialog` and its
  `writeoff_handler` wiring unchanged.

Leave the existing `PackingListDialog` / `StockExportDialog` classes in place
for this task; Task 8 removes them once nothing references them.

- [ ] **Step 4: Wire the handler and the button**

In `gui/actions_handler.py`, replace `open_report_selection_dialog(report_type)`
with a no-argument `open_generate_reports_dialog()` that keeps all the existing
guards (analysis present, client selected, session open, fresh config reload),
reads **both** config keys, warns only when both are empty, and connects:

```python
        dialog.reportsSelected.connect(
            lambda batch: self._generate_reports(batch, session_path)
        )
```

Add the loop, with per-report isolation so one failure cannot abort the rest:

```python
    def _generate_reports(self, batch, session_path):
        """Generate every report the dialog emitted.

        One report failing must not cost the user the others -- that is the
        whole point of generating them in one pass.
        """
        failures = []
        for report_config in batch:
            report_type = report_config.get("report_type")
            try:
                self._generate_single_report(report_type, report_config, session_path)
            except Exception as exc:
                self.log.exception(f"Failed to generate {report_config.get('name')}")
                failures.append(f"{report_config.get('name', 'Unknown')}: {exc}")

        if failures:
            QMessageBox.warning(
                self.mw,
                "Some Reports Failed",
                "These reports could not be generated:\n\n" + "\n".join(failures),
            )
```

In `_generate_single_report`, pass the configured columns through to the writer:

```python
                    columns=report_config.get("columns"),
```

as an argument to the `packing_lists.create_packing_list(...)` call.

In `gui/main_window_pyside.py`, collapse the two report buttons into one
"Generate Reports" button calling `open_generate_reports_dialog()`. Keep the
existing enable/disable wiring (`main_window_pyside.py:760-769`) pointed at the
surviving button and drop the references to the removed one.

- [ ] **Step 5: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_generate_reports_dialog.py -q`

Expected: PASS, 3 tests.

- [ ] **Step 6: Commit**

```bash
git add gui/report_selection_dialog.py gui/actions_handler.py gui/main_window_pyside.py tests/test_generate_reports_dialog.py
git commit -m "$(cat <<'EOF'
One Generate Reports dialog for both report kinds

Multi-select across packing lists and stock exports, generated in one pass,
with per-report isolation so one failure does not cost the others. Replaces
two buttons opening two single-select modal dialogs.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PCmhFN4SuzRPDTB111c69T
EOF
)"
```

---

## Task 8: Remove the superseded dialogs and run the gate

**Files:**
- Modify: `gui/report_selection_dialog.py` — delete `PackingListDialog`, `StockExportDialog`, and `ReportSelectionDialog` if unreferenced

- [ ] **Step 1: Find what is still referenced**

```bash
grep -rn "PackingListDialog\|StockExportDialog\|ReportSelectionDialog\|open_report_selection_dialog" --include=*.py .
```

Delete each class that has no remaining reference outside its own definition
and its own tests. If a test references one, delete that test — its behaviour
is covered by `tests/test_generate_reports_dialog.py`. If anything outside
`gui/` or `tests/` still references one, stop and leave it in place rather than
breaking a caller.

- [ ] **Step 2: Run the full gate**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest
.venv/bin/ruff check . --exclude shared
```

Expected: all tests pass, ruff clean. Do not proceed with a red gate — fix
what broke.

- [ ] **Step 3: Refresh the knowledge graph**

```bash
graphify update .
```

Required by this repo's CLAUDE.md — a stale graph silently returns wrong
answers about `shared/` ownership and theme delegation.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "$(cat <<'EOF'
Remove the superseded single-select report dialogs

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PCmhFN4SuzRPDTB111c69T
EOF
)"
```

---

## Notes for the reviewer

- **Behaviour change on existing configs is intended.** Any saved config using
  `in`, `not in` or `contains` produces different output after this change —
  correct output, where it was previously silently wrong or missing. Call this
  out in the PR body.
- **Not addressed here:** reports already generated with the broken filters are
  not reconciled. This stops the bug; it does not correct past output.
- **Version string not bumped.** `gui_main.py:11`, `shopify_tool/__init__.py:7`
  and `README.md:3` must move together when it is; left for the maintainer to
  decide as part of the release, not this branch.
- **Delete this plan and its spec after the PR merges**, so the archive that
  #286 cleared does not regrow.
