# Phase 9 Bundle 14 — Selection, bulk actions and the toast, implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the results document a selection bar, one bulk popover in place of
five blocking dialog chains, and a toast that lives inside the page — restoring
seven bulk verbs that have had no entry point since Bundle 12.

**Architecture:** The page owns the gesture and the copy; Python owns the write.
Ten new bridge members carry the selection and the verb across; every existing
`actions_handler` bulk handler keeps its body and its undo record but loses its
dialogs and gains arguments. One new web file, `gui/web/bulk.js`, holds the bar,
the menu, the popover and the toast.

**Tech Stack:** PySide6 (`QWebChannel`, `QWebEngineView`), vanilla ES2020 (no
build step, no framework, no dependency), pandas, pytest with
`QT_QPA_PLATFORM=offscreen`.

**Spec:** `docs/superpowers/specs/2026-09-14-phase9-bundle14-selection-bulk-design.md`
— read it before Task 1 and keep it open. The plan argues from it and does not
repeat its reasoning.

## Global Constraints

- **Never hand-edit `shared/`.** It is synced one-way from `../packing-tool`.
  Nothing in this bundle needs to change there.
- **No hardcoded colours anywhere**, Python or CSS. Use the theme tokens
  (`var(--status-danger)`, `var(--text-secondary)`, …). `shared/style_lint.py`
  fails the build on a literal.
- **Banned in web assets** by that same linter: `box-shadow`, `transition`,
  `transform`, `scale`, `rotate`, `translate`, `opacity`. Separate surfaces
  with `--surface-overlay` plus a 1px `--border`, never a shadow.
- **`gui/web/bulk.js` loads before `results.js`.** Reference `el`, `svg`,
  `num`, `str`, `fmtMoney`, `fmtInt`, `NUMBER`, `courierOf`, `state` and `els`
  **only inside function bodies** — naming one at top level, including inside
  an object literal evaluated at load, crashes the page at load time. This bit
  Bundle 13 twice.
- **`QVariantMap` reaches JS with alphabetically sorted keys.** Never compare
  a bridge dict to a local literal with `JSON.stringify`; compare positionally.
- **`runJavaScript`'s callback marshals JS `null`/`undefined` to Python `''`,
  never `None`** on this VM's Qt build. Assert `== ""`. Prove an element is
  absent with `document.querySelectorAll(sel).length === 0`.
- **`undo_manager` params are frozen.** Every `record_operation` call keeps its
  existing `operation_type` and `params` keys exactly. Histories already on
  disk are read with them.
- **Run the suite as** `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest`.
  Lint with `.venv/bin/python -m ruff check . --exclude shared`.
- **Commit after every task.** Branch `worktree-phase9-bundle14-selection-bulk`;
  never commit to `main`.
- A write hook reformats any Python file an edit touches with `ruff format`.
  Do not fight it, and do not add an import before the code that uses it —
  the hook strips it.

---

### Task 1: The bridge's ten new members

**Files:**
- Modify: `gui/results_bridge.py`
- Test: `tests/test_results_bridge_bulk.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: on `ResultsBridge` — slots `setStatus(list, bool)`,
  `addTag(list, str)`, `removeTag(list, str)`, `excludeOrders(list)`,
  `removeSkuFromOrders(list, str)`, `removeOrdersWithSku(list, str)`,
  `exportSelection(list, str)`, `undo()`; signals
  `bulkStatusRequested(list, bool)`, `bulkTagAddRequested(list, str)`,
  `bulkTagRemovalRequested(list, str)`, `bulkExcludeRequested(list)`,
  `bulkSkuRemovalRequested(list, str)`, `bulkOrderRemovalRequested(list, str)`,
  `bulkExportRequested(list, str)`, `undoRequested()`,
  `toastRaised(str, bool)`; property `undoAvailable: bool` with
  `undoAvailableChanged`; Python-facing `set_undo_available(bool)` and
  `raise_toast(str, undoable=False)`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_results_bridge_bulk.py`:

```python
"""Bundle 14's bridge members: every bulk verb and the toast."""

import pytest

from gui.results_bridge import ResultsBridge


@pytest.fixture
def bridge(qtbot):
    return ResultsBridge()


def _capture(signal):
    seen = []
    signal.connect(lambda *args: seen.append(args))
    return seen


def test_set_status_carries_the_orders_and_the_flag(bridge):
    seen = _capture(bridge.bulkStatusRequested)
    bridge.setStatus(["10443", 10444], True)
    assert seen == [(["10443", "10444"], True)]


def test_add_tag_carries_orders_and_tag(bridge):
    seen = _capture(bridge.bulkTagAddRequested)
    bridge.addTag(["10443"], "FRAGILE")
    assert seen == [(["10443"], "FRAGILE")]


def test_remove_tag_carries_orders_and_tag(bridge):
    seen = _capture(bridge.bulkTagRemovalRequested)
    bridge.removeTag(["10443"], "FRAGILE")
    assert seen == [(["10443"], "FRAGILE")]


def test_exclude_orders_carries_the_orders(bridge):
    seen = _capture(bridge.bulkExcludeRequested)
    bridge.excludeOrders(["10443", "10444"])
    assert seen == [(["10443", "10444"],)]


def test_sku_removals_carry_orders_and_sku(bridge):
    lines = _capture(bridge.bulkSkuRemovalRequested)
    orders = _capture(bridge.bulkOrderRemovalRequested)
    bridge.removeSkuFromOrders(["10443"], "TS-4409-B")
    bridge.removeOrdersWithSku(["10443"], "TS-4409-B")
    assert lines == [(["10443"], "TS-4409-B")]
    assert orders == [(["10443"], "TS-4409-B")]


@pytest.mark.parametrize("fmt", ["xlsx", "csv"])
def test_export_selection_passes_a_known_format(bridge, fmt):
    seen = _capture(bridge.bulkExportRequested)
    bridge.exportSelection(["10443"], fmt)
    assert seen == [(["10443"], fmt)]


def test_export_selection_drops_an_unknown_format(bridge):
    seen = _capture(bridge.bulkExportRequested)
    bridge.exportSelection(["10443"], "pdf")
    assert seen == []


def test_undo_is_a_bare_signal(bridge):
    seen = _capture(bridge.undoRequested)
    bridge.undo()
    assert seen == [()]


def test_undo_available_notifies_only_on_change(bridge):
    seen = _capture(bridge.undoAvailableChanged)
    assert bridge.undoAvailable is False
    bridge.set_undo_available(True)
    bridge.set_undo_available(True)
    assert bridge.undoAvailable is True
    assert len(seen) == 1


def test_raise_toast_emits_text_and_undoability(bridge):
    seen = _capture(bridge.toastRaised)
    bridge.raise_toast("3 orders held")
    bridge.raise_toast("FRAGILE added to 28 orders", undoable=True)
    assert seen == [("3 orders held", False), ("FRAGILE added to 28 orders", True)]
```

- [ ] **Step 2: Run it and watch it fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_results_bridge_bulk.py -q`
Expected: every test errors with `AttributeError: 'ResultsBridge' object has no attribute 'setStatus'` or similar.

- [ ] **Step 3: Add the members**

In `gui/results_bridge.py`, beside the Bundle 13 signals, add:

```python
    undoAvailableChanged = Signal()
    # JS-facing: the page draws its own toast, because a Qt child widget
    # cannot paint above this view's surface (ADR 0007).
    toastRaised = Signal(str, bool)
    # Python-facing (Bundle 14): the selection bar's verbs. Named bulk* so
    # nothing collides with Bundle 13's singular pane signals.
    bulkStatusRequested = Signal(list, bool)
    bulkTagAddRequested = Signal(list, str)
    bulkTagRemovalRequested = Signal(list, str)
    bulkExcludeRequested = Signal(list)
    bulkSkuRemovalRequested = Signal(list, str)
    bulkOrderRemovalRequested = Signal(list, str)
    bulkExportRequested = Signal(list, str)
    undoRequested = Signal()
```

In `__init__`, add `self._undo_available = False`.

Beside the other out-properties:

```python
    def _get_undo_available(self) -> bool:
        return self._undo_available

    undoAvailable = Property(
        bool, _get_undo_available, notify=undoAvailableChanged
    )
```

Beside the other in-slots:

```python
    EXPORT_FORMATS = ("xlsx", "csv")

    @Slot("QVariantList", bool)
    def setStatus(self, order_numbers, fulfillable) -> None:
        self.bulkStatusRequested.emit(_orders(order_numbers), bool(fulfillable))

    @Slot("QVariantList", str)
    def addTag(self, order_numbers, tag) -> None:
        self.bulkTagAddRequested.emit(_orders(order_numbers), str(tag))

    @Slot("QVariantList", str)
    def removeTag(self, order_numbers, tag) -> None:
        self.bulkTagRemovalRequested.emit(_orders(order_numbers), str(tag))

    @Slot("QVariantList")
    def excludeOrders(self, order_numbers) -> None:
        self.bulkExcludeRequested.emit(_orders(order_numbers))

    @Slot("QVariantList", str)
    def removeSkuFromOrders(self, order_numbers, sku) -> None:
        self.bulkSkuRemovalRequested.emit(_orders(order_numbers), str(sku))

    @Slot("QVariantList", str)
    def removeOrdersWithSku(self, order_numbers, sku) -> None:
        self.bulkOrderRemovalRequested.emit(_orders(order_numbers), str(sku))

    @Slot("QVariantList", str)
    def exportSelection(self, order_numbers, fmt) -> None:
        # A format, not a verb: §5.1's ban is on a string that selects
        # behaviour, and an unknown one is dropped rather than guessed.
        if str(fmt) not in self.EXPORT_FORMATS:
            return
        self.bulkExportRequested.emit(_orders(order_numbers), str(fmt))

    @Slot()
    def undo(self) -> None:
        self.undoRequested.emit()
```

Beside the other Python-facing methods:

```python
    def set_undo_available(self, available: bool) -> None:
        available = bool(available)
        if available == self._undo_available:
            return
        self._undo_available = available
        self.undoAvailableChanged.emit()

    def raise_toast(self, message: str, undoable: bool = False) -> None:
        self.toastRaised.emit(str(message), bool(undoable))
```

And at module level, beside `normalize_column_settings`:

```python
def _orders(raw) -> list[str]:
    """Order numbers as JS sent them, made str and deduplicated in order."""
    return list(dict.fromkeys(str(n) for n in (raw or [])))
```

- [ ] **Step 4: Run it and watch it pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_results_bridge_bulk.py -q`
Expected: 11 passed.

- [ ] **Step 5: Record the catalogue amendment**

The catalogue in
`docs/superpowers/specs/2026-09-11-phase9-bundle11-seam-design.md` § 5.2 must
name every member before it exists. Append these four rows under the Bundle 14
block, matching the table's existing format:

```markdown
| in | `setStatus(orderNumbers: list[str], fulfillable: bool)` | slot | 14 (9.17) — added by Bundle 14 §8.1; the catalogue named no bulk status verb |
| in | `removeSkuFromOrders(orderNumbers: list[str], sku: str)` | slot | 14 (9.17) — added by Bundle 14 §8.1, restored by the owner |
| in | `removeOrdersWithSku(orderNumbers: list[str], sku: str)` | slot | 14 (9.17) — added by Bundle 14 §8.1, restored by the owner |
| in | `exportSelection(orderNumbers: list[str], fmt: str)` | slot | 14 (9.17) — added by Bundle 14 §8.1; `fmt` is `"xlsx"` or `"csv"`, validated Python-side |
```

- [ ] **Step 6: Commit**

```bash
git add gui/results_bridge.py tests/test_results_bridge_bulk.py docs/superpowers/specs/2026-09-11-phase9-bundle11-seam-design.md
git commit -m "Bundle 14: the bridge's bulk verbs, undoAvailable and toastRaised"
```

---

### Task 2: The Python verbs lose their dialogs and gain their arguments

**Files:**
- Modify: `gui/actions_handler.py` (`bulk_change_status` ~1488, `bulk_add_tag`
  ~1550, `bulk_remove_tag` ~1665, `bulk_remove_sku_from_orders` ~1761,
  `bulk_remove_orders_with_sku` ~1841, `bulk_delete_orders` ~1933,
  `bulk_export_selection` ~2070, `add_tag_manually` ~991)
- Test: `tests/test_actions_handler_bulk.py` (create)

**Interfaces:**
- Consumes: `ResultsBridge.raise_toast` from Task 1.
- Produces: `ActionsHandler.bulk_change_status(order_numbers: list[str],
  fulfillable: bool)`, `bulk_add_tag(order_numbers, tag)`,
  `bulk_remove_tag(order_numbers, tag)`,
  `bulk_remove_sku_from_orders(order_numbers, sku)`,
  `bulk_remove_orders_with_sku(order_numbers, sku)`,
  `bulk_delete_orders(order_numbers)`,
  `bulk_export_selection(order_numbers, format_type)`, and
  `_results_toast(text: str, undoable: bool = False)`. `add_tag_manually` no
  longer exists.

**How to rewrite each handler.** Read the existing body first. Keep, unchanged:
the `selection_helper` lookups that gather the frame slice, the
`affected_rows_before` capture, the write, the `undo_manager.record_operation`
call **with its existing `operation_type` and `params` keys**,
`save_session_state()`, `_update_all_views()`, `_populate_tag_filter()` where
present, `log_activity`, and `_update_undo_button()`. Delete: the
`QMessageBox.warning` no-selection guard, the `QInputDialog` chain, the
`QMessageBox.question` confirm, the `QMessageBox.information` success box.
Add: `self._set_selection(order_numbers)` as the first line, and one
`self._results_toast(...)` at the end.

The three destructive verbs (`bulk_delete_orders`,
`bulk_remove_sku_from_orders`, `bulk_remove_orders_with_sku`) keep a confirm,
but as `ConfirmDialog.ask(...)` rather than `QMessageBox.question`, with the
copy from spec § 5.3.

- [ ] **Step 1: Write the failing test**

Create `tests/test_actions_handler_bulk.py`. The fixture builds a real
`ActionsHandler` against a stub main window — follow the pattern in
`tests/test_actions_handler.py` for constructing it, reusing that file's
fixtures where they fit rather than inventing new ones.

```python
"""Bundle 14: the bulk verbs, once the dialogs are gone."""

from pathlib import Path

import pandas as pd
import pytest

import gui.actions_handler as actions_handler_module


def test_no_input_dialog_survives_in_actions_handler():
    source = Path("gui/actions_handler.py").read_text(encoding="utf-8")
    assert "QInputDialog" not in source
    assert "Please select orders first" not in source


def test_bulk_change_status_writes_from_its_arguments(handler, mw):
    handler.bulk_change_status(["10443", "10444"], False)
    written = mw.analysis_results_df.loc[
        mw.analysis_results_df["Order_Number"].isin(["10443", "10444"]),
        "Order_Fulfillment_Status",
    ]
    assert set(written) == {"Not Fulfillable"}


def test_bulk_change_status_records_undo_with_the_frozen_params(handler, mw):
    handler.bulk_change_status(["10443"], True)
    call = mw.undo_manager.record_operation.call_args.kwargs
    assert call["operation_type"] == "bulk_change_status"
    assert set(call["params"]) == {"is_fulfillable", "affected_indexes"}


def test_bulk_change_status_toasts_with_undo(handler, mw):
    handler.bulk_change_status(["10443", "10444"], True)
    mw.results_bridge.raise_toast.assert_called_once_with(
        "2 orders marked fulfillable", undoable=True
    )


def test_bulk_add_tag_skips_orders_that_already_carry_it(handler, mw):
    handler.bulk_add_tag(["10443", "10444"], "FRAGILE")
    handler.bulk_add_tag(["10443", "10444"], "FRAGILE")
    tags = mw.analysis_results_df.loc[
        mw.analysis_results_df["Order_Number"] == "10443", "Internal_Tags"
    ].iloc[0]
    assert tags.count("FRAGILE") == 1


def test_bulk_delete_orders_confirms_before_it_writes(handler, mw, monkeypatch):
    asked = {}

    def fake_ask(parent, *, title, body, verb):
        asked.update(title=title, verb=verb)
        return False

    monkeypatch.setattr(actions_handler_module.ConfirmDialog, "ask", fake_ask)
    before = len(mw.analysis_results_df)
    handler.bulk_delete_orders(["10443"])
    assert asked["title"] == "Exclude 1 order from the run?"
    assert asked["verb"] == "Exclude 1 order"
    assert len(mw.analysis_results_df) == before


def test_bulk_delete_orders_writes_when_confirmed(handler, mw, monkeypatch):
    monkeypatch.setattr(
        actions_handler_module.ConfirmDialog,
        "ask",
        lambda parent, **kw: True,
    )
    handler.bulk_delete_orders(["10443"])
    assert "10443" not in set(mw.analysis_results_df["Order_Number"])
    mw.results_bridge.raise_toast.assert_called_once_with(
        "1 order excluded from the run", undoable=True
    )
```

Write the same four-part shape (`writes from arguments`, `records undo`,
`toasts`, `confirms when destructive`) for `bulk_remove_tag`,
`bulk_remove_sku_from_orders`, `bulk_remove_orders_with_sku` and
`bulk_export_selection`, using the toast strings in spec § 6. For
`bulk_export_selection`, monkeypatch `QFileDialog.getSaveFileName` to return
`(str(tmp_path / "s.csv"), "")` and assert the file exists and the toast names
it.

- [ ] **Step 2: Run it and watch it fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_actions_handler_bulk.py -q`
Expected: `test_no_input_dialog_survives_in_actions_handler` fails on the
assertion; the rest fail on `TypeError: bulk_change_status() takes 2 positional
arguments but 3 were given`.

- [ ] **Step 3: Add the two helpers**

In `gui/actions_handler.py`, beside `_order_mask`:

```python
    def _set_selection(self, order_numbers) -> None:
        """Act on exactly the orders the page counted, not on ambient state."""
        self.mw.selection_helper.set_selected_orders([str(n) for n in order_numbers])

    def _results_toast(self, text: str, undoable: bool = False) -> None:
        """The Results screen's toast lives in the document (ADR 0007)."""
        bridge = getattr(self.mw, "results_bridge", None)
        if bridge is not None:
            bridge.raise_toast(text, undoable=undoable)
```

Import `ConfirmDialog` at the top: `from gui.components import ConfirmDialog,
show_error, toast` — check `gui/components/__init__.py` exports it, and add it
to `__all__` there if it does not.

- [ ] **Step 4: Rewrite the seven handlers and delete `add_tag_manually`**

Work one handler at a time, running its tests after each. Delete
`add_tag_manually` entirely, then remove `QInputDialog` from the
`PySide6.QtWidgets` import line at the top of the file. `QMessageBox` stays
only if another surviving method still uses it — grep before removing it.

For the singular/plural in every toast and confirm, use the existing helper if
one is already in the file; otherwise add:

```python
def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"
```

- [ ] **Step 5: Run the whole file and watch it pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_actions_handler_bulk.py tests/test_actions_handler.py -q`
Expected: all pass. If a pre-existing test in `test_actions_handler.py` calls
one of these verbs with no arguments, update it — the signature change is the
point of this task.

- [ ] **Step 6: Commit**

```bash
git add gui/actions_handler.py gui/components/__init__.py tests/test_actions_handler_bulk.py tests/test_actions_handler.py
git commit -m "Bundle 14: the bulk verbs take arguments and raise no dialogs"
```

---

### Task 3: Wire the verbs to the bridge, and push `undoAvailable`

**Files:**
- Modify: `gui/ui_manager.py:620-650` (beside Bundle 13's connections)
- Modify: `gui/actions_handler.py` (`_update_undo_button`)
- Test: `tests/test_results_bridge_bulk.py` (extend)

**Interfaces:**
- Consumes: Task 1's signals, Task 2's handler signatures.
- Produces: nothing new; the seam is closed after this task.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_results_bridge_bulk.py`:

```python
def test_update_undo_button_pushes_availability_to_the_page(handler, mw):
    mw.undo_manager.can_undo.return_value = True
    handler._update_undo_button()
    mw.results_bridge.set_undo_available.assert_called_with(True)
```

Reuse the `handler` / `mw` fixtures from Task 2 by moving them into
`tests/conftest.py` if they are not already shared.

- [ ] **Step 2: Run it and watch it fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_results_bridge_bulk.py -q`
Expected: `AssertionError: Expected call not found`.

- [ ] **Step 3: Add the connections and the push**

In `gui/ui_manager.py`, directly after the Bundle 13 block that ends with
`bridge.columnSettingsChanged.connect(...)`:

```python
        # Bundle 14: the selection bar's verbs. The page sends the order list
        # it counted, so the set written is the set the button named.
        def bulk(name):
            def run(order_numbers, *args):
                handler = actions()
                handler._set_selection(order_numbers)
                getattr(handler, name)(order_numbers, *args)

            return run

        bridge.bulkStatusRequested.connect(bulk("bulk_change_status"))
        bridge.bulkTagAddRequested.connect(bulk("bulk_add_tag"))
        bridge.bulkTagRemovalRequested.connect(bulk("bulk_remove_tag"))
        bridge.bulkExcludeRequested.connect(bulk("bulk_delete_orders"))
        bridge.bulkSkuRemovalRequested.connect(bulk("bulk_remove_sku_from_orders"))
        bridge.bulkOrderRemovalRequested.connect(bulk("bulk_remove_orders_with_sku"))
        bridge.bulkExportRequested.connect(bulk("bulk_export_selection"))
        bridge.undoRequested.connect(lambda: actions().undo_last_operation())
```

Check `undo_last_operation`'s real name in `actions_handler.py` before wiring
it — use whatever the rail's Undo button already calls.

In `actions_handler._update_undo_button`, add as its last line:

```python
        bridge = getattr(self.mw, "results_bridge", None)
        if bridge is not None:
            bridge.set_undo_available(self.mw.undo_manager.can_undo())
```

- [ ] **Step 4: Run it and watch it pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_results_bridge_bulk.py tests/test_ui_manager.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add gui/ui_manager.py gui/actions_handler.py tests/
git commit -m "Bundle 14: the bulk verbs reach the page"
```

---

### Task 4: The selection bar

**Files:**
- Modify: `gui/web/results.html` (inside `.table-wrap`, above `#table`)
- Create: `gui/web/bulk.js`
- Modify: `gui/web/results.css`
- Modify: `gui/web/results.js` (`els` lookup, `render()`, `layout()`, `renderExport()`)
- Test: `tests/test_results_selection_bar.py` (create)

**Interfaces:**
- Consumes: nothing from earlier tasks — this is page-only.
- Produces: in `bulk.js` — `renderSelectionBar()`, `selectionSummary()`
  returning `{orders, units, value, couriers}`, `selectedOrders()` returning
  the selected order objects in view order, `clearSelection()`, and the
  constant `SELECTION_BAR_PX = 44`. `results.js` calls `renderSelectionBar()`
  from `render()`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_results_selection_bar.py`, driving a real page the way
`tests/test_results_pane.py` does — copy that file's fixture and its
`_text()` / `_eval()` helpers rather than writing new ones.

```python
"""Bundle 14: the bar that exists only while orders are selected."""


def test_the_bar_is_absent_with_no_selection(page):
    assert _eval(page, "document.getElementById('selection-bar').hidden") is True


def test_the_bar_counts_orders_and_units(page):
    _select(page, ["10443", "10444", "10445"])
    assert _text(page, "#selection-count") == "3 orders · 19 units selected"


def test_one_order_reads_singular_and_the_verbs_drop_their_count(page):
    _select(page, ["10443"])
    assert _text(page, "#selection-count") == "1 order · 7 units selected"
    assert _text(page, "#selection-mark") == "Mark fulfillable"
    assert _text(page, "#selection-hold") == "Hold"


def test_the_verbs_carry_the_count_above_one(page):
    _select(page, ["10443", "10444"])
    assert _text(page, "#selection-mark") == "Mark 2 fulfillable"
    assert _text(page, "#selection-hold") == "Hold these 2"


def test_the_sub_line_counts_value_and_couriers(page):
    _select(page, ["10443", "10444"])
    assert _text(page, "#selection-sub") == "334.60 · 2 couriers"


def test_export_drops_to_secondary_while_the_bar_is_up(page):
    _select(page, ["10443"])
    assert "secondary" in _eval(page, "document.getElementById('export').className")
    _eval(page, "document.getElementById('selection-clear').click()")
    assert "primary" in _eval(page, "document.getElementById('export').className")


def test_the_bar_takes_its_height_from_the_table(page):
    before = int(_eval(page, "document.getElementById('table').dataset.visibleRows"))
    _select(page, ["10443"])
    after = int(_eval(page, "document.getElementById('table').dataset.visibleRows"))
    assert before - after == 2


def test_mounting_the_bar_does_not_move_focus(page):
    _eval(page, "document.getElementById('search').focus()")
    _select(page, ["10443"])
    assert _eval(page, "document.activeElement.id") == "search"


def test_clear_empties_the_selection_and_hides_the_bar(page):
    _select(page, ["10443"])
    _eval(page, "document.getElementById('selection-clear').click()")
    assert _eval(page, "document.getElementById('selection-bar').hidden") is True
```

`_select` sets `state.selected` and re-renders:

```python
def _select(page, order_numbers):
    keys = ", ".join(repr(str(n)) for n in order_numbers)
    _eval(page, f"state.selected = new Set([{keys}]); render();")
```

Pin the fixture's order payload so `19 units`, `334.60` and `2 couriers` are
the true numbers for those three orders — build it explicitly in the fixture
rather than reusing a shared one whose values may move.

- [ ] **Step 2: Run it and watch it fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_results_selection_bar.py -q`
Expected: every test fails — `#selection-bar` does not exist.

- [ ] **Step 3: Add the markup**

In `gui/web/results.html`, inside `.table-wrap`, immediately above
`<div id="table" …>`:

```html
      <div id="selection-bar" class="selection-bar" role="toolbar"
           aria-label="Actions for the selected orders" hidden>
        <div class="selection-counts">
          <span id="selection-count" class="selection-count" aria-live="polite"></span>
          <span id="selection-sub" class="selection-sub"></span>
        </div>
        <span class="spacer"></span>
        <button id="selection-mark" class="btn primary" type="button"></button>
        <button id="selection-hold" class="btn secondary" type="button"></button>
        <div class="menu-anchor">
          <button id="selection-more" class="btn ghost" type="button"
                  aria-haspopup="menu" aria-expanded="false">More</button>
          <div id="selection-menu" class="menu" role="menu" hidden></div>
        </div>
        <span class="selection-separator" role="presentation"></span>
        <button id="selection-exclude" class="btn danger" type="button">Exclude from run</button>
        <button id="selection-clear" class="btn ghost" type="button">Clear</button>
      </div>
```

And add `<script src="bulk.js" defer></script>` between the `pane.js` and
`results.js` script tags.

- [ ] **Step 4: Add the CSS**

In `gui/web/results.css`:

```css
.selection-bar {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  height: 44px;
  padding: 0 var(--spacing-md);
  background: var(--surface-raised);
  border-bottom: 1px solid var(--border-subtle);
}
.selection-counts { display: flex; align-items: baseline; gap: var(--spacing-sm); }
.selection-count { color: var(--text-primary); font-weight: 700; }
.selection-sub { color: var(--text-secondary); font-size: var(--type-caption-size); }
.selection-separator {
  width: 1px;
  height: 20px;
  margin: 0 var(--spacing-sm);
  background: var(--border-subtle);
}
```

- [ ] **Step 5: Write `bulk.js`**

Create `gui/web/bulk.js`. Every name from `results.js` is referenced inside a
function body only:

```js
// The selection bar, its menu, the bulk popover and the toast (Bundle 14).
// Loads before results.js: nothing here may name results.js's helpers at the
// top level, only inside a function body.
// Spec: docs/superpowers/specs/2026-09-14-phase9-bundle14-selection-bulk-design.md
"use strict";

const SELECTION_BAR_PX = 44;

function selectedOrders() {
  return state.view.filter((r) => state.selected.has(r.key)).map((r) => r.o);
}

function selectionSummary() {
  const orders = selectedOrders();
  let units = 0;
  let value = 0;
  let anyValue = false;
  const couriers = new Set();
  for (const o of orders) {
    units += num(o.Units) || 0;
    const v = num(o.Total_Price);
    if (v !== null) {
      value += v;
      anyValue = true;
    }
    couriers.add(courierOf(o));
  }
  return { orders: orders.length, units, value: anyValue ? value : null, couriers: couriers.size };
}

function countedWord(n, word) {
  return NUMBER.format(n) + " " + word + (n === 1 ? "" : "s");
}

function renderSelectionBar() {
  const n = state.selected.size;
  els.selectionBar.hidden = n === 0;
  els.exportBtn.className = "btn " + (n === 0 ? "primary" : "secondary");
  if (n === 0) {
    closeSelectionMenu();
    closeBulkPopover();
    return;
  }
  const s = selectionSummary();
  els.selectionCount.textContent =
    countedWord(s.orders, "order") + " · " + countedWord(s.units, "unit") + " selected";
  const parts = [];
  if (s.value !== null) parts.push(fmtMoney(s.value));
  parts.push(countedWord(s.couriers, "courier"));
  els.selectionSub.textContent = parts.join(" · ");
  els.selectionMark.textContent = n === 1 ? "Mark fulfillable" : "Mark " + n + " fulfillable";
  els.selectionHold.textContent = n === 1 ? "Hold" : "Hold these " + n;
}

function selectedKeys() {
  return state.view.filter((r) => state.selected.has(r.key)).map((r) => r.key);
}

function clearSelection() {
  state.selected = new Set();
  render();
  els.table.focus();
}

function bindSelectionBar() {
  els.selectionMark.addEventListener("click", () => {
    state.bridge.setStatus(selectedKeys(), true);
  });
  els.selectionHold.addEventListener("click", () => {
    state.bridge.setStatus(selectedKeys(), false);
  });
  els.selectionExclude.addEventListener("click", () => {
    state.bridge.excludeOrders(selectedKeys());
  });
  els.selectionClear.addEventListener("click", clearSelection);
}
```

`closeSelectionMenu` and `closeBulkPopover` arrive in Tasks 5 and 6. Until
then, add two no-op stubs at the bottom of the file and delete them when the
real ones land — a `ReferenceError` inside `renderSelectionBar` would break
every test in this task.

- [ ] **Step 6: Hook it into `results.js`**

Add the element lookups where `els` is populated (match the existing style in
that function — `els.selectionBar = document.getElementById("selection-bar")`
and so on for `selectionCount`, `selectionSub`, `selectionMark`,
`selectionHold`, `selectionMore`, `selectionMenu`, `selectionExclude`,
`selectionClear`).

Call `renderSelectionBar()` from `render()`, immediately before `layout()` —
the bar's visibility must be settled before the row budget is measured.

Call `bindSelectionBar()` wherever `bindPane()` is called.

In `layout()`, replace the `rows` line with:

```js
  const barPx = els.selectionBar.hidden ? 0 : SELECTION_BAR_PX;
  const rows = Math.max(0, Math.floor((els.tableArea.clientHeight - barPx - HEADER_PX) / state.rowH));
```

In `renderExport()`, leave the text and `disabled` logic alone —
`renderSelectionBar` owns the class now.

- [ ] **Step 7: Run it and watch it pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_results_selection_bar.py -q`
Expected: 9 passed.

- [ ] **Step 8: Commit**

```bash
git add gui/web/ tests/test_results_selection_bar.py
git commit -m "Bundle 14: the selection bar mounts with the selection"
```

---

### Task 5: More, Copy and Export

**Files:**
- Modify: `gui/web/bulk.js`
- Modify: `gui/web/results.js` (the document keydown handler)
- Test: `tests/test_results_selection_bar.py` (extend)

**Interfaces:**
- Consumes: Task 4's `selectedKeys()`, `renderSelectionBar()`.
- Produces: `openSelectionMenu()`, `closeSelectionMenu()`, and
  `moreItems()` returning `[{id, label, hint, danger, disabled, title, run}]`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_results_selection_bar.py`:

```python
def test_more_lists_its_seven_items_in_order(page):
    _select(page, ["10443", "10444", "10445"])
    _eval(page, "document.getElementById('selection-more').click()")
    labels = _eval(
        page,
        "[...document.querySelectorAll('#selection-menu .menu-item')].map(b => b.firstChild.textContent.trim())",
    )
    assert labels == [
        "Add a tag to 3 orders",
        "Remove a tag from 3 orders",
        "Copy 3 order numbers",
        "Export just these 3 to Excel",
        "Export just these 3 to CSV",
        "Remove a SKU from these 3 orders",
        "Remove whole orders containing a SKU",
    ]


def test_a_separator_sits_above_the_two_destructive_items(page):
    _select(page, ["10443"])
    _eval(page, "document.getElementById('selection-more').click()")
    assert _eval(
        page,
        "document.querySelectorAll('#selection-menu .menu-separator').length",
    ) == 1


def test_remove_a_tag_is_disabled_when_nothing_carries_one(page):
    _select(page, ["10446"])  # an order with no internal tags in the fixture
    _eval(page, "document.getElementById('selection-more').click()")
    assert _eval(page, "document.getElementById('more-remove-tag').disabled") is True
    assert (
        _eval(page, "document.getElementById('more-remove-tag').title")
        == "None of these 1 orders carry a tag"
    )


def test_copy_sends_the_order_numbers_one_per_line(page, bridge_calls):
    _select(page, ["10443", "10444"])
    _eval(page, "document.getElementById('selection-more').click()")
    _eval(page, "document.getElementById('more-copy').click()")
    assert bridge_calls("copyText") == [("10443\n10444",)]


def test_ctrl_c_copies_without_opening_the_menu(page, bridge_calls):
    _select(page, ["10443"])
    _eval(
        page,
        "document.dispatchEvent(new KeyboardEvent('keydown', {key: 'c', ctrlKey: true, bubbles: true}))",
    )
    assert bridge_calls("copyText") == [("10443",)]


def test_export_items_send_their_format(page, bridge_calls):
    _select(page, ["10443"])
    _eval(page, "document.getElementById('selection-more').click()")
    _eval(page, "document.getElementById('more-export-csv').click()")
    assert bridge_calls("exportSelection") == [(["10443"], "csv")]
```

`bridge_calls` is a fixture recording what the page sent. Follow whatever
`tests/test_results_pane.py` already does to observe bridge calls; if it has no
such helper, install a recording stub over `state.bridge`'s methods in JS and
read the record back with `_eval`.

- [ ] **Step 2: Run it and watch it fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_results_selection_bar.py -q -k "more or copy or ctrl or export_items"`
Expected: failures — `#selection-menu` renders nothing.

- [ ] **Step 3: Build the menu**

In `gui/web/bulk.js`, replacing the `closeSelectionMenu` stub:

```js
function selectionTags() {
  const seen = new Set();
  for (const o of selectedOrders()) for (const t of o.Tag_List || []) seen.add(String(t));
  return [...seen].sort();
}

function moreItems() {
  const n = state.selected.size;
  const orders = countedWord(n, "order");
  const tagged = selectionTags().length > 0;
  return [
    { id: "more-add-tag", label: "Add a tag to " + orders, run: () => openTagPopover("add") },
    {
      id: "more-remove-tag",
      label: "Remove a tag from " + orders,
      disabled: !tagged,
      title: tagged ? "" : "None of these " + orders + " carry a tag",
      run: () => openTagPopover("remove"),
    },
    { id: "more-copy", label: "Copy " + countedWord(n, "order number"), hint: "Ctrl+C", run: copySelection },
    { id: "more-export-xlsx", label: "Export just these " + n + " to Excel", run: () => exportSelection("xlsx") },
    { id: "more-export-csv", label: "Export just these " + n + " to CSV", run: () => exportSelection("csv") },
    { separator: true },
    { id: "more-remove-sku", label: "Remove a SKU from these " + orders, danger: true, run: () => openSkuPopover("line") },
    { id: "more-remove-orders", label: "Remove whole orders containing a SKU", danger: true, run: () => openSkuPopover("order") },
  ];
}

function copySelection() {
  state.bridge.copyText(selectedKeys().join("\n"));
  raiseToast(countedWord(state.selected.size, "order number") + " copied", false);
}

function exportSelection(fmt) {
  state.bridge.exportSelection(selectedKeys(), fmt);
}

function renderSelectionMenu() {
  els.selectionMenu.textContent = "";
  for (const item of moreItems()) {
    if (item.separator) {
      els.selectionMenu.appendChild(el("div", "menu-separator"));
      continue;
    }
    const button = document.createElement("button");
    button.type = "button";
    button.id = item.id;
    button.className = "menu-item" + (item.danger ? " danger" : "");
    button.setAttribute("role", "menuitem");
    button.disabled = Boolean(item.disabled);
    if (item.title) button.title = item.title;
    button.appendChild(document.createTextNode(item.label));
    if (item.hint) button.appendChild(el("span", "menu-hint", item.hint));
    button.addEventListener("click", () => {
      closeSelectionMenu();
      item.run();
    });
    els.selectionMenu.appendChild(button);
  }
}

function openSelectionMenu() {
  renderSelectionMenu();
  els.selectionMenu.hidden = false;
  els.selectionMore.setAttribute("aria-expanded", "true");
  const first = els.selectionMenu.querySelector(".menu-item:not(:disabled)");
  if (first) first.focus();
}

function closeSelectionMenu() {
  if (!els.selectionMenu) return;
  els.selectionMenu.hidden = true;
  els.selectionMore.setAttribute("aria-expanded", "false");
}
```

`raiseToast`, `openTagPopover` and `openSkuPopover` arrive in Tasks 6, 7, 8 —
keep stubs for them until then, as in Task 4.

Add to `bindSelectionBar()`:

```js
  els.selectionMore.addEventListener("click", () => {
    if (els.selectionMenu.hidden) openSelectionMenu();
    else closeSelectionMenu();
  });
  document.addEventListener("mousedown", (e) => {
    if (!e.target.closest("#selection-menu, #selection-more")) closeSelectionMenu();
  });
```

- [ ] **Step 4: Add the CSS and the shortcut**

In `results.css`:

```css
.menu-separator { height: 1px; margin: var(--spacing-xs) 0; background: var(--border-subtle); }
.menu-item.danger { color: var(--status-danger); }
.menu-hint { margin-left: auto; padding-left: var(--spacing-md); color: var(--text-secondary); }
.menu-item { display: flex; align-items: center; }
```

Check `.menu-item`'s existing rule first — if it is already a flex row, do not
restate it.

In `results.js`'s document keydown handler, beside the existing shortcuts:

```js
  if ((event.ctrlKey || event.metaKey) && event.key === "c" && state.selected.size) {
    if (event.target.matches("input, textarea")) return;
    event.preventDefault();
    copySelection();
  }
```

- [ ] **Step 5: Run it and watch it pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_results_selection_bar.py -q`
Expected: 15 passed.

- [ ] **Step 6: Commit**

```bash
git add gui/web/ tests/test_results_selection_bar.py
git commit -m "Bundle 14: More, Copy and the two export routes"
```

---

### Task 6: One tag picker, and the add-tag popover

**Files:**
- Modify: `gui/web/bulk.js`
- Modify: `gui/web/pane.js` (`openTagMenu` moves onto the shared builder)
- Modify: `gui/web/results.css`
- Test: `tests/test_results_bulk_popover.py` (create)
- Test: `tests/test_results_pane.py` (the pane's tag menu must still pass unchanged)

**Interfaces:**
- Consumes: Task 5's `openTagPopover(mode)` call site.
- Produces: `tagRows(categories, exclude)` returning
  `[{id, label, tags: [string]}]`; `renderTagList(host, rows, counts, onPick)`;
  `openBulkPopover({anchor, title, rows, counts, verb, onCommit, danger})`;
  `closeBulkPopover()`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_results_bulk_popover.py`, with the same page fixture as
Task 4:

```python
"""Bundle 14: the one popover that carries a whole bulk action."""


def _open_add_tag(page, orders):
    _select(page, orders)
    _eval(page, "document.getElementById('selection-more').click()")
    _eval(page, "document.getElementById('more-add-tag').click()")


def test_the_title_carries_the_count(page):
    _open_add_tag(page, ["10443", "10444"])
    assert _text(page, "#bulk-title") == "Add a tag to 2 orders"


def test_the_list_is_grouped_by_tag_category(page):
    _open_add_tag(page, ["10443"])
    groups = _eval(
        page,
        "[...document.querySelectorAll('#bulk-list .menu-group')].map(g => g.textContent)",
    )
    assert groups == ["Handling", "Priority", "NEW"]


def test_a_tag_already_on_some_orders_shows_its_count(page):
    _open_add_tag(page, ["10443", "10444", "10445"])
    assert _text(page, "[data-tag='FRAGILE'] .bulk-count") == "on 1 of 3"


def test_a_tag_on_no_selected_order_shows_no_count(page):
    _open_add_tag(page, ["10443"])
    assert _eval(page, "document.querySelectorAll(\"[data-tag='URGENT'] .bulk-count\").length") == 0


def test_the_verb_excludes_the_orders_that_already_carry_it(page):
    _open_add_tag(page, ["10443", "10444", "10445"])
    _eval(page, "document.querySelector(\"[data-tag='FRAGILE']\").click()")
    assert _text(page, "#bulk-verb") == "Add to 2 orders"


def test_the_verb_is_disabled_until_a_tag_is_picked(page):
    _open_add_tag(page, ["10443"])
    assert _eval(page, "document.getElementById('bulk-verb').disabled") is True


def test_a_tag_already_on_every_order_cannot_be_added(page):
    _open_add_tag(page, ["10443"])
    _eval(page, "document.querySelector(\"[data-tag='FRAGILE']\").click()")
    assert _text(page, "#bulk-verb") == "Already on all 1"
    assert _eval(page, "document.getElementById('bulk-verb').disabled") is True


def test_committing_sends_the_orders_and_the_tag(page, bridge_calls):
    _open_add_tag(page, ["10443", "10444"])
    _eval(page, "document.querySelector(\"[data-tag='URGENT']\").click()")
    _eval(page, "document.getElementById('bulk-verb').click()")
    assert bridge_calls("addTag") == [(["10443", "10444"], "URGENT")]


def test_a_new_tag_commits_on_enter(page, bridge_calls):
    _open_add_tag(page, ["10443"])
    _eval(page, "document.getElementById('bulk-new-tag').value = 'FRAG'")
    _eval(
        page,
        "document.getElementById('bulk-new-tag').dispatchEvent("
        "new KeyboardEvent('keydown', {key: 'Enter', bubbles: true}))",
    )
    assert bridge_calls("addTag") == [(["10443"], "FRAG")]


def test_escape_closes_the_popover_and_keeps_the_selection(page):
    _open_add_tag(page, ["10443"])
    _eval(
        page,
        "document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}))",
    )
    assert _eval(page, "document.querySelectorAll('#bulk-popover').length") == 0
    assert _eval(page, "state.selected.size") == 1


def test_a_click_outside_closes_it(page):
    _open_add_tag(page, ["10443"])
    _eval(page, "document.getElementById('search').dispatchEvent(new MouseEvent('mousedown', {bubbles: true}))")
    assert _eval(page, "document.querySelectorAll('#bulk-popover').length") == 0


def test_the_pane_tag_menu_still_groups_and_excludes_own_tags(page):
    """The pane's menu now shares the builder; it must not have changed."""
    _eval(page, "state.cursorKey = '10443'; render();")
    _eval(page, "document.getElementById('pane-add-tag').click()")
    labels = _eval(
        page,
        "[...document.querySelectorAll('.pane-menu .menu-item')].map(b => b.textContent.trim())",
    )
    assert "FRAGILE" not in labels  # 10443 already carries it
```

Give the page fixture a `tagCategories` of exactly
`{"handling": {"label": "Handling", "tags": ["FRAGILE", "FRAGILE-GLASS"]},
"priority": {"label": "Priority", "tags": ["URGENT"]}}` and put `FRAGILE` on
order 10443 only, so every count above is the true one.

- [ ] **Step 2: Run it and watch it fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_results_bulk_popover.py -q`
Expected: failures — no `#bulk-popover` exists.

- [ ] **Step 3: Write the shared builder and the popover**

In `gui/web/bulk.js`:

```js
const BULK_SEARCH_FROM = 10;

function tagRows(categories, exclude) {
  const skip = exclude || new Set();
  const rows = [];
  for (const id of Object.keys(categories || {})) {
    const category = categories[id] || {};
    const tags = (category.tags || []).map(String).filter((t) => !skip.has(t));
    if (tags.length) rows.push({ id, label: str(category.label) || id, tags });
  }
  return rows;
}

function renderTagList(host, rows, counts, onPick) {
  for (const row of rows) {
    host.appendChild(el("div", "menu-group", row.label));
    for (const tag of row.tags) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "menu-item bulk-row";
      button.dataset.tag = tag;
      button.appendChild(document.createTextNode(tag));
      const on = counts ? counts.get(tag) || 0 : 0;
      if (on) button.appendChild(el("span", "bulk-count", "on " + on + " of " + counts.get("__total__")));
      button.addEventListener("click", () => onPick(tag, button));
      host.appendChild(button);
    }
  }
}

function tagCounts(tags) {
  const counts = new Map();
  const orders = selectedOrders();
  counts.set("__total__", orders.length);
  for (const o of orders) {
    for (const t of o.Tag_List || []) {
      const key = String(t);
      if (tags.has(key)) counts.set(key, (counts.get(key) || 0) + 1);
    }
  }
  return counts;
}

let bulkPicked = null;

function closeBulkPopover() {
  const open = document.getElementById("bulk-popover");
  if (open) open.remove();
  bulkPicked = null;
}

function openBulkPopover(opts) {
  closeBulkPopover();
  const box = el("div", "bulk-popover");
  box.id = "bulk-popover";
  box.setAttribute("role", "dialog");
  box.setAttribute("aria-label", opts.title);

  const title = el("div", "bulk-title", opts.title);
  title.id = "bulk-title";
  box.appendChild(title);

  const list = el("div", "bulk-list");
  list.id = "bulk-list";
  box.appendChild(list);

  const verb = document.createElement("button");
  verb.type = "button";
  verb.id = "bulk-verb";
  verb.className = "btn " + (opts.danger ? "danger" : "primary");
  verb.disabled = true;
  const cancel = document.createElement("button");
  cancel.type = "button";
  cancel.className = "btn ghost";
  cancel.textContent = "Cancel";
  cancel.addEventListener("click", closeBulkPopover);
  const footer = el("div", "bulk-footer");
  footer.append(cancel, verb);
  box.appendChild(footer);

  opts.fill(list, (value, row) => {
    bulkPicked = value;
    for (const other of list.querySelectorAll(".bulk-row")) other.classList.remove("picked");
    row.classList.add("picked");
    const label = opts.verb(value);
    verb.textContent = label.text;
    verb.disabled = label.disabled;
  });

  verb.addEventListener("click", () => {
    const value = bulkPicked;
    closeBulkPopover();
    opts.onCommit(value);
  });

  els.selectionBar.appendChild(box);
  const first = list.querySelector(".bulk-row");
  if (first) first.focus();
  return box;
}

function openTagPopover(mode) {
  const n = state.selected.size;
  const orders = countedWord(n, "order");
  const categories = (state.bridge && state.bridge.tagCategories) || {};
  const present = new Set(selectionTags());
  const add = mode === "add";
  const rows = add ? tagRows(categories, null) : [{ id: "on", label: "On these orders", tags: [...present] }];
  const known = new Set();
  for (const row of rows) for (const t of row.tags) known.add(t);
  const counts = tagCounts(known);

  openBulkPopover({
    title: (add ? "Add a tag to " : "Remove a tag from ") + orders,
    danger: false,
    fill: (host, onPick) => {
      renderTagList(host, rows, counts, onPick);
      if (!add) return;
      host.appendChild(el("div", "menu-group", "NEW"));
      const input = el("input", "new-tag");
      input.id = "bulk-new-tag";
      input.placeholder = "New tag";
      input.setAttribute("aria-label", "New tag");
      input.addEventListener("keydown", (e) => {
        const tag = input.value.trim();
        if (e.key !== "Enter" || !tag) return;
        const keys = selectedKeys();
        closeBulkPopover();
        state.bridge.addTag(keys, tag);
      });
      host.appendChild(input);
    },
    verb: (tag) => {
      const on = counts.get(tag) || 0;
      if (add) {
        return on === n
          ? { text: "Already on all " + n, disabled: true }
          : { text: "Add to " + countedWord(n - on, "order"), disabled: false };
      }
      return { text: "Remove from " + countedWord(on, "order"), disabled: on === 0 };
    },
    onCommit: (tag) => {
      const keys = selectedKeys();
      if (add) state.bridge.addTag(keys, tag);
      else state.bridge.removeTag(keys, tag);
    },
  });
}
```

Add Escape and outside-click handling in `bindSelectionBar()`:

```js
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape" || !document.getElementById("bulk-popover")) return;
    e.stopPropagation();
    closeBulkPopover();
    els.selectionMore.focus();
  });
  document.addEventListener("mousedown", (e) => {
    if (!e.target.closest("#bulk-popover, #selection-menu, #selection-more")) closeBulkPopover();
  });
```

The Escape listener must be registered **before** `results.js`'s own Escape
handler runs so the popover closes instead of the selection. Confirm the
ordering by running `test_escape_closes_the_popover_and_keeps_the_selection`;
if `results.js` wins, register this one in the capture phase
(`{capture: true}`).

- [ ] **Step 4: Move the pane onto the shared builder**

In `gui/web/pane.js`, replace `openTagMenu`'s grouping loop with a call to the
shared pair, keeping every other line of the function as it is:

```js
function openTagMenu(anchor, o) {
  const order = str(o.Order_Number);
  const own = new Set((o.Tag_List || []).map(String));
  const menu = newMenu("tag-menu");
  renderTagList(menu, tagRows((state.bridge && state.bridge.tagCategories) || {}, own), null,
                (tag) => { closePaneMenus(); if (state.bridge) state.bridge.addOrderTag(order, tag); });
  // the new-tag input below is unchanged
  …
}
```

`renderTagList` gives its rows `class="menu-item bulk-row"`, which the pane's
CSS already styles through `.menu-item`. Do not add a pane-specific rule.

- [ ] **Step 5: Add the popover CSS**

```css
.bulk-popover {
  position: absolute;
  z-index: 3;
  top: 44px;
  right: var(--spacing-md);
  display: flex;
  flex-direction: column;
  width: 320px;
  max-height: 380px;
  background: var(--surface-overlay);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}
.bulk-title { padding: var(--spacing-sm) var(--spacing-md); font-weight: 700; }
.bulk-list { flex: 1; min-height: 0; overflow-y: auto; }
.bulk-list .menu-group { position: sticky; top: 0; background: var(--surface-overlay); }
.bulk-row.picked { background: var(--selection-bg); }
.bulk-count { margin-left: auto; padding-left: var(--spacing-md); color: var(--text-secondary); }
.bulk-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  border-top: 1px solid var(--border-subtle);
}
```

`.selection-bar` needs `position: relative` for the popover's anchoring — add
it to that rule.

- [ ] **Step 6: Run both files and watch them pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_results_bulk_popover.py tests/test_results_pane.py -q`
Expected: all pass. `test_results_pane.py` must pass **without being edited** —
if it does not, the shared builder changed the pane's behaviour and the builder
is wrong, not the test.

- [ ] **Step 7: Walk the rows with the arrows**

Spec § 10: inside a popover the arrows walk rows and Enter picks — the same
gesture `columns.js` already uses. Add the test:

```python
def test_the_arrows_walk_the_rows(page):
    _open_add_tag(page, ["10443"])
    _eval(
        page,
        "document.querySelector('#bulk-list .bulk-row').dispatchEvent("
        "new KeyboardEvent('keydown', {key: 'ArrowDown', bubbles: true}))",
    )
    assert _eval(page, "document.activeElement.dataset.tag") == "FRAGILE-GLASS"
```

Then, inside `openBulkPopover` after the list is filled:

```js
  list.addEventListener("keydown", (e) => {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    const rows = [...list.querySelectorAll(".bulk-row")].filter((r) => !r.hidden);
    const here = rows.indexOf(document.activeElement);
    const next = here + (e.key === "ArrowDown" ? 1 : -1);
    if (next < 0 || next >= rows.length) return;
    e.preventDefault();
    rows[next].focus();
  });
```

Enter needs no handler: the rows are `<button>`s, so Enter clicks them.

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_results_bulk_popover.py -q`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add gui/web/ tests/
git commit -m "Bundle 14: one tag picker, two callers, and the add/remove-tag popover"
```

---

### Task 7: The two SKU popovers and their confirms

**Files:**
- Modify: `gui/web/bulk.js`
- Test: `tests/test_results_bulk_popover.py` (extend)

**Interfaces:**
- Consumes: Task 6's `openBulkPopover`.
- Produces: `openSkuPopover(mode)` where `mode` is `"line"` or `"order"`, and
  `skuCounts()` returning a `Map` of SKU → number of selected orders carrying it.

- [ ] **Step 1: Write the failing test**

```python
def _open_sku(page, orders, item):
    _select(page, orders)
    _eval(page, "document.getElementById('selection-more').click()")
    _eval(page, f"document.getElementById('{item}').click()")


def test_the_sku_list_counts_orders_not_lines(page):
    _open_sku(page, ["10443", "10445"], "more-remove-sku")
    assert _text(page, "[data-tag='TS-4409-B'] .bulk-count") == "on 2 of 2"


def test_the_sku_list_sorts_by_count_then_name(page):
    _open_sku(page, ["10443", "10445"], "more-remove-sku")
    skus = _eval(
        page,
        "[...document.querySelectorAll('#bulk-list .bulk-row')].map(b => b.dataset.tag)",
    )
    assert skus == sorted(skus, key=lambda s: s) or skus[0] == "TS-4409-B"


def test_the_line_removal_verb_names_the_orders_it_touches(page):
    _open_sku(page, ["10443", "10445"], "more-remove-sku")
    _eval(page, "document.querySelector(\"[data-tag='TS-4409-B']\").click()")
    assert _text(page, "#bulk-verb") == "Remove from 2 orders"
    assert "danger" in _eval(page, "document.getElementById('bulk-verb').className")


def test_the_order_removal_verb_names_the_orders_it_deletes(page):
    _open_sku(page, ["10443", "10445"], "more-remove-orders")
    _eval(page, "document.querySelector(\"[data-tag='TS-4409-B']\").click()")
    assert _text(page, "#bulk-verb") == "Remove 2 orders"


def test_committing_a_line_removal_sends_the_sku(page, bridge_calls):
    _open_sku(page, ["10443"], "more-remove-sku")
    _eval(page, "document.querySelector(\"[data-tag='TS-4409-B']\").click()")
    _eval(page, "document.getElementById('bulk-verb').click()")
    assert bridge_calls("removeSkuFromOrders") == [(["10443"], "TS-4409-B")]


def test_committing_an_order_removal_sends_the_sku(page, bridge_calls):
    _open_sku(page, ["10443"], "more-remove-orders")
    _eval(page, "document.querySelector(\"[data-tag='TS-4409-B']\").click()")
    _eval(page, "document.getElementById('bulk-verb').click()")
    assert bridge_calls("removeOrdersWithSku") == [(["10443"], "TS-4409-B")]


def test_a_search_row_appears_only_above_ten_skus(page):
    _open_sku(page, ["10443"], "more-remove-sku")
    assert _eval(page, "document.querySelectorAll('#bulk-search').length") == 0
```

- [ ] **Step 2: Run it and watch it fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_results_bulk_popover.py -q -k sku`
Expected: `openSkuPopover is not defined`.

- [ ] **Step 3: Implement**

In `gui/web/bulk.js`, replacing the `openSkuPopover` stub:

```js
function skuCounts() {
  const counts = new Map();
  const orders = selectedOrders();
  counts.set("__total__", orders.length);
  for (const o of orders) {
    const own = new Set();
    for (const line of o.lines || []) {
      const sku = str(line.SKU).trim();
      if (sku) own.add(sku);
    }
    for (const sku of own) counts.set(sku, (counts.get(sku) || 0) + 1);
  }
  return counts;
}

function openSkuPopover(mode) {
  const n = state.selected.size;
  const counts = skuCounts();
  const skus = [...counts.keys()]
    .filter((k) => k !== "__total__")
    .sort((a, b) => counts.get(b) - counts.get(a) || a.localeCompare(b));
  const line = mode === "line";

  openBulkPopover({
    title: line
      ? "Remove a SKU from these " + countedWord(n, "order")
      : "Remove whole orders containing a SKU",
    danger: true,
    fill: (host, onPick) => {
      if (skus.length >= BULK_SEARCH_FROM) {
        const search = el("input", "bulk-search");
        search.id = "bulk-search";
        search.type = "search";
        search.placeholder = "Find a SKU";
        search.setAttribute("aria-label", "Find a SKU");
        search.addEventListener("input", () => {
          const q = search.value.trim().toLowerCase();
          for (const row of host.querySelectorAll(".bulk-row")) {
            row.hidden = q !== "" && !row.dataset.tag.toLowerCase().includes(q);
          }
        });
        host.appendChild(search);
      }
      renderTagList(host, [{ id: "skus", label: "SKUs on these orders", tags: skus }], counts, onPick);
    },
    verb: (sku) => {
      const on = counts.get(sku) || 0;
      return {
        text: (line ? "Remove from " : "Remove ") + countedWord(on, "order"),
        disabled: on === 0,
      };
    },
    onCommit: (sku) => {
      const keys = selectedKeys();
      if (line) state.bridge.removeSkuFromOrders(keys, sku);
      else state.bridge.removeOrdersWithSku(keys, sku);
    },
  });
}
```

The search input is inside the scroller so it scrolls away; that matches the
column manager, whose search sits in the chrome — accept the difference here
because this list is short and the search appears only when it is not.

- [ ] **Step 4: Run it and watch it pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_results_bulk_popover.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add gui/web/bulk.js tests/test_results_bulk_popover.py
git commit -m "Bundle 14: the two SKU removals, restored behind one popover"
```

---

### Task 8: The toast, in the document

**Files:**
- Modify: `gui/web/results.html`, `gui/web/results.css`, `gui/web/bulk.js`
- Modify: `gui/web/results.js` (connect `toastRaised` where the bridge is bound)
- Modify: `gui/actions_handler.py` (the three pane verbs' `toast(...)` calls)
- Test: `tests/test_results_toast.py` (create)

**Interfaces:**
- Consumes: Task 1's `toastRaised` and `undoAvailable`.
- Produces: `raiseToast(text, undoable)`, `bindToast()`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_results_toast.py`:

```python
"""Bundle 14: the toast the page draws itself (ADR 0007)."""


def test_a_toast_shows_its_text(page, bridge):
    bridge.raise_toast("3 orders held")
    assert _text(page, "#toast-text") == "3 orders held"
    assert _eval(page, "document.getElementById('toast').hidden") is False


def test_an_undoable_toast_offers_undo(page, bridge):
    bridge.set_undo_available(True)
    bridge.raise_toast("FRAGILE added to 28 orders", undoable=True)
    assert _eval(page, "document.getElementById('toast-undo').hidden") is False


def test_undo_is_hidden_when_nothing_can_be_undone(page, bridge):
    bridge.set_undo_available(False)
    bridge.raise_toast("FRAGILE added to 28 orders", undoable=True)
    assert _eval(page, "document.getElementById('toast-undo').hidden") is True


def test_a_non_undoable_toast_never_offers_undo(page, bridge):
    bridge.set_undo_available(True)
    bridge.raise_toast("3 order numbers copied")
    assert _eval(page, "document.getElementById('toast-undo').hidden") is True


def test_undo_calls_the_bridge_and_dismisses(page, bridge, bridge_calls):
    bridge.set_undo_available(True)
    bridge.raise_toast("3 orders held", undoable=True)
    _eval(page, "document.getElementById('toast-undo').click()")
    assert bridge_calls("undo") == [()]
    assert _eval(page, "document.getElementById('toast').hidden") is True


def test_the_newest_replaces_the_oldest(page, bridge):
    bridge.raise_toast("first")
    bridge.raise_toast("second")
    assert _text(page, "#toast-text") == "second"
    assert _eval(page, "document.querySelectorAll('#toast').length") == 1


def test_the_badge_counts_from_the_third_in_a_run(page, bridge):
    bridge.raise_toast("one")
    assert _eval(page, "document.getElementById('toast-badge').hidden") is True
    bridge.raise_toast("two")
    assert _eval(page, "document.getElementById('toast-badge').hidden") is True
    bridge.raise_toast("three")
    assert _text(page, "#toast-badge") == "3"


def test_it_dismisses_itself(page, bridge):
    bridge.raise_toast("gone in four seconds")
    _wait_until(page, "document.getElementById('toast').hidden === true", timeout_ms=6000)
```

`_wait_until` polls `_eval` — reuse `tests/test_results_pane.py`'s waiting
helper if it has one rather than writing a second.

- [ ] **Step 2: Run it and watch it fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_results_toast.py -q`
Expected: failures — `#toast` does not exist.

- [ ] **Step 3: Markup and CSS**

In `results.html`, as the last child of `<main id="results">`:

```html
  <div id="toast" class="toast" role="status" aria-live="polite" hidden>
    <span id="toast-text" class="toast-text"></span>
    <span id="toast-badge" class="toast-badge" hidden></span>
    <button id="toast-undo" class="btn ghost" type="button" hidden>Undo</button>
  </div>
```

In `results.css` — the numbers come from `gui/components/toast.py` and must
stay equal to it:

```css
/* Mirrors gui/components/toast.py: 16px margin, 360 max, no fade (ADR 0007). */
.toast {
  position: absolute;
  right: 16px;
  bottom: 16px;
  z-index: 4;
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  max-width: 360px;
  padding: var(--spacing-sm) var(--spacing-sm) var(--spacing-sm) var(--spacing-md);
  background: var(--surface-overlay);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
}
.toast-badge {
  min-width: 18px;
  padding: 0 var(--spacing-xs);
  background: var(--surface-sunken);
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  font-size: var(--type-caption-size);
  text-align: center;
}
```

`#results` needs `position: relative` if it does not already have it.

- [ ] **Step 4: The JS**

In `gui/web/bulk.js`:

```js
// Mirrors gui/components/toast.py. Two implementations, one appearance —
// change one and change the other (ADR 0007).
const TOAST_MS = 4000;
const TOAST_BADGE_AT = 3;
let toastTimer = null;
let toastRun = 0;

function raiseToast(text, undoable) {
  toastRun += 1;
  els.toastText.textContent = text;
  els.toastBadge.hidden = toastRun < TOAST_BADGE_AT;
  els.toastBadge.textContent = String(toastRun);
  els.toastUndo.hidden = !(undoable && state.bridge && state.bridge.undoAvailable);
  els.toast.hidden = false;
  if (toastTimer !== null) clearTimeout(toastTimer);
  toastTimer = setTimeout(dismissToast, TOAST_MS);
}

function dismissToast() {
  if (toastTimer !== null) clearTimeout(toastTimer);
  toastTimer = null;
  toastRun = 0;
  els.toast.hidden = true;
}

function bindToast() {
  els.toastUndo.addEventListener("click", () => {
    dismissToast();
    if (state.bridge) state.bridge.undo();
  });
}
```

Add `els.toast`, `els.toastText`, `els.toastBadge`, `els.toastUndo` to the
`els` lookups in `results.js`, call `bindToast()` beside `bindSelectionBar()`,
and connect the signal where the other bridge signals are connected:

```js
    state.bridge.toastRaised.connect((text, undoable) => raiseToast(text, undoable));
```

- [ ] **Step 5: Reroute the pane's three verbs**

In `gui/actions_handler.py`, change the `toast(...)` calls inside
`remove_entire_order`, `remove_line` and `set_order_fulfillable` to
`self._results_toast(...)`, keeping their existing text and undoability. Leave
every other `toast(...)` call in the file and in the app untouched — this is a
Results-screen change only. If `set_order_fulfillable` raises no toast today
(the pane shows the change), leave it alone.

- [ ] **Step 6: Run it and watch it pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_results_toast.py tests/test_results_pane.py -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add gui/web/ gui/actions_handler.py tests/test_results_toast.py
git commit -m "Bundle 14: the Results screen toasts inside its own document"
```

---

### Task 9: The gate

**Files:**
- Modify: whatever the gate turns up.

- [ ] **Step 1: The whole suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
Expected: every test passes. The baseline before this bundle was 1664.

- [ ] **Step 2: Lint**

Run: `.venv/bin/python -m ruff check . --exclude shared`
Expected: no findings.

- [ ] **Step 3: Style lint, both tiers**

```bash
.venv/bin/python -c "
from pathlib import Path
from shared.style_lint import find_style_literals
print('\n'.join(find_style_literals([Path('gui'), Path('shopify_tool')])) or 'clean')
"
```
Expected: `clean`. A hex literal, a `box-shadow`, a `transition` or a
non-token colour in `bulk.js` or `results.css` fails here.

- [ ] **Step 4: The Done-when, by hand**

```bash
grep -n "QInputDialog" gui/actions_handler.py || echo "no QInputDialog: done-when met"
```
Expected: the `echo`.

- [ ] **Step 5: Refresh the graph**

Run: `graphify update .`
Expected: it completes. The repo's CLAUDE.md requires this after any code change.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "Bundle 14: gate — suite, lint, style lint, graph"
git push -u origin worktree-phase9-bundle14-selection-bulk
```

---

## Self-review notes for the executor

Three things in this plan are guesses about code you will be reading for the
first time, and the plan says so rather than pretending otherwise:

1. **Task 2's fixtures.** `tests/test_actions_handler.py` exists and builds an
   `ActionsHandler`; reuse its construction rather than the sketch here.
2. **Task 3's undo entry point.** Wire `undoRequested` to whatever the rail's
   Undo button already calls, not to a name invented here.
3. **Task 6's Escape ordering.** If `results.js` clears the selection before
   the popover closes, move the popover's listener to the capture phase. The
   test tells you which happened.

Everywhere else, if the repo disagrees with the plan, the repo is right —
report the disagreement in the commit message rather than bending the code to
match a plan written a day earlier.
