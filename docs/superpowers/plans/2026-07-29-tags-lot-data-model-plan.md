# Tags & Lot Data Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the four root causes behind six reported "Tags & Lot data model" bugs (plus two found during design review) in the Analysis Results table, without restructuring the underlying per-line DataFrame.

**Architecture:** `Internal_Tags` is semantically order-level but stored per DataFrame line; a new shared helper (`tag_manager.expand_to_order_rows`) makes every write path apply to a whole order's rows consistently instead of each picking a different subset. `Tags` gets a missing forward-fill. `Lot_Details` gets a dedicated renderer (fixing a live crash) and a more capable expiry parser. The Tag Categories dialog gets a deep copy so Cancel is a true no-op.

**Tech Stack:** Python, pandas, PySide6 (Qt), pytest + pytest-qt, ruff.

## Global Constraints

- Tests run via `QT_QPA_PLATFORM=offscreen python -m pytest` (headless Qt).
- Lint via `ruff check . --exclude shared` must pass before merge.
- Never hand-edit anything under `shared/` (one-way synced from `packing-tool`) — none of this plan's files are under `shared/`.
- No hardcoded colors in stylesheets — not applicable to this plan (no stylesheet changes).
- No UI calls from background threads — not applicable (no threading changes).
- Follow existing patterns: `isinstance(value, list)` before `pd.isna(value)` is already the established idiom for tag-like values in this codebase (`shopify_tool/tag_manager.py:20-22`, `parse_tags`) — reuse it, don't invent a new one.
- No version bump — this repo only bumps `__version__` at release time, not per epic (confirmed: Phase 1's merged PR #255 did not touch `gui_main.py`/`shopify_tool/__init__.py`/`README.md`).

---

## File Structure

| File | Responsibility in this plan |
|---|---|
| `shopify_tool/tag_manager.py` | New `expand_to_order_rows()` helper (Task 1) |
| `gui/actions_handler.py` | `bulk_add_tag`/`bulk_remove_tag` write all rows of selected orders (Task 2) |
| `shopify_tool/undo_manager.py` | `_undo_bulk_add_tag`/`_undo_bulk_remove_tag` restore all rows, not just one (Task 3) |
| `gui/main_window_pyside.py` | `_add_internal_tag` (right-click) expands to whole order (Task 4); `on_selection_changed_for_tags` shows merged tags (Task 6) |
| `shopify_tool/rules.py` | `ADD_INTERNAL_TAG` rule action expands to whole order (Task 5) |
| `shopify_tool/analysis.py` | `Tags` forward-fill (Task 7); `_parse_expiry_date` extended formats (Task 9); `simulate_stock_allocation` carries `expiry_dt` (Task 9) |
| `gui/pandas_model.py` | `Lot_Details` renderer + crash fix (Task 8) |
| `gui/tag_categories_dialog.py` | `TagCategoriesPanel` deep-copy isolation (Task 10) |
| `tests/test_tag_manager.py` | Task 1 tests |
| `tests/test_actions_handler.py` | Task 2 tests |
| `tests/test_undo_manager.py` | Task 3 tests |
| `tests/test_main_window_tags.py` (new) | Task 4, 6 tests |
| `tests/test_rules.py` | Task 5 tests |
| `tests/test_analysis.py` | Task 7, 9 tests |
| `tests/test_pandas_model.py` (new) | Task 8 tests |
| `tests/test_tag_categories_dialog.py` (new) | Task 10 tests |

Tasks are ordered so Task 1 (the shared helper) lands before anything that consumes it, and each task is independently testable/committable.

---

### Task 1: `tag_manager.expand_to_order_rows()`

**Files:**
- Modify: `shopify_tool/tag_manager.py`
- Test: `tests/test_tag_manager.py`

**Interfaces:**
- Produces: `expand_to_order_rows(df: pd.DataFrame, mask: pd.Series) -> pd.Series` — given a boolean row mask, returns a boolean mask covering every row of every order touched by the input mask (matched via `Order_Number`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_tag_manager.py`:

```python
import pandas as pd

from shopify_tool.tag_manager import expand_to_order_rows


class TestExpandToOrderRows:
    def _df(self):
        return pd.DataFrame({
            "Order_Number": ["A", "A", "B", "C", "C"],
            "SKU": ["S1", "S2", "S1", "S1", "S2"],
        })

    def test_single_line_mask_expands_to_all_lines_of_that_order(self):
        df = self._df()
        mask = (df["Order_Number"] == "A") & (df["SKU"] == "S1")  # matches only row 0
        result = expand_to_order_rows(df, mask)
        assert result.tolist() == [True, True, False, False, False]

    def test_multi_order_mask_expands_each_order_independently(self):
        df = self._df()
        mask = df.index.isin([0, 3])  # row 0 (order A), row 3 (order C)
        result = expand_to_order_rows(df, pd.Series(mask, index=df.index))
        assert result.tolist() == [True, True, False, True, True]

    def test_mask_matching_zero_rows_returns_all_false(self):
        df = self._df()
        mask = df["Order_Number"] == "DOES-NOT-EXIST"
        result = expand_to_order_rows(df, mask)
        assert not result.any()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_tag_manager.py::TestExpandToOrderRows -v`
Expected: FAIL with `ImportError: cannot import name 'expand_to_order_rows'`

- [ ] **Step 3: Implement**

Add to `shopify_tool/tag_manager.py`, after `has_tag()` (after line 126):

```python
def expand_to_order_rows(df: pd.DataFrame, mask: pd.Series) -> pd.Series:
    """Expand a row mask to cover every row of every order it touches.

    Internal_Tags is order-level, not line-level, but ``df`` has one row per
    order line -- callers that only know about a subset of an order's rows
    (a single clicked SKU line, a rule match on one line, etc.) must expand
    to the full order before writing Internal_Tags, or different lines of
    the same order end up with inconsistent tags.

    Args:
        df: DataFrame with an "Order_Number" column.
        mask: Boolean row mask (any subset of df's rows).

    Returns:
        Boolean mask covering every row whose Order_Number matches at least
        one row in the input mask.
    """
    order_numbers = df.loc[mask, "Order_Number"].unique()
    return df["Order_Number"].isin(order_numbers)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_tag_manager.py::TestExpandToOrderRows -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Lint and commit**

```bash
ruff check shopify_tool/tag_manager.py tests/test_tag_manager.py
git add shopify_tool/tag_manager.py tests/test_tag_manager.py
git commit -m "Add tag_manager.expand_to_order_rows for order-level tag writes"
```

---

### Task 2: Fix `bulk_add_tag`/`bulk_remove_tag` to write all rows of an order

**Files:**
- Modify: `gui/actions_handler.py:1614-1660` (`bulk_add_tag`), `gui/actions_handler.py:1731-1760` (`bulk_remove_tag`)
- Test: `tests/test_actions_handler.py`

**Interfaces:**
- Consumes: nothing new (this task uses `df["Order_Number"].isin(...)` directly, not `expand_to_order_rows`, since `unique_orders` is already computed here — see spec's RC-A table).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_actions_handler.py` (extends the existing `mw` fixture pattern; needs `selection_helper`, `active_profile_config`, `ui_manager` added):

```python
from gui.selection_helper import SelectionHelper
from PySide6.QtWidgets import QInputDialog


@pytest.fixture
def mw_with_tags():
    df = pd.DataFrame(
        [
            {"Order_Number": "1001", "SKU": "A1", "Quantity": 1, "Internal_Tags": "[]"},
            {"Order_Number": "1001", "SKU": "A2", "Quantity": 1, "Internal_Tags": "[]"},
            {"Order_Number": "1002", "SKU": "B1", "Quantity": 1, "Internal_Tags": '["URGENT"]'},
        ]
    )
    mw = SimpleNamespace(
        analysis_results_df=df,
        undo_manager=Mock(),
        save_session_state=Mock(),
        log_activity=Mock(),
        active_profile_config={"tag_categories": {}},
    )
    mw.selection_helper = SelectionHelper(table_view=None, proxy_model=None, main_window=mw)
    return mw


def test_bulk_add_tag_writes_every_row_of_a_multi_line_order(mw_with_tags, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    monkeypatch.setattr(
        QInputDialog, "getItem", lambda *a, **k: ("--- Custom Tag ---", True)
    )
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("FRAGILE", True))

    mw_with_tags.selection_helper.checked_rows = {0}  # only line 1 of order 1001 checked
    handler = ActionsHandler(mw_with_tags)

    handler.bulk_add_tag()

    tags = mw_with_tags.analysis_results_df.set_index("SKU")["Internal_Tags"]
    assert '"FRAGILE"' in tags.loc["A1"]
    assert '"FRAGILE"' in tags.loc["A2"]  # order 1001's other line, not just the checked one
    assert '"FRAGILE"' not in tags.loc["B1"]  # different order, untouched


def test_bulk_remove_tag_removes_from_every_row_of_a_multi_line_order(mw_with_tags, monkeypatch):
    df = mw_with_tags.analysis_results_df
    df.loc[df["Order_Number"] == "1001", "Internal_Tags"] = '["URGENT"]'

    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    monkeypatch.setattr(
        QInputDialog, "getItem", lambda *a, **k: ("URGENT", True)
    )

    mw_with_tags.selection_helper.checked_rows = {0}  # only line 1 of order 1001 checked
    handler = ActionsHandler(mw_with_tags)

    handler.bulk_remove_tag()

    tags = mw_with_tags.analysis_results_df.set_index("SKU")["Internal_Tags"]
    assert tags.loc["A1"] == "[]"
    assert tags.loc["A2"] == "[]"  # order 1001's other line, not just the checked one
    assert tags.loc["B1"] == '["URGENT"]'  # different order, untouched
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_actions_handler.py -k bulk_add_tag_writes_every_row -v`
Expected: FAIL — `A2` still has `"[]"` (only the representative row `A1` got the tag)

- [ ] **Step 3: Implement**

In `gui/actions_handler.py`, replace the `bulk_add_tag` body from `# Get affected rows BEFORE modification` (line 1614) through the `record_operation` call (line 1660) with:

```python
        # Get affected rows BEFORE modification
        from shopify_tool.tag_manager import add_tag

        selected_indexes = self.mw.selection_helper.get_selected_source_rows()

        # Get unique orders, then mask every row of every selected order
        # (Internal_Tags is order-level -- see tag_manager.expand_to_order_rows)
        selected_df = self.mw.analysis_results_df.loc[selected_indexes]
        unique_orders = selected_df["Order_Number"].unique()
        mask = self.mw.analysis_results_df["Order_Number"].isin(unique_orders)

        # Store affected rows BEFORE modification (every row of every selected order)
        affected_rows_before = self.mw.analysis_results_df[mask].copy()

        # Ensure Internal_Tags column exists
        if "Internal_Tags" not in self.mw.analysis_results_df.columns:
            self.mw.analysis_results_df["Internal_Tags"] = "[]"

        # Apply tag to every row of every selected order
        current_tags = self.mw.analysis_results_df.loc[mask, "Internal_Tags"]
        new_tags = current_tags.apply(lambda t: add_tag(t, tag_value))
        self.mw.analysis_results_df.loc[mask, "Internal_Tags"] = new_tags

        # Record undo operation
        self.mw.undo_manager.record_operation(
            operation_type="bulk_add_tag",
            description=f"Bulk Add Tag: '{tag_value}' to {orders_count} orders",
            params={
                "tag": tag_value,
                "order_numbers": unique_orders.tolist(),
            },
            affected_rows_before=affected_rows_before,
        )
```

Replace the `bulk_remove_tag` body from `# Get affected rows BEFORE modification` (line 1731) through the `record_operation` call (line ~1770, ends just before the `# Update UI` comment) with:

```python
        # Get affected rows BEFORE modification
        selected_indexes = self.mw.selection_helper.get_selected_source_rows()

        # Get unique orders, then mask every row of every selected order
        selected_df_full = self.mw.analysis_results_df.loc[selected_indexes]
        unique_orders = selected_df_full["Order_Number"].unique()
        mask = self.mw.analysis_results_df["Order_Number"].isin(unique_orders)

        # Store affected rows BEFORE modification (every row of every selected order)
        affected_rows_before = self.mw.analysis_results_df[mask].copy()

        # Apply tag removal to every row of every selected order
        current_tags = self.mw.analysis_results_df.loc[mask, "Internal_Tags"]
        new_tags = current_tags.apply(lambda t: remove_tag(t, tag))
        self.mw.analysis_results_df.loc[mask, "Internal_Tags"] = new_tags

        # Record undo operation
        self.mw.undo_manager.record_operation(
            operation_type="bulk_remove_tag",
            description=f"Bulk Remove Tag: '{tag}' from {orders_count} orders",
            params={
                "tag": tag,
                "order_numbers": unique_orders.tolist(),
            },
            affected_rows_before=affected_rows_before,
        )
```

(Both changes drop the `representative_indexes` list and the now-meaningless `affected_indexes` param — it was already unread by the undo handlers, which match by `Order_Number` instead; see Task 3.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_actions_handler.py -v`
Expected: PASS (all tests, including the 3 pre-existing `remove_item_*` tests — unaffected by this change)

- [ ] **Step 5: Lint and commit**

```bash
ruff check gui/actions_handler.py tests/test_actions_handler.py
git add gui/actions_handler.py tests/test_actions_handler.py
git commit -m "Fix bulk_add_tag/bulk_remove_tag to write all rows of an order, not just the first"
```

---

### Task 3: Fix `_undo_bulk_add_tag`/`_undo_bulk_remove_tag` to restore all rows

**Why this task is required:** Task 2 made the bulk write paths apply to every row of an order. Their undo handlers currently restore only `order_rows[0]` (`shopify_tool/undo_manager.py:530-598`, both handlers), because they were written to mirror the old representative-row-only write. Left unfixed, undoing a bulk tag op after Task 2's fix would restore only the first line of a multi-line order and leave the rest of the order's lines incorrectly tagged — a data-corrupting regression, not a pre-existing bug.

**Files:**
- Modify: `shopify_tool/undo_manager.py:530-598` (`_undo_bulk_add_tag`, `_undo_bulk_remove_tag`)
- Test: `tests/test_undo_manager.py`

- [ ] **Step 1: Write the failing test**

The existing `mw` fixture in `tests/test_undo_manager.py` has exactly one row per order, so it can't distinguish "restore first row" from "restore all rows." Add a second fixture with a multi-line order:

```python
@pytest.fixture
def mw_multiline():
    df = pd.DataFrame(
        {
            "Order_Number": ["A", "A", "B"],
            "SKU": ["S1", "S2", "S1"],
            "Internal_Tags": ["[]", "[]", "[]"],
        }
    )
    return SimpleNamespace(
        analysis_results_df=df,
        analysis_stats=None,
        current_client_id="1",
        session_path=None,
    )


def test_undo_bulk_add_tag_restores_every_line_of_a_multiline_order(mw_multiline):
    um = UndoManager(mw_multiline)
    mask = mw_multiline.analysis_results_df["Order_Number"] == "A"
    affected_before = mw_multiline.analysis_results_df[mask].copy()
    mw_multiline.analysis_results_df.loc[mask, "Internal_Tags"] = '["fragile"]'
    um.record_operation(
        "bulk_add_tag", "Bulk add tag", {"order_numbers": ["A"]}, affected_before
    )

    ok, _ = um.undo()

    tags = mw_multiline.analysis_results_df.set_index("SKU")["Internal_Tags"]
    assert ok is True
    assert tags.loc["S1"] == "[]"  # order A, line 1 -- restored
    assert tags.loc["S2"] == "[]"  # order A, line 2 -- must ALSO be restored
    assert tags.loc["S1"] == "[]" or mw_multiline.analysis_results_df.iloc[2]["Internal_Tags"] == "[]"  # order B untouched
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_undo_manager.py::test_undo_bulk_add_tag_restores_every_line_of_a_multiline_order -v`
Expected: FAIL — `tags.loc["S2"]` is still `'["fragile"]'` because only `order_rows[0]` (S1) gets restored.

- [ ] **Step 3: Implement**

In `shopify_tool/undo_manager.py`, replace the loop body in `_undo_bulk_add_tag` (lines 550-556):

```python
            df = self.main_window.analysis_results_df
            restored = 0
            for order_number, group in affected_rows_before.groupby("Order_Number"):
                order_mask = df["Order_Number"] == order_number
                order_rows = df.index[order_mask]
                if not len(order_rows):
                    continue
                if "Internal_Tags" in group.columns:
                    for idx, original_idx in enumerate(order_rows):
                        if idx < len(group):
                            df.loc[original_idx, "Internal_Tags"] = group["Internal_Tags"].iloc[idx]
                restored += 1
```

Apply the identical replacement to `_undo_bulk_remove_tag`'s loop body (lines 585-591) — same code, different surrounding method.

(This mirrors the positional-restore pattern already used by `_undo_add_internal_tag`, lines 317-321, which assumes the same row count/order between snapshot and restore — true here since only column values change, no rows are added or removed between snapshot and undo.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_undo_manager.py -v`
Expected: PASS (all tests, including the pre-existing single-row-per-order tests — unaffected since restoring "all rows" and "the first row" are identical when there's only one row per order)

- [ ] **Step 5: Lint and commit**

```bash
ruff check shopify_tool/undo_manager.py tests/test_undo_manager.py
git add shopify_tool/undo_manager.py tests/test_undo_manager.py
git commit -m "Fix bulk tag undo to restore every row of an order, not just the first"
```

---

### Task 4: Fix right-click "Add tag" to apply to the whole order

**Files:**
- Modify: `gui/main_window_pyside.py:455-465` (`_add_internal_tag`)
- Test: `tests/test_main_window_tags.py` (new)

**Interfaces:**
- Consumes: `tag_manager.expand_to_order_rows(df, mask)` from Task 1.

- [ ] **Step 1: Write the failing test**

Create `tests/test_main_window_tags.py`. Following this codebase's established
convention of never instantiating the real `MainWindow` in tests (see
`tests/test_selection_helper.py`'s `_FakeMainWindow`, `tests/test_actions_handler.py`'s
`SimpleNamespace` fixture) — use a `SimpleNamespace` fake and bind the specific
`MainWindow` methods under test onto it with `types.MethodType`, so the real
method bodies run against a lightweight fake `self` instead of a fully
Qt-constructed window:

```python
"""Regression tests for order-level Internal_Tags consistency in MainWindow.

Internal_Tags is order-level (see shopify_tool.tag_manager.expand_to_order_rows),
but several write/read paths in MainWindow used to operate on a single row
(the clicked SKU line, or whichever line happened to be table-selected)
instead of the whole order. These tests cover the fixed behavior.

Uses a SimpleNamespace fake with the real MainWindow methods bound onto it
(types.MethodType), matching this codebase's established pattern of never
instantiating the real MainWindow in tests (see test_selection_helper.py's
_FakeMainWindow, test_actions_handler.py's SimpleNamespace fixture).
"""
import types
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest

from gui.main_window_pyside import MainWindow


@pytest.fixture
def mw():
    fake = SimpleNamespace(
        analysis_results_df=pd.DataFrame(
            [
                {"Order_Number": "1001", "SKU": "A1", "Internal_Tags": "[]"},
                {"Order_Number": "1001", "SKU": "A2", "Internal_Tags": "[]"},
                {"Order_Number": "1002", "SKU": "B1", "Internal_Tags": "[]"},
            ]
        ),
        undo_manager=Mock(),
        save_session_state=Mock(),
        log_activity=Mock(),
    )
    fake._apply_tag_operation = types.MethodType(MainWindow._apply_tag_operation, fake)
    fake._add_internal_tag = types.MethodType(MainWindow._add_internal_tag, fake)
    return fake


def test_add_internal_tag_from_right_click_tags_every_line_of_the_order(mw):
    mw._add_internal_tag("1001", "A1", "GIFT")

    tags = mw.analysis_results_df.set_index("SKU")["Internal_Tags"]
    assert '"GIFT"' in tags.loc["A1"]  # the clicked line
    assert '"GIFT"' in tags.loc["A2"]  # the order's other line -- must ALSO be tagged
    assert '"GIFT"' not in tags.loc["B1"]  # different order, untouched
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_main_window_tags.py::test_add_internal_tag_from_right_click_tags_every_line_of_the_order -v`
Expected: FAIL — `tags.loc["A2"]` is still `"[]"`

- [ ] **Step 3: Implement**

In `gui/main_window_pyside.py`, replace `_add_internal_tag` (lines 455-465):

```python
    def _add_internal_tag(self, order_number: str, sku: str, tag: str):
        """Add internal tag to the whole order containing the clicked SKU line.

        Internal_Tags is order-level -- the click identifies which order via
        its SKU line, but the tag applies to every row of that order (see
        tag_manager.expand_to_order_rows).
        """
        from shopify_tool.tag_manager import expand_to_order_rows

        clicked_mask = (self.analysis_results_df["Order_Number"] == order_number) & (
            self.analysis_results_df["SKU"] == sku
        )
        mask = expand_to_order_rows(self.analysis_results_df, clicked_mask)
        self._apply_tag_operation(
            mask,
            description=f"Add Internal Tag: {tag} to order {order_number}",
            params={"order_number": order_number, "sku": sku, "tag": tag},
            tag=tag,
        )
```

No change needed to `_apply_tag_operation` or its undo handler (`_undo_add_internal_tag`, `shopify_tool/undo_manager.py:294-330`) — it already restores every row in the mask positionally, so it generalizes correctly to the wider mask automatically.

- [ ] **Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_main_window_tags.py -v`
Expected: PASS

- [ ] **Step 5: Lint and commit**

```bash
ruff check gui/main_window_pyside.py tests/test_main_window_tags.py
git add gui/main_window_pyside.py tests/test_main_window_tags.py
git commit -m "Fix right-click Add Internal Tag to apply to the whole order"
```

---

### Task 5: Fix rule engine `ADD_INTERNAL_TAG` to apply to the whole order

**Files:**
- Modify: `shopify_tool/rules.py:1045-1051`
- Test: `tests/test_rules.py`

**Interfaces:**
- Consumes: `tag_manager.expand_to_order_rows(df, mask)` from Task 1.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_rules.py`, in `TestRulePriorityAndAccumulation` (or as a new test near `test_add_internal_tag_deduplicates_via_tag_manager`):

```python
    def test_add_internal_tag_applies_to_every_line_of_the_matched_order(self):
        # Rule matches only the line with Quantity == 5 (row 0), but
        # Internal_Tags is order-level -- both of order "1001"'s lines must
        # get the tag, not just the matched line.
        df = _df({
            "Order_Number": ["1001", "1001", "1002"],
            "Quantity": [5, 1, 5],
            "Internal_Tags": ["[]", "[]", "[]"],
        })
        rules = [_rule([{"field": "Quantity", "operator": "equals", "value": 5}],
                        [{"type": "ADD_INTERNAL_TAG", "value": "GIFT"}])]
        out = RuleEngine(rules).apply(df.copy())
        assert parse_tags(out.loc[0, "Internal_Tags"]) == ["GIFT"]
        assert parse_tags(out.loc[1, "Internal_Tags"]) == ["GIFT"]  # order 1001's other line
        assert parse_tags(out.loc[2, "Internal_Tags"]) == ["GIFT"]  # order 1002, matched directly
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_rules.py -k add_internal_tag_applies_to_every_line -v`
Expected: FAIL — `out.loc[1, "Internal_Tags"]` (order 1001's unmatched line) is still `"[]"`

- [ ] **Step 3: Implement**

In `shopify_tool/rules.py`, replace the `ADD_INTERNAL_TAG` branch (lines 1045-1051):

```python
            elif action_type == "ADD_INTERNAL_TAG":
                # Internal_Tags is order-level -- expand the rule's line-level
                # match to every row of each matched order before writing
                # (see tag_manager.expand_to_order_rows).
                from shopify_tool.tag_manager import add_tag, expand_to_order_rows

                order_mask = expand_to_order_rows(df, matches)
                current_tags = df.loc[order_mask, "Internal_Tags"]
                new_tags = current_tags.apply(lambda t, value=value: add_tag(t, value))
                df.loc[order_mask, "Internal_Tags"] = new_tags
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_rules.py -v`
Expected: PASS (all tests, including the pre-existing `test_add_internal_tag_deduplicates_via_tag_manager`, which has no `Order_Number` column — see note below)

**Note:** `test_add_internal_tag_deduplicates_via_tag_manager`'s fixture (`_df({"Quantity": [1], "Internal_Tags": ["[]"]})`) has no `Order_Number` column. `expand_to_order_rows` requires one (`df.loc[mask, "Order_Number"]`). Since `ADD_INTERNAL_TAG` only ever runs against `final_df` in production (which always has `Order_Number`), add `"Order_Number": ["X"]` to that fixture's `_df()` call so it keeps passing:

```python
    def test_add_internal_tag_deduplicates_via_tag_manager(self):
        df = _df({"Order_Number": ["X"], "Quantity": [1], "Internal_Tags": ["[]"]})
        ...
```

- [ ] **Step 5: Lint and commit**

```bash
ruff check shopify_tool/rules.py tests/test_rules.py
git add shopify_tool/rules.py tests/test_rules.py
git commit -m "Fix ADD_INTERNAL_TAG rule action to tag the whole order, not just matched lines"
```

---

### Task 6: Fix tag sidebar to show merged tags across an order's rows

**Files:**
- Modify: `gui/main_window_pyside.py:33` (import), `gui/main_window_pyside.py:557-561` (`on_selection_changed_for_tags`)
- Test: `tests/test_main_window_tags.py`

**Interfaces:**
- Consumes: `tag_manager.merge_tags(tags_values: list) -> str` (already exists, `shopify_tool/tag_manager.py:61-82`).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_main_window_tags.py`:

```python
import json
from unittest.mock import MagicMock


def test_selection_changed_shows_merged_tags_across_the_orders_lines(mw):
    mw.on_selection_changed_for_tags = types.MethodType(
        MainWindow.on_selection_changed_for_tags, mw
    )
    mw.analysis_results_df.loc[0, "Internal_Tags"] = '["A"]'  # order 1001, line 1
    mw.analysis_results_df.loc[1, "Internal_Tags"] = '["B"]'  # order 1001, line 2 (different tag)

    mw.tag_management_panel = MagicMock()
    mw.tag_management_panel.isVisible.return_value = True

    # Select row 1 (the line carrying only "B") in the table
    fake_index = MagicMock()
    fake_index.row.return_value = 1
    mw.proxy_model = MagicMock()
    mw.proxy_model.mapToSource.return_value = fake_index
    mw.tableView = MagicMock()
    mw.tableView.selectionModel.return_value.selectedRows.return_value = [MagicMock()]

    mw.on_selection_changed_for_tags()

    order_number, current_tags = mw.tag_management_panel.set_selected_order.call_args[0]
    assert order_number == "1001"
    assert set(json.loads(current_tags)) == {"A", "B"}  # merged, not just line 2's "B"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_main_window_tags.py::test_selection_changed_shows_merged_tags_across_the_orders_lines -v`
Expected: FAIL — `current_tags` is `'["B"]"'` (only the selected row's own value), missing `"A"`

- [ ] **Step 3: Implement**

In `gui/main_window_pyside.py`, change the import at line 33 to also bring in `merge_tags`:

```python
from shopify_tool.tag_manager import _normalize_tag_categories, merge_tags
```

Replace the last 3 lines of `on_selection_changed_for_tags` (lines 557-561):

```python
        # Get order number, then merge Internal_Tags across every row of that
        # order (Internal_Tags is order-level -- a single selected line may
        # not carry the order's full tag set).
        order_number = self.analysis_results_df.iloc[row]["Order_Number"]
        order_mask = self.analysis_results_df["Order_Number"] == order_number
        current_tags = merge_tags(
            self.analysis_results_df.loc[order_mask, "Internal_Tags"].tolist()
        )

        self.tag_management_panel.set_selected_order(order_number, current_tags)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_main_window_tags.py -v`
Expected: PASS

- [ ] **Step 5: Lint and commit**

```bash
ruff check gui/main_window_pyside.py tests/test_main_window_tags.py
git add gui/main_window_pyside.py tests/test_main_window_tags.py
git commit -m "Fix tag sidebar to merge Internal_Tags across an order's rows"
```

---

### Task 7: Forward-fill the `Tags` column per order

**Files:**
- Modify: `shopify_tool/analysis.py:238-247`
- Test: `tests/test_analysis.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_analysis.py` (near the top-level tests, using the existing `_orders`/`_stock`/`_run` helpers):

```python
class TestTagsForwardFill:
    def test_tags_survive_ffill_across_a_multiline_order(self):
        orders = _orders([
            {"Name": "#1", "Lineitem sku": "A1", "Lineitem quantity": 1, "Tags": "vip, fragile"},
            {"Name": "#1", "Lineitem sku": "A2", "Lineitem quantity": 1, "Tags": ""},  # blank, like real Shopify exports
        ])
        stock = _stock([
            {"Артикул": "A1", "Наличност": 10},
            {"Артикул": "A2", "Наличност": 10},
        ])
        final_df, *_ = _run(orders, stock)
        assert (final_df["Tags"] == "vip, fragile").all()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_analysis.py::TestTagsForwardFill -v`
Expected: FAIL — the second line's `Tags` is `""`, not `"vip, fragile"`

- [ ] **Step 3: Implement**

In `shopify_tool/analysis.py`, add to the ffill block (after line 247, the `Subtotal` ffill):

```python
        if "Tags" in orders_df.columns:
            orders_df["Tags"] = orders_df["Tags"].ffill()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_analysis.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Lint and commit**

```bash
ruff check shopify_tool/analysis.py tests/test_analysis.py
git add shopify_tool/analysis.py tests/test_analysis.py
git commit -m "Forward-fill Tags column per order, matching Shopify's export format"
```

---

### Task 8: Fix `Lot_Details` rendering and the multi-lot crash bug

**Files:**
- Modify: `gui/pandas_model.py:165-172` (`data()`), add `_format_lot()` helper
- Test: `tests/test_pandas_model.py` (new)

**Interfaces:**
- Produces: `_format_lot(lot: dict) -> str` (module-private, `gui/pandas_model.py`).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_pandas_model.py`:

```python
"""Regression tests for gui.pandas_model.PandasModel's Lot_Details rendering.

Root cause: Lot_Details cells hold a raw list[dict] (or None), which fell
through to the generic scalar renderer. That renderer's `if pd.isna(value):`
raises ValueError for any list with 2+ elements (pd.isna returns an array,
not a scalar, for list input) -- a live crash for any order with 2+ lots
allocated to one SKU line.
"""
from datetime import date

import pandas as pd
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from gui.pandas_model import PandasModel


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


def _model(lot_details_value):
    df = pd.DataFrame({"SKU": ["A1"], "Lot_Details": [lot_details_value]})
    return PandasModel(df)


def test_empty_lot_details_shows_blank_not_crash():
    model = _model(None)
    index = model.index(0, 1)
    assert model.data(index, Qt.ItemDataRole.DisplayRole) == ""


def test_single_lot_shows_count_and_tooltip_detail():
    lots = [{"expiry": "261230", "expiry_dt": date(2026, 12, 30), "batch": "B1", "qty_allocated": 2.0}]
    model = _model(lots)
    index = model.index(0, 1)
    assert model.data(index, Qt.ItemDataRole.DisplayRole) == "1 lot"
    tooltip = model.data(index, Qt.ItemDataRole.ToolTipRole)
    assert "2026-12-30" in tooltip
    assert "B1" in tooltip


def test_multi_lot_cell_does_not_raise_and_shows_count():
    """Regression test for the pd.isna(list) ValueError crash."""
    lots = [
        {"expiry": "261230", "expiry_dt": date(2026, 12, 30), "batch": "B1", "qty_allocated": 2.0},
        {"expiry": "270101", "expiry_dt": date(2027, 1, 1), "batch": None, "qty_allocated": 1.0},
    ]
    model = _model(lots)
    index = model.index(0, 1)
    assert model.data(index, Qt.ItemDataRole.DisplayRole) == "2 lots"  # must not raise
    tooltip = model.data(index, Qt.ItemDataRole.ToolTipRole)
    assert "2026-12-30" in tooltip and "2027-01-01" in tooltip


def test_unparseable_expiry_shown_in_tooltip_not_hidden():
    lots = [{"expiry": "2805", "expiry_dt": None, "batch": None, "qty_allocated": 1.0}]
    model = _model(lots)
    index = model.index(0, 1)
    tooltip = model.data(index, Qt.ItemDataRole.ToolTipRole)
    assert "unparsed" in tooltip and "2805" in tooltip


def test_plain_scalar_cell_still_renders_and_has_no_tooltip():
    df = pd.DataFrame({"SKU": ["A1"]})
    model = PandasModel(df)
    index = model.index(0, 0)
    assert model.data(index, Qt.ItemDataRole.DisplayRole) == "A1"
    assert model.data(index, Qt.ItemDataRole.ToolTipRole) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_pandas_model.py -v`
Expected: FAIL — `test_multi_lot_cell_does_not_raise_and_shows_count` fails with `ValueError: The truth value of an array with more than one element is ambiguous`; the others fail on missing tooltip support / wrong display text.

- [ ] **Step 3: Implement**

In `gui/pandas_model.py`, add before `class PandasModel(QAbstractTableModel):` (before line 80):

```python
def _format_lot(lot: dict) -> str:
    """Render one Lot_Details entry as a human-readable line for the tooltip."""
    qty = lot.get("qty_allocated", lot.get("qty", 0))
    qty_str = f"{qty:g}" if isinstance(qty, float) else str(qty)
    expiry_dt = lot.get("expiry_dt")
    expiry_str = f"exp {expiry_dt.isoformat()}" if expiry_dt is not None else f"exp unparsed ({lot.get('expiry')!r})"
    batch = lot.get("batch")
    batch_str = f", Batch {batch}" if batch else ""
    return f"{qty_str}x, {expiry_str}{batch_str}"
```

Replace the `DisplayRole` branch in `data()` (lines 165-172):

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

            if role == Qt.ItemDataRole.ToolTipRole:
                return None  # no tooltip for plain scalar cells

            if pd.isna(value):
                return ""
            return str(value)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_pandas_model.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Lint and commit**

```bash
ruff check gui/pandas_model.py tests/test_pandas_model.py
git add gui/pandas_model.py tests/test_pandas_model.py
git commit -m "Fix Lot_Details crash on multi-lot cells, add badge+tooltip rendering"
```

---

### Task 9: Extend expiry parsing (DDMMYY, MMYY) and carry `expiry_dt` through allocation

**Files:**
- Modify: `shopify_tool/analysis.py:17-46` (`_parse_expiry_date`), `shopify_tool/analysis.py:650-656` (`simulate_stock_allocation`'s `sku_alloc.append`)
- Test: `tests/test_analysis.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_analysis.py`:

```python
class TestParseExpiryDate:
    """_parse_expiry_date tries YYMMDD, then DDMMYY (6-digit), YYYYMMDD
    (8-digit), MMYY (4-digit) in that priority order, keeping the first
    calendar-valid candidate. See the ponytail comment on the function for
    why priority order (not per-client config) resolves 6-digit ambiguity."""

    def test_yymmdd_6_digit(self):
        assert analysis._parse_expiry_date("261230") == date(2026, 12, 30)

    def test_yyyymmdd_8_digit(self):
        assert analysis._parse_expiry_date("20270131") == date(2027, 1, 31)

    def test_ddmmyy_used_when_yymmdd_is_calendar_invalid(self):
        # As YYMMDD: yy=31, mm=12, dd=99 -> invalid (day 99).
        # As DDMMYY: dd=31, mm=12, yy=99 -> valid: 2099-12-31.
        assert analysis._parse_expiry_date("311299") == date(2099, 12, 31)

    def test_mmyy_4_digit_defaults_to_day_1(self):
        assert analysis._parse_expiry_date("0528") == date(2028, 5, 1)

    def test_ambiguous_6_digit_prefers_yymmdd(self, caplog):
        # Valid as both YYMMDD (2026-12-30) and DDMMYY (2030-12-26) -- priority picks YYMMDD.
        with caplog.at_level("WARNING", logger="shopify_tool.analysis"):
            result = analysis._parse_expiry_date("261230")
        assert result == date(2026, 12, 30)
        assert any("Ambiguous expiry" in r.message for r in caplog.records)

    def test_unparseable_value_returns_none_and_logs_warning(self, caplog):
        with caplog.at_level("WARNING", logger="shopify_tool.analysis"):
            result = analysis._parse_expiry_date("2805")  # month 28 invalid under MMYY too
        assert result is None
        assert any("Could not parse expiry date" in r.message for r in caplog.records)

    def test_sentinel_and_none_and_blank(self):
        assert analysis._parse_expiry_date("1") is None
        assert analysis._parse_expiry_date(None) is None
        assert analysis._parse_expiry_date("") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_analysis.py::TestParseExpiryDate -v`
Expected: FAIL — `test_ddmmyy_used_when_yymmdd_is_calendar_invalid` and `test_mmyy_4_digit_defaults_to_day_1` fail (current code returns `None` for both; the ambiguous test fails because `debug`-level logging isn't captured/asserted as `WARNING`)

- [ ] **Step 3: Implement**

Replace `_parse_expiry_date` in `shopify_tool/analysis.py` (lines 17-46):

```python
def _parse_expiry_date(raw) -> date | None:
    """Parse a raw expiry string from the stock CSV to a comparable date object.

    Tries candidate formats in priority order, keeping the first
    calendar-valid one:
    - "1" or None or NaN or "" -> None  (sentinel for "no expiry info")
    - 6-digit: YYMMDD, then DDMMYY
    - 8-digit: YYYYMMDD
    - 4-digit: MMYY (day defaults to 1)
    - No valid candidate -> None (logged as a warning)

    If more than one candidate format is calendar-valid for the same raw
    value (e.g. "261230" is valid as both YYMMDD and DDMMYY), this is logged
    as ambiguous and the higher-priority format's result is used.

    ponytail: format priority is a heuristic, not a guaranteed-correct
    disambiguation for 6-digit values valid under more than one format --
    add a per-client date-format setting if that turns out to be common in
    practice.
    """
    if raw is None:
        return None
    try:
        if isinstance(raw, float) and math.isnan(raw):
            return None
    except (TypeError, ValueError):
        pass
    s = str(raw).strip()
    if not s or s == "1":
        return None

    if len(s) == 6:
        candidate_specs = [("YYMMDD", s[0:2], s[2:4], s[4:6]), ("DDMMYY", s[4:6], s[2:4], s[0:2])]
    elif len(s) == 8:
        candidate_specs = [("YYYYMMDD", s[0:4], s[4:6], s[6:8])]
    elif len(s) == 4:
        candidate_specs = [("MMYY", s[2:4], s[0:2], "01")]
    else:
        candidate_specs = []

    valid: list[tuple[str, date]] = []
    for fmt, y_s, m_s, d_s in candidate_specs:
        try:
            year = int(y_s) if len(y_s) == 4 else 2000 + int(y_s)
            valid.append((fmt, date(year, int(m_s), int(d_s))))
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

Then, in `simulate_stock_allocation`, add `expiry_dt` to the allocation record (lines 650-656):

```python
                        if take > 0:
                            sku_alloc.append(
                                {
                                    "expiry": lot["expiry"],
                                    "expiry_dt": lot["expiry_dt"],
                                    "batch": lot["batch"],
                                    "qty_allocated": take,
                                }
                            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_analysis.py -v`
Expected: PASS (all tests, including the pre-existing `TestFifoLotAllocation` tests — they only assert on the raw `expiry`/`qty_allocated` keys, unaffected by adding `expiry_dt`)

- [ ] **Step 5: Lint and commit**

```bash
ruff check shopify_tool/analysis.py tests/test_analysis.py
git add shopify_tool/analysis.py tests/test_analysis.py
git commit -m "Extend expiry parsing to DDMMYY/MMYY, carry expiry_dt through allocation"
```

---

### Task 10: Isolate Tag Categories dialog edits from the live config

**Files:**
- Modify: `gui/tag_categories_dialog.py:1-9` (imports), `gui/tag_categories_dialog.py:56` (`TagCategoriesPanel.__init__`)
- Test: `tests/test_tag_categories_dialog.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_tag_categories_dialog.py`:

```python
"""Regression test: TagCategoriesPanel must not mutate the live config dict
it's constructed with -- edits should only reach the caller via the
categories_updated signal on Save/Apply. Root cause: __init__ did a shallow
.copy(), so working_categories["categories"] was the same nested dict object
as the caller's live config; deleting/editing a category mutated it
immediately, and Cancel never restored it.
"""
import pytest
from PySide6.QtWidgets import QApplication

from gui.tag_categories_dialog import TagCategoriesPanel


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


def test_deleting_a_category_does_not_mutate_the_caller_s_dict():
    live_config = {
        "version": 2,
        "categories": {
            "packaging": {"label": "Packaging", "color": "#FF0000", "tags": ["BOX", "BAG"], "order": 1},
        },
    }
    panel = TagCategoriesPanel(live_config)

    panel.working_categories["categories"].pop("packaging")

    assert "packaging" in live_config["categories"]  # caller's dict untouched
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_tag_categories_dialog.py -v`
Expected: FAIL — `"packaging" in live_config["categories"]` is `False` because `working_categories["categories"]` is the same dict object

- [ ] **Step 3: Implement**

In `gui/tag_categories_dialog.py`, add `import copy` to the imports (top of file, after `import logging` at line 7):

```python
import copy
import logging
```

Change line 56:

```python
        self.working_categories = copy.deepcopy(tag_categories)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_tag_categories_dialog.py -v`
Expected: PASS

- [ ] **Step 5: Lint and commit**

```bash
ruff check gui/tag_categories_dialog.py tests/test_tag_categories_dialog.py
git add gui/tag_categories_dialog.py tests/test_tag_categories_dialog.py
git commit -m "Deep-copy tag_categories in TagCategoriesPanel so Cancel is a true no-op"
```

---

## Final Verification

After all 10 tasks:

- [ ] Run the full suite: `QT_QPA_PLATFORM=offscreen python -m pytest -v` — expect all green.
- [ ] Run the full lint: `ruff check . --exclude shared` — expect no errors.
- [ ] Manually smoke-test in the app (per `run` skill / `python run_dev.py`): bulk-tag a multi-line order, right-click-tag a multi-line order, verify Lot_Details shows a badge + hover tooltip on a multi-lot order, open Tag Categories, delete a category, hit Cancel, reopen and confirm it's still there.
- [ ] `graphify update .` (per this repo's `CLAUDE.md` — stale graph gives wrong answers about this codebase's structure).
