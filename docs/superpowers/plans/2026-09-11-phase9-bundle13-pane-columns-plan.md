# Phase 9 Bundle 13 — Detail pane and column manager: Implementation Plan

> **For agentic workers:** Stage B runs this plan **in one session, task by
> task, with no subagents** (the roadmap runner's rule). Steps use checkbox
> (`- [ ]`) syntax for tracking.

**Goal:** Fill the results document's 400px slot with the order detail pane
(9.14) and the column manager (9.16). Give the additional-columns editor a
home on Settings › Mappings. Delete the Qt column manager.

**Architecture:**
- **Python owns the data and the handlers.** It parses the run's reason
  strings into a per-order `Verdict`, stores column settings per client, and
  handles pane verbs through the existing `ActionsHandler` operations.
- **The page owns rendering.** It holds the column registry, verdict copy,
  pane, manager, and the slot's modes. Pane verbs arrive as bridge slots,
  which emit Python-facing signals.
- **Additional columns** move into the shopify config's `column_mappings`,
  and the analysis reads them through one helper (ADR 0006).

**Tech stack:** Python 3 / PySide6 (QtWebEngine, QWebChannel), pandas, vanilla
JS and CSS in `gui/web/`, pytest with pytest-qt.

**Spec:** `docs/superpowers/specs/2026-09-11-phase9-bundle13-pane-columns-design.md`.
**Read it before starting.** Every pixel, copy string and rule not repeated
here is there. §-numbers below point into it.

## Global constraints

- **Setup:** first run `./scripts/setup_venv.sh` in the worktree. Tests run as
  `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest …`. Lint is
  `.venv/bin/ruff check . --exclude shared`.
- **VM guard:** use `/usr/bin/git`, one git command per call. No `&&` chains,
  no heredocs, and no `git -C` pointed at the main checkout. Write files with
  the Write or Edit tools.
- **Write hook:** it strips an import added before its usage exists, so add
  the usage first and the import second. It also reformats touched Python
  files.
- **Web assets:**
  - Tokens from `theme_css_vars` only.
  - Never a hex colour, `box-shadow`, `text-shadow`, gradient, `transition`,
    `animation`, `transform`, `opacity` or px font size.
  - Hover reveals use `visibility`; position with `top`/`left`.
  - `shared/style_lint.py` enforces this over `gui/web/`.
- **Bridge rules** (Bundle 11 §5.1):
  - one member per message;
  - JSON-native values;
  - camelCase channel members and snake_case Python API;
  - JS never connects to Python-facing signals.
- **Chromium quirk on this VM:** `runJavaScript` cannot return an array or an
  object. Return `JSON.stringify(...)` and `json.loads` it in Python.
- **Test helpers:** import them as
  `from test_results_bridge import _eval, _until_js`. `tests/` has no
  `__init__.py`.
- **Deletions:** never hand-edit `shared/`. Never `git stash`. Never delete a
  test to make a suite pass unless this plan deletes it.
- **Copy strings** are the spec's, verbatim (§6.3, §6.4, §6.9, §7.5).
- **Commits** end with the attribution lines from the session's system
  reminder.

## File map

| File | Change | Responsibility |
|---|---|---|
| `gui/orders_view.py` | modify | `order_verdict`; `order_payload` adds `Verdict` and per-line `Short` |
| `shopify_tool/core.py` | modify | `effective_additional_columns` and its two call sites |
| `gui/results_bridge.py` | modify | `normalize_column_settings`, and the Bundle 13 members (§4) |
| `docs/superpowers/specs/2026-09-11-phase9-bundle11-seam-design.md` | modify | §5.2 catalogue rows for Bundle 13 |
| `gui/actions_handler.py` | modify | `set_order_fulfillable`, `remove_line`, `add_internal_tag`, `remove_internal_tag` |
| `gui/ui_manager.py` | modify | wire bridge signals to handlers |
| `gui/main_window_pyside.py` | modify | column settings load and save, tag categories push, drop `TableConfigManager` |
| `gui/settings/mappings.py`, `gui/settings/window.py` | modify | the Additional columns section and its fallback |
| `gui/web/results.html`, `results.css`, `results.js` | modify | slot grid, registry-driven table, filter-bar Columns button |
| `gui/web/columns.js` | create | column registry and effective columns (Task 7); column manager (Task 9) |
| `gui/web/pane.js` | create | detail pane, strip, menus (Task 8) |
| `gui/column_config_dialog.py`, `gui/table_config_manager.py` | delete | |
| `tests/test_column_config_dialog.py`, `tests/test_table_config_manager.py` | delete | |
| `tests/test_order_verdict.py` | create | pure verdict and payload tests |
| `tests/test_additional_columns.py` | create | pure `effective_additional_columns` tests |
| `tests/test_results_bridge.py` | modify | Python-side bridge member tests |
| `tests/test_pane_actions.py` | create | `ActionsHandler` pane verbs |
| `tests/test_results_screen.py` | modify | wiring, column-settings round trip, done check |
| `tests/test_settings_additional_columns.py` | create | Settings section |
| `tests/test_results_columns.py` | create | Chromium: slot, registry, manager |
| `tests/test_results_pane.py` | create | Chromium: pane |
| `tests/test_message_routes.py` | modify | drop the `column_config_dialog.py` entry |

---

### Task 1: The verdict and the payload

**Files:**
- Modify: `gui/orders_view.py`
- Create: `tests/test_order_verdict.py`

**Interfaces:**
- Produces:
  - `order_verdict(status, notes: list, line_skus: list, has_sku: list) -> dict`,
    returning `{"state": "ready"|"short"|"review", "by_hand": bool,
    "problems": list[dict]}`. Problem shapes are in spec §3.1.
  - `order_payload(df)` entries gain `"Verdict"`, and each `lines[i]` gains
    `"Short": bool`.

- [ ] **Step 1: Write the failing tests** in `tests/test_order_verdict.py`:

```python
"""order_verdict and the payload's Verdict/Short (Bundle 13 spec §3.1)."""

import json

import pandas as pd
import pytest

from gui.orders_view import order_payload, order_verdict

SHORT = "Cannot fulfill: A: Insufficient stock (need 6, have 4); B: Out of stock"


def test_a_fulfillable_order_with_no_note_is_ready():
    assert order_verdict("Fulfillable", ["", ""], ["A", "B"], [True, True]) == {
        "state": "ready",
        "by_hand": False,
        "problems": [],
    }


def test_stock_reasons_parse_with_their_numbers():
    v = order_verdict("Not Fulfillable", [SHORT, SHORT], ["A", "B"], [True, True])
    assert v["state"] == "short"
    assert v["by_hand"] is False
    assert v["problems"] == [
        {"code": "short", "sku": "A", "need": 6, "have": 4},
        {"code": "out_of_stock", "sku": "B"},
    ]


def test_a_repeat_prefix_and_a_no_sku_suffix_are_tolerated():
    note = "Repeat; Cannot fulfill: A: Out of stock [NO_SKU]"
    v = order_verdict("Not Fulfillable", [note], ["A"], [True])
    assert v["problems"] == [{"code": "out_of_stock", "sku": "A"}]


def test_lines_without_a_sku_are_a_data_problem():
    v = order_verdict("Not Fulfillable", ["[NO_SKU]", ""], [None, "A"], [False, True])
    assert v == {
        "state": "review",
        "by_hand": False,
        "problems": [{"code": "no_sku", "lines": 1}],
    }


def test_an_invalid_quantity_is_a_data_problem():
    v = order_verdict(
        "Not Fulfillable", ["Cannot fulfill: A: Missing/invalid quantity"], ["A"], [True]
    )
    assert v["state"] == "review"
    assert v["problems"] == [{"code": "invalid_quantity", "sku": "A"}]


def test_an_unrecognised_reason_is_kept_as_text():
    v = order_verdict("Not Fulfillable", ["Cannot fulfill: Unknown reason"], ["A"], [True])
    assert v["state"] == "review"
    assert v["problems"] == [{"code": "other", "text": "Unknown reason"}]


def test_forcing_a_blocked_order_fulfillable_reads_as_by_hand():
    v = order_verdict("Fulfillable", [SHORT], ["A", "B"], [True, True])
    assert (v["state"], v["by_hand"]) == ("review", True)


def test_holding_an_order_the_run_could_ship_reads_as_by_hand():
    v = order_verdict("Not Fulfillable", [""], ["A"], [True])
    assert v == {"state": "review", "by_hand": True, "problems": []}


def test_a_reason_for_a_removed_line_is_dropped():
    v = order_verdict("Not Fulfillable", [SHORT], ["B"], [True])
    assert v["problems"] == [{"code": "out_of_stock", "sku": "B"}]


@pytest.mark.parametrize("missing", [None, float("nan")])
def test_blank_notes_are_skipped(missing):
    assert order_verdict("Fulfillable", [missing], ["A"], [True])["state"] == "ready"


def test_the_payload_carries_the_verdict_and_edges_short_lines():
    df = pd.DataFrame(
        [
            {"Order_Number": "1", "Order_Fulfillment_Status": "Not Fulfillable",
             "SKU": "A", "Quantity": 6, "System_note": SHORT, "Has_SKU": True},
            {"Order_Number": "1", "Order_Fulfillment_Status": "Not Fulfillable",
             "SKU": "B", "Quantity": 1, "System_note": SHORT, "Has_SKU": True},
            {"Order_Number": "1", "Order_Fulfillment_Status": "Not Fulfillable",
             "SKU": "C", "Quantity": 1, "System_note": SHORT, "Has_SKU": True},
        ]
    )
    (entry,) = order_payload(df)
    assert entry["Verdict"]["state"] == "short"
    assert [line["Short"] for line in entry["lines"]] == [True, True, False]
    json.dumps(order_payload(df), allow_nan=False)


def test_the_payload_verdict_survives_missing_columns():
    df = pd.DataFrame([{"Order_Number": "1", "SKU": "A"}])
    (entry,) = order_payload(df)
    assert entry["Verdict"] == {"state": "review", "by_hand": True, "problems": []}
```

The last case has no status column, so its status is `""`: not fulfillable,
with no problem. It reads as set by a person, which is the documented
fallback.

- [ ] **Step 2: Run the tests and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_order_verdict.py -v`
Expected: FAIL with `ImportError: cannot import name 'order_verdict'`.

- [ ] **Step 3: Implement** in `gui/orders_view.py`.

Add `import re` at the top. Below `BLOCKER_PREFIX`, add:

```python
NO_SKU_SUFFIX = " [NO_SKU]"
# The allocation's own reason strings (analysis.py, legacy and FIFO paths).
_SHORT = re.compile(r"^(?P<sku>.+): Insufficient stock \(need (?P<need>\d+), have (?P<have>\d+)\)$")
_OUT_OF_STOCK = re.compile(r"^(?P<sku>.+): Out of stock$")
_INVALID_QTY = re.compile(r"^(?P<sku>.+): Missing/invalid quantity$")
_DATA_CODES = {"invalid_quantity", "no_sku", "other"}
_STOCK_CODES = {"short", "out_of_stock"}


def _blank(value) -> bool:
    return value is None or (isinstance(value, float) and pd.isna(value))


def _reason_problems(notes) -> list[dict]:
    """The problems in the first note carrying a blocker, in the run's order."""
    for note in notes:
        if _blank(note):
            continue
        text = str(note)
        if text.endswith(NO_SKU_SUFFIX):
            text = text[: -len(NO_SKU_SUFFIX)]
        _, sep, tail = text.partition(BLOCKER_PREFIX)
        if not sep:
            continue
        problems = []
        for part in (p.strip() for p in tail.split("; ")):
            if not part:
                continue
            if m := _SHORT.match(part):
                problems.append(
                    {"code": "short", "sku": m["sku"], "need": int(m["need"]), "have": int(m["have"])}
                )
            elif m := _OUT_OF_STOCK.match(part):
                problems.append({"code": "out_of_stock", "sku": m["sku"]})
            elif m := _INVALID_QTY.match(part):
                problems.append({"code": "invalid_quantity", "sku": m["sku"]})
            else:
                problems.append({"code": "other", "text": part})
        return problems
    return []


def order_verdict(status, notes, line_skus, has_sku) -> dict:
    """Whether the order ships and why not, from the run's reason codes (§3.1).

    `by_hand` is true when the status disagrees with the run: a manual toggle
    rewrites Order_Fulfillment_Status and never System_note.
    """
    skus = {str(s) for s in line_skus if not _blank(s)}
    problems, seen = [], set()
    for p in _reason_problems(notes):
        if "sku" in p and p["sku"] not in skus:
            continue  # its line was removed after the run
        key = (p["code"], p.get("sku"), p.get("text"))
        if key not in seen:
            seen.add(key)
            problems.append(p)
    missing = sum(1 for h in has_sku if isinstance(h, (bool, np.bool_)) and not h)
    if missing:
        problems.append({"code": "no_sku", "lines": missing})

    fulfillable = status == FULFILLABLE
    by_hand = fulfillable == bool(problems)
    if by_hand or any(p["code"] in _DATA_CODES for p in problems):
        state = "review"
    elif not fulfillable:
        state = "short"
    else:
        state = "ready"
    return {"state": state, "by_hand": by_hand, "problems": problems}
```

In `order_payload`, replace the `lines = {…}` comprehension with one loop that
builds both dicts:

```python
    lines, verdicts = {}, {}
    for key, group in df.groupby(ORDER_KEY, sort=False):
        lines[key] = [
            dict(zip(line_level, map(_json_value, row)))
            for row in group[line_level].itertuples(index=False, name=None)
        ]
        status = group["Order_Fulfillment_Status"].iloc[0] if "Order_Fulfillment_Status" in group else ""
        verdicts[key] = order_verdict(
            status,
            group["System_note"].tolist() if "System_note" in group else [],
            group["SKU"].tolist() if "SKU" in group else [],
            group["Has_SKU"].tolist() if "Has_SKU" in group else [],
        )
```

In the per-entry loop, after `entry["lines"] = lines.get(key, [])`, add:

```python
        verdict = verdicts.get(key, {"state": "review", "by_hand": True, "problems": []})
        entry["Verdict"] = _json_value(verdict)
        short = {p["sku"] for p in verdict["problems"] if p["code"] in _STOCK_CODES}
        for line in entry["lines"]:
            line["Short"] = line.get("SKU") is not None and str(line["SKU"]) in short
```

- [ ] **Step 4: Run the new tests and the existing payload tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_order_verdict.py tests/test_orders_view.py tests/test_results_bridge.py -v`
Expected: PASS. If `tests/test_orders_view.py` has another name, find the
payload's tests with `grep -rln order_payload tests`.

- [ ] **Step 5: Commit**

```bash
/usr/bin/git add gui/orders_view.py tests/test_order_verdict.py
/usr/bin/git commit -m "Bundle 13: the verdict comes from the run's reason codes (9.14)"
```

---

### Task 2: One reader for additional columns (ADR 0006)

**Files:**
- Modify: `shopify_tool/core.py`, at ≈L814–821 in `_run_analysis_and_rules`
  and ≈L1304–1317
- Create: `tests/test_additional_columns.py`

**Interfaces:**
- Produces: `shopify_tool.core.effective_additional_columns(column_mappings: dict, client_config: dict) -> list`.

- [ ] **Step 1: Write the failing tests**

```python
"""Additional columns are read from the column mappings first (ADR 0006)."""

from shopify_tool.core import effective_additional_columns

OLD = {"ui_settings": {"table_view": {"additional_columns": [{"csv_name": "Old"}]}}}


def test_the_mappings_key_wins():
    mappings = {"additional_columns": [{"csv_name": "New"}]}
    assert effective_additional_columns(mappings, OLD) == [{"csv_name": "New"}]


def test_an_empty_mappings_list_still_wins():
    assert effective_additional_columns({"additional_columns": []}, OLD) == []


def test_absent_key_falls_back_to_the_client_config():
    assert effective_additional_columns({"orders": {}}, OLD) == [{"csv_name": "Old"}]


def test_nothing_anywhere_is_empty():
    assert effective_additional_columns({}, {}) == []
    assert effective_additional_columns(None, None) == []
```

- [ ] **Step 2: Run and see the tests fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_additional_columns.py -v`
Expected: FAIL with ImportError.

- [ ] **Step 3: Implement.** Add at module level in `shopify_tool/core.py`:

```python
def effective_additional_columns(column_mappings, client_config) -> list:
    """The additional-columns list the analysis uses (ADR 0006).

    Settings writes it under column_mappings; profiles never saved since
    Bundle 13 still carry it in client_config.ui_settings.table_view.
    """
    if isinstance(column_mappings, dict) and "additional_columns" in column_mappings:
        return list(column_mappings["additional_columns"] or [])
    ui_settings = (client_config or {}).get("ui_settings", {}) or {}
    return list((ui_settings.get("table_view", {}) or {}).get("additional_columns", []) or [])
```

Replace the ≈L814–821 block with:

```python
    # Additional columns: the mappings' own list, else the pre-Bundle-13
    # client-config key (ADR 0006).
    client_config = config.get("_client_config", {})  # Passed from main_window
    additional_columns = effective_additional_columns(column_mappings, client_config)
    column_mappings["additional_columns"] = additional_columns
```

Keep the two `logger.debug` lines that follow. In the ≈L1304 logging block,
replace the chained `.get("table_view")…` read with:

```python
            additional_cols = effective_additional_columns(
                config.get("column_mappings", {}), client_config
            )
```

- [ ] **Step 4: Run the new tests and the core suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_additional_columns.py tests/test_core.py -q`
Expected: PASS. If `tests/test_core.py` is named differently, run
`grep -rln "_run_analysis_and_rules\|run_full_analysis" tests`.

- [ ] **Step 5: Commit**

```bash
/usr/bin/git add shopify_tool/core.py tests/test_additional_columns.py
/usr/bin/git commit -m "Bundle 13: additional columns read from the column mappings first (ADR 0006)"
```

---

### Task 3: The bridge's Bundle 13 members

**Files:**
- Modify: `gui/results_bridge.py`
- Modify: `tests/test_results_bridge.py` (append)
- Modify: `docs/superpowers/specs/2026-09-11-phase9-bundle11-seam-design.md` §5.2

**Interfaces:**
- Consumes: `classify_columns`, `ORDER_LEVEL_COLUMNS`, `ORDER_KEY` from
  `gui.orders_view`.
- Produces:
  - `normalize_column_settings(raw) -> dict`;
  - on `ResultsBridge`:
    - properties `columns` and `tagCategories`;
    - slots `holdOrder(str)`, `fulfillOrder(str)`, `excludeOrder(str)`,
      `removeLine(str, int, str)`, `addOrderTag(str, str)`,
      `removeOrderTag(str, str)`, `copyText(str)`, `setColumnOrder(list)`,
      `setVisibleColumns(list)`, `resetColumns()`, `setAutoHideEmpty(bool)`;
    - Python-facing signals `holdRequested(str)`, `fulfillRequested(str)`,
      `excludeRequested(str)`, `lineRemovalRequested(str, int, str)`,
      `tagAddRequested(str, str)`, `tagRemovalRequested(str, str)`,
      `columnSettingsChanged(dict)`;
    - methods `set_column_settings(raw)` and `set_tag_categories(dict)`.

- [ ] **Step 1: Write the failing tests.** Append to `tests/test_results_bridge.py`:

Extend the file's existing `from gui.results_bridge import …` line with
`normalize_column_settings`. Add it after the tests that use it exist, because
of the write hook. Then append:

```python
def test_normalize_column_settings_cleans_junk():
    assert normalize_column_settings(None) == {"order": None, "visible": None, "auto_hide_empty": False}
    assert normalize_column_settings(
        {"order": ["age", 3, "age", "lines"], "visible": "x", "auto_hide_empty": 1}
    ) == {"order": ["age", "lines"], "visible": None, "auto_hide_empty": True}


@pytest.mark.parametrize(
    ("slot", "args", "signal"),
    [
        ("holdOrder", ("#1",), "holdRequested"),
        ("fulfillOrder", ("#1",), "fulfillRequested"),
        ("excludeOrder", ("#1",), "excludeRequested"),
        ("removeLine", ("#1", 2, "SKU-A"), "lineRemovalRequested"),
        ("addOrderTag", ("#1", "vip"), "tagAddRequested"),
        ("removeOrderTag", ("#1", "vip"), "tagRemovalRequested"),
    ],
)
def test_each_pane_verb_is_a_request_python_hears(qtbot, slot, args, signal):
    bridge = ResultsBridge()
    with qtbot.waitSignal(getattr(bridge, signal), timeout=1000) as blocker:
        getattr(bridge, slot)(*args)
    assert tuple(blocker.args) == args


def test_column_slots_store_names_and_announce_them(qtbot):
    bridge = ResultsBridge()
    with qtbot.waitSignal(bridge.columnSettingsChanged, timeout=1000) as blocker:
        bridge.setColumnOrder(["age", "lines"])
    assert blocker.args[0] == {"order": ["age", "lines"], "visible": None, "auto_hide_empty": False}
    bridge.setVisibleColumns(["age"])
    bridge.setAutoHideEmpty(True)
    assert bridge.columns["visible"] == ["age"]
    bridge.resetColumns()
    assert bridge.columns["order"] is None
    assert bridge.columns["visible"] is None
    assert bridge.columns["auto_hide_empty"] is True


def test_set_orders_names_the_clients_extra_order_columns(qapp):
    bridge = ResultsBridge()
    df = pd.DataFrame(
        [
            {"Order_Number": "1", "SKU": "A", "Channel": "web"},
            {"Order_Number": "1", "SKU": "B", "Channel": "web"},
            {"Order_Number": "2", "SKU": "C", "Channel": "shop"},
        ]
    )
    bridge.set_orders(df)
    assert bridge.columns["extras"] == ["Channel"]


def test_set_column_settings_keeps_extras(qapp):
    bridge = ResultsBridge()
    bridge._columns["extras"] = ["Channel"]
    bridge.set_column_settings({"visible": ["age"]})
    assert bridge.columns == {"order": None, "visible": ["age"], "auto_hide_empty": False, "extras": ["Channel"]}


def test_copy_text_reaches_the_clipboard(qapp):
    from PySide6.QtGui import QGuiApplication

    ResultsBridge().copyText("#10445")
    assert QGuiApplication.clipboard().text() == "#10445"


def test_tag_categories_notify(qtbot):
    bridge = ResultsBridge()
    with qtbot.waitSignal(bridge.tagCategoriesChanged, timeout=1000):
        bridge.set_tag_categories({"prio": {"label": "Priority", "tags": ["vip"]}})
    assert bridge.tagCategories["prio"]["tags"] == ["vip"]
```

In the SKU line `{"Order_Number": "1", "SKU": "A", "Channel": "web"}`,
`Channel` is constant across order 1's two lines, so `classify_columns`
treats it as order-level.

- [ ] **Step 2: Run and see the tests fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_results_bridge.py -q`
Expected: the new tests FAIL (ImportError or AttributeError).

- [ ] **Step 3: Implement.** In `gui/results_bridge.py`, extend the import to
  `from gui.orders_view import ORDER_KEY, ORDER_LEVEL_COLUMNS, classify_columns, order_payload, results_summary`,
  and add a module function:

```python
def normalize_column_settings(raw) -> dict:
    """A stored column layout, made safe to hand to the page (Bundle 13 §3.2).

    Python stores names only: titles, groups, defaults and pinning are the
    page's (columns.js). None means "use the page's default".
    """
    raw = raw if isinstance(raw, dict) else {}

    def names(value):
        if not isinstance(value, list):
            return None
        return list(dict.fromkeys(v for v in value if isinstance(v, str)))

    return {
        "order": names(raw.get("order")),
        "visible": names(raw.get("visible")),
        "auto_hide_empty": bool(raw.get("auto_hide_empty", False)),
    }
```

Add these to the class:

```python
    columnsChanged = Signal()
    tagCategoriesChanged = Signal()
    # Python-facing (Bundle 13): the pane's verbs and the column layout.
    holdRequested = Signal(str)
    fulfillRequested = Signal(str)
    excludeRequested = Signal(str)
    lineRemovalRequested = Signal(str, int, str)
    tagAddRequested = Signal(str, str)
    tagRemovalRequested = Signal(str, str)
    columnSettingsChanged = Signal(dict)
```

In `__init__`:

```python
        self._columns: dict = {**normalize_column_settings(None), "extras": []}
        self._tag_categories: dict = {}
```

The properties:

```python
    def _get_columns(self) -> dict:
        return self._columns

    columns = Property("QVariantMap", _get_columns, notify=columnsChanged)

    def _get_tag_categories(self) -> dict:
        return self._tag_categories

    tagCategories = Property("QVariantMap", _get_tag_categories, notify=tagCategoriesChanged)
```

The slots:

```python
    @Slot(str)
    def holdOrder(self, order_number) -> None:
        self.holdRequested.emit(str(order_number))

    @Slot(str)
    def fulfillOrder(self, order_number) -> None:
        self.fulfillRequested.emit(str(order_number))

    @Slot(str)
    def excludeOrder(self, order_number) -> None:
        self.excludeRequested.emit(str(order_number))

    @Slot(str, int, str)
    def removeLine(self, order_number, line_index, sku) -> None:
        self.lineRemovalRequested.emit(str(order_number), int(line_index), str(sku))

    @Slot(str, str)
    def addOrderTag(self, order_number, tag) -> None:
        self.tagAddRequested.emit(str(order_number), str(tag))

    @Slot(str, str)
    def removeOrderTag(self, order_number, tag) -> None:
        self.tagRemovalRequested.emit(str(order_number), str(tag))

    @Slot(str)
    def copyText(self, text) -> None:
        # navigator.clipboard is not dependable under the page's file:// base.
        QGuiApplication.clipboard().setText(str(text))

    @Slot("QVariantList")
    def setColumnOrder(self, names) -> None:
        self._store_columns(order=names)

    @Slot("QVariantList")
    def setVisibleColumns(self, names) -> None:
        self._store_columns(visible=names)

    @Slot()
    def resetColumns(self) -> None:
        self._store_columns(order=None, visible=None)

    @Slot(bool)
    def setAutoHideEmpty(self, on) -> None:
        self._store_columns(auto_hide_empty=bool(on))

    def _store_columns(self, **changes) -> None:
        stored = normalize_column_settings({**self._columns, **changes})
        self._columns = {**stored, "extras": self._columns["extras"]}
        self.columnsChanged.emit()
        self.columnSettingsChanged.emit(stored)
```

The Python-facing API:

```python
    def set_column_settings(self, raw) -> None:
        self._columns = {**normalize_column_settings(raw), "extras": self._columns["extras"]}
        self.columnsChanged.emit()

    def set_tag_categories(self, categories: dict) -> None:
        self._tag_categories = dict(categories or {})
        self.tagCategoriesChanged.emit()
```

In `set_orders`, before the emits, add:

```python
        extras = []
        if df is not None and not df.empty and ORDER_KEY in df.columns:
            order_level, _ = classify_columns(df)
            extras = [c for c in order_level if c not in ORDER_LEVEL_COLUMNS]
        if extras != self._columns["extras"]:
            self._columns = {**self._columns, "extras": extras}
            self.columnsChanged.emit()
```

Change the Qt import to
`from PySide6.QtGui import QGuiApplication`, beside the existing `QtCore`
import, **after** `copyText` exists (the write hook).

- [ ] **Step 4: Update the catalogue.** In the Bundle 11 spec §5.2 table:
  - Strike the rows `columns: list[{name, visible, pinned}]` and
    `setColumnVisible(name: str, visible: bool)`, writing "amended by
    Bundle 13 spec §4".
  - Replace `one slot per pane action…` with the Bundle 13 rows from the
    Bundle 13 spec §4, marked `13`.
  - Change the header docstring of `gui/results_bridge.py` to also cite
    `2026-09-11-phase9-bundle13-pane-columns-design.md section 4`.

- [ ] **Step 5: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_results_bridge.py tests/test_results_document.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
/usr/bin/git add gui/results_bridge.py tests/test_results_bridge.py docs/superpowers/specs/2026-09-11-phase9-bundle11-seam-design.md
/usr/bin/git commit -m "Bundle 13: pane verbs and column layout cross the bridge"
```

### Task 4: The pane's verbs on `ActionsHandler`

**Files:**
- Modify: `gui/actions_handler.py` (next to `toggle_fulfillment_status_for_order`, ≈L838)
- Create: `tests/test_pane_actions.py`

**Interfaces:**
- Consumes: the existing `toggle_fulfillment_status_for_order(order_number)`,
  `remove_item_from_order(order_number, sku, row_position, row_snapshot=None)`,
  `shopify_tool.tag_manager.add_tag` / `remove_tag` / `has_tag`, and
  `undo_manager.record_operation(operation_type, description, params, affected_rows_before)`.
- Produces:
  - `ActionsHandler.set_order_fulfillable(order_number, fulfillable: bool)`
  - `ActionsHandler.remove_line(order_number, line_index: int, sku)`
  - `ActionsHandler.add_internal_tag(order_number, tag)`
  - `ActionsHandler.remove_internal_tag(order_number, tag)`

- [ ] **Step 1: Write the failing tests**

```python
"""The detail pane's verbs on ActionsHandler (Bundle 13 spec §7.2)."""

import pandas as pd
import pytest


@pytest.fixture
def main_window(qapp, monkeypatch):
    from gui.main_window_pyside import MainWindow

    window = MainWindow()
    monkeypatch.setattr(window, "save_session_state", lambda: None)
    window.undo_manager.reset_for_session()
    yield window
    window.close()


def _frame():
    return pd.DataFrame(
        [
            {"Order_Number": "1001", "Order_Fulfillment_Status": "Fulfillable",
             "SKU": "A", "Quantity": 1, "Final_Stock": 5, "Internal_Tags": "[]"},
            {"Order_Number": "1001", "Order_Fulfillment_Status": "Fulfillable",
             "SKU": "A", "Quantity": 2, "Final_Stock": 5, "Internal_Tags": "[]"},
            {"Order_Number": "1002", "Order_Fulfillment_Status": "Not Fulfillable",
             "SKU": "B", "Quantity": 1, "Final_Stock": 0, "Internal_Tags": '["vip"]'},
        ]
    )


def _tags(window, order):
    df = window.analysis_results_df
    return df.loc[df["Order_Number"] == order, "Internal_Tags"].tolist()


def test_set_order_fulfillable_toggles_only_when_the_status_differs(main_window, monkeypatch):
    main_window.analysis_results_df = _frame()
    calls = []
    handler = main_window.actions_handler
    monkeypatch.setattr(handler, "toggle_fulfillment_status_for_order", calls.append)
    handler.set_order_fulfillable("1001", True)
    handler.set_order_fulfillable("1002", False)
    handler.set_order_fulfillable("9999", True)
    assert calls == []
    handler.set_order_fulfillable(" 1001 ", False)
    assert calls == [" 1001 "]


def test_remove_line_removes_the_indexed_one_of_two_same_sku_lines(main_window):
    main_window.analysis_results_df = _frame()
    main_window.actions_handler.remove_line("1001", 1, "A")
    df = main_window.analysis_results_df
    assert df.loc[df["Order_Number"] == "1001", "Quantity"].tolist() == [1]


@pytest.mark.parametrize(("index", "sku"), [(2, "A"), (-1, "A"), (0, "B")])
def test_remove_line_refuses_a_line_that_moved(main_window, index, sku):
    main_window.analysis_results_df = _frame()
    main_window.actions_handler.remove_line("1001", index, sku)
    assert len(main_window.analysis_results_df) == 3


def test_an_internal_tag_lands_on_every_line_and_undo_takes_it_back(main_window):
    main_window.analysis_results_df = _frame()
    main_window.actions_handler.add_internal_tag("1001", " rush ")
    assert all("rush" in t for t in _tags(main_window, "1001"))
    ok, _message = main_window.undo_manager.undo()
    assert ok
    assert all("rush" not in t for t in _tags(main_window, "1001"))


def test_removing_an_internal_tag(main_window):
    main_window.analysis_results_df = _frame()
    main_window.actions_handler.remove_internal_tag("1002", "vip")
    assert "vip" not in _tags(main_window, "1002")[0]
    assert main_window.undo_manager.can_undo()


def test_a_blank_or_absent_tag_records_nothing(main_window):
    main_window.analysis_results_df = _frame()
    main_window.actions_handler.add_internal_tag("1001", "   ")
    main_window.actions_handler.remove_internal_tag("1001", "never-there")
    assert main_window.undo_manager.can_undo() is False
```

- [ ] **Step 2: Run and see the tests fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_pane_actions.py -v`
Expected: FAIL with `AttributeError: 'ActionsHandler' object has no attribute 'set_order_fulfillable'`.

If `undo()` or `reset_for_session()` fails because no session is open, give
the fixture a session: point `window.session_path` at a `tmp_path` directory.
Fix the fixture, not the assertions.

- [ ] **Step 3: Implement.** Add to `ActionsHandler`:

```python
    def _order_mask(self, order_number):
        df = self.mw.analysis_results_df
        return df["Order_Number"].astype(str).str.strip() == str(order_number).strip()

    def set_order_fulfillable(self, order_number, fulfillable: bool):
        """The pane's Hold / Mark fulfillable. A no-op when already so, so a
        page that is one push behind cannot flip an order the wrong way."""
        df = self.mw.analysis_results_df
        if df is None or df.empty:
            return
        mask = self._order_mask(order_number)
        if not mask.any():
            self.log.warning(f"Order {order_number} is no longer in the analysis")
            return
        is_fulfillable = df.loc[mask, "Order_Fulfillment_Status"].iloc[0] == "Fulfillable"
        if is_fulfillable != bool(fulfillable):
            self.toggle_fulfillment_status_for_order(order_number)

    def remove_line(self, order_number, line_index: int, sku):
        """The pane's Remove this line: the order's `line_index`-th line, in
        frame order, only while it still carries `sku`."""
        df = self.mw.analysis_results_df
        if df is None or df.empty:
            return
        labels = df.index[self._order_mask(order_number)]
        if not 0 <= line_index < len(labels):
            self.log.warning("Aborted line removal: the line is gone")
            return
        label = labels[line_index]
        own_sku = df.loc[label, "SKU"]
        own = "" if pd.isna(own_sku) else str(own_sku).strip()
        if own != str(sku).strip():
            self.log.warning("Aborted line removal: the line moved")
            return
        # The frame's own SKU value, so a no-SKU line (NaN) still matches.
        self.remove_item_from_order(order_number, own_sku, df.index.get_loc(label))

    def add_internal_tag(self, order_number, tag):
        self._change_internal_tag(order_number, tag, adding=True)

    def remove_internal_tag(self, order_number, tag):
        self._change_internal_tag(order_number, tag, adding=False)

    def _change_internal_tag(self, order_number, tag, adding: bool):
        """Restored from Bundle 12's deleted MainWindow._apply_tag_operation."""
        from shopify_tool.tag_manager import add_tag, has_tag, remove_tag

        tag = str(tag).strip()
        df = self.mw.analysis_results_df
        if not tag or df is None or df.empty:
            return
        mask = self._order_mask(order_number)
        if not mask.any():
            return
        if "Internal_Tags" not in df.columns:
            if not adding:
                return
            df["Internal_Tags"] = "[]"
        if not adding and not df.loc[mask, "Internal_Tags"].map(lambda t: has_tag(t, tag)).any():
            return

        affected_rows_before = df[mask].copy()
        change = add_tag if adding else remove_tag
        df.loc[mask, "Internal_Tags"] = df.loc[mask, "Internal_Tags"].apply(lambda t: change(t, tag))
        description = (
            f"Added internal tag '{tag}' to order {order_number}"
            if adding
            else f"Removed internal tag '{tag}' from order {order_number}"
        )
        self.mw.undo_manager.record_operation(
            "add_internal_tag" if adding else "remove_internal_tag",
            description,
            {"order_number": order_number, "tag": tag},
            affected_rows_before,
        )
        self.data_changed.emit()
        self.mw.save_session_state()
        self._update_undo_button()
        self.mw.log_activity("Internal Tag", description)
```

`pd` is already imported in `actions_handler.py`; check it with
`grep -n "^import pandas" gui/actions_handler.py`.

- [ ] **Step 4: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_pane_actions.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
/usr/bin/git add gui/actions_handler.py tests/test_pane_actions.py
/usr/bin/git commit -m "Bundle 13: Hold, Mark fulfillable, Remove line and tags for one order"
```

---

### Task 5: Main window — wiring, column layout, tag categories; the Qt column manager goes

**Files:**
- Modify: `gui/ui_manager.py` (`_create_tab2_analysis_results`, ≈L619–629)
- Modify: `gui/main_window_pyside.py`:
  - ≈L164–166, where `TableConfigManager` is built;
  - ≈L180–196, `load_client_config`;
  - ≈L519–530, `_load_client_data`;
  - ≈L575–609, `_on_client_data_loaded`;
  - new methods.
- Modify: `gui/actions_handler.py`, the three places that set
  `self.mw.active_profile_config` (≈L375, ≈L422, ≈L484).
- Modify: `tests/test_results_screen.py` (append), `tests/test_message_routes.py`
- Modify (comments only): `gui/settings/report_editor.py` ≈L138,
  `gui/report_selection_dialog.py` ≈L205
- Delete: `gui/column_config_dialog.py`, `gui/table_config_manager.py`,
  `tests/test_column_config_dialog.py`, `tests/test_table_config_manager.py`

**Interfaces:**
- Consumes (Task 3): bridge signals `holdRequested`, `fulfillRequested`,
  `excludeRequested`, `lineRemovalRequested`, `tagAddRequested`,
  `tagRemovalRequested`, `columnSettingsChanged`, plus `set_column_settings`,
  `set_tag_categories` and `normalize_column_settings`.
- Consumes (Task 4): the four `ActionsHandler` methods.
- Produces:
  - `MainWindow.schedule_results_columns_save(settings: dict)`
  - `MainWindow._write_results_columns(client_id, settings)`
  - `MainWindow.push_tag_categories()`
  - `MainWindow._load_client_data(client_id) -> (shopify_config, column_settings)`

- [ ] **Step 1: Write the failing tests.** Append to `tests/test_results_screen.py`:

```python
import json


class _Profiles:
    """ProfileManager's client-config surface, in memory."""

    def __init__(self):
        self.client = {}
        self.saved = 0

    def load_client_config(self, client_id):
        return json.loads(json.dumps(self.client))

    def save_client_config(self, client_id, config):
        self.client = config
        self.saved += 1
        return True

    def load_shopify_config(self, client_id):
        return {"tag_categories": {}}


def test_the_column_layout_round_trips_through_the_client_config(main_window, qtbot, monkeypatch):
    profiles = _Profiles()
    monkeypatch.setattr(main_window, "profile_manager", profiles)
    main_window.current_client_id = "ACME"
    layout = {"order": ["age"], "visible": ["age", "type"], "auto_hide_empty": True}
    main_window.schedule_results_columns_save(layout)
    qtbot.waitUntil(lambda: profiles.saved == 1, timeout=5000)
    assert profiles.client["ui_settings"]["results_columns"] == layout
    _shopify, settings = main_window._load_client_data("ACME")
    assert settings == layout


@pytest.mark.parametrize(
    ("signal", "args", "handler", "expected"),
    [
        ("holdRequested", ("1001",), "set_order_fulfillable", ("1001", False)),
        ("fulfillRequested", ("1001",), "set_order_fulfillable", ("1001", True)),
        ("excludeRequested", ("1001",), "remove_entire_order", ("1001",)),
        ("lineRemovalRequested", ("1001", 0, "A"), "remove_line", ("1001", 0, "A")),
        ("tagAddRequested", ("1001", "vip"), "add_internal_tag", ("1001", "vip")),
        ("tagRemovalRequested", ("1001", "vip"), "remove_internal_tag", ("1001", "vip")),
    ],
)
def test_each_pane_request_reaches_its_handler(main_window, monkeypatch, signal, args, handler, expected):
    calls = []
    monkeypatch.setattr(main_window.actions_handler, handler, lambda *a: calls.append(a))
    getattr(main_window.results_bridge, signal).emit(*args)
    assert calls == [expected]


def test_the_profiles_tag_categories_reach_the_page(main_window):
    main_window.active_profile_config = {
        "tag_categories": {"prio": {"label": "Priority", "color": "#e53935", "tags": ["vip"]}}
    }
    main_window.push_tag_categories()
    assert main_window.results_bridge.tagCategories["prio"]["tags"] == ["vip"]


GONE_COLUMN_MANAGER = re.compile(
    r"ColumnConfigPanel|ColumnConfigDialog|TableConfigManager|table_config_manager|column_config_dialog"
)


def test_the_qt_column_manager_is_gone():
    root = Path(__file__).resolve().parents[1]
    hits = [
        f"{path.relative_to(root)}:{number}"
        for base in ("gui", "tests")
        for path in sorted((root / base).rglob("*.py"))
        if path.name != "test_results_screen.py"  # this pattern names them
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if GONE_COLUMN_MANAGER.search(line)
    ]
    assert hits == []
```

If `_normalize_tag_categories` rewrites that dict's shape, assert on whatever
it returns for it. Read `shopify_tool/tag_manager.py:267` first.

- [ ] **Step 2: Run and see the tests fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_results_screen.py -q`
Expected: the five new tests FAIL.

- [ ] **Step 3: Wire the bridge.** In `ui_manager._create_tab2_analysis_results`,
  after the `screenMenuRequested` connection, add:

```python
        # The detail pane's verbs (Bundle 13 spec §7.1). Resolved at call
        # time: actions_handler is built after this tab.
        def actions():
            return self.mw.actions_handler

        bridge.holdRequested.connect(lambda n: actions().set_order_fulfillable(n, False))
        bridge.fulfillRequested.connect(lambda n: actions().set_order_fulfillable(n, True))
        bridge.excludeRequested.connect(lambda n: actions().remove_entire_order(n))
        bridge.lineRemovalRequested.connect(lambda n, i, s: actions().remove_line(n, i, s))
        bridge.tagAddRequested.connect(lambda n, t: actions().add_internal_tag(n, t))
        bridge.tagRemovalRequested.connect(lambda n, t: actions().remove_internal_tag(n, t))
        bridge.columnSettingsChanged.connect(lambda s: self.mw.schedule_results_columns_save(s))
```

- [ ] **Step 4: Column layout, load and save.** In `gui/main_window_pyside.py`:

  **a.** Delete the `TableConfigManager` import and construction (≈L164–166),
  along with any `try`/`if` that wraps only them.

  **b.** Replace `_load_client_data`'s body and docstring with:

```python
    def _load_client_data(self, client_id: str):
        """Worker-thread IO for a client switch.

        Returns (shopify_config, column_settings): the results table's saved
        column layout, normalized (Bundle 13 spec §7.3).
        """
        shopify_config = self.profile_manager.load_shopify_config(client_id)
        client_config = self.profile_manager.load_client_config(client_id) or {}
        column_settings = normalize_column_settings(
            (client_config.get("ui_settings") or {}).get("results_columns")
        )
        return shopify_config, column_settings
```

  **c.** In `_on_client_data_loaded`: unpack
  `shopify_config, column_settings = result`, delete the
  `if table_config is not None:` block, and put this right after
  `self.load_client_config(client_id)`:

```python
            self.results_bridge.set_column_settings(column_settings)
```

  **d.** Add the methods:

```python
    def schedule_results_columns_save(self, settings: dict):
        """Debounced: a drag sends a burst of layouts, the share gets one write."""
        self._pending_columns = (self.current_client_id, dict(settings))
        if not hasattr(self, "_columns_save_timer"):
            self._columns_save_timer = QTimer(self)
            self._columns_save_timer.setSingleShot(True)
            self._columns_save_timer.setInterval(500)
            self._columns_save_timer.timeout.connect(self._flush_results_columns)
        self._columns_save_timer.start()

    def _flush_results_columns(self):
        client_id, settings = self._pending_columns
        if not client_id:
            return
        worker = Worker(self._write_results_columns, client_id, settings)
        # A layout preference: a failed write is logged, and the next change retries.
        worker.signals.error.connect(
            lambda error: logger.warning(f"The column layout wasn't saved: {error[1]}")
        )
        self._columns_save_worker = worker  # see _client_load_worker for why
        QThreadPool.globalInstance().start(worker)

    def _write_results_columns(self, client_id: str, settings: dict):
        config = self.profile_manager.load_client_config(client_id) or {}
        config.setdefault("ui_settings", {})["results_columns"] = settings
        self.profile_manager.save_client_config(client_id, config)

    def push_tag_categories(self):
        """The profile's tag vocabulary, for the pane's "+ Tag" menu."""
        if hasattr(self, "results_bridge"):
            self.results_bridge.set_tag_categories(
                _normalize_tag_categories((self.active_profile_config or {}).get("tag_categories", {}))
            )
```

  Add the imports **after** their usages exist:
  `from gui.results_bridge import normalize_column_settings` and
  `from shopify_tool.tag_manager import _normalize_tag_categories`. Also add
  `QThreadPool` / `QTimer` to the `PySide6.QtCore` import if either is
  missing.

  **e.** Call `self.push_tag_categories()`:
  - in `load_client_config`, right after `self.active_profile_config = config`;
  - in `actions_handler.py`, right after each of the three
    `self.mw.active_profile_config = …` assignments (≈L375, ≈L484), and after
    `self.mw.active_profile_config["tag_categories"] = updated_categories`
    (≈L422), each as `self.mw.push_tag_categories()`.

- [ ] **Step 5: Delete the Qt column manager**

```bash
/usr/bin/git rm gui/column_config_dialog.py gui/table_config_manager.py tests/test_column_config_dialog.py tests/test_table_config_manager.py
```

Then clean up what referenced it:
- Remove the `("gui/column_config_dialog.py", "*"): …` entry from
  `tests/test_message_routes.py`.
- Reword the comments at `gui/settings/report_editor.py` ≈L138 and
  `gui/report_selection_dialog.py` ≈L205 so they describe the pattern without
  naming the deleted file.
- Run `/usr/bin/git grep -n -E "ColumnConfig|TableConfigManager|table_config|column_config_dialog"`.
  Expected: only `tests/test_results_screen.py` (the pattern), plus any build
  or packaging mention, which you remove too.

- [ ] **Step 6: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_results_screen.py tests/test_message_routes.py tests/test_pane_actions.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
/usr/bin/git add -A gui tests
/usr/bin/git commit -m "Bundle 13: pane requests reach their handlers; column layout saved per client; Qt column manager deleted"
```

### Task 6: Settings › Mappings › Additional columns

**Files:**
- Modify: `gui/settings/mappings.py`: `_MappingPageBase._load_headers_from_csv`
  and `OrdersMappingPage`
- Modify: `gui/settings/window.py`, where it builds `OrdersMappingPage` (≈L230)
- Create: `tests/test_settings_additional_columns.py`

**Interfaces:**
- Consumes (Task 2): `shopify_tool.core.effective_additional_columns`.
  Also `shopify_tool.csv_utils.discover_additional_columns(orders_df,
  column_mappings, current_additional_columns) -> list[dict]`, whose entries
  carry the keys `csv_name`, `internal_name`, `enabled`, `is_order_level` and
  `exists_in_df`.
- Produces:
  - `OrdersMappingPage(column_mappings, courier_mappings, fallback_additional_columns=None, parent=None)`
  - `page.additional_entries: list[dict]`
  - `page.additional_container: QWidget`
  - `_MappingPageBase._headers_loaded(headers)`, a no-op hook

- [ ] **Step 1: Write the failing tests**

```python
"""Additional columns on Settings › Mappings (Bundle 13 spec §7.5, ADR 0006)."""

from PySide6.QtWidgets import QCheckBox

from gui.settings.mappings import OrdersMappingPage


def _entry(name, enabled=False):
    return {"csv_name": name, "internal_name": name, "enabled": enabled,
            "is_order_level": True, "exists_in_df": True}


def test_without_the_key_the_page_shows_the_old_client_config_list(qapp):
    page = OrdersMappingPage({"orders": {}}, {}, fallback_additional_columns=[_entry("Email")])
    assert [e["csv_name"] for e in page.additional_entries] == ["Email"]


def test_the_mappings_key_wins_over_the_fallback(qapp):
    page = OrdersMappingPage(
        {"orders": {}, "additional_columns": []}, {}, fallback_additional_columns=[_entry("Email")]
    )
    assert page.additional_entries == []


def test_loading_headers_lists_the_unmapped_columns(qapp, monkeypatch):
    page = OrdersMappingPage({"orders": {"Name": "Order_Number", "Lineitem sku": "SKU"}}, {})
    monkeypatch.setattr(
        "gui.settings.mappings.QFileDialog.getOpenFileName", lambda *a, **k: ("orders.csv", "")
    )
    monkeypatch.setattr(
        "gui.settings.mappings.read_csv_headers", lambda path: ["Name", "Lineitem sku", "Email", "Phone"]
    )
    page._load_headers_from_csv()
    assert [e["csv_name"] for e in page.additional_entries] == ["Email", "Phone"]


def test_collect_writes_the_list_and_snapshot_sees_a_toggle(qapp):
    mappings = {"orders": {}}
    page = OrdersMappingPage(mappings, {}, fallback_additional_columns=[_entry("Email")])
    before = page.snapshot()
    box = next(b for b in page.additional_container.findChildren(QCheckBox) if b.text() == "Email")
    box.setChecked(True)
    assert page.snapshot() != before
    result = page.collect()
    assert result["column_mappings"]["additional_columns"][0]["enabled"] is True
    assert mappings["additional_columns"][0]["enabled"] is True  # the live dict
```

If the mapping widget's `get_mappings()` also returns `Name`/`Lineitem sku`
rows under a different key shape, check `gui/column_mapping_widget.py:114`
and adjust the constructor's `orders` dict to that shape. Do not change the
assertion.

- [ ] **Step 2: Run and see the tests fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_settings_additional_columns.py -v`
Expected: FAIL with `TypeError: … unexpected keyword argument 'fallback_additional_columns'`.

- [ ] **Step 3: Implement the base hook.** In
  `_MappingPageBase._load_headers_from_csv`, after
  `self.mapping_widget.set_available_headers(headers)`, add
  `self._headers_loaded(headers)`. Then add to the class:

```python
    def _headers_loaded(self, headers: list[str]) -> None:
        """Called with a picked CSV's headers after the dropdowns take them."""
```

- [ ] **Step 4: Implement the section** in `OrdersMappingPage`. Change the
  signature to
  `def __init__(self, column_mappings: dict, courier_mappings: dict, fallback_additional_columns=None, parent=None):`.
  Directly after `self.orders_mapping_widget = self.mapping_widget`, add:

```python
        # ADR 0006: the list lives in column_mappings; a profile not saved
        # since Bundle 13 still has it only in the client config.
        source = (
            column_mappings.get("additional_columns")
            if "additional_columns" in column_mappings
            else fallback_additional_columns
        )
        self.additional_entries = [_additional_entry(e) for e in (source or []) if _is_entry(e)]
        additional_box = FormSection(
            "Additional columns",
            "Orders-file columns the analysis carries through under their own names. "
            "Load headers from CSV to list the file's unmapped columns.",
        )
        self.additional_container = QWidget()
        self.additional_layout = QVBoxLayout(self.additional_container)
        self.additional_layout.setContentsMargins(0, 0, 0, 0)
        additional_box.add_widget(self.additional_container)
        self.scroll_layout.addWidget(additional_box)
        self._render_additional_columns()
```

This block must come **before** `courier_box` is added to `scroll_layout`, so
the section sits between the mapping and Courier Mappings. Add these methods:

```python
    def _render_additional_columns(self):
        while self.additional_layout.count():
            widget = self.additional_layout.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()
        if not self.additional_entries:
            empty = QLabel(
                "No additional columns yet. Load headers from CSV to list the file's unmapped columns."
            )
            empty.setWordWrap(True)
            _secondary(empty)
            self.additional_layout.addWidget(empty)
            return
        for entry in self.additional_entries:
            row = QWidget()
            layout = QHBoxLayout(row)
            layout.setContentsMargins(0, 2, 0, 2)
            enabled = QCheckBox(entry["csv_name"])
            enabled.setChecked(bool(entry.get("enabled")))
            enabled.toggled.connect(lambda on, e=entry: e.__setitem__("enabled", on))
            order_level = QCheckBox("Order-level")
            order_level.setChecked(bool(entry.get("is_order_level", True)))
            order_level.setToolTip("Filled down onto every line of a multi-line order")
            order_level.toggled.connect(lambda on, e=entry: e.__setitem__("is_order_level", on))
            layout.addWidget(enabled)
            layout.addStretch()
            layout.addWidget(order_level)
            if entry.get("exists_in_df") is False:
                missing = QLabel("Not in this file")
                _secondary(missing)
                layout.addWidget(missing)
            self.additional_layout.addWidget(row)

    def _headers_loaded(self, headers):
        self.additional_entries = discover_additional_columns(
            pd.DataFrame(columns=headers),
            {"orders": self.mapping_widget.get_mappings()},
            self.additional_entries,
        )
        self._render_additional_columns()
```

Add these module-level helpers:

```python
def _is_entry(value) -> bool:
    return isinstance(value, dict) and bool(value.get("csv_name"))


def _additional_entry(value: dict) -> dict:
    """A stored entry with every key discover_additional_columns reads."""
    name = str(value["csv_name"])
    return {
        "csv_name": name,
        "internal_name": value.get("internal_name") or name.strip().replace(" ", "_").replace("-", "_"),
        "enabled": bool(value.get("enabled", False)),
        "is_order_level": bool(value.get("is_order_level", True)),
        "exists_in_df": value.get("exists_in_df", True),
    }


def _secondary(label: QLabel) -> None:
    on_theme_changed(label, lambda t: label.setStyleSheet(f"color: {t.text_secondary};"))
```

Change `OrdersMappingPage.snapshot` and `collect`:

```python
    def snapshot(self) -> str:
        return json.dumps(
            [super().snapshot(), self._courier_rows(), self.additional_entries],
            sort_keys=True,
            default=str,
        )

    def collect(self) -> dict:
        new_couriers = self._courier_rows()
        self.courier_mappings.clear()
        self.courier_mappings.update(new_couriers)
        mappings = self._collect_column_mappings()
        mappings["additional_columns"] = [dict(e) for e in self.additional_entries]
        return {"column_mappings": mappings, "courier_mappings": self.courier_mappings}
```

Keep the existing comment in `collect`. Add the imports after their usages:
`import pandas as pd`, `QCheckBox` in the `QtWidgets` import, and
`from shopify_tool.csv_utils import discover_additional_columns` beside
`read_csv_headers`.

- [ ] **Step 5: Pass the fallback from the window.** In `gui/settings/window.py`:

```python
            OrdersMappingPage(
                self.config_data.get("column_mappings", {}),
                self.config_data.get("courier_mappings", {}),
                fallback_additional_columns=self._stored_additional_columns(),
            ),
```

Add this method to the window class:

```python
    def _stored_additional_columns(self) -> list:
        """The list's pre-Bundle-13 home, read only as a fallback (ADR 0006)."""
        try:
            client_config = self.profile_manager.load_client_config(self.client_id) or {}
        except Exception:
            logger.exception("The client config's additional columns couldn't be read")
            return []
        return effective_additional_columns({}, client_config)
```

Import it: `from shopify_tool.core import effective_additional_columns`.

- [ ] **Step 6: Run the Settings suites**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_settings_additional_columns.py tests/ -q -k "settings or mapping"`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
/usr/bin/git add gui/settings/mappings.py gui/settings/window.py tests/test_settings_additional_columns.py
/usr/bin/git commit -m "Bundle 13: additional columns editable again, on Settings › Mappings"
```

---

### Task 7: The slot grid and the column registry (web)

**Files:**
- Create: `gui/web/columns.js` (registry now; the manager arrives in Task 9)
- Create: `gui/web/pane.js` (stubs now; filled in Task 8)
- Modify: `gui/web/results.html`, `gui/web/results.css`, `gui/web/results.js`
- Create: `tests/test_results_columns.py`

**Interfaces:**
- Consumes (Task 3): `bridge.columns` / `columnsChanged` and
  `bridge.set_column_settings`.
- Produces (page globals that later tasks use):
  - Registry: `REGISTRY`, `COLUMN_GROUPS`, `PINNED_KEYS`, `allColumns()`,
    `orderedColumns()`, `userVisible(col)`, `autoHidden(col)`,
    `visibleColumns()`, `storeColumns(changes, send)`.
  - Table and slot: `refreshColumns()`, `renderSlot()`, `slotMode()`.
  - State fields: `state.columnSettings`, `state.emptyKeys`, `state.narrow`,
    `state.paneHidden`, `state.paneForced`, `state.columnsOpen`.
  - Hooks later tasks fill: `renderPane()`, `bindPane()`,
    `renderColumnsPanel()`, `bindColumns()`.

- [ ] **Step 1: Write the failing tests** in `tests/test_results_columns.py`:

```python
"""The slot and the column registry (Bundle 13 spec §6.1, §6.8), through Chromium.

Sizes are the page area: 1310x692 is the page at 1366x768. Never mark skip.
"""

import json

import pytest
from PySide6.QtWebEngineWidgets import QWebEngineView
from test_results_bridge import _eval, _until_js
from test_results_document import results_lines

from gui.results_bridge import mount_results_page


@pytest.fixture
def doc(qtbot):
    view = QWebEngineView()
    qtbot.addWidget(view)
    bridge = mount_results_page(view)
    view.resize(1310, 692)
    view.show()
    _until_js(qtbot, view, "document.documentElement.dataset.bridge === 'ready'")
    bridge.set_export_enabled(True)
    bridge.set_orders(results_lines())
    _until_js(qtbot, view, "document.querySelectorAll('#rows .row').length > 0")
    return view, bridge


def _json(qtbot, view, expr):
    return json.loads(_eval(qtbot, view, f"JSON.stringify({expr})"))


HEADERS = "[...document.querySelectorAll('#header .cell')].map(c => c.textContent.trim()).filter(Boolean)"


def _has_header(title):
    return f"{HEADERS}.includes({title!r})"


def _width(qtbot, view, selector):
    return _eval(
        qtbot, view, f"Math.round(document.querySelector({selector!r}).getBoundingClientRect().width)"
    )


def test_the_pane_slot_leaves_the_table_866_wide_and_17_rows(qtbot, doc):
    view, _ = doc
    assert _eval(qtbot, view, "document.getElementById('table-area').dataset.slot") == "pane"
    assert _width(qtbot, view, ".table-wrap") == 866
    assert _width(qtbot, view, "#slot") == 400
    assert _eval(qtbot, view, "document.getElementById('table').dataset.visibleRows") == "17"


def test_the_columns_button_counts_shown_of_total(qtbot, doc):
    view, _ = doc
    assert _eval(qtbot, view, "document.getElementById('columns-button').textContent") == "Columns 8/18"


def test_a_saved_layout_orders_and_hides_columns(qtbot, doc):
    view, bridge = doc
    bridge.set_column_settings({"order": ["age", "units"], "visible": ["age", "type"]})
    _until_js(qtbot, view, _has_header("Type"))
    assert _json(qtbot, view, HEADERS) == ["Status", "Order", "Age", "Type"]


def test_hiding_customer_leaves_a_filler_not_a_stretched_column(qtbot, doc):
    view, bridge = doc
    bridge.set_column_settings({"visible": ["lines"]})
    _until_js(qtbot, view, "document.querySelector('#rows .row .cell.filler') !== null")


def test_auto_hide_drops_a_column_empty_in_every_order(qtbot, doc):
    view, bridge = doc  # results_lines() has no Subtotal column
    bridge.set_column_settings({"visible": ["subtotal", "lines"], "auto_hide_empty": False})
    _until_js(qtbot, view, _has_header("Subtotal"))
    bridge.set_column_settings({"visible": ["subtotal", "lines"], "auto_hide_empty": True})
    _until_js(qtbot, view, f"!{_has_header('Subtotal')}")


def test_a_clients_extra_order_column_can_be_shown(qtbot, doc):
    view, bridge = doc
    df = results_lines()
    df["Sales_Channel"] = df["Order_Number"].map(lambda n: "web" if int(n[1:]) % 2 else "shop")
    bridge.set_orders(df)
    assert bridge.columns["extras"] == ["Sales_Channel"]
    bridge.set_column_settings({"visible": ["extra:Sales_Channel"]})
    _until_js(qtbot, view, _has_header("Sales Channel"))
```

- [ ] **Step 2: Run and see the tests fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_results_columns.py -v`
Expected: FAIL (no `.table-wrap`, no `#columns-button`).

- [ ] **Step 3: HTML.** In `results.html`:
  - Load the scripts in this order, all `defer`: `columns.js`, `pane.js`,
    `results.js`.
  - Insert this between `#count` and `#screen-menu`:
    `<button id="columns-button" class="btn ghost" type="button" aria-pressed="false" disabled>Columns</button>`
  - Replace the table-area section with:

```html
  <section id="table-area" class="table-area" data-slot="none">
    <div class="table-wrap">
      <!-- #table, #results-empty and #results-no-match exactly as before -->
    </div>
    <div id="slot" class="slot">
      <aside id="pane" class="pane" aria-label="Order detail" hidden></aside>
      <div id="pane-strip" class="pane-strip" hidden>
        <button id="pane-show" class="btn ghost icon strip-button" type="button"
                aria-label="Show the pane" title="Show the pane"></button>
      </div>
      <aside id="columns-panel" class="columns-panel" aria-label="Columns" hidden></aside>
    </div>
  </section>
```

Move the three existing blocks into `.table-wrap` unchanged. That comment is
an instruction, not markup to keep.

- [ ] **Step 4: CSS.** Replace the `.table-area` rule with:

```css
/* The slot (Bundle 13 §6.1): pane or column manager 400 + 12, strip 36. */
.table-area {
  position: relative;
  min-width: 0;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr);
}
.table-area[data-slot="pane"],
.table-area[data-slot="columns"] {
  grid-template-columns: minmax(0, 1fr) 400px;
  column-gap: var(--spacing-md);
}
.table-area[data-slot="strip"] { grid-template-columns: minmax(0, 1fr) 36px; }
.table-area[data-slot="none"] .slot { display: none; }
.table-wrap, .slot { position: relative; min-width: 0; min-height: 0; }
.cell.filler { padding: 0; }
```

- [ ] **Step 5: `gui/web/columns.js`** with this content:

```js
// The column registry (Bundle 13 spec §6.8). Keys are persisted per client,
// so never rename one. Python stores only names; titles, groups, defaults and
// pinning live here. Loaded before results.js: nothing at top level may call
// into it, only function bodies.
"use strict";

const COLUMN_GROUPS = ["Order", "Customer", "Money", "Shipping", "Tags & notes", "Other"];

const REGISTRY = [
  { key: "status", title: "Status", group: "Order", width: 132, pinned: true, shown: true,
    text: (o) => (isFulfillable(o) ? FULFILLABLE : "Blocked"), sortValue: (o) => (isFulfillable(o) ? 0 : 1) },
  { key: "order", title: "Order", group: "Order", width: 84, pinned: true, shown: true, mono: true,
    text: (o) => str(o.Order_Number) },
  { key: "customer", title: "Customer", group: "Customer", stretch: true, shown: true, text: (o) => str(o.Customer) },
  { key: "lines", title: "Lines", group: "Order", width: 56, shown: true, numeric: true,
    text: (o) => fmtInt(o.Items), sortValue: (o) => num(o.Items) },
  { key: "units", title: "Units", group: "Order", width: 56, shown: true, numeric: true,
    text: (o) => fmtInt(o.Units), sortValue: (o) => num(o.Units) },
  { key: "value", title: "Value", group: "Money", width: 84, shown: true, numeric: true,
    text: (o) => fmtMoney(o.Total_Price), sortValue: (o) => num(o.Total_Price) },
  { key: "courier", title: "Courier", group: "Shipping", width: 76, shown: true, text: (o) => str(o.Shipping_Provider) },
  { key: "age", title: "Age", group: "Order", width: 56, shown: true, numeric: true,
    text: (o) => fmtAge(o.Created_At), sortValue: (o) => ageMs(o.Created_At) },
  { key: "type", title: "Type", group: "Order", width: 64, maxWidth: 120, text: (o) => str(o.Order_Type) },
  { key: "reason", title: "Reason", group: "Order", width: 120, maxWidth: 240, text: (o) => str(o.Blocker) },
  { key: "country", title: "Country", group: "Customer", width: 64, maxWidth: 120, text: (o) => str(o.Destination_Country) },
  { key: "subtotal", title: "Subtotal", group: "Money", width: 84, numeric: true,
    text: (o) => fmtMoney(o.Subtotal), sortValue: (o) => num(o.Subtotal) },
  { key: "method", title: "Shipping method", group: "Shipping", width: 120, maxWidth: 240, text: (o) => str(o.Shipping_Method) },
  { key: "internal_tags", title: "Internal tags", group: "Tags & notes", width: 120, maxWidth: 240,
    text: (o) => (o.Tag_List || []).map(String).join(", ") },
  { key: "shopify_tags", title: "Shopify tags", group: "Tags & notes", width: 120, maxWidth: 240, text: (o) => str(o.Tags) },
  { key: "notes", title: "Notes", group: "Tags & notes", width: 160, maxWidth: 240, text: (o) => str(o.Notes) },
  { key: "status_note", title: "Status note", group: "Tags & notes", width: 120, maxWidth: 240, text: (o) => str(o.Status_Note) },
  { key: "repeat", title: "Repeat", group: "Tags & notes", width: 64, text: (o) => (o._repeat === true ? "Repeat" : "") },
];
const PINNED_KEYS = REGISTRY.filter((c) => c.pinned).map((c) => c.key);

function allColumns() {
  const extras = (state.columnSettings.extras || []).map((field) => ({
    key: "extra:" + field, title: String(field).replace(/_/g, " "), group: "Other",
    width: 120, maxWidth: 240, text: (o) => str(o[field]),
  }));
  return REGISTRY.concat(extras).map((col) => (col.sortValue ? col : Object.assign({ sortValue: col.text }, col)));
}

// Pinned first, then the saved order, then everything else in registry order.
function orderedColumns() {
  const all = allColumns();
  const byKey = new Map(all.map((c) => [c.key, c]));
  const keys = PINNED_KEYS.slice();
  for (const key of state.columnSettings.order || []) if (byKey.has(key) && !keys.includes(key)) keys.push(key);
  for (const col of all) if (!keys.includes(col.key)) keys.push(col.key);
  return keys.map((key) => byKey.get(key));
}

// The operator's choice, before auto-hide.
function userVisible(col) {
  if (col.pinned) return true;
  const visible = state.columnSettings.visible;
  return visible ? visible.includes(col.key) : Boolean(col.shown);
}

function autoHidden(col) {
  return !col.pinned && Boolean(state.columnSettings.auto_hide_empty) && state.emptyKeys.has(col.key);
}

function visibleColumns() {
  return orderedColumns().filter((col) => userVisible(col) && !autoHidden(col));
}

// Apply a layout change here at once, then tell Python to store it.
function storeColumns(changes, send) {
  state.columnSettings = Object.assign({}, state.columnSettings, changes);
  refreshColumns();
  if (state.bridge) send(state.bridge);
}

function renderColumnsPanel() {} // Task 9
function bindColumns() {} // Task 9
```

- [ ] **Step 6: `gui/web/pane.js`** with this content:

```js
// The order detail pane (Bundle 13 spec §6.2-6.7). Filled in Task 8.
"use strict";

function renderPane() {}
function bindPane() {}
```

- [ ] **Step 7: `results.js`.** Make these changes, and nothing else:
  1. Delete the `COLUMNS` array; the registry replaces it. Add
     `const SELECT_COLUMN = { key: "select", title: "", width: 32 };` and
     `const SLOT_NARROW_PX = 1192; // table minimum 780 + gap 12 + pane 400`.
  2. Add these fields to `state`:
     - `columnSettings: { order: null, visible: null, auto_hide_empty: false, extras: [] }`
     - `emptyKeys: new Set()`
     - `tableCols: [SELECT_COLUMN]`
     - `filler: false`
     - `narrow: false`
     - `paneHidden: false`
     - `paneForced: false`
     - `columnsOpen: false`
  3. In `recompute`, change the sort lookup to
     `allColumns().find((c) => c.key === state.sort.key)`.
  4. In `renderHeader` and `rowElement`, iterate `state.tableCols` instead
     of `COLUMNS`. After the loop, when `state.filler` is true, append
     `<div class="cell filler" role="presentation">`.
  5. Replace `measureColumns` with:

```js
function measureColumns() {
  measureColumns.ctx = measureColumns.ctx || document.createElement("canvas").getContext("2d");
  const ctx = measureColumns.ctx;
  const cols = [SELECT_COLUMN].concat(visibleColumns());
  const body = getComputedStyle(document.body);
  const sans = body.fontSize + " " + body.fontFamily;
  const mono = body.fontSize + " " + cssVar("--font-family-mono");
  const caption = cssVar("--type-caption-size") + " " + body.fontFamily;
  const widths = cols.map((col) => {
    if (col.key === "select" || col.stretch) return col.width || 0;
    ctx.font = "700 " + caption;
    let widest = ctx.measureText(col.title).width + 14; // + the sort caret
    if (col.key === "status") {
      ctx.font = caption;
      widest = Math.max(widest, ctx.measureText(FULFILLABLE).width + 30); // chip padding + border
    } else {
      ctx.font = col.mono ? mono : sans;
      for (const r of state.records) widest = Math.max(widest, ctx.measureText(col.text(r.o) || DASH).width);
    }
    const width = Math.max(col.width, Math.ceil(widest + 16));
    return col.maxWidth ? Math.min(col.maxWidth, width) : width;
  });
  const fixed = widths.reduce((a, b) => a + b, 0);
  const stretch = cols.some((c) => c.stretch);
  const customerMin = stretch ? Math.max(120, TABLE_MIN_PX - fixed) : 0;
  const template = cols.map((col, i) => (col.stretch ? "minmax(" + customerMin + "px, 1fr)" : widths[i] + "px"));
  // Customer hidden: an empty track takes the growth, so no column stretches.
  if (!stretch) template.push("minmax(0, 1fr)");
  state.tableCols = cols;
  state.filler = !stretch;
  els.table.style.setProperty("--cols", template.join(" "));
  els.table.style.setProperty("--table-min", fixed + customerMin + "px");
}
```

  6. Add these functions:

```js
function refreshColumns() {
  const empty = (col) => state.records.every((r) => {
    const t = col.text(r.o);
    return t === "" || t === DASH;
  });
  state.emptyKeys = new Set(allColumns().filter(empty).map((c) => c.key));
  if (state.sort && !visibleColumns().some((c) => c.key === state.sort.key)) state.sort = null;
  measureColumns();
  render();
}

function slotMode() {
  if (!state.records.length) return "none";
  if (state.columnsOpen) return "columns";
  return state.paneHidden || (state.narrow && !state.paneForced) ? "strip" : "pane";
}

function renderSlot() {
  const mode = slotMode();
  els.tableArea.dataset.slot = mode;
  els.pane.hidden = mode !== "pane";
  els.paneStrip.hidden = mode !== "strip";
  els.columnsPanel.hidden = mode !== "columns";
  els.columnsButton.disabled = mode === "none";
  els.columnsButton.setAttribute("aria-pressed", String(state.columnsOpen));
  els.columnsButton.textContent = "Columns " + visibleColumns().length + "/" + allColumns().length;
  if (mode === "pane") renderPane();
  if (mode === "columns") renderColumnsPanel();
}

function onColumns() {
  const next = state.bridge.columns || {};
  if (JSON.stringify(next) === JSON.stringify(state.columnSettings)) return;
  state.columnSettings = Object.assign({ order: null, visible: null, auto_hide_empty: false, extras: [] }, next);
  refreshColumns();
}
```

  7. In `render()`, call `renderSlot()` right after `renderStates()`.
  8. At the top of `layout()`:

```js
  const narrow = els.tableArea.clientWidth < SLOT_NARROW_PX;
  if (narrow !== state.narrow) {
    state.narrow = narrow;
    if (!narrow) state.paneForced = false;
    renderSlot();
  }
```

  9. In `onOrders`, replace `measureColumns(); renderKpis(); render();` with
     `renderKpis(); refreshColumns();`.
  10. In `bind()`, add these to `ids`:
      - `columnsButton: "columns-button"`
      - `pane: "pane"`
      - `paneStrip: "pane-strip"`
      - `paneShow: "pane-show"`
      - `columnsPanel: "columns-panel"`

      At the end of `bind()`, call `bindPane(); bindColumns();`.
  11. In the channel callback, before `onOrders()`, add:

```js
  bridge.columnsChanged.connect(onColumns);
  state.columnSettings = Object.assign(state.columnSettings, bridge.columns || {});
```

- [ ] **Step 8: Run the new tests, Bundle 12's, and the lint**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_results_columns.py tests/test_results_document.py tests/test_results_bridge.py tests/test_style_lint.py -q`
Expected: PASS. If the lint test is named differently, run
`grep -rln style_lint tests`. Bundle 12's 780px horizontal-scroll test still
passes: at 780 the slot is a strip and the table scrolls.

- [ ] **Step 9: Commit**

```bash
/usr/bin/git add gui/web tests/test_results_columns.py
/usr/bin/git commit -m "Bundle 13: the slot beside the table, and a column registry the page owns"
```

### Task 8: The detail pane (web)

**Files:**
- Modify: `gui/web/pane.js` (replace the stubs), `gui/web/results.css` (append)
- Create: `tests/test_results_pane.py`

**Interfaces:**
- Consumes:
  - Task 1: `order.Verdict` and `line.Short`.
  - Task 3: bridge slots `holdOrder`, `fulfillOrder`, `excludeOrder`,
    `removeLine`, `addOrderTag`, `removeOrderTag`, `copyText`; property
    `tagCategories`.
  - Task 7: `state.paneHidden`, `state.paneForced`, `state.narrow`,
    `render()`, `renderSlot()`.
  - `results.js` helpers: `str`, `num`, `fmtInt`, `fmtMoney`, `fmtAge`,
    `ageMs`, `plural`, `isFulfillable`, `svg`, `NUMBER`, `DASH`.
- Produces: `renderPane()`, `bindPane()`, `verdictCopy(order) -> {role, title, text, source}`.
  Test hooks:
  - `#pane-empty`, `.pane-order`, `.pane-position`
  - `.verdict[data-state][data-role][data-by-hand]` with `.verdict-title`,
    `.verdict-text`, `.verdict-source` and `.mark.solid`
  - `.line[data-index]` and `.line.short`, with `.line-menu-button`
  - `#line-menu`, `#order-menu`, `#tag-menu`, `#new-tag`
  - `.tag-chip[data-tag]`, `#add-tag`
  - `#pane-status-verb`, `#pane-exclude`, `#pane-more`
  - `#pane-hide`, `#pane-show`

- [ ] **Step 1: Write the failing tests** in `tests/test_results_pane.py`:

```python
"""The order detail pane (Bundle 13 spec §6.2-6.7), through Chromium. Never mark skip."""

import pandas as pd
import pytest
from PySide6.QtWebEngineWidgets import QWebEngineView
from test_results_bridge import _eval, _until_js

from gui.results_bridge import mount_results_page

SHORT = "Cannot fulfill: TS-4409-B: Insufficient stock (need 6, have 4)"


def pane_lines():
    """Ready, short, review by the run (no SKU), review set by a person."""
    base = {"Shipping_Provider": "DPD", "Customer": "B. Fischer", "Destination_Country": "AT",
            "Total_Price": 204.3, "Created_At": "2026-09-11 06:00:00 +0000",
            "Internal_Tags": "[]", "Has_SKU": True, "Stock_Alert": ""}
    rows = []

    def add(order, status, sku, qty, left, note="", **extra):
        rows.append({**base, "Order_Number": order, "Order_Fulfillment_Status": status,
                     "SKU": sku, "Product_Name": f"Product {sku}", "Quantity": qty,
                     "Final_Stock": left, "System_note": note, **extra})

    add("#10443", "Fulfillable", "TS-4410-B", 4, 96)
    add("#10443", "Fulfillable", "TS-9001-C", 2, 41)
    for sku, qty, left in (("TS-4409-B", 6, 4), ("TS-9002-C", 2, 18), ("BX-3311-A", 1, 7)):
        add("#10445", "Not Fulfillable", sku, qty, left, SHORT)
    add("#10447", "Not Fulfillable", None, 1, None, "[NO_SKU]", Has_SKU=False)
    add("#10447", "Not Fulfillable", "TS-6640-D", 1, 33)
    add("#10449", "Fulfillable", "BX-7742-D", 1, 0,
        "Cannot fulfill: BX-7742-D: Out of stock", Internal_Tags='["vip"]')
    return pd.DataFrame(rows)


@pytest.fixture
def doc(qtbot):
    view = QWebEngineView()
    qtbot.addWidget(view)
    bridge = mount_results_page(view)
    view.resize(1310, 692)
    view.show()
    _until_js(qtbot, view, "document.documentElement.dataset.bridge === 'ready'")
    bridge.set_tag_categories({"prio": {"label": "Priority", "tags": ["rush", "vip"]}})
    bridge.set_orders(pane_lines())
    _until_js(qtbot, view, "document.querySelectorAll('#rows .row').length === 4")
    return view, bridge


def _js(qtbot, view, statement):
    _eval(qtbot, view, f"{statement}; true")


def _text(qtbot, view, selector):
    return _eval(qtbot, view, f"(document.querySelector({selector!r}) || {{textContent: null}}).textContent")


def _select(qtbot, view, order):
    _js(qtbot, view, f"document.querySelector('#rows .row[data-order=\"{order}\"]').click()")
    _until_js(qtbot, view, f"(document.querySelector('.pane-order') || {{}}).textContent === {order!r}")


def _menu_item(menu, label):
    return f"[...document.querySelectorAll('#{menu} .menu-item')].find(b => b.textContent === {label!r}).click()"


def test_nothing_selected_says_how_to_move(qtbot, doc):
    view, _ = doc
    assert _text(qtbot, view, "#pane-empty .state-title") == "No order selected"
    assert "moves through the 4 shown." in _text(qtbot, view, "#pane-empty .state-text")


def test_the_pane_is_400_by_508_beside_the_table(qtbot, doc):
    view, _ = doc
    size = _eval(qtbot, view, "(r => Math.round(r.width) + 'x' + Math.round(r.height))(document.getElementById('pane').getBoundingClientRect())")
    assert size == "400x508"


def test_a_short_order_names_the_sku_and_both_numbers(qtbot, doc):
    view, _ = doc
    _select(qtbot, view, "#10445")
    assert _text(qtbot, view, ".verdict-title") == "Cannot ship: 1 of 3 lines is short"
    assert "There were 4 units of TS-4409-B left for this order, and it wants 6." in _text(qtbot, view, ".verdict-text")
    assert _eval(qtbot, view, "document.querySelectorAll('#pane .line.short').length") == 1
    assert _text(qtbot, view, ".pane-position") == "2 of 4"
    assert _text(qtbot, view, "#pane-status-verb") == "Mark fulfillable"


def test_a_ready_order_has_no_source_line_and_offers_hold(qtbot, doc):
    view, _ = doc
    _select(qtbot, view, "#10443")
    assert _text(qtbot, view, ".verdict-title") == "Ships complete"
    assert _text(qtbot, view, ".verdict-source") is None
    assert _text(qtbot, view, "#pane-status-verb") == "Hold"


@pytest.mark.parametrize(
    ("order", "title", "source", "by_hand"),
    [
        ("#10447", "Fix the data before this ships", "Detected by the run, not set by a person.", "false"),
        ("#10449", "Marked fulfillable by hand", "Set by a person, not detected by the run.", "true"),
    ],
)
def test_the_review_state_says_which_cause(qtbot, doc, order, title, source, by_hand):
    view, _ = doc
    _select(qtbot, view, order)
    assert _text(qtbot, view, ".verdict-title") == title
    assert _text(qtbot, view, ".verdict-source") == source
    assert _eval(qtbot, view, "document.querySelector('.verdict').dataset.byHand") == by_hand
    assert _eval(qtbot, view, "document.querySelector('.verdict .mark.solid') !== null") is (by_hand == "true")


@pytest.mark.parametrize(
    ("order", "click", "signal", "args"),
    [
        ("#10443", "document.getElementById('pane-status-verb').click()", "holdRequested", ["#10443"]),
        ("#10445", "document.getElementById('pane-status-verb').click()", "fulfillRequested", ["#10445"]),
        ("#10443", "document.getElementById('pane-exclude').click()", "excludeRequested", ["#10443"]),
        ("#10449", "document.querySelector('.tag-chip[data-tag=\"vip\"]').click()", "tagRemovalRequested", ["#10449", "vip"]),
    ],
)
def test_each_action_reaches_python(qtbot, doc, order, click, signal, args):
    view, bridge = doc
    _select(qtbot, view, order)
    with qtbot.waitSignal(getattr(bridge, signal), timeout=3000) as blocker:
        _js(qtbot, view, click)
    assert list(blocker.args) == args


def test_remove_this_line_sends_the_index_and_its_sku(qtbot, doc):
    view, bridge = doc
    _select(qtbot, view, "#10445")
    _js(qtbot, view, "document.querySelector('#pane .line[data-index=\"1\"] .line-menu-button').click()")
    with qtbot.waitSignal(bridge.lineRemovalRequested, timeout=3000) as blocker:
        _js(qtbot, view, _menu_item("line-menu", "Remove this line"))
    assert list(blocker.args) == ["#10445", 1, "TS-9002-C"]


def test_the_tag_menu_offers_only_tags_the_order_lacks(qtbot, doc):
    view, bridge = doc
    _select(qtbot, view, "#10449")
    _js(qtbot, view, "document.getElementById('add-tag').click()")
    items = _eval(qtbot, view, "[...document.querySelectorAll('#tag-menu .menu-item')].map(b => b.textContent).join('|')")
    assert items == "rush"
    with qtbot.waitSignal(bridge.tagAddRequested, timeout=3000) as blocker:
        _js(qtbot, view, _menu_item("tag-menu", "rush"))
    assert list(blocker.args) == ["#10449", "rush"]


def test_a_new_tag_is_typed_and_entered(qtbot, doc):
    view, bridge = doc
    _select(qtbot, view, "#10443")
    _js(qtbot, view, "document.getElementById('add-tag').click()")
    with qtbot.waitSignal(bridge.tagAddRequested, timeout=3000) as blocker:
        _js(qtbot, view, "(i => { i.value = ' gift '; i.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', bubbles: true})); })(document.getElementById('new-tag'))")
    assert list(blocker.args) == ["#10443", "gift"]


def _table_width(qtbot, view):
    return _eval(qtbot, view, "Math.round(document.querySelector('.table-wrap').getBoundingClientRect().width)")


def test_hiding_leaves_a_strip_and_showing_restores_the_table(qtbot, doc):
    view, _ = doc
    _js(qtbot, view, "document.getElementById('pane-hide').click()")
    _until_js(qtbot, view, "document.getElementById('table-area').dataset.slot === 'strip'")
    assert _table_width(qtbot, view) == 1242
    _js(qtbot, view, "document.getElementById('pane-show').click()")
    _until_js(qtbot, view, "document.getElementById('table-area').dataset.slot === 'pane'")
    assert _table_width(qtbot, view) == 866


def test_a_narrow_page_collapses_the_pane_until_asked(qtbot, doc):
    view, _ = doc
    view.resize(1100, 692)
    _until_js(qtbot, view, "document.getElementById('table-area').dataset.slot === 'strip'")
    _js(qtbot, view, "document.getElementById('pane-show').click()")
    _until_js(qtbot, view, "document.getElementById('table-area').dataset.slot === 'pane'")
    _until_js(qtbot, view, "(s => s.scrollWidth > s.clientWidth)(document.getElementById('scroller'))")
```

- [ ] **Step 2: Run and see the tests fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_results_pane.py -v`
Expected: FAIL. `#pane-empty` is missing, because the pane is still a stub.

- [ ] **Step 3: Replace `gui/web/pane.js`** with:

```js
// The order detail pane (Bundle 13 spec §6.2-6.7): the cursor order's
// identity, verdict, lines, tags, notes and actions. One order, never the
// multi-selection. No optimistic updates: it changes when `orders` comes back.
"use strict";

const RUN_SOURCE = "Detected by the run, not set by a person.";
const HAND_SOURCE = "Set by a person, not detected by the run.";
const CHEVRON_RIGHT = "m9 18 6-6-6-6";
const CHEVRON_LEFT = "m15 18-6-6 6-6";
const FLAG_CHIPS = [["_repeat", "Repeat"], ["Unknown_SKU", "Unknown SKU"], ["Low_Stock", "Low stock"]];
const MENU_WIDTH = 220;
let paneMenuOpener = null;

function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
}

function paneButton(cls, text, label) {
  const b = el("button", "btn " + cls, text);
  b.type = "button";
  if (label) {
    b.setAttribute("aria-label", label);
    b.title = label;
  }
  return b;
}

function problemSentence(p) {
  if (p.code === "short") {
    return "There were " + NUMBER.format(p.have) + " units of " + p.sku +
      " left for this order, and it wants " + NUMBER.format(p.need) + ".";
  }
  if (p.code === "out_of_stock") return p.sku + " had none left.";
  if (p.code === "invalid_quantity") return p.sku + " has no valid quantity in the orders file.";
  if (p.code === "no_sku") {
    return p.lines === 1
      ? "1 line has no SKU, so no stock can be matched to it."
      : NUMBER.format(p.lines) + " lines have no SKU, so no stock can be matched to them.";
  }
  const text = str(p.text).trim();
  return /[.!?]$/.test(text) ? text : text + ".";
}

// One template per reason code, with the run's numbers in it (§6.3).
function verdictCopy(o) {
  const v = o.Verdict || { state: "ready", by_hand: false, problems: [] };
  const lines = o.lines || [];
  const n = lines.length;
  const k = lines.filter((line) => line.Short).length;
  const sentences = (v.problems || []).map(problemSentence).join(" ");
  if (v.state === "ready") {
    const value = num(o.Total_Price) === null ? "" : ", " + fmtMoney(o.Total_Price);
    const opening = n === 1
      ? "Its one line is in stock and reserved for this order."
      : "All " + NUMBER.format(n) + " lines are in stock and reserved for this order.";
    return { role: "success", title: "Ships complete", source: "",
      text: opening + " One parcel, " + plural(num(o.Units) || 0, "unit") + value + ". Nothing is waiting on anyone." };
  }
  if (v.state === "short") {
    const rest = n - k === 1 ? " The other line is covered."
      : n > k ? " The other " + NUMBER.format(n - k) + " lines are covered." : "";
    return { role: "danger", source: "", text: sentences + rest,
      title: "Cannot ship: " + NUMBER.format(k) + " of " + plural(n, "line") + (k === 1 ? " is short" : " are short") };
  }
  if (!v.by_hand) return { role: "warning", title: "Fix the data before this ships", text: sentences, source: RUN_SOURCE };
  if (isFulfillable(o)) {
    return { role: "warning", title: "Marked fulfillable by hand", source: HAND_SOURCE,
      text: "The run could not ship it. " + sentences + " Someone marked it fulfillable anyway." };
  }
  return { role: "warning", title: "On hold", source: HAND_SOURCE,
    text: "Nothing in this order is short now. It stays blocked until someone marks it fulfillable." };
}

function paneRecord() {
  if (state.cursorKey === null) return null;
  const index = state.view.findIndex((r) => r.key === state.cursorKey);
  return index < 0 ? null : { o: state.view[index].o, index: index };
}

function renderPane() {
  const pane = els.pane;
  pane.textContent = ""; // also drops any open pane menu
  const hit = paneRecord();
  const head = el("div", "pane-head");
  if (hit) {
    head.append(
      el("span", "pane-order", str(hit.o.Order_Number)),
      el("span", "pane-age", ageMs(hit.o.Created_At) === null ? "" : fmtAge(hit.o.Created_At) + " old"),
    );
  }
  head.append(el("span", "spacer"));
  if (hit) head.append(el("span", "pane-position", NUMBER.format(hit.index + 1) + " of " + NUMBER.format(state.view.length)));
  const hide = paneButton("ghost icon pane-icon", undefined, "Hide the pane");
  hide.id = "pane-hide";
  hide.innerHTML = svg(CHEVRON_RIGHT, "glyph");
  hide.addEventListener("click", hidePane);
  head.append(hide);
  pane.append(head);

  if (!hit) {
    const empty = el("div", "pane-empty");
    empty.id = "pane-empty";
    empty.append(
      el("p", "state-title", "No order selected"),
      el("p", "state-text", "Click a row to see whether it can ship and, if it cannot, why. ↑ ↓ moves through the " +
        NUMBER.format(state.view.length) + " shown."),
    );
    pane.append(empty);
    return;
  }
  const o = hit.o;
  pane.append(paneWho(o), paneVerdict(o), paneNumbers(o), paneLines(o), paneTags(o), paneNotes(o), paneActions(o));
}

function paneWho(o) {
  const parts = [o.Customer, o.Destination_Country, o.Shipping_Provider].map((v) => str(v).trim()).filter(Boolean);
  return el("div", "pane-who", parts.length ? parts.join(" · ") : DASH);
}

function paneVerdict(o) {
  const v = o.Verdict || {};
  const copy = verdictCopy(o);
  const box = el("div", "verdict");
  box.dataset.state = v.state || "ready";
  box.dataset.role = copy.role;
  box.dataset.byHand = String(Boolean(v.by_hand));
  const title = el("div", "verdict-title");
  // The mark: hollow when the run detected it, solid when a person set it.
  title.append(el("span", "mark" + (v.by_hand ? " solid" : "")), document.createTextNode(copy.title));
  box.append(title, el("p", "verdict-text", copy.text));
  if (copy.source) box.append(el("p", "verdict-source", copy.source));
  return box;
}

function paneNumbers(o) {
  const parts = [plural((o.lines || []).length, "line"), plural(num(o.Units) || 0, "unit")];
  if (num(o.Total_Price) !== null) parts.push(fmtMoney(o.Total_Price));
  return el("div", "pane-numbers", parts.join(" · "));
}

function paneLines(o) {
  const order = str(o.Order_Number);
  const box = el("div", "lines");
  const head = el("div", "line line-head");
  for (const [text, cls] of [["SKU", ""], ["Product", ""], ["Want", " num"], ["Left", " num"], ["", ""]]) {
    head.append(el("span", "line-cell" + cls, text));
  }
  box.append(head);
  (o.lines || []).forEach((line, index) => {
    const sku = str(line.SKU);
    const row = el("div", "line" + (line.Short ? " short" : ""));
    row.dataset.index = String(index);
    const product = el("span", "line-cell product", str(line.Product_Name) || DASH);
    product.title = str(line.Product_Name);
    const more = paneButton("ghost icon line-menu-button", "⋯", "Actions for this line");
    more.addEventListener("click", () => openPaneMenu(more, "line-menu", [
      ["Remove this line", () => state.bridge.removeLine(order, index, sku)],
      ["Copy SKU", () => state.bridge.copyText(sku)],
    ]));
    const actions = el("span", "line-cell");
    actions.append(more);
    row.append(el("span", "line-cell sku", sku || DASH), product,
      el("span", "line-cell num", fmtInt(line.Quantity)), el("span", "line-cell num", fmtInt(line.Final_Stock)), actions);
    box.append(row);
  });
  return box;
}

function paneTags(o) {
  const order = str(o.Order_Number);
  const box = el("div", "pane-tags");
  for (const [field, label] of FLAG_CHIPS) if (o[field] === true) box.append(el("span", "flag-chip", label));
  for (const tag of (o.Tag_List || []).map(String)) {
    const chip = paneButton("", tag + "  ×", "Remove tag " + tag);
    chip.className = "chip-filter tag-chip";
    chip.dataset.tag = tag;
    chip.addEventListener("click", () => state.bridge && state.bridge.removeOrderTag(order, tag));
    box.append(chip);
  }
  const add = paneButton("ghost small", "+ Tag");
  add.id = "add-tag";
  add.addEventListener("click", () => openTagMenu(add, o));
  box.append(add);
  return box;
}

function paneNotes(o) {
  const parts = [str(o.Notes).trim(), str(o.Status_Note).trim()].filter(Boolean);
  if (str(o.Tags).trim()) parts.push("Shopify tags: " + str(o.Tags).trim());
  return el("p", "pane-notes", parts.length ? parts.join("\n") : "No notes on this order.");
}

// Never a primary: the screen's one primary is Export (§6.6).
function paneActions(o) {
  const order = str(o.Order_Number);
  const fulfillable = isFulfillable(o);
  const box = el("div", "pane-actions");
  const verb = paneButton("secondary", fulfillable ? "Hold" : "Mark fulfillable");
  verb.id = "pane-status-verb";
  verb.addEventListener("click", () => {
    if (!state.bridge) return;
    if (fulfillable) state.bridge.holdOrder(order);
    else state.bridge.fulfillOrder(order);
  });
  const exclude = paneButton("danger", "Exclude from run");
  exclude.id = "pane-exclude";
  exclude.addEventListener("click", () => state.bridge && state.bridge.excludeOrder(order));
  const more = paneButton("ghost icon", "⋯", "More actions for this order");
  more.id = "pane-more";
  more.addEventListener("click", () => openPaneMenu(more, "order-menu", [
    ["Copy order number", () => state.bridge.copyText(order)],
  ]));
  box.append(verb, exclude, more);
  return box;
}

function closePaneMenus() {
  for (const menu of els.pane.querySelectorAll(".pane-menu")) menu.remove();
}

// Menus open upward inside the pane, which clips anything outside it.
function placeMenu(menu, anchor) {
  const pane = els.pane.getBoundingClientRect();
  const a = anchor.getBoundingClientRect();
  menu.style.left = Math.max(0, Math.min(a.left - pane.left, pane.width - MENU_WIDTH - 8)) + "px";
  menu.style.bottom = Math.round(pane.bottom - a.top + 4) + "px";
  els.pane.append(menu);
  paneMenuOpener = anchor;
  const first = menu.querySelector(".menu-item, input");
  if (first) first.focus();
}

function newMenu(id) {
  closePaneMenus();
  const menu = el("div", "menu pane-menu");
  menu.id = id;
  menu.setAttribute("role", "menu");
  return menu;
}

function menuItem(label, act) {
  const item = el("button", "menu-item", label);
  item.type = "button";
  item.setAttribute("role", "menuitem");
  item.addEventListener("click", () => {
    closePaneMenus();
    if (state.bridge) act();
  });
  return item;
}

function openPaneMenu(anchor, id, items) {
  const menu = newMenu(id);
  for (const [label, act] of items) menu.append(menuItem(label, act));
  placeMenu(menu, anchor);
}

function openTagMenu(anchor, o) {
  const order = str(o.Order_Number);
  const own = new Set((o.Tag_List || []).map(String));
  const categories = (state.bridge && state.bridge.tagCategories) || {};
  const menu = newMenu("tag-menu");
  for (const id of Object.keys(categories)) {
    const category = categories[id] || {};
    const tags = (category.tags || []).map(String).filter((t) => !own.has(t));
    if (!tags.length) continue;
    menu.append(el("div", "menu-group", str(category.label) || id));
    for (const tag of tags) menu.append(menuItem(tag, () => state.bridge.addOrderTag(order, tag)));
  }
  const input = el("input", "new-tag");
  input.id = "new-tag";
  input.placeholder = "New tag";
  input.setAttribute("aria-label", "New tag");
  input.addEventListener("keydown", (e) => {
    const tag = input.value.trim();
    if (e.key !== "Enter" || !tag) return;
    closePaneMenus();
    if (state.bridge) state.bridge.addOrderTag(order, tag);
  });
  menu.append(input);
  placeMenu(menu, anchor);
}

function hidePane() {
  state.paneHidden = true;
  state.paneForced = false;
  render();
  els.paneShow.focus();
}

function showPane() {
  state.paneHidden = false;
  if (state.narrow) state.paneForced = true; // the table scrolls sideways instead
  render();
  const hide = document.getElementById("pane-hide");
  if (hide) hide.focus();
}

function bindPane() {
  els.paneShow.innerHTML = svg(CHEVRON_LEFT, "glyph");
  els.paneShow.addEventListener("click", showPane);
  els.pane.addEventListener("keydown", (e) => {
    if (e.key !== "Escape" || !els.pane.querySelector(".pane-menu")) return;
    e.stopPropagation();
    closePaneMenus();
    if (paneMenuOpener && paneMenuOpener.isConnected) paneMenuOpener.focus();
  });
  document.addEventListener("mousedown", (e) => {
    if (!e.target.closest(".pane-menu, .line-menu-button, #add-tag, #pane-more")) closePaneMenus();
  });
}
```

- [ ] **Step 4: Append the pane CSS** to `results.css`. Before writing
  `.btn.secondary` / `.btn.danger`, open `shared/theme.py` ≈L1170–1215 and
  make the values match `QPushButton[role="secondary"]` / `[role="danger"]`,
  including `:disabled`, which the existing `.btn:disabled` rule already
  covers.

```css
/* --- detail pane and column manager planes (Bundle 13 §6.2, §6.9) ----------- */

.pane, .columns-panel {
  position: relative;
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: var(--spacing-lg);
  overflow: hidden;
  background: var(--surface-raised);   /* the Card rule, as the KPI cards */
  border-radius: var(--radius-md);
}
.pane { gap: var(--spacing-md); }

.pane-head { flex-shrink: 0; display: flex; align-items: center; gap: var(--spacing-sm); height: 28px; }
.pane-order { font-family: var(--font-family-mono); font-size: var(--type-heading-size); font-weight: 700; }
.pane-age, .pane-position { font-size: var(--type-caption-size); color: var(--text-secondary); white-space: nowrap; }
.btn.pane-icon { width: 24px; height: 24px; }
.glyph { width: 14px; height: 14px; fill: none; stroke: currentColor; stroke-width: 2; vertical-align: middle; }

.pane-who { flex-shrink: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

.verdict { flex-shrink: 0; }
.verdict[data-role="success"] { --role: var(--status-success); }
.verdict[data-role="danger"] { --role: var(--status-danger); }
.verdict[data-role="warning"] { --role: var(--status-warning); }
.verdict-title {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  font-size: var(--type-label-size);
  font-weight: 700;
}
/* The mark (CONTEXT.md): hollow when detected by the run, solid when set by a person. */
.mark { flex-shrink: 0; width: 8px; height: 8px; border: 1.5px solid var(--role); border-radius: 50%; }
.mark.solid { background: var(--role); }
.verdict-text {
  margin: var(--spacing-xs) 0 0;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 4;
  overflow: hidden;
}
.verdict-source { margin: var(--spacing-xs) 0 0; font-size: var(--type-caption-size); color: var(--text-secondary); }
.pane-numbers { flex-shrink: 0; font-size: var(--type-caption-size); color: var(--text-secondary); }

/* Lines scroll inside the pane; the pane itself never scrolls. */
.lines { flex: 1 1 auto; min-height: 0; overflow-y: auto; }
.line {
  position: relative;
  display: grid;
  grid-template-columns: 112px minmax(0, 1fr) 48px 48px 24px;
  align-items: center;
  height: 28px;
}
.line.line-head {
  position: sticky;
  top: 0;
  z-index: 1;
  background: var(--surface-raised);
  font-size: var(--type-caption-size);
  font-weight: 700;
  color: var(--text-secondary);
}
.line-cell { padding: 0 var(--spacing-xs); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.line-cell.sku { font-family: var(--font-family-mono); }
.line-cell.product { color: var(--text-secondary); }
/* Short lines are edged, not tinted. */
.line.short::before {
  content: "";
  position: absolute;
  left: 0;
  top: 2px;
  bottom: 2px;
  width: 3px;
  background: var(--status-danger);
}
.btn.line-menu-button { visibility: hidden; width: 24px; height: 24px; padding: 0; }
.line:hover .line-menu-button, .line:focus-within .line-menu-button { visibility: visible; }

.pane-tags { flex-shrink: 0; display: flex; flex-wrap: wrap; align-items: center; gap: var(--spacing-xs); }
.flag-chip {
  padding: 3px 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  font-size: var(--type-caption-size);
  color: var(--text-secondary);
}
.btn.small { height: 24px; padding: 0 var(--spacing-sm); font-size: var(--type-caption-size); }
.pane-notes {
  flex-shrink: 0;
  margin: 0;
  white-space: pre-line;
  font-size: var(--type-caption-size);
  color: var(--text-secondary);
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
  overflow: hidden;
}
.pane-actions { flex-shrink: 0; display: flex; gap: var(--spacing-sm); }

.pane-menu { top: auto; max-height: 240px; }
.pane-menu .new-tag {
  display: block;
  margin: var(--spacing-xs) var(--spacing-md);
  width: calc(100% - 2 * var(--spacing-md));
  height: var(--control-height);
  padding: 0 var(--padding-h);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
}
.pane-menu .new-tag:focus { outline: 2px solid var(--focus-ring); outline-offset: -1px; }

.pane-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-sm);
  text-align: center;
}

.pane-strip { height: 100%; }
.btn.strip-button { width: 36px; height: 28px; }

.btn.secondary { border-color: var(--border); background: var(--surface); }
.btn.secondary:hover { background: var(--hover); }
.btn.secondary:active { background: var(--selection-bg); }
.btn.danger { border-color: var(--status-danger); color: var(--status-danger); }
.btn.danger:hover, .btn.danger:active { background: var(--status-danger-bg); }
.btn.secondary:focus-visible, .btn.danger:focus-visible, .tag-chip:focus-visible {
  outline: 2px solid var(--focus-ring);
  outline-offset: 1px;
}
```

- [ ] **Step 5: Run the pane tests, the Bundle 12 document tests, and the lint**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_results_pane.py tests/test_results_document.py tests/test_results_columns.py -q`
Then run the style-lint test (`grep -rln style_lint tests` names it).
Expected: PASS. If the lint rejects `-webkit-line-clamp`, drop the clamp and
keep `max-height` in `em` with `overflow: hidden`. Do not suppress the rule.

- [ ] **Step 6: Commit**

```bash
/usr/bin/git add gui/web/pane.js gui/web/results.css tests/test_results_pane.py
/usr/bin/git commit -m "Bundle 13: the order detail pane — verdict, lines, tags and actions (9.14)"
```

### Task 9: The column manager (web)

**Files:**
- Modify: `gui/web/columns.js` (replace the `renderColumnsPanel` / `bindColumns`
  stubs from Task 7), `gui/web/results.css` (append)
- Modify: `tests/test_results_columns.py` (append)

**Interfaces:**
- Consumes (Task 7): `COLUMN_GROUPS`, `PINNED_KEYS`, `allColumns()`,
  `orderedColumns()`, `userVisible(col)`, `autoHidden(col)`,
  `visibleColumns()`, `storeColumns(changes, send)`; `state.columnSettings`,
  `state.emptyKeys`, `state.columnsOpen`; `renderSlot()`; `els.columnsPanel`,
  `els.columnsButton`.
- Consumes (Task 3): bridge slots `setVisibleColumns(list)`,
  `setColumnOrder(list)`, `resetColumns()`, `setAutoHideEmpty(bool)`, each of
  which emits `columnSettingsChanged(dict)` on the Python side.
- Consumes (Task 8): `el(tag, cls, text)`. `pane.js` loads after `columns.js`,
  so `el` only exists at call time — never at `columns.js`'s top level. Same
  rule for `results.js`'s `svg`, `NUMBER` and `cssVar`.
- Produces: `renderColumnsPanel()`, `bindColumns()`, and
  `openColumnsPanel()` / `closeColumnsPanel()`.

The manager is the slot's third mode. It never renders while `slotMode()` is
anything else, so it does not need to know about the pane or the strip. The
slot narrowing the table when the manager opens from the strip is the Task 7
CSS doing its job (`data-slot="columns"` is a 400px track) — no code here, and
nothing recomputes it mid-drag because a drop re-renders rows, not the slot.

- [ ] **Step 1: Write the failing tests.** Append to
  `tests/test_results_columns.py`:

```python
# --- the column manager (spec §6.9) ------------------------------------------

ROW = "document.querySelector('.col-row[data-key=\"{}\"] {}')"


def _open_columns(qtbot, view):
    _eval(qtbot, view, "document.getElementById('columns-button').click()")
    _until_js(qtbot, view, "document.getElementById('table-area').dataset.slot === 'columns'")


def _settings(qtbot, view, bridge, js):
    """Run `js` and return the settings dict Python was told to store."""
    with qtbot.waitSignal(bridge.columnSettingsChanged, timeout=3000) as blocker:
        _eval(qtbot, view, js)
    return blocker.args[0]


def test_the_manager_keeps_the_table_width_and_counts_shown_and_hidden(qtbot, doc):
    view, _ = doc
    _open_columns(qtbot, view)
    assert _width(qtbot, view, ".table-wrap") == 866
    assert _eval(qtbot, view, "document.getElementById('columns-count').textContent") == "8 shown · 10 hidden"


def test_every_registry_column_has_a_row_and_the_scroller_reaches_the_last(qtbot, doc):
    view, _ = doc
    _open_columns(qtbot, view)
    assert _eval(qtbot, view, "document.querySelectorAll('.col-row').length") == 18
    assert _eval(
        qtbot, view,
        "(() => { const s = document.getElementById('columns-scroller');"
        " s.scrollTop = s.scrollHeight;"
        " const rows = s.querySelectorAll('.col-row');"
        " const last = rows[rows.length - 1].getBoundingClientRect();"
        " return last.bottom <= s.getBoundingClientRect().bottom + 1; })()",
    )


def test_a_pinned_row_is_checked_disabled_and_has_no_drag_handle(qtbot, doc):
    view, _ = doc
    _open_columns(qtbot, view)
    assert _eval(qtbot, view, ROW.format("order", ".col-check") + ".disabled") is True
    assert _eval(qtbot, view, ROW.format("order", ".col-check") + ".checked") is True
    assert _eval(qtbot, view, ROW.format("order", ".col-note") + ".textContent") == "pinned"
    assert _eval(qtbot, view, ROW.format("order", ".col-grip") + ".innerHTML") == ""


def test_toggling_a_column_stores_it_and_the_header_gains_it(qtbot, doc):
    view, bridge = doc
    _open_columns(qtbot, view)
    stored = _settings(qtbot, view, bridge, ROW.format("type", ".col-check") + ".click()")
    assert "type" in stored["visible"]
    _until_js(qtbot, view, _has_header("Type"))


def test_alt_up_moves_a_column_before_the_previous_row(qtbot, doc):
    view, bridge = doc
    _open_columns(qtbot, view)
    stored = _settings(
        qtbot, view, bridge,
        "document.querySelector('.col-row[data-key=\"age\"]').dispatchEvent("
        "new KeyboardEvent('keydown', {key: 'ArrowUp', altKey: true, bubbles: true, cancelable: true}))",
    )
    order = stored["order"]
    assert order.index("age") == order.index("units") - 1


def test_a_drop_on_the_top_half_moves_the_column_before_that_row(qtbot, doc):
    view, bridge = doc
    _open_columns(qtbot, view)
    stored = _settings(
        qtbot, view, bridge,
        "(() => { const s = document.getElementById('columns-scroller');"
        " const src = s.querySelector('.col-row[data-key=\"age\"]');"
        " const dst = s.querySelector('.col-row[data-key=\"lines\"]');"
        " const dt = new DataTransfer();"
        " src.dispatchEvent(new DragEvent('dragstart', {dataTransfer: dt, bubbles: true}));"
        " const box = dst.getBoundingClientRect();"
        " dst.dispatchEvent(new DragEvent('dragover',"
        " {dataTransfer: dt, bubbles: true, cancelable: true, clientY: box.top + 2}));"
        " dst.dispatchEvent(new DragEvent('drop', {dataTransfer: dt, bubbles: true, cancelable: true}));"
        " return 1; })()",
    )
    order = stored["order"]
    assert order.index("age") == order.index("lines") - 1


def test_a_drop_above_the_pinned_pair_lands_after_order(qtbot, doc):
    view, bridge = doc
    _open_columns(qtbot, view)
    stored = _settings(
        qtbot, view, bridge,
        "(() => { const s = document.getElementById('columns-scroller');"
        " const src = s.querySelector('.col-row[data-key=\"age\"]');"
        " const dst = s.querySelector('.col-row[data-key=\"status\"]');"
        " const dt = new DataTransfer();"
        " src.dispatchEvent(new DragEvent('dragstart', {dataTransfer: dt, bubbles: true}));"
        " const box = dst.getBoundingClientRect();"
        " dst.dispatchEvent(new DragEvent('dragover',"
        " {dataTransfer: dt, bubbles: true, cancelable: true, clientY: box.top + 2}));"
        " dst.dispatchEvent(new DragEvent('drop', {dataTransfer: dt, bubbles: true, cancelable: true}));"
        " return 1; })()",
    )
    assert stored["order"][:3] == ["status", "order", "age"]


def test_the_search_hides_groups_with_no_match_and_the_handles(qtbot, doc):
    view, _ = doc
    _open_columns(qtbot, view)
    _eval(
        qtbot, view,
        "(() => { const s = document.getElementById('columns-search'); s.value = 'ship';"
        " s.dispatchEvent(new Event('input', {bubbles: true})); return 1; })()",
    )
    assert _json(qtbot, view, "[...document.querySelectorAll('.col-group')].map(g => g.dataset.group)") == ["Shipping"]
    assert _json(qtbot, view, "[...document.querySelectorAll('.col-row')].map(r => r.dataset.key)") == ["method"]
    assert _eval(qtbot, view, ROW.format("method", ".col-grip") + ".innerHTML") == ""


def test_the_group_header_counts_shown_of_that_group(qtbot, doc):
    view, _ = doc
    _open_columns(qtbot, view)
    # Order holds status, order, lines, units, age, type, reason; five are shown.
    assert _eval(qtbot, view, "document.querySelector('.col-group[data-group=\"Order\"]').textContent") == "ORDER 5 of 7"


def test_the_footer_checkbox_sets_auto_hide_and_the_row_says_empty(qtbot, doc):
    view, bridge = doc
    bridge.set_column_settings({"visible": ["subtotal", "lines"], "auto_hide_empty": False})
    _until_js(qtbot, view, _has_header("Subtotal"))
    _open_columns(qtbot, view)
    stored = _settings(qtbot, view, bridge, "document.getElementById('hide-empty').click()")
    assert stored["auto_hide_empty"] is True
    _until_js(qtbot, view, f"!{_has_header('Subtotal')}")
    assert _eval(qtbot, view, ROW.format("subtotal", ".col-note") + ".textContent") == "empty"
    assert _eval(qtbot, view, ROW.format("subtotal", ".col-check") + ".checked") is True


def test_reset_clears_the_layout_and_keeps_auto_hide(qtbot, doc):
    view, bridge = doc
    bridge.set_column_settings({"visible": ["type"], "auto_hide_empty": True})
    _until_js(qtbot, view, f"!{_has_header('Customer')}")
    _open_columns(qtbot, view)
    stored = _settings(qtbot, view, bridge, "document.getElementById('columns-reset').click()")
    assert stored["visible"] is None and stored["order"] is None
    assert stored["auto_hide_empty"] is True
    _until_js(qtbot, view, _has_header("Customer"))


def test_done_closes_the_manager_and_returns_focus_to_the_button(qtbot, doc):
    view, _ = doc
    _open_columns(qtbot, view)
    _eval(qtbot, view, "document.getElementById('columns-done').click()")
    _until_js(qtbot, view, "document.getElementById('table-area').dataset.slot === 'pane'")
    assert _eval(qtbot, view, "document.activeElement.id") == "columns-button"
    assert _eval(qtbot, view, "document.getElementById('columns-button').getAttribute('aria-pressed')") == "false"


def test_escape_closes_the_manager(qtbot, doc):
    view, _ = doc
    _open_columns(qtbot, view)
    assert _eval(qtbot, view, "document.activeElement.id") == "columns-search"
    _eval(
        qtbot, view,
        "document.getElementById('columns-panel').dispatchEvent("
        "new KeyboardEvent('keydown', {key: 'Escape', bubbles: true, cancelable: true}))",
    )
    _until_js(qtbot, view, "document.getElementById('table-area').dataset.slot === 'pane'")
```

- [ ] **Step 2: Run and see the tests fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_results_columns.py -v`
Expected: the Task 7 tests still PASS, every test added above FAILS (the panel
renders nothing).

- [ ] **Step 3: Replace the two stubs at the end of `gui/web/columns.js`**
  (`renderColumnsPanel` and `bindColumns`) with:

```js
// --- the column manager (spec §6.9) -----------------------------------------
// The slot's third mode. It shows every column grouped for finding, while the
// table beside it keeps the one order a drop rearranges.

// Six dots, drawn as zero-length round-capped subpaths.
const GRIP = "M9 5h.01M9 12h.01M9 19h.01M15 5h.01M15 12h.01M15 19h.01";
let columnQuery = "";
let columnDragKey = null;

function openColumnsPanel() {
  columnQuery = "";
  state.columnsOpen = true;
  renderSlot();
  const search = document.getElementById("columns-search");
  search.value = "";
  search.focus();
}

function closeColumnsPanel() {
  state.columnsOpen = false;
  columnDragKey = null;
  renderSlot();
  els.columnsButton.focus();
}

// The chrome is built once so typing in the search box keeps the caret.
function renderColumnsPanel() {
  if (!els.columnsPanel.firstChild) buildColumnsChrome();
  const shown = visibleColumns().length;
  const total = allColumns().length;
  document.getElementById("columns-count").textContent =
    NUMBER.format(shown) + " shown · " + NUMBER.format(total - shown) + " hidden";
  document.getElementById("hide-empty").checked = Boolean(state.columnSettings.auto_hide_empty);
  renderColumnRows();
}

function buildColumnsChrome() {
  const panel = els.columnsPanel;
  const head = el("div", "columns-head");
  const titles = el("div", "columns-titles");
  titles.append(el("div", "columns-title", "Columns"), el("div", "columns-count-line"));
  titles.lastChild.id = "columns-count";
  const close = paneButton("ghost icon columns-close", "×", "Close column manager");
  close.id = "columns-close";
  close.addEventListener("click", closeColumnsPanel);
  head.append(titles, el("span", "spacer"), close);

  const search = el("input", "columns-search");
  search.id = "columns-search";
  search.type = "search";
  search.placeholder = "Find a column";
  search.setAttribute("aria-label", "Find a column");
  search.addEventListener("input", () => {
    columnQuery = search.value;
    renderColumnRows();
  });

  const scroller = el("div", "columns-scroller");
  scroller.id = "columns-scroller";

  const foot = el("div", "columns-foot");
  const hideLabel = el("label", "columns-hide-empty");
  const hideBox = el("input");
  hideBox.id = "hide-empty";
  hideBox.type = "checkbox";
  hideBox.addEventListener("change", () =>
    storeColumns({ auto_hide_empty: hideBox.checked }, (b) => b.setAutoHideEmpty(hideBox.checked)),
  );
  hideLabel.append(hideBox, el("span", "", "Hide empty columns"));
  const reset = paneButton("ghost", "Reset to defaults");
  reset.id = "columns-reset";
  reset.addEventListener("click", () => storeColumns({ order: null, visible: null }, (b) => b.resetColumns()));
  const done = paneButton("secondary", "Done");
  done.id = "columns-done";
  done.addEventListener("click", closeColumnsPanel);
  foot.append(hideLabel, el("span", "spacer"), reset, done);

  panel.append(head, search, scroller, foot);
}

function renderColumnRows() {
  const scroller = document.getElementById("columns-scroller");
  const active = document.activeElement;
  const keep = active && active.closest ? active.closest(".col-row") : null;
  const keepKey = keep ? keep.dataset.key : null;
  const keepCheck = Boolean(keep && active.classList.contains("col-check"));

  const query = columnQuery.trim().toLowerCase();
  const visible = new Set(visibleColumns().map((c) => c.key));
  const ordered = orderedColumns();
  scroller.textContent = "";
  for (const group of COLUMN_GROUPS) {
    const cols = ordered.filter((c) => c.group === group);
    const hits = cols.filter((c) => c.title.toLowerCase().includes(query));
    if (!hits.length) continue;
    const head = el("div", "col-group", group.toUpperCase() + " ");
    head.dataset.group = group;
    head.append(el("span", "col-group-count",
      NUMBER.format(cols.filter((c) => visible.has(c.key)).length) + " of " + NUMBER.format(cols.length)));
    scroller.append(head);
    for (const col of hits) scroller.append(columnRow(col));
  }
  if (!keepKey) return;
  const row = scroller.querySelector('.col-row[data-key="' + CSS.escape(keepKey) + '"]');
  if (row) (keepCheck ? row.querySelector(".col-check") : row).focus();
}

function columnRow(col) {
  const reorderable = !col.pinned && columnQuery.trim() === "";
  const hidden = autoHidden(col);
  const row = el("div", "col-row");
  row.dataset.key = col.key;
  row.tabIndex = 0;

  const grip = el("span", "col-grip");
  if (reorderable) grip.innerHTML = svg(GRIP, "grip");
  row.append(grip);

  const box = el("input", "col-check");
  box.type = "checkbox";
  box.checked = userVisible(col);
  box.disabled = Boolean(col.pinned);
  box.setAttribute("aria-label", col.title);
  box.addEventListener("change", () => setColumnShown(col.key, box.checked));
  row.append(box);

  const title = el("span", "col-title" + (hidden ? " muted" : ""), col.title);
  title.title = col.title;
  row.append(title, el("span", "col-note", col.pinned ? "pinned" : hidden ? "empty" : ""));

  if (reorderable) bindColumnDrag(row, col.key);
  row.addEventListener("keydown", (e) => onColumnRowKey(e, col));
  return row;
}

// The operator's choice, before auto-hide. Pinned keys are never in the list:
// `userVisible` returns true for them whatever it holds.
function setColumnShown(key, on) {
  const keys = orderedColumns()
    .filter((c) => !c.pinned && (c.key === key ? on : userVisible(c)))
    .map((c) => c.key);
  storeColumns({ visible: keys }, (b) => b.setVisibleColumns(keys));
}

// The table's one sequence, pinned pair first.
function moveColumn(key, target, after) {
  const keys = orderedColumns().map((c) => c.key).filter((k) => k !== key);
  const floor = keys.indexOf(PINNED_KEYS[PINNED_KEYS.length - 1]) + 1;
  const at = Math.max(floor, keys.indexOf(target) + (after ? 1 : 0));
  keys.splice(at, 0, key);
  storeColumns({ order: keys }, (b) => b.setColumnOrder(keys));
}

// Alt+arrow uses the rows on screen, so it reads as moving up or down the list.
function moveByList(key, delta) {
  const keys = [...document.querySelectorAll(".col-row")].map((r) => r.dataset.key);
  const target = keys[keys.indexOf(key) + delta];
  if (target !== undefined) moveColumn(key, target, delta > 0);
}

function onColumnRowKey(e, col) {
  if (e.key === " " && !e.target.classList.contains("col-check")) {
    e.preventDefault();
    if (!col.pinned) setColumnShown(col.key, !userVisible(col));
    return;
  }
  if (!e.altKey || col.pinned || columnQuery.trim() !== "") return;
  if (e.key === "ArrowUp" || e.key === "ArrowDown") {
    e.preventDefault();
    moveByList(col.key, e.key === "ArrowDown" ? 1 : -1);
  }
}

function clearDropMarks() {
  for (const row of document.querySelectorAll(".col-row[data-drop]")) delete row.dataset.drop;
}

function bindColumnDrag(row, key) {
  row.draggable = true;
  row.addEventListener("dragstart", (e) => {
    columnDragKey = key;
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", key);
  });
  row.addEventListener("dragend", () => {
    columnDragKey = null;
    clearDropMarks();
  });
  row.addEventListener("dragover", (e) => {
    if (columnDragKey === null || columnDragKey === key) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    const box = row.getBoundingClientRect();
    row.dataset.drop = e.clientY - box.top > box.height / 2 ? "after" : "before";
  });
  row.addEventListener("dragleave", () => delete row.dataset.drop);
  row.addEventListener("drop", (e) => {
    e.preventDefault();
    const after = row.dataset.drop === "after";
    const moved = columnDragKey;
    columnDragKey = null;
    clearDropMarks();
    if (moved !== null && moved !== key) moveColumn(moved, key, after);
  });
}

function bindColumns() {
  els.columnsButton.addEventListener("click", () =>
    state.columnsOpen ? closeColumnsPanel() : openColumnsPanel(),
  );
  els.columnsPanel.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    e.stopPropagation();
    closeColumnsPanel();
  });
}
```

The pinned row still gets a `dragover` listener through no path at all: it is
not `reorderable`, so a drop cannot land on it. `moveColumn`'s `floor` is what
keeps a drop **above** the pinned pair legal — it lands after `order`.

- [ ] **Step 4: Append the manager CSS** to `results.css`. The
  `.pane, .columns-panel` plane rule is already there from Task 8; this adds
  only what the manager needs.

```css
/* --- the column manager (Bundle 13 §6.9) ------------------------------------ */
/* 16 + 40 + 8 + 32 + 8 + scroller + 8 + 32 + 16 = 508, so the scroller is 348. */

.columns-panel { gap: var(--spacing-sm); }

.columns-head { flex-shrink: 0; display: flex; align-items: flex-start; height: 40px; }
.columns-titles { min-width: 0; }
.columns-title { font-size: var(--type-label-size); font-weight: 700; }
.columns-count-line { font-size: var(--type-caption-size); color: var(--text-secondary); }
.btn.columns-close { width: 32px; height: 32px; }

.columns-search {
  flex: 0 0 32px;
  width: 100%;
  padding: 0 var(--padding-h);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
}
.columns-search::placeholder { color: var(--text-placeholder); }
.columns-search:focus { outline: 2px solid var(--focus-ring); outline-offset: -1px; }

.columns-scroller { flex: 1; min-height: 0; overflow-y: auto; }

.col-group {
  position: sticky;
  top: 0;
  height: 22px;
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  background: var(--surface-raised);
  font-size: var(--type-caption-size);
  font-weight: 700;
  letter-spacing: 0.06em;
  color: var(--text-secondary);
}
.col-group-count { font-weight: 400; letter-spacing: normal; }

.col-row {
  position: relative;
  height: 30px;
  display: grid;
  grid-template-columns: 16px 20px minmax(0, 1fr) auto;
  align-items: center;
  gap: var(--spacing-xs);
}
.col-row:hover { background: var(--hover); }
.col-row:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: -2px; }
.col-grip { display: flex; align-items: center; color: var(--text-secondary); cursor: grab; }
.grip { width: 14px; height: 14px; fill: none; stroke: currentColor; stroke-width: 2.5; stroke-linecap: round; }
.col-title { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.col-title.muted { color: var(--text-secondary); }
.col-note { font-size: var(--type-caption-size); color: var(--text-secondary); white-space: nowrap; }

/* The insertion line a drop would land on. */
.col-row[data-drop]::before {
  content: "";
  position: absolute;
  left: 0;
  right: 0;
  height: 2px;
  background: var(--focus-ring);
}
.col-row[data-drop="before"]::before { top: 0; }
.col-row[data-drop="after"]::before { bottom: 0; }

.columns-foot { flex: 0 0 32px; display: flex; align-items: center; gap: var(--spacing-sm); }
.columns-hide-empty { display: flex; align-items: center; gap: var(--spacing-xs); white-space: nowrap; }
```

If `--padding-h`, `--radius`, `--surface` or `--text-placeholder` are not the
names the existing `#search` rule uses, copy that rule's names instead — the
manager's search must look like the table's.

- [ ] **Step 5: Run the columns tests, the pane tests, Bundle 12's, and the lint**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_results_columns.py tests/test_results_pane.py tests/test_results_document.py -q`
Then the style-lint test (`grep -rln style_lint tests` names it).
Expected: PASS. The lint bans shadow, gradient, transition, transform and
opacity; none of the above uses one. `cursor: grab` and `stroke-linecap` are
not on its list — if the lint has grown a rule that rejects one, drop the
declaration rather than suppressing the rule.

- [ ] **Step 6: Commit**

```bash
/usr/bin/git add gui/web/columns.js gui/web/results.css tests/test_results_columns.py
```

```bash
/usr/bin/git commit -m "Bundle 13: the column manager in the slot, with search, drag and auto-hide (9.16)"
```

### Task 10: The whole bundle, verified

No new code. This task proves the eight before it hold together, and leaves the
branch in the state Stage C reviews.

**Files:** none, unless a failure sends you back into one.

- [ ] **Step 1: The full suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
Expected: PASS, with no skips in `tests/test_results_columns.py` or
`tests/test_results_pane.py` — a Chromium test that skips is a test that never
ran. If something outside this bundle fails, fix it here rather than leaving it
for the review; if it fails on `main` too, say so in the PR body instead.

- [ ] **Step 2: The lint**

Run: `.venv/bin/ruff check . --exclude shared`
Expected: clean.

- [ ] **Step 3: The done check (spec §7.6)**

Run: `grep -rn "ColumnConfigPanel\|ColumnConfigDialog\|TableConfigManager\|table_config_manager\|column_config_dialog" gui tests`
Expected: no output. Task 5's file-scan test asserts the same thing; this is
the ten-second version of it. `shared/` and `docs/` are out of scope — a spec
naming the deleted modules is history, not a live reference.

- [ ] **Step 4: The screen, by hand**

Run: `.venv/bin/python run_dev.py`, open a run's results, and check the five
things the tests cannot see:
  - the pane and the manager sit on the same plane as the KPI cards, in both
    themes (switch in Settings and look again);
  - dragging a column lands where the insertion line said it would, and the
    table's header moves with it;
  - the manager's search finds a column and the handles disappear while typing;
  - at a narrow window the strip appears, and its button opens the pane;
  - the pane's verbs raise their Qt toasts, and Undo in the toast works.

- [ ] **Step 5: Refresh the graph** (this repo's CLAUDE.md)

Run: `.venv/bin/python -m graphify update .` — or `graphify update .` if that
is what is on `PATH`. Two new modules and two deleted ones make a stale graph
actively wrong about this screen.

- [ ] **Step 6: Commit whatever Steps 1–5 changed**

If nothing changed, there is nothing to commit; the graph output is committed
only if this repo already tracks it (`git status --short graphify-out`).

```bash
/usr/bin/git status --short
```

Stage C pushes the branch and opens the PR. Do not push here.
