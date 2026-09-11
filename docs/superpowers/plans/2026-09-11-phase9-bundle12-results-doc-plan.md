# Phase 9 Bundle 12 — The Results Document Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task, **in this session**. Do not fan out to subagents: this runner's CLAUDE.md forbids it. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Qt Analysis Results screen with one `QWebEngineView` holding the results document: a KPI strip, a filter bar and a windowed order table. Add optional `Customer`/`Created_At` orders-file fields.

**Architecture:**
- **Python** folds the line frame into an order payload and a KPI summary (pure functions in `gui/orders_view.py`) and pushes both through the existing `ResultsBridge`.
- **The page** (`gui/web/results.{html,css,js}`, plain JS) owns sort, search, filter chips and the selection gesture (ADR 0005). It reports only the selection and two commands (`openExport`, `openScreenMenu`) back.
- **The Qt table screen** and everything only it reached are deleted.

**Tech Stack:** PySide6 6.7+ (QtWebEngine, QtWebChannel), pandas, pytest + pytest-qt, plain ES2020 JS, CSS custom properties from `shared.theme.theme_css_vars`.

**Spec:** `docs/superpowers/specs/2026-09-11-phase9-bundle12-results-doc-design.md`. Read it first. ADR 0005 and Bundle 11's `docs/superpowers/specs/2026-09-11-phase9-bundle11-seam-design.md` §5 are background.

## Global Constraints

- **Test command:** `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest <path> -q`. There is no `python` on PATH. Run `./scripts/setup_venv.sh` first if `.venv` is missing in the worktree.
- **Lint:** `.venv/bin/python -m ruff check . --exclude shared`. `tests/test_style_literals_guard.py` scans `gui/` including `gui/web/*.css|html|js`.
- **Web assets:**
  - No hex colours. No `box-shadow`, `transition*`, `transform`/`scale`/`rotate`/`translate`, `opacity` or gradients. No px font sizes. No `var(--<alias>)`.
  - Every colour is a `var(--token)` from `theme_css_vars`.
  - Position windowed rows with `top`, never `transform`.
- **Never edit `shared/`.** It is synced from packing-tool, and this bundle needs no `shared/` change.
- **Copy, verbatim:**
  - `Order, customer or SKU`
  - `Add filter`, `Clear all`
  - `312 orders` / `44 of 312 orders`
  - `Export 281 orders`
  - `Nothing analysed yet` / `Load the orders and stock files in Setup, then run the analysis. Every order it finds lands here.`
  - `No orders match` / `Remove a filter or clear the search.`
  - KPI labels: `Orders`, `Fulfillable`, `Blocked`, `Labels`, `Value ready`, `Oldest waiting`
  - Column titles: `Status`, `Order`, `Customer`, `Lines`, `Units`, `Value`, `Courier`, `Age`
  - Status labels: `Fulfillable`, `Blocked`
  - Chip labels: `Repeat`, `Unknown SKU`, `Low stock`, `3 or more lines`, `Courier: <name>`, `Tag: <name>`, `No courier`
  - `More actions for this screen`
- **Geometry (desk density):**
  - page padding 16, row gap 12, KPI strip 88, filter bar 40, header 28, row `--row-height` (28)
  - column widths: select 32, Status 132, Order 84, Lines 56, Units 56, Value 84, Courier 76, Age 56
  - table minimum 780
- **Tests import the bridge-test helpers** with `from test_results_bridge import _eval, _until_js`. `tests/` has no `__init__.py`, so pytest puts `tests/` on `sys.path`.
- **VM guard:**
  - Call git as `/usr/bin/git`, one command per Bash call.
  - No `&&` chains and no heredocs.
  - Commit messages end with `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.

## File map

| File | Change | Responsibility |
|---|---|---|
| `gui/settings/mappings.py` | modify | `Customer`, `Created_At` become optional orders fields |
| `shopify_tool/profile_manager.py` | modify | New profiles map `Shipping Name`, `Created at` |
| `shopify_tool/analysis.py` | modify | Carry and per-order fill both fields |
| `gui/orders_view.py` | modify | Payload derived keys; `results_summary` |
| `gui/results_bridge.py` | modify | `summary`, `exportEnabled`, `openExport`, `openScreenMenu`, `focusSearchRequested` |
| `docs/superpowers/specs/2026-09-11-phase9-bundle11-seam-design.md` | modify | Catalogue §5.2 amended |
| `gui/web/results.html`, `results.css`, `results.js` | rewrite | The document |
| `gui/ui_manager.py` | modify | Tab 2 becomes the web view; command-bar role; session chips; deletions |
| `gui/main_window_pyside.py` | modify | Wiring; deletions |
| `gui/components/commandbar.py` | modify | `bind_action(role)`, `stock_chip`, `set_stock_age` |
| `gui/selection_helper.py` | modify | Drop dead `table_view`/`proxy_model` |
| `gui/actions_handler.py`, `gui/column_config_dialog.py`, `gui/pandas_model.py`, `gui/components/__init__.py` | modify | Remove Qt-table remnants |
| `gui/order_detail_pane.py`, `gui/tag_management_panel.py`, `gui/tag_delegate.py`, `gui/components/statcard.py` | delete | Only the Qt screen used them |
| `tests/test_results_data_fields.py` | create | Task 1 |
| `tests/test_results_summary.py` | create | Task 2 |
| `tests/test_results_bridge.py` | modify | Task 3 |
| `tests/test_results_document.py` | create | Tasks 4–5 |
| `tests/test_results_screen.py` | create | Tasks 6–7 |

---

### Task 1: `Customer` and `Created_At` reach the analysis frame

**Files:**
- Modify: `gui/settings/mappings.py:148-155`, `shopify_tool/profile_manager.py:409-420`, `shopify_tool/analysis.py:211-224`, `:287-292`, `:310-321`, `:1119-1140`, `gui/orders_view.py:19-32`
- Test: `tests/test_results_data_fields.py`

**Interfaces:**
- Produces: the analysis frame has columns `Customer` and `Created_At` (raw CSV strings, filled within each order) whenever the orders CSV maps them, and neither column otherwise. `ORDER_LEVEL_COLUMNS` contains both.

- [ ] **Step 1: Write the failing tests**

```python
"""Customer and Created_At: two optional orders-file fields (Bundle 12 spec §3)."""

import pandas as pd

from gui.orders_view import ORDER_LEVEL_COLUMNS
from shopify_tool import analysis


def _orders(rows):
    defaults = {"Name": "", "Lineitem sku": "", "Lineitem quantity": 1, "Shipping Method": "Standard"}
    return pd.DataFrame([{**defaults, **r} for r in rows])


def _stock():
    return pd.DataFrame([{"Артикул": "A", "Име": "A", "Наличност": 50},
                         {"Артикул": "B", "Име": "B", "Наличност": 50}])


def _run(orders):
    history = pd.DataFrame(columns=["Order_Number", "Execution_Date"])
    final_df, *_ = analysis.run_analysis(_stock(), orders, history)
    return final_df


def test_customer_and_created_at_are_carried_and_filled_within_each_order():
    final_df = _run(_orders([
        {"Name": "#1", "Lineitem sku": "A", "Shipping Name": "B. Fischer",
         "Created at": "2026-09-02 09:12:44 +0200"},
        {"Name": "#1", "Lineitem sku": "B"},  # Shopify leaves order fields blank on later lines
        {"Name": "#2", "Lineitem sku": "A"},  # an order with neither
    ]))
    first = final_df[final_df["Order_Number"] == "#1"]
    assert first["Customer"].tolist() == ["B. Fischer", "B. Fischer"]
    assert first["Created_At"].tolist() == ["2026-09-02 09:12:44 +0200"] * 2
    second = final_df[final_df["Order_Number"] == "#2"]
    # Filled per order, never from the order above it.
    assert second["Customer"].isna().all()
    assert second["Created_At"].isna().all()


def test_absent_columns_are_not_invented():
    final_df = _run(_orders([{"Name": "#1", "Lineitem sku": "A"}]))
    assert "Customer" not in final_df.columns
    assert "Created_At" not in final_df.columns


def test_both_are_order_level():
    assert "Customer" in ORDER_LEVEL_COLUMNS
    assert "Created_At" in ORDER_LEVEL_COLUMNS


def test_the_mapping_page_offers_both():
    from gui.settings.mappings import OrdersMappingPage

    assert {"Customer", "Created_At"} <= set(OrdersMappingPage.OPTIONAL_FIELDS)


def test_new_profiles_map_shopifys_headers(profile_manager):
    profile_manager.create_client_profile("M", "Client")
    orders = profile_manager.load_shopify_config("M")["column_mappings"]["orders"]
    assert orders["Shipping Name"] == "Customer"
    assert orders["Created at"] == "Created_At"
```

If `load_shopify_config("M")` is not where `column_mappings` lives, find the reader with `git grep -n "column_mappings" -- tests/test_profile_manager.py` and use the same call that file uses. Keep the two assertions.

- [ ] **Step 2: Run to verify failure**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_results_data_fields.py -q`
Expected: 5 failed (`KeyError: 'Customer'`, the assertions, and the missing mapping).

- [ ] **Step 3: Implement**

`gui/settings/mappings.py`, in `OrdersMappingPage.OPTIONAL_FIELDS` after `"Subtotal",`:
```python
        "Customer",
        "Created_At",
```

`shopify_tool/profile_manager.py`, in the new-profile `"orders"` dict after `"Subtotal": "Subtotal",`:
```python
                    "Shipping Name": "Customer",
                    "Created at": "Created_At",
```

`shopify_tool/analysis.py`:
- In the `column_mappings is None` fallback `"orders"` dict, after `"Subtotal": "Subtotal",`, add the same two entries.
- Directly after the `Tags` forward-fill (`orders_df["Tags"] = orders_df["Tags"].ffill()`), add:
```python
    # Shopify writes these on an order's first line only. Filled within the
    # order, never from the one above it: an order with no customer stays blank.
    for col in ("Customer", "Created_At"):
        if col in orders_df.columns:
            orders_df[col] = orders_df.groupby("Order_Number")[col].ffill()
```
- In `base_columns`, after `"Subtotal",`, add `"Customer",` and `"Created_At",`.
- In the `output_columns = [` literal, after `"Lot_Details",  # …`, add:
```python
        # Appended last so the positional inserts below (3, 6, 7) do not move.
        "Customer",
        "Created_At",
```

`gui/orders_view.py`, in `ORDER_LEVEL_COLUMNS` after `"Subtotal",`, add `"Customer",` and `"Created_At",`.

- [ ] **Step 4: Run to verify pass, and the neighbours**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_results_data_fields.py tests/test_analysis.py tests/test_profile_manager.py tests/test_settings_page_mappings.py tests/test_orders_view.py -q`
Expected: all pass. If a test pins an exact column list or an exact default-mapping dict, add the two names to that expectation. Do not remove them from the code.

- [ ] **Step 5: Commit**

```
/usr/bin/git add gui/settings/mappings.py shopify_tool/profile_manager.py shopify_tool/analysis.py gui/orders_view.py tests/test_results_data_fields.py
/usr/bin/git commit -m "feat(results): optional Customer and Created_At orders fields"
```
(Include any test files adjusted in Step 4.)

---

### Task 2: Payload derived keys and `results_summary`

**Files:**
- Modify: `gui/orders_view.py`
- Test: `tests/test_results_summary.py`

**Interfaces:**
- Consumes: `ORDER_LEVEL_COLUMNS` with `Customer`/`Created_At` (Task 1).
- Produces:
  - `order_payload(df) -> list[dict]`: each entry also has `Units: int`, `Created_At: str | None` (ISO 8601, UTC offset), `Tag_List: list[str]`, `Unknown_SKU: bool`, `Low_Stock: bool`. Existing keys stay, including `Items` and `_repeat`.
  - `results_summary(df) -> dict`: `{}` when there is nothing; otherwise the keys `orders, lines, skus, fulfillable, blocked, blocked_lines, blocked_skus, labels_by_courier, value_ready, value_total, oldest`.
  - Constants `FULFILLABLE = "Fulfillable"` and `NO_COURIER = "No courier"`.

- [ ] **Step 1: Write the failing tests**

```python
"""The two Python seams behind the results document (Bundle 12 spec §4)."""

import json

import pandas as pd
import pytest

from gui.orders_view import order_payload, results_summary


@pytest.fixture
def lines():
    base = {"System_note": "", "Has_SKU": True, "Stock_Alert": ""}
    return pd.DataFrame([
        {**base, "Order_Number": "#1", "Order_Fulfillment_Status": "Fulfillable",
         "Shipping_Provider": "DHL", "SKU": "A", "Quantity": 2, "Total_Price": 10.0,
         "Created_At": "2026-09-02 09:00:00 +0200", "Internal_Tags": '["vip"]'},
        {**base, "Order_Number": "#1", "Order_Fulfillment_Status": "Fulfillable",
         "Shipping_Provider": "DHL", "SKU": "B", "Quantity": 1, "Total_Price": 10.0,
         "Created_At": "2026-09-02 09:00:00 +0200", "Internal_Tags": '["vip"]',
         "Stock_Alert": "Low Stock"},
        {**base, "Order_Number": "#2", "Order_Fulfillment_Status": "Not Fulfillable",
         "Shipping_Provider": "DPD", "SKU": "C", "Quantity": 4, "Total_Price": 25.5,
         "Created_At": "2026-09-01 08:00:00 +0200", "Internal_Tags": "[]", "Has_SKU": False},
        {**base, "Order_Number": "#3", "Order_Fulfillment_Status": "Fulfillable",
         "Shipping_Provider": "", "SKU": "A", "Quantity": "x", "Total_Price": 5.0,
         "Created_At": "not a date", "Internal_Tags": ""},
    ])


def _by_order(payload):
    return {entry["Order_Number"]: entry for entry in payload}


def test_the_payload_counts_units_and_coerces_junk_to_zero(lines):
    orders = _by_order(order_payload(lines))
    assert orders["#1"]["Units"] == 3
    assert orders["#2"]["Units"] == 4
    assert orders["#3"]["Units"] == 0


def test_the_payload_normalises_created_at_or_drops_it(lines):
    orders = _by_order(order_payload(lines))
    assert orders["#1"]["Created_At"] == "2026-09-02T07:00:00+00:00"
    assert orders["#3"]["Created_At"] is None


def test_the_payload_carries_tags_and_flags(lines):
    orders = _by_order(order_payload(lines))
    assert orders["#1"]["Tag_List"] == ["vip"]
    assert orders["#3"]["Tag_List"] == []
    assert (orders["#1"]["Low_Stock"], orders["#1"]["Unknown_SKU"]) == (True, False)
    assert (orders["#2"]["Low_Stock"], orders["#2"]["Unknown_SKU"]) == (False, True)


def test_the_payload_flags_default_off_without_their_columns():
    payload = order_payload(pd.DataFrame({"Order_Number": ["#1"], "SKU": ["A"]}))
    assert payload[0]["Units"] == 0
    assert payload[0]["Created_At"] is None
    assert payload[0]["Tag_List"] == []
    assert payload[0]["Unknown_SKU"] is False
    assert payload[0]["Low_Stock"] is False


def test_the_summary_counts_the_session(lines):
    s = results_summary(lines)
    assert (s["orders"], s["lines"], s["skus"]) == (3, 4, 3)
    assert (s["fulfillable"], s["blocked"]) == (2, 1)
    assert (s["blocked_lines"], s["blocked_skus"]) == (1, 1)


def test_labels_are_fulfillable_orders_by_courier_blank_named(lines):
    # Equal counts fall back to name order.
    assert results_summary(lines)["labels_by_courier"] == [["DHL", 1], ["No courier", 1]]


def test_value_counts_each_order_once(lines):
    s = results_summary(lines)
    assert s["value_total"] == pytest.approx(40.5)
    assert s["value_ready"] == pytest.approx(15.0)


def test_value_is_none_without_a_price_column(lines):
    s = results_summary(lines.drop(columns=["Total_Price"]))
    assert s["value_total"] is None
    assert s["value_ready"] is None


def test_oldest_is_the_earliest_parseable_order(lines):
    assert results_summary(lines)["oldest"] == {
        "order_number": "#2", "created_at": "2026-09-01T06:00:00+00:00"}
    assert results_summary(lines.drop(columns=["Created_At"]))["oldest"] is None


def test_nothing_to_summarise_is_an_empty_dict():
    assert results_summary(None) == {}
    assert results_summary(pd.DataFrame()) == {}
    assert results_summary(pd.DataFrame({"SKU": ["A"]})) == {}


def test_both_survive_strict_json(lines):
    json.dumps(order_payload(lines), allow_nan=False)
    json.dumps(results_summary(lines), allow_nan=False)
```

- [ ] **Step 2: Run to verify failure**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_results_summary.py -q`
Expected: collection fails with `ImportError: cannot import name 'results_summary'`.

- [ ] **Step 3: Implement in `gui/orders_view.py`**

Add `from shopify_tool.tag_manager import parse_tags` to the imports. After `ORDER_KEY = "Order_Number"`, add:

```python
FULFILLABLE = "Fulfillable"
NO_COURIER = "No courier"
```

Add these helpers above `order_payload`:

```python
def _iso_or_none(value):
    """An orders-file timestamp as ISO 8601 in UTC, or None if it isn't one."""
    if isinstance(value, (list, dict)):
        return None
    stamp = pd.to_datetime(value, utc=True, errors="coerce")
    return None if pd.isna(stamp) else stamp.isoformat()


def _per_order_any(df: pd.DataFrame, mask: pd.Series) -> pd.Series:
    return mask.groupby(df[ORDER_KEY], sort=False).any()
```

Replace the body of `order_payload` from `payload = []` to the end with:

```python
    by_order = df[ORDER_KEY]
    units = (
        pd.to_numeric(df["Quantity"], errors="coerce").fillna(0).groupby(by_order, sort=False).sum()
        if "Quantity" in df.columns
        else pd.Series(dtype=float)
    )
    unknown_sku = (
        _per_order_any(df, df["Has_SKU"].eq(False))
        if "Has_SKU" in df.columns
        else pd.Series(dtype=bool)
    )
    low_stock = (
        _per_order_any(df, df["Stock_Alert"].fillna("").astype(str).str.strip().ne(""))
        if "Stock_Alert" in df.columns
        else pd.Series(dtype=bool)
    )

    payload = []
    for row in orders[columns].itertuples(index=False, name=None):
        key = row[0]
        entry = dict(zip(columns, map(_json_value, row)))
        entry["lines"] = lines.get(key, [])
        # Derived per order, for the results document (Bundle 12 spec §4.1).
        entry["Units"] = int(units.get(key, 0))
        entry["Created_At"] = _iso_or_none(entry.get("Created_At"))
        entry["Tag_List"] = parse_tags(entry.get("Internal_Tags"))
        entry["Unknown_SKU"] = bool(unknown_sku.get(key, False))
        entry["Low_Stock"] = bool(low_stock.get(key, False))
        payload.append(entry)
    return payload
```

Append at the end of the module:

```python
def _order_values(df: pd.DataFrame) -> pd.Series:
    """Each order's Total_Price, once: the column repeats on every line."""
    firsts = df.groupby(ORDER_KEY, sort=False)["Total_Price"].first()
    return pd.to_numeric(firsts, errors="coerce").fillna(0.0)


def _labels_by_courier(df: pd.DataFrame, fulfillable_orders: set) -> list:
    """One label per fulfillable order, counted per courier, biggest first."""
    if not fulfillable_orders:
        return []
    ready = df[df[ORDER_KEY].isin(fulfillable_orders)].drop_duplicates(ORDER_KEY)
    if "Shipping_Provider" in ready.columns:
        couriers = ready["Shipping_Provider"].fillna("").astype(str).str.strip()
        couriers = couriers.mask(couriers.eq(""), NO_COURIER)
    else:
        couriers = pd.Series(NO_COURIER, index=ready.index)
    pairs = [[str(name), int(count)] for name, count in couriers.value_counts().items()]
    return sorted(pairs, key=lambda pair: (-pair[1], pair[0]))


def _oldest(df: pd.DataFrame):
    """The order created longest ago, among those with a readable Created_At."""
    if "Created_At" not in df.columns:
        return None
    firsts = df.groupby(ORDER_KEY, sort=False)["Created_At"].first()
    iso = firsts.map(_iso_or_none).dropna()
    if iso.empty:
        return None
    stamps = pd.to_datetime(iso, utc=True)
    key = stamps.idxmin()
    return {"order_number": _json_value(key), "created_at": stamps[key].isoformat()}


def results_summary(df: pd.DataFrame) -> dict:
    """The KPI strip's numbers, over the whole session (Bundle 12 spec §4.2).

    Computed from the line frame, as the Qt strip was: quantities, SKUs and
    lines only exist there. Never narrowed by the page's filters.
    """
    if df is None or df.empty or ORDER_KEY not in df.columns:
        return {}

    if "Order_Fulfillment_Status" in df.columns:
        ready_mask = df["Order_Fulfillment_Status"].eq(FULFILLABLE)
    else:
        ready_mask = pd.Series(False, index=df.index)
    fulfillable_orders = set(df.loc[ready_mask, ORDER_KEY])
    blocked_rows = df[~df[ORDER_KEY].isin(fulfillable_orders)]
    has_sku = "SKU" in df.columns
    orders = int(df[ORDER_KEY].nunique())

    summary = {
        "orders": orders,
        "lines": int(len(df)),
        "skus": int(df["SKU"].nunique()) if has_sku else 0,
        "fulfillable": len(fulfillable_orders),
        "blocked": orders - len(fulfillable_orders),
        "blocked_lines": int(len(blocked_rows)),
        "blocked_skus": int(blocked_rows["SKU"].nunique()) if has_sku else 0,
        "labels_by_courier": _labels_by_courier(df, fulfillable_orders),
        "value_ready": None,
        "value_total": None,
        "oldest": _oldest(df),
    }
    if "Total_Price" in df.columns:
        values = _order_values(df)
        summary["value_total"] = float(values.sum())
        summary["value_ready"] = float(values[values.index.isin(fulfillable_orders)].sum())
    return summary
```

- [ ] **Step 4: Run to verify pass, and the Bundle 11 tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_results_summary.py tests/test_orders_view.py tests/test_results_bridge.py -q`
Expected: all pass. (If `tests/test_orders_view.py` does not exist, drop it from the command.)

- [ ] **Step 5: Commit**

```
/usr/bin/git add gui/orders_view.py tests/test_results_summary.py
/usr/bin/git commit -m "feat(results): payload derived keys and results_summary"
```

---

### Task 3: The bridge's Bundle 12 members

**Files:**
- Modify: `gui/results_bridge.py`, `docs/superpowers/specs/2026-09-11-phase9-bundle11-seam-design.md` (§5.2 table)
- Test: `tests/test_results_bridge.py` (append)

**Interfaces:**
- Consumes: `results_summary(df)` (Task 2).
- Produces, on `ResultsBridge`:
  - properties `summary` (`QVariantMap`, notify `summaryChanged`) and `exportEnabled` (`bool`, notify `exportEnabledChanged`)
  - slots `openExport()` and `openScreenMenu()`
  - JS-facing signal `focusSearchRequested()`
  - Python-facing signals `exportRequested()` and `screenMenuRequested()`
  - Python API `set_orders(df)`, which now also sets `summary`, and `set_export_enabled(enabled: bool)`

- [ ] **Step 1: Write the failing tests** (append to `tests/test_results_bridge.py`)

```python
def test_set_orders_also_sets_the_summary(qapp):
    bridge = ResultsBridge()
    seen = []
    bridge.summaryChanged.connect(lambda: seen.append(bridge.summary))
    bridge.set_orders(pd.DataFrame({"Order_Number": ["#1", "#2"], "SKU": ["A", "B"]}))
    assert seen and seen[-1]["orders"] == 2


def test_open_export_is_a_request_python_hears(qapp):
    bridge = ResultsBridge()
    heard = []
    bridge.exportRequested.connect(lambda: heard.append(True))
    bridge.openExport()
    assert heard == [True]


def test_open_screen_menu_is_a_request_python_hears(qapp):
    bridge = ResultsBridge()
    heard = []
    bridge.screenMenuRequested.connect(lambda: heard.append(True))
    bridge.openScreenMenu()
    assert heard == [True]


def test_export_enabled_notifies_only_on_change(qapp):
    bridge = ResultsBridge()
    changes = []
    bridge.exportEnabledChanged.connect(lambda: changes.append(bridge.exportEnabled))
    bridge.set_export_enabled(True)
    bridge.set_export_enabled(True)
    bridge.set_export_enabled(False)
    assert changes == [True, False]


def test_the_summary_arrives_in_js(qtbot, page):
    view, bridge = page
    bridge.set_orders(pd.DataFrame({"Order_Number": ["#1", "#1", "#2"], "SKU": ["A", "B", "C"]}))
    _until_js(qtbot, view, "window.resultsBridge.summary.orders === 2")
    assert _eval(qtbot, view, "window.resultsBridge.summary.lines") == 3
```

- [ ] **Step 2: Run to verify failure**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_results_bridge.py -q`
Expected: the five new tests fail with `AttributeError` (`summaryChanged`, `openExport`, …).

- [ ] **Step 3: Implement in `gui/results_bridge.py`**

Change the import to `from gui.orders_view import order_payload, results_summary`. Change the module docstring's last paragraph to:

```python
The full catalogue, and which bundle adds each member, is section 5.2 of
docs/superpowers/specs/2026-09-11-phase9-bundle11-seam-design.md, as amended
by Bundle 12 (docs/superpowers/specs/2026-09-11-phase9-bundle12-results-doc-design.md
section 5). Add a member there before adding it here.
```

Replace the class with:

```python
class ResultsBridge(QObject):
    """The results document's one channel object (Bundles 11 and 12)."""

    ordersChanged = Signal()
    summaryChanged = Signal()
    themeCssChanged = Signal()
    exportEnabledChanged = Signal()
    # JS-facing: Ctrl+F in the Qt window focuses the page's search field.
    focusSearchRequested = Signal()
    # Python-facing. JS reports through the slots below and never connects to
    # these, so nothing it sends can echo back into the page.
    selectionChanged = Signal(list)
    exportRequested = Signal()
    screenMenuRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._orders: list = []
        self._summary: dict = {}
        self._theme_css = ""
        self._export_enabled = False
        self._selection: list[str] = []

    # --- out: Python -> JS -------------------------------------------------

    def _get_orders(self) -> list:
        return self._orders

    orders = Property("QVariantList", _get_orders, notify=ordersChanged)

    def _get_summary(self) -> dict:
        return self._summary

    summary = Property("QVariantMap", _get_summary, notify=summaryChanged)

    def _get_theme_css(self) -> str:
        return self._theme_css

    themeCss = Property(str, _get_theme_css, notify=themeCssChanged)

    def _get_export_enabled(self) -> bool:
        return self._export_enabled

    exportEnabled = Property(bool, _get_export_enabled, notify=exportEnabledChanged)

    # --- in: JS -> Python --------------------------------------------------

    @Slot("QVariantList")
    def setSelection(self, order_numbers) -> None:
        selection = [str(n) for n in order_numbers]
        if selection == self._selection:
            return
        self._selection = selection
        self.selectionChanged.emit(selection)

    @Slot()
    def openExport(self) -> None:
        self.exportRequested.emit()

    @Slot()
    def openScreenMenu(self) -> None:
        self.screenMenuRequested.emit()

    # --- Python-facing API -------------------------------------------------

    def selection(self) -> list[str]:
        return list(self._selection)

    def set_orders(self, df) -> None:
        """Push the session: the order payload and the KPI numbers, together."""
        self._orders = order_payload(df)
        self._summary = results_summary(df)
        self.summaryChanged.emit()
        self.ordersChanged.emit()

    def set_export_enabled(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if enabled == self._export_enabled:
            return
        self._export_enabled = enabled
        self.exportEnabledChanged.emit()

    def set_theme_css(self, css: str) -> None:
        if css == self._theme_css:
            return
        self._theme_css = css
        self.themeCssChanged.emit()
```

`mount_results_page` is unchanged.

- [ ] **Step 4: Amend the Bundle 11 catalogue**

In `docs/superpowers/specs/2026-09-11-phase9-bundle11-seam-design.md` §5.2, replace the three rows
```
| in | `setSort(column: str, descending: bool)` | slot | 12 (9.13) |
| in | `setFilterText(text: str)` | slot | 12 (9.13) |
| in | `setFilterChips(chips: list[str])` | slot | 12 (9.13) |
```
with
```
| ~~in~~ | ~~`setSort`, `setFilterText`, `setFilterChips`~~ | removed | 12 — no Python consumer, the page owns view state (ADR 0005) |
| out | `summary: dict` | property | 12 (9.13) |
| out | `exportEnabled: bool` | property | 12 (9.13) |
| out | `focusSearchRequested()` | signal | 12 (9.13) |
| in | `openExport()` | slot | 12 (9.13) — canvas W3 puts Export in the document |
| in | `openScreenMenu()` | slot | 12 (9.13) |
```
Also, in the paragraph under the table, replace `Export is **not** on the bridge: it is the Qt command bar's primary.` with `Export was first kept off the bridge; Bundle 12 moved it into the document per canvas W3.`

- [ ] **Step 5: Run to verify pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_results_bridge.py -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```
/usr/bin/git add gui/results_bridge.py tests/test_results_bridge.py docs/superpowers/specs/2026-09-11-phase9-bundle11-seam-design.md
/usr/bin/git commit -m "feat(results): bridge summary, export and screen-menu members"
```

---

### Task 4: The document's tests, shell and stylesheet

Tasks 4 and 5 build one unit, the page. This task writes every Chromium test for it and the static markup and CSS. The tests stay red until Task 5 adds the script.

**Files:**
- Create: `tests/test_results_document.py`
- Rewrite: `gui/web/results.html`, `gui/web/results.css`

**Interfaces:**
- Consumes: the bridge members from Task 3.
- Produces the DOM contract that `results.js` (Task 5) fills in and the tests query. These ids and classes are fixed:
  - `#results`, `#kpis` (`.kpi[data-kpi=orders|fulfillable|blocked|labels|value|oldest]` > `.kpi-label`, `.kpi-value`, `.kpi-sub`; `.kpi-wide` on the oldest card; `.has-wide` on `#kpis`)
  - `#search`, `#chips` (`.chip-filter[data-chip]`), `#add-filter`, `#filter-menu` (`.menu-group`, `.menu-item[role=menuitemcheckbox]`), `#clear-all`, `#count`, `#screen-menu`, `#export`
  - `#table-area`, `#table[data-visible-rows]`, `#scroller`, `#header` (`.cell.head[data-sort]`), `#rows` (`.row[data-order][data-index]` > `.cell.<column key>`)
  - `#results-empty`, `#results-no-match`, `#no-match-clear`
  - column keys: `select, status, order, customer, lines, units, value, courier, age`

- [ ] **Step 1: Write the failing tests** — `tests/test_results_document.py`

```python
"""The results document (9.13 + 9.15), driven through a real Chromium.

Sizes are the *page* area: the window minus the 56px rail and the 48 + 28 of
Qt chrome. 1366x768 -> 1310x692, 1920x1080 -> 1864x1004. Never mark skip.
"""

import pandas as pd
import pytest
from PySide6.QtWebEngineWidgets import QWebEngineView

from gui.results_bridge import mount_results_page
from test_results_bridge import _eval, _until_js


def results_lines(orders=312):
    """A deterministic session: 1-5 lines per order, every 10th (from #3) blocked."""
    couriers = ["DHL", "DPD", "Packeta", ""]
    rows = []
    for i in range(orders):
        for line in range(1 + i % 5):
            rows.append({
                "Order_Number": f"#{10001 + i}",
                "Order_Fulfillment_Status": "Not Fulfillable" if i % 10 == 3 else "Fulfillable",
                "Shipping_Provider": couriers[i % 4],
                "Customer": f"Customer {i:03d}",
                "Created_At": f"2026-09-0{1 + i % 3} 0{i % 10}:15:00 +0200",
                "Total_Price": 10.0 + i,
                "SKU": f"SKU-{i:03d}-{line}",
                "Product_Name": f"Product {line}",
                "Quantity": 1 + line,
                "Internal_Tags": '["vip"]' if i % 7 == 0 else "[]",
                "System_note": "",
                "Stock_Alert": "Low Stock" if i % 11 == 0 else "",
                "Has_SKU": i % 13 != 0,
            })
    return pd.DataFrame(rows)


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


def _text(qtbot, view, selector):
    return _eval(qtbot, view, f"document.querySelector({selector!r}).textContent.trim()")


def _resize(qtbot, view, width, height):
    view.resize(width, height)
    _until_js(qtbot, view, f"window.innerWidth === {width} && window.innerHeight === {height}")


def _choose_filter(qtbot, view, label):
    _eval(qtbot, view, "document.getElementById('add-filter').click(); true")
    _eval(
        qtbot,
        view,
        "Array.from(document.querySelectorAll('#filter-menu .menu-item'))"
        f".find(function (b) {{ return b.textContent.trim() === {label!r}; }}).click(); true",
    )


def _count_is(qtbot, view, text):
    _until_js(qtbot, view, f"document.getElementById('count').textContent === {text!r}")


# --- 9.15: the numbers ------------------------------------------------------

def test_17_whole_rows_at_1366(qtbot, doc):
    view, _ = doc
    _until_js(qtbot, view, "document.getElementById('table').dataset.visibleRows === '17'")
    assert _eval(qtbot, view, "document.getElementById('scroller').clientHeight") == 28 + 17 * 28


def test_28_whole_rows_at_1920(qtbot, doc):
    view, _ = doc
    _resize(qtbot, view, 1864, 1004)
    _until_js(qtbot, view, "document.getElementById('table').dataset.visibleRows === '28'")


def test_no_horizontal_scroll_until_the_table_minimum(qtbot, doc):
    view, _ = doc
    scroller = "document.getElementById('scroller')"
    assert _eval(qtbot, view, f"{scroller}.scrollWidth <= {scroller}.clientWidth") is True
    _resize(qtbot, view, 780, 692)
    _until_js(qtbot, view, f"{scroller}.scrollWidth > {scroller}.clientWidth")


def test_only_a_window_of_rows_exists(qtbot, doc):
    view, _ = doc
    assert _eval(qtbot, view, "document.querySelectorAll('#rows .row').length") <= 17 + 8
    _eval(qtbot, view, "document.getElementById('scroller').scrollTop = 28 * 150; true")
    _until_js(qtbot, view, "!!document.querySelector('#rows .row[data-index=\"150\"]')")
    assert _eval(qtbot, view, "document.querySelectorAll('#rows .row').length") <= 17 + 8


# --- 9.13: the document -------------------------------------------------------

def test_the_nine_columns_in_order(qtbot, doc):
    view, _ = doc
    titles = _eval(
        qtbot, view,
        "Array.from(document.querySelectorAll('#header .head'))"
        ".map(function (c) { return c.textContent.trim(); })",
    )
    assert titles == ["", "Status", "Order", "Customer", "Lines", "Units", "Value", "Courier", "Age"]


def test_a_row_reads_as_the_order(qtbot, doc):
    view, _ = doc
    row = "#rows .row[data-order=\"#10004\"]"
    assert _text(qtbot, view, row + " .status") == "Blocked"
    assert _text(qtbot, view, row + " .customer") == "Customer 003"
    assert _text(qtbot, view, row + " .lines") == "4"
    assert _text(qtbot, view, row + " .units") == "10"
    assert _text(qtbot, view, row + " .value") == "13.00"
    # i=3 ships with no courier: a missing value is a dash, not an empty cell.
    assert _text(qtbot, view, row + " .courier") == "—"


def test_the_kpis_count_the_session(qtbot, doc):
    view, _ = doc
    _until_js(qtbot, view, "document.querySelector('[data-kpi=orders] .kpi-value').textContent === '312'")
    assert _text(qtbot, view, "[data-kpi=fulfillable] .kpi-value") == "281"
    assert _text(qtbot, view, "[data-kpi=blocked] .kpi-value") == "31"
    assert _text(qtbot, view, "[data-kpi=labels] .kpi-value") == "281"
    assert _text(qtbot, view, "[data-kpi=labels] .kpi-sub").startswith("DHL ")


def test_the_sixth_card_only_on_a_wide_page(qtbot, doc):
    view, _ = doc
    display = "getComputedStyle(document.querySelector('[data-kpi=oldest]')).display"
    assert _eval(qtbot, view, display) == "none"
    _resize(qtbot, view, 1864, 1004)
    _until_js(qtbot, view, f"{display} !== 'none'")


def test_export_names_the_count_and_reaches_python(qtbot, doc):
    view, bridge = doc
    _until_js(qtbot, view, "document.getElementById('export').textContent === 'Export 281 orders'")
    with qtbot.waitSignal(bridge.exportRequested, timeout=5000):
        _eval(qtbot, view, "document.getElementById('export').click(); true")


def test_nothing_analysed_shows_its_state(qtbot, doc):
    view, bridge = doc
    bridge.set_orders(pd.DataFrame())
    _until_js(qtbot, view, "!document.getElementById('results-empty').hidden")
    assert _text(qtbot, view, "[data-kpi=orders] .kpi-value") == "—"
    assert _eval(qtbot, view, "document.getElementById('export').disabled") is True


# --- filtering ------------------------------------------------------------------

def test_search_finds_an_order_by_its_sku(qtbot, doc):
    view, _ = doc
    _count_is(qtbot, view, "312 orders")
    _eval(
        qtbot, view,
        "var s = document.getElementById('search'); s.value = 'sku-042-0';"
        " s.dispatchEvent(new Event('input')); true",
    )
    _count_is(qtbot, view, "1 of 312 orders")


def test_chips_and_across_groups_and_or_within_one(qtbot, doc):
    view, _ = doc
    _choose_filter(qtbot, view, "Blocked")
    _count_is(qtbot, view, "31 of 312 orders")
    _choose_filter(qtbot, view, "Courier: DHL")  # no blocked order ships DHL
    _count_is(qtbot, view, "0 of 312 orders")
    _until_js(qtbot, view, "!document.getElementById('results-no-match').hidden")
    _choose_filter(qtbot, view, "Courier: DPD")  # blocked AND (DHL OR DPD)
    _count_is(qtbot, view, "15 of 312 orders")
    _eval(qtbot, view, "document.getElementById('clear-all').click(); true")
    _count_is(qtbot, view, "312 orders")


def test_a_chip_removes_itself_when_clicked(qtbot, doc):
    view, _ = doc
    _choose_filter(qtbot, view, "Repeat")
    _until_js(qtbot, view, "document.querySelectorAll('#chips .chip-filter').length === 1")
    _eval(qtbot, view, "document.querySelector('#chips .chip-filter').click(); true")
    _count_is(qtbot, view, "312 orders")


# --- selection and sort ------------------------------------------------------------

def test_a_row_click_reaches_python_and_a_hiding_filter_drops_it(qtbot, doc):
    view, bridge = doc
    with qtbot.waitSignal(bridge.selectionChanged, timeout=5000) as blocker:
        _eval(qtbot, view, "document.querySelector('#rows .row[data-order=\"#10001\"] .order').click(); true")
    assert blocker.args == [["#10001"]]
    with qtbot.waitSignal(bridge.selectionChanged, timeout=5000) as blocker:
        _choose_filter(qtbot, view, "Blocked")  # #10001 is fulfillable
    assert blocker.args == [[]]


def test_arrow_down_moves_the_selection(qtbot, doc):
    view, bridge = doc
    _eval(qtbot, view, "document.querySelector('#rows .row[data-order=\"#10001\"] .order').click(); true")
    with qtbot.waitSignal(bridge.selectionChanged, timeout=5000) as blocker:
        _eval(
            qtbot, view,
            "document.getElementById('table').dispatchEvent("
            "new KeyboardEvent('keydown', {key: 'ArrowDown', bubbles: true})); true",
        )
    assert blocker.args == [["#10002"]]


def test_sorting_value_twice_is_descending(qtbot, doc):
    view, _ = doc
    head = "document.querySelector('#header .head[data-sort=value]')"
    _eval(qtbot, view, f"{head}.click(); {head}.click(); true")
    _until_js(qtbot, view, "document.querySelector('#rows .row[data-index=\"0\"]').dataset.order === '#10312'")
```

- [ ] **Step 2: Run to verify failure**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_results_document.py -q`
Expected: every test errors or fails. `doc` times out waiting for `#rows .row`, because nothing renders yet.

- [ ] **Step 3: Rewrite `gui/web/results.html`**

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Analysis Results</title>
<!-- gui/results_bridge.py writes theme_css_vars() over the marker before the
     page loads, then results.js keeps it current from the bridge. -->
<style id="theme-vars">/* theme-vars */</style>
<link rel="stylesheet" href="results.css">
<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
<script src="results.js" defer></script>
</head>
<body>
<main id="results">
  <section id="kpis" class="kpis" aria-label="Session numbers"></section>

  <div id="filterbar" class="filterbar">
    <input id="search" type="search" placeholder="Order, customer or SKU"
           aria-label="Search orders" autocomplete="off" spellcheck="false">
    <div id="chips" class="chips"></div>
    <div class="menu-anchor">
      <button id="add-filter" class="btn ghost" type="button"
              aria-haspopup="menu" aria-expanded="false">Add filter</button>
      <div id="filter-menu" class="menu" role="menu" hidden></div>
    </div>
    <button id="clear-all" class="btn ghost" type="button" hidden>Clear all</button>
    <span class="spacer"></span>
    <span id="count" class="count"></span>
    <button id="screen-menu" class="btn ghost icon" type="button"
            title="More actions for this screen" aria-label="More actions for this screen">⋯</button>
    <button id="export" class="btn primary" type="button" disabled>Export</button>
  </div>

  <section id="table-area" class="table-area">
    <div id="table" class="table" role="grid" tabindex="0" aria-label="Orders" data-visible-rows="0">
      <div id="scroller" class="scroller">
        <div id="header" class="row header" role="row"></div>
        <div id="rows" class="rows" role="rowgroup"></div>
      </div>
    </div>
    <div id="results-empty" class="state" hidden>
      <p class="state-title">Nothing analysed yet</p>
      <p class="state-text">Load the orders and stock files in Setup, then run the analysis. Every order it finds lands here.</p>
    </div>
    <div id="results-no-match" class="state" hidden>
      <p class="state-title">No orders match</p>
      <p class="state-text">Remove a filter or clear the search.</p>
      <button id="no-match-clear" class="btn ghost" type="button">Clear all</button>
    </div>
  </section>
</main>
</body>
</html>
```

Keep `/* theme-vars */` exactly once. `test_the_page_carries_the_theme_marker_exactly_once` guards it.

- [ ] **Step 4: Rewrite `gui/web/results.css`**

```css
/* The results document (Bundle 12). Every value is a token from
   theme_css_vars(): no hex, and nothing the Qt tier cannot draw
   (ADR 0001, shared/style_lint.py). Geometry: spec section 6. */

/* Chromium cannot see fonts registered with Qt's QFontDatabase, so the
   bundled Inter the Qt tier renders in is declared again here. The relative
   path holds in the dev tree and under _internal/ in the --onedir build. */
@font-face {
  font-family: "Inter";
  font-weight: 400;
  src: url("../../shared/assets/fonts/Inter-Regular.ttf");
}
@font-face {
  font-family: "Inter";
  font-weight: 700;
  src: url("../../shared/assets/fonts/Inter-Bold.ttf");
}

*, *::before, *::after { box-sizing: border-box; }

html, body { margin: 0; height: 100%; }

body {
  overflow: hidden;
  background: var(--surface);
  color: var(--text);
  font-family: var(--font-family);
  font-size: var(--type-body-size);
  font-variant-numeric: tabular-nums;
}

button, input { font: inherit; color: inherit; }

[hidden] { display: none !important; }

/* --- page: 88 KPI + 40 filter bar + table, 12 apart, 16 in from the edge -- */

#results {
  height: 100%;
  padding: var(--spacing-lg);
  display: grid;
  grid-template-rows: 88px 40px minmax(0, 1fr);
  row-gap: var(--spacing-md);
  container-type: inline-size;
}

/* --- KPI strip ----------------------------------------------------------- */

.kpis {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: var(--spacing-sm);
}

.kpi {
  display: flex;
  flex-direction: column;
  justify-content: center;
  min-width: 0;
  overflow: hidden;
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--surface-raised);   /* the Card rule in build_stylesheet */
  border-radius: var(--radius-md);
}

.kpi-label, .kpi-sub {
  line-height: 1.3;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--type-caption-size);
  color: var(--text-secondary);
}

.kpi-label { font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; }

.kpi-value {
  font-size: var(--type-display-xl-size);
  font-weight: 700;
  line-height: 1;
}

.kpi-wide { display: none; }

/* The one container query: a page of 1544px (a 1600px window) is a content
   box of 1512px once the 16px padding is off both sides. */
@container (min-width: 1512px) {
  .kpis.has-wide { grid-template-columns: repeat(6, minmax(0, 1fr)); }
  .kpis.has-wide .kpi-wide { display: flex; }
}

/* --- filter bar ------------------------------------------------------------- */

.filterbar {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  min-width: 0;
}

#search {
  flex: 0 0 280px;
  height: var(--control-height);
  padding: 0 var(--padding-h);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
}
#search::placeholder { color: var(--text-placeholder); }
#search:focus { outline: 2px solid var(--focus-ring); outline-offset: -1px; }

.chips { display: flex; gap: var(--spacing-xs); min-width: 0; overflow: hidden; }

.chip-filter {
  flex-shrink: 0;
  padding: 3px 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  font-size: var(--type-caption-size);
  white-space: nowrap;
  cursor: pointer;
}
.chip-filter:hover { background: var(--hover); }

.spacer { flex: 1 1 auto; }

.count {
  font-size: var(--type-caption-size);
  color: var(--text-secondary);
  white-space: nowrap;
}

.btn {
  flex-shrink: 0;
  height: var(--control-height);
  padding: 0 12px;
  border: 1px solid transparent;
  border-radius: var(--radius);
  background: transparent;
  white-space: nowrap;
  cursor: pointer;
}
.btn.ghost:hover { background: var(--hover); }
.btn.icon { width: var(--control-height); padding: 0; }
.btn.primary { background: var(--accent-fill); color: var(--on-accent); font-weight: 700; }
.btn.primary:hover { background: var(--accent-fill-hover); }
.btn.primary:active { background: var(--accent-fill-active); }
/* QPushButton[role=…]:disabled in build_stylesheet. */
.btn:disabled,
.btn:disabled:hover {
  background: var(--surface);
  color: var(--text-disabled);
  border-color: var(--border-subtle);
  cursor: default;
}

.btn:focus-visible,
.chip-filter:focus-visible,
.menu-item:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 1px; }

.menu-anchor { position: relative; flex-shrink: 0; }

.menu {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  z-index: 3;
  min-width: 220px;
  max-height: 360px;
  overflow-y: auto;
  padding: var(--spacing-xs) 0;
  background: var(--surface-overlay);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
}

.menu-group {
  padding: var(--spacing-xs) var(--spacing-md);
  font-size: var(--type-caption-size);
  font-weight: 700;
  color: var(--text-secondary);
}

.menu-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  width: 100%;
  padding: var(--spacing-xs) var(--spacing-md);
  border: 0;
  background: transparent;
  text-align: left;
  white-space: nowrap;
  cursor: pointer;
}
.menu-item:hover { background: var(--hover); }

.check {
  flex-shrink: 0;
  width: 12px;
  height: 12px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  visibility: hidden;
}
.menu-item[aria-checked="true"] .check { visibility: visible; }

/* --- table ------------------------------------------------------------------ */

.table-area { position: relative; min-height: 0; }

.table:focus { outline: none; }
.table:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 1px; }

.scroller { overflow: auto; }

.row {
  display: grid;
  grid-template-columns: var(--cols);
  min-width: 780px;
  background: var(--surface);
}

.header {
  position: sticky;
  top: 0;
  z-index: 2;
  height: 28px;
  border-bottom: 1px solid var(--border-subtle);
}

.rows { position: relative; min-width: 780px; }

.rows .row {
  position: absolute;
  left: 0;
  right: 0;
  height: var(--row-height);
}
.rows .row:hover { background: var(--hover); }
/* The selection ring: a closed rectangle, never a left border (F4). */
.rows .row.selected {
  background: var(--selection-bg);
  outline: 2px solid var(--selection-border);
  outline-offset: -2px;
}

.cell {
  padding: 0 8px;
  line-height: var(--row-height);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.head {
  line-height: 27px;
  font-size: var(--type-caption-size);
  font-weight: 700;
  color: var(--text-secondary);
  cursor: pointer;
  user-select: none;
}
.head.sorted { color: var(--text); }
.head.select { cursor: default; }

.caret {
  width: 12px;
  height: 12px;
  margin-left: 2px;
  vertical-align: middle;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  visibility: hidden;
}
.head:hover .caret, .head.sorted .caret { visibility: visible; }

.num { text-align: right; }
.cell.order { font-family: var(--font-family-mono); }
.cell.age, .cell.missing { color: var(--text-secondary); }

/* Pinned when the table scrolls sideways. No z-index, so the row's selection
   outline still paints over them. */
.cell.select, .cell.status { position: sticky; background: inherit; }
.cell.select { left: 0; text-align: center; }
.cell.status { left: 32px; }
.cell.select input { margin: 0; vertical-align: middle; }

/* --- status chip: shared.theme.StatusChip's "chip" variant, same geometry -- */

.chip {
  position: relative;
  display: inline-block;
  vertical-align: middle;
  line-height: normal;
  padding: 2px 8px 2px 20px;
  border: 1px solid var(--chip-fg);
  border-radius: var(--radius);
  color: var(--chip-fg);
  font-size: var(--type-caption-size);
}
/* The mark: hollow, because the run derived the status (CONTEXT.md "Mark"). */
.chip::before {
  content: "";
  position: absolute;
  left: 7px;
  top: 50%;
  width: 8px;
  height: 8px;
  margin-top: -4px;
  border: 1.5px solid var(--chip-fg);
  border-radius: 50%;
}
.chip.success { --chip-fg: var(--status-success); }
.chip.danger { --chip-fg: var(--status-danger); background: var(--status-danger-bg); }

/* --- states -------------------------------------------------------------------- */

.state {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-sm);
  text-align: center;
}
.state-title { margin: 0; font-weight: 700; }
.state-text { margin: 0; max-width: 420px; color: var(--text-secondary); }
```

- [ ] **Step 5: Lint the web assets**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_style_literals_guard.py -q`
Expected: pass. If `currentColor` or `none` is reported as `css-name`, append `/* style-lint: allow */` to that line (the Bundle 11 escape). Do not change the value.

- [ ] **Step 6: Commit** (the tests are red until Task 5; say so)

```
/usr/bin/git add tests/test_results_document.py gui/web/results.html gui/web/results.css
/usr/bin/git commit -m "test(results): document tests, shell and stylesheet (red until results.js)"
```

---

### Task 5: `results.js` — the document's behaviour

**Files:**
- Rewrite: `gui/web/results.js`

**Interfaces:**
- Consumes: the DOM contract (Task 4) and the bridge members `orders`, `summary`, `themeCss`, `exportEnabled`, `setSelection`, `openExport`, `openScreenMenu`, `focusSearchRequested` (Bundle 11 + Task 3).
- Produces: `window.resultsBridge` and `<html data-bridge="ready">`, as Bundle 11 did.

- [ ] **Step 1: Replace `gui/web/results.js` with**

```js
// The results document (Bundle 12): KPI strip, filter bar and a windowed
// order table over the bridge's `orders` and `summary`. The page owns sort,
// search, filter chips and the selection gesture (ADR 0005). Python hears
// only the selection and two commands. Numbers and copy:
// docs/superpowers/specs/2026-09-11-phase9-bundle12-results-doc-design.md
"use strict";

const HEADER_PX = 28;
const OVERSCAN = 4;
const TABLE_MIN_PX = 780;
const DASH = "—";
const FULFILLABLE = "Fulfillable";
const NO_COURIER = "No courier";
const NUMBER = new Intl.NumberFormat("en-US");

// Lucide chevron-down, chevron-up and check. Paths, not a transform: the
// web tier may not rotate anything (ADR 0001).
const CHEVRON_DOWN = "m6 9 6 6 6-6";
const CHEVRON_UP = "m18 15-6-6-6 6";
const CHECK = "M20 6 9 17l-5-5";

const els = {};
const state = {
  bridge: null,
  records: [], // {o, index, key, hay} in frame order
  view: [], // records that pass the filters, in display order
  query: "",
  chips: [], // {kind, value, label}
  sort: null, // {key, dir: 1 | -1}
  selected: new Set(), // order numbers
  anchorKey: null, // the row a Shift-click or an arrow key starts from
  rowH: 28,
  visible: 0,
};

// --- formatting -------------------------------------------------------------

function num(v) {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}
function str(v) {
  return v === null || v === undefined ? "" : String(v);
}
function fmtInt(v) {
  const n = num(v);
  return n === null ? DASH : NUMBER.format(n);
}
function fmtMoney(v) {
  const n = num(v);
  return n === null ? DASH : n.toFixed(2);
}
function fmtCompact(v) {
  const n = num(v);
  if (n === null) return DASH;
  const abs = Math.abs(n);
  if (abs >= 1e6) return (n / 1e6).toFixed(1) + "M";
  if (abs >= 1e3) return (n / 1e3).toFixed(1) + "k";
  return String(Math.round(n));
}
function ageMs(iso) {
  if (!iso) return null;
  const t = Date.parse(iso);
  return Number.isNaN(t) ? null : Math.max(0, Date.now() - t);
}
function fmtAge(iso) {
  const ms = ageMs(iso);
  if (ms === null) return DASH;
  const minutes = Math.floor(ms / 60000);
  if (minutes < 60) return minutes + " min";
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return hours + " h";
  return Math.floor(hours / 24) + " d";
}
function plural(n, word) {
  return NUMBER.format(n) + " " + word + (n === 1 ? "" : "s");
}
function isFulfillable(o) {
  return o.Order_Fulfillment_Status === FULFILLABLE;
}
function courierOf(o) {
  return str(o.Shipping_Provider).trim() || NO_COURIER;
}
function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}
function svg(path, cls) {
  return '<svg class="' + cls + '" viewBox="0 0 24 24" aria-hidden="true"><path d="' + path + '"/></svg>';
}

// --- columns, filters, sort -----------------------------------------------

// Widths are the canvas's (W3); a column grows to its widest real value but
// never reflows after that. Only Customer stretches (9.15).
const COLUMNS = [
  { key: "select", title: "", width: 32 },
  { key: "status", title: "Status", width: 132, sortValue: (o) => (isFulfillable(o) ? 0 : 1) },
  { key: "order", title: "Order", width: 84, mono: true, text: (o) => str(o.Order_Number), sortValue: (o) => str(o.Order_Number) },
  { key: "customer", title: "Customer", stretch: true, text: (o) => str(o.Customer), sortValue: (o) => str(o.Customer) },
  { key: "lines", title: "Lines", width: 56, numeric: true, text: (o) => fmtInt(o.Items), sortValue: (o) => num(o.Items) },
  { key: "units", title: "Units", width: 56, numeric: true, text: (o) => fmtInt(o.Units), sortValue: (o) => num(o.Units) },
  { key: "value", title: "Value", width: 84, numeric: true, text: (o) => fmtMoney(o.Total_Price), sortValue: (o) => num(o.Total_Price) },
  { key: "courier", title: "Courier", width: 76, text: (o) => str(o.Shipping_Provider), sortValue: (o) => str(o.Shipping_Provider) },
  { key: "age", title: "Age", width: 56, numeric: true, text: (o) => fmtAge(o.Created_At), sortValue: (o) => ageMs(o.Created_At) },
];

const FLAGS = [
  { value: "repeat", label: "Repeat", test: (o) => o._repeat === true },
  { value: "unknown_sku", label: "Unknown SKU", test: (o) => o.Unknown_SKU === true },
  { value: "low_stock", label: "Low stock", test: (o) => o.Low_Stock === true },
  { value: "lines3", label: "3 or more lines", test: (o) => (num(o.Items) || 0) >= 3 },
];

function chipId(chip) {
  return chip.kind + ":" + chip.value;
}

function menuGroups() {
  const couriers = new Set();
  const tags = new Set();
  for (const r of state.records) {
    couriers.add(courierOf(r.o));
    for (const t of r.o.Tag_List || []) tags.add(String(t));
  }
  const byName = (a, b) => a.localeCompare(b);
  return [
    ["Status", [
      { kind: "status", value: "fulfillable", label: "Fulfillable" },
      { kind: "status", value: "blocked", label: "Blocked" },
    ]],
    ["Flags", FLAGS.map((f) => ({ kind: "flag", value: f.value, label: f.label }))],
    ["Courier", [...couriers].sort(byName).map((c) => ({ kind: "courier", value: c, label: "Courier: " + c }))],
    ["Tags", [...tags].sort(byName).map((t) => ({ kind: "tag", value: t, label: "Tag: " + t }))],
  ];
}

function toggleChip(chip) {
  const id = chipId(chip);
  if (state.chips.some((c) => chipId(c) === id)) {
    state.chips = state.chips.filter((c) => chipId(c) !== id);
    return;
  }
  // Status is one question with one answer: a second status replaces the first.
  if (chip.kind === "status") state.chips = state.chips.filter((c) => c.kind !== "status");
  state.chips.push(chip);
}

// Search AND every group; within Courier and within Tags, OR.
function matches(record) {
  const o = record.o;
  if (state.query && !record.hay.includes(state.query)) return false;
  const of = (kind) => state.chips.filter((c) => c.kind === kind);
  for (const c of of("status")) {
    if ((c.value === "fulfillable") !== isFulfillable(o)) return false;
  }
  for (const c of of("flag")) {
    if (!FLAGS.find((f) => f.value === c.value).test(o)) return false;
  }
  const couriers = of("courier");
  if (couriers.length && !couriers.some((c) => c.value === courierOf(o))) return false;
  const tags = of("tag");
  const own = (o.Tag_List || []).map(String);
  if (tags.length && !tags.some((c) => own.includes(c.value))) return false;
  return true;
}

function searchText(o) {
  const parts = [o.Order_Number, o.Customer, o.Shipping_Provider].concat(o.Tag_List || []);
  for (const line of o.lines || []) parts.push(line.SKU, line.Product_Name);
  return parts.map(str).join(" ").toLowerCase();
}

// Empty values sort last in both directions; ties keep frame order.
function compare(col, dir) {
  return function (a, b) {
    const x = col.sortValue(a.o);
    const y = col.sortValue(b.o);
    const xEmpty = x === null || x === "";
    const yEmpty = y === null || y === "";
    if (xEmpty || yEmpty) return xEmpty === yEmpty ? a.index - b.index : xEmpty ? 1 : -1;
    const c = typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y));
    return c === 0 ? a.index - b.index : c * dir;
  };
}

function recompute() {
  let view = state.records.filter(matches);
  if (state.sort) {
    const col = COLUMNS.find((c) => c.key === state.sort.key);
    view = view.slice().sort(compare(col, state.sort.dir));
  }
  state.view = view;
  // A filter that hides a selected order deselects it, so a bulk action can
  // never reach a row the operator cannot see (ADR 0005).
  const shown = new Set(view.map((r) => r.key));
  state.selected = new Set([...state.selected].filter((k) => shown.has(k)));
  if (state.anchorKey !== null && !shown.has(state.anchorKey)) state.anchorKey = null;
}

// --- rendering ----------------------------------------------------------------

function render() {
  recompute();
  renderChips();
  renderCount();
  renderExport();
  renderStates();
  renderHeader();
  layout();
  renderRows();
  reportSelection();
}

function reportSelection() {
  if (!state.bridge) return;
  // The bridge drops a list equal to the last one, so this is safe on every render.
  state.bridge.setSelection(state.view.filter((r) => state.selected.has(r.key)).map((r) => r.key));
}

function renderKpis() {
  const s = (state.bridge && state.bridge.summary) || {};
  const has = s.orders !== undefined;
  const oldest = has ? s.oldest : null;
  let valueSub = "";
  if (has) {
    valueSub = s.value_total === null ? "No price column mapped" : "of " + fmtCompact(s.value_total) + " analysed";
  }
  const cards = [
    ["orders", "Orders", has ? fmtInt(s.orders) : DASH,
      has ? NUMBER.format(s.lines) + " lines · " + NUMBER.format(s.skus) + " SKUs touched" : ""],
    ["fulfillable", "Fulfillable", has ? fmtInt(s.fulfillable) : DASH,
      has && s.orders ? Math.round((100 * s.fulfillable) / s.orders) + "% of orders" : ""],
    ["blocked", "Blocked", has ? fmtInt(s.blocked) : DASH,
      has ? NUMBER.format(s.blocked_lines) + " lines, " + NUMBER.format(s.blocked_skus) + " SKUs" : ""],
    ["labels", "Labels", has ? fmtInt(s.fulfillable) : DASH,
      has ? (s.labels_by_courier || []).map((p) => p[0] + " " + NUMBER.format(p[1])).join(" · ") : ""],
    ["value", "Value ready", has && s.value_ready !== null ? fmtCompact(s.value_ready) : DASH, valueSub],
    ["oldest", "Oldest waiting", oldest ? fmtAge(oldest.created_at) : DASH,
      oldest ? "order " + oldest.order_number : ""],
  ];
  els.kpis.classList.toggle("has-wide", Boolean(oldest));
  els.kpis.textContent = "";
  for (const [key, label, value, sub] of cards) {
    const card = document.createElement("div");
    card.className = "kpi" + (key === "oldest" ? " kpi-wide" : "");
    card.dataset.kpi = key;
    for (const [cls, text] of [["kpi-label", label], ["kpi-value", value], ["kpi-sub", sub]]) {
      const part = document.createElement("div");
      part.className = cls;
      part.textContent = text;
      card.appendChild(part);
    }
    els.kpis.appendChild(card);
  }
}

function renderChips() {
  els.chips.textContent = "";
  for (const chip of state.chips) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "chip-filter";
    button.dataset.chip = chipId(chip);
    button.title = "Remove this filter";
    button.textContent = chip.label + "  ×";
    button.addEventListener("click", () => {
      toggleChip(chip);
      render();
    });
    els.chips.appendChild(button);
  }
  els.clearAll.hidden = !(state.chips.length || state.query);
}

function renderCount() {
  const total = state.records.length;
  const shown = state.view.length;
  els.count.textContent = shown === total ? plural(total, "order") : NUMBER.format(shown) + " of " + plural(total, "order");
}

function renderExport() {
  const s = (state.bridge && state.bridge.summary) || {};
  const n = s.fulfillable || 0;
  els.exportBtn.textContent = s.fulfillable === undefined ? "Export" : "Export " + plural(n, "order");
  els.exportBtn.disabled = !(state.bridge && state.bridge.exportEnabled && n > 0);
}

function renderStates() {
  const none = state.records.length === 0;
  const noMatch = !none && state.view.length === 0;
  els.empty.hidden = !none;
  els.noMatch.hidden = !noMatch;
  els.table.hidden = none || noMatch;
  els.search.disabled = none;
  els.addFilter.disabled = none;
}

function renderMenu() {
  els.menu.textContent = "";
  for (const [group, items] of menuGroups()) {
    if (!items.length) continue;
    const head = document.createElement("div");
    head.className = "menu-group";
    head.textContent = group;
    els.menu.appendChild(head);
    for (const item of items) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "menu-item";
      button.setAttribute("role", "menuitemcheckbox");
      button.setAttribute("aria-checked", String(state.chips.some((c) => chipId(c) === chipId(item))));
      button.innerHTML = svg(CHECK, "check");
      button.appendChild(document.createTextNode(item.label));
      button.addEventListener("click", () => {
        toggleChip(item);
        closeMenu();
        render();
      });
      els.menu.appendChild(button);
    }
  }
}

function openMenu() {
  renderMenu();
  els.menu.hidden = false;
  els.addFilter.setAttribute("aria-expanded", "true");
  const first = els.menu.querySelector(".menu-item");
  if (first) first.focus();
}

function closeMenu() {
  els.menu.hidden = true;
  els.addFilter.setAttribute("aria-expanded", "false");
}

function renderHeader() {
  els.header.textContent = "";
  const picked = state.view.filter((r) => state.selected.has(r.key)).length;
  const all = picked > 0 && picked === state.view.length;
  for (const col of COLUMNS) {
    const cell = document.createElement("div");
    cell.className = "cell head " + col.key + (col.numeric ? " num" : "");
    cell.setAttribute("role", "columnheader");
    if (col.key === "select") {
      const box = document.createElement("input");
      box.type = "checkbox";
      box.tabIndex = -1;
      box.setAttribute("aria-label", "Select every order shown");
      box.checked = all;
      box.indeterminate = picked > 0 && !all;
      box.addEventListener("click", () => selectAll(!all));
      cell.appendChild(box);
    } else {
      const sorted = Boolean(state.sort && state.sort.key === col.key);
      cell.dataset.sort = col.key;
      cell.classList.toggle("sorted", sorted);
      cell.setAttribute("aria-sort", sorted ? (state.sort.dir === 1 ? "ascending" : "descending") : "none");
      const label = document.createElement("span");
      label.textContent = col.title;
      cell.appendChild(label);
      cell.insertAdjacentHTML("beforeend", svg(sorted && state.sort.dir === 1 ? CHEVRON_UP : CHEVRON_DOWN, "caret"));
      cell.addEventListener("click", () => cycleSort(col.key));
    }
    els.header.appendChild(cell);
  }
}

function measureColumns() {
  measureColumns.ctx = measureColumns.ctx || document.createElement("canvas").getContext("2d");
  const ctx = measureColumns.ctx;
  const body = getComputedStyle(document.body);
  const sans = body.fontSize + " " + body.fontFamily;
  const mono = body.fontSize + " " + cssVar("--font-family-mono");
  const caption = cssVar("--type-caption-size") + " " + body.fontFamily;
  const widths = COLUMNS.map((col) => {
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
    return Math.max(col.width, Math.ceil(widest + 16));
  });
  const fixed = widths.reduce((a, b) => a + b, 0);
  const customerMin = Math.max(120, TABLE_MIN_PX - fixed);
  const template = COLUMNS.map((col, i) => (col.stretch ? "minmax(" + customerMin + "px, 1fr)" : widths[i] + "px"));
  els.table.style.setProperty("--cols", template.join(" "));
}

// Whole rows only: the table is as tall as the rows that fit, and whatever is
// left over stays page surface below it (9.15).
// ponytail: a horizontal scrollbar (page < 812px) eats into the last row; that
// state is unreachable at 1366, so it is not compensated for.
function layout() {
  state.rowH = parseFloat(cssVar("--row-height")) || 28;
  const rows = Math.max(0, Math.floor((els.tableArea.clientHeight - HEADER_PX) / state.rowH));
  state.visible = rows;
  els.scroller.style.height = HEADER_PX + rows * state.rowH + "px";
  els.rows.style.height = state.view.length * state.rowH + "px";
  els.table.dataset.visibleRows = String(Math.min(rows, state.view.length));
}

function renderRows() {
  const start = Math.floor(els.scroller.scrollTop / state.rowH);
  const first = Math.max(0, start - OVERSCAN);
  const last = Math.min(state.view.length, start + state.visible + OVERSCAN);
  const frag = document.createDocumentFragment();
  for (let i = first; i < last; i++) frag.appendChild(rowElement(state.view[i], i));
  els.rows.replaceChildren(frag);
}

function rowElement(record, index) {
  const row = document.createElement("div");
  const selected = state.selected.has(record.key);
  row.className = "row" + (selected ? " selected" : "");
  row.setAttribute("role", "row");
  row.setAttribute("aria-selected", String(selected));
  row.dataset.order = record.key;
  row.dataset.index = String(index);
  row.style.top = index * state.rowH + "px";
  for (const col of COLUMNS) row.appendChild(cellElement(col, record, selected));
  return row;
}

function cellElement(col, record, selected) {
  const cell = document.createElement("div");
  cell.className = "cell " + col.key + (col.numeric ? " num" : "");
  cell.setAttribute("role", "gridcell");
  if (col.key === "select") {
    const box = document.createElement("input");
    box.type = "checkbox";
    box.tabIndex = -1;
    box.checked = selected;
    box.setAttribute("aria-label", "Select order " + record.key);
    cell.appendChild(box);
  } else if (col.key === "status") {
    const ok = isFulfillable(record.o);
    const chip = document.createElement("span");
    chip.className = "chip " + (ok ? "success" : "danger");
    chip.textContent = ok ? "Fulfillable" : "Blocked";
    cell.appendChild(chip);
  } else {
    const text = col.text(record.o);
    const missing = text === "" || text === DASH;
    cell.textContent = missing ? DASH : text;
    cell.classList.toggle("missing", missing);
  }
  return cell;
}

// --- interaction ----------------------------------------------------------------

function cycleSort(key) {
  if (!state.sort || state.sort.key !== key) state.sort = { key: key, dir: 1 };
  else if (state.sort.dir === 1) state.sort = { key: key, dir: -1 };
  else state.sort = null;
  render();
}

function selectAll(on) {
  state.selected = on ? new Set(state.view.map((r) => r.key)) : new Set();
  render();
}

function selectRange(fromKey, toKey, additive) {
  const keys = state.view.map((r) => r.key);
  const a = keys.indexOf(fromKey);
  const b = keys.indexOf(toKey);
  if (a < 0 || b < 0) return;
  if (!additive) state.selected = new Set();
  for (let i = Math.min(a, b); i <= Math.max(a, b); i++) state.selected.add(keys[i]);
}

function onRowClick(event) {
  const row = event.target.closest(".row");
  if (!row || !row.dataset.order) return;
  const key = row.dataset.order;
  const ctrl = event.ctrlKey || event.metaKey;
  if (event.shiftKey && state.anchorKey !== null) {
    selectRange(state.anchorKey, key, ctrl);
  } else if (ctrl || event.target.matches("input[type=checkbox]")) {
    if (state.selected.has(key)) state.selected.delete(key);
    else state.selected.add(key);
    state.anchorKey = key;
  } else {
    state.selected = new Set([key]);
    state.anchorKey = key;
  }
  els.table.focus({ preventScroll: true });
  render();
}

function scrollIntoView(index) {
  const top = index * state.rowH;
  const s = els.scroller;
  if (top < s.scrollTop) s.scrollTop = top;
  else if (top + state.rowH > s.scrollTop + state.visible * state.rowH) {
    s.scrollTop = top + state.rowH - state.visible * state.rowH;
  }
}

function onTableKey(event) {
  const ctrl = event.ctrlKey || event.metaKey;
  if (ctrl && event.key.toLowerCase() === "a") {
    event.preventDefault();
    selectAll(true);
    return;
  }
  if (event.key === "Escape") {
    state.selected = new Set();
    state.anchorKey = null;
    render();
    return;
  }
  if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
  event.preventDefault();
  if (!state.view.length) return;
  const keys = state.view.map((r) => r.key);
  const at = state.anchorKey === null ? -1 : keys.indexOf(state.anchorKey);
  const next = Math.min(keys.length - 1, Math.max(0, at + (event.key === "ArrowDown" ? 1 : -1)));
  if (event.shiftKey) state.selected.add(keys[next]);
  else state.selected = new Set([keys[next]]);
  state.anchorKey = keys[next];
  scrollIntoView(next);
  render();
}

function clearFilters() {
  state.query = "";
  els.search.value = "";
  state.chips = [];
  render();
}

// --- bridge ---------------------------------------------------------------------

function onOrders() {
  const orders = state.bridge.orders || [];
  state.records = orders.map((o, index) => ({ o: o, index: index, key: str(o.Order_Number), hay: searchText(o) }));
  measureColumns();
  renderKpis();
  render();
}

function onTheme() {
  els.themeVars.textContent = state.bridge.themeCss;
  // Density moves the type scale and the row height: re-measure, re-lay.
  measureColumns();
  render();
}

function bind() {
  const ids = {
    kpis: "kpis", search: "search", chips: "chips", addFilter: "add-filter", menu: "filter-menu",
    clearAll: "clear-all", count: "count", screenMenu: "screen-menu", exportBtn: "export",
    tableArea: "table-area", table: "table", scroller: "scroller", header: "header", rows: "rows",
    empty: "results-empty", noMatch: "results-no-match", noMatchClear: "no-match-clear",
    themeVars: "theme-vars",
  };
  for (const name of Object.keys(ids)) els[name] = document.getElementById(ids[name]);

  els.search.addEventListener("input", () => {
    state.query = els.search.value.trim().toLowerCase();
    render();
  });
  els.addFilter.addEventListener("click", () => (els.menu.hidden ? openMenu() : closeMenu()));
  els.menu.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      closeMenu();
      els.addFilter.focus();
    }
  });
  document.addEventListener("mousedown", (e) => {
    if (!els.menu.hidden && !e.target.closest(".menu-anchor")) closeMenu();
  });
  els.clearAll.addEventListener("click", clearFilters);
  els.noMatchClear.addEventListener("click", clearFilters);
  els.screenMenu.addEventListener("click", () => state.bridge && state.bridge.openScreenMenu());
  els.exportBtn.addEventListener("click", () => state.bridge && state.bridge.openExport());
  els.rows.addEventListener("click", onRowClick);
  els.table.addEventListener("keydown", onTableKey);
  els.scroller.addEventListener("scroll", renderRows);
  new ResizeObserver(() => {
    layout();
    renderRows();
  }).observe(els.tableArea);
}

bind();
renderKpis();
render();

new QWebChannel(qt.webChannelTransport, function (channel) {
  const bridge = channel.objects.results;
  state.bridge = bridge;
  els.themeVars.textContent = bridge.themeCss;
  bridge.themeCssChanged.connect(onTheme);
  bridge.ordersChanged.connect(onOrders);
  bridge.summaryChanged.connect(() => {
    renderKpis();
    renderExport();
  });
  bridge.exportEnabledChanged.connect(renderExport);
  bridge.focusSearchRequested.connect(() => els.search.focus());
  onOrders();
  window.resultsBridge = bridge;
  document.documentElement.dataset.bridge = "ready";
});
```

- [ ] **Step 2: Run the document, bridge and lint tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_results_document.py tests/test_results_bridge.py tests/test_style_literals_guard.py -q`
Expected: all pass.

Debugging hints, in order of likelihood:
- **A `_count_is` or `_until_js` times out.** Read the page's actual value with `_eval(qtbot, view, "document.getElementById('count').textContent")` and compare it to the spec copy. Fix the code, not the test's copy.
- **`visibleRows` is off by one.** Log `document.getElementById('table-area').clientHeight`: it must be 508 at 1310×692. If it is not, the grid rows or the page padding in `results.css` are wrong.
- **The linter flags a line in `results.js`.** Rephrase the code. Use `/* style-lint: allow */` only for a false positive.

- [ ] **Step 3: Commit**

```
/usr/bin/git add gui/web/results.js
/usr/bin/git commit -m "feat(results): the results document - KPIs, filters, windowed table, selection"
```

---

### Task 6: Swap the Qt screen for the document, and delete what only it reached

The owner decided (2026-09-11) to replace the screen now and leave the pane slot empty. The pane, row menu, tag panel, bulk bar and column manager leave `main` until Bundles 13 and 14. Do not keep any of them alive "for later".

**Files:**
- Modify: `gui/ui_manager.py`, `gui/main_window_pyside.py`, `gui/selection_helper.py`, `gui/actions_handler.py:1753-1754,1849-1850,1906-1907`, `gui/column_config_dialog.py:141,749-757`, `gui/pandas_model.py`, `gui/components/__init__.py`
- Delete: `gui/order_detail_pane.py`, `gui/tag_management_panel.py`, `gui/tag_delegate.py`, `gui/components/statcard.py`, `tests/test_analysis_results_1b_chrome.py`, `tests/test_main_window_tags.py`, `tests/test_components_statcard.py`
- Modify tests: `tests/test_analysis_results_1b.py`, `tests/test_pandas_model.py`, `tests/test_selection_ring_renders.py`, `tests/test_selection_helper.py:43`, `tests/test_actions_handler.py:105`
- Create: `tests/test_results_screen.py`

**Interfaces:**
- Consumes: `mount_results_page`, `ResultsBridge` (Task 3), and the document (Task 5).
- Produces:
  - on `MainWindow`: `results_view: QWebEngineView`, `results_bridge: ResultsBridge`, `results_menu: QMenu`, and `_focus_results_search()`
  - on `UIManager`: `set_export_enabled(enabled: bool)`
  - `SelectionHelper(main_window)`, with a single parameter

- [ ] **Step 1: Write the failing tests** — `tests/test_results_screen.py`

```python
"""The Analysis Results screen is the results document (Bundle 12 spec §7)."""

import re
from pathlib import Path

import pandas as pd
import pytest
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QTableView


@pytest.fixture
def main_window(qapp):
    from gui.main_window_pyside import MainWindow

    window = MainWindow()
    yield window
    window.close()


@pytest.fixture
def lines_df():
    return pd.DataFrame([
        {"Order_Number": "1001", "Order_Fulfillment_Status": "Fulfillable",
         "Shipping_Provider": "DHL", "SKU": "AAA", "Quantity": 2, "System_note": "",
         "Internal_Tags": "[]"},
        {"Order_Number": "1001", "Order_Fulfillment_Status": "Fulfillable",
         "Shipping_Provider": "DHL", "SKU": "BBB", "Quantity": 1, "System_note": "",
         "Internal_Tags": "[]"},
        {"Order_Number": "1002", "Order_Fulfillment_Status": "Not Fulfillable",
         "Shipping_Provider": "DPD", "SKU": "CCC", "Quantity": 4,
         "System_note": "Cannot fulfill: insufficient stock for CCC", "Internal_Tags": "[]"},
    ])


def test_the_results_page_is_one_web_view(main_window):
    page = main_window.main_tabs.widget(1)
    assert isinstance(main_window.results_view, QWebEngineView)
    assert main_window.results_view.parent() is page
    assert page.findChildren(QTableView) == []


def test_update_all_views_pushes_orders_and_summary(main_window, lines_df):
    main_window.analysis_results_df = lines_df
    main_window._update_all_views()
    assert [o["Order_Number"] for o in main_window.results_bridge.orders] == ["1001", "1002"]
    assert main_window.results_bridge.summary["blocked"] == 1


def test_a_page_selection_reaches_the_selection_helper(main_window, lines_df):
    main_window.analysis_results_df = lines_df
    main_window.results_bridge.setSelection(["1002"])
    picked = main_window.selection_helper.get_selected_orders_data()
    assert picked["Order_Number"].unique().tolist() == ["1002"]


def test_export_clicks_generate_reports_only_while_enabled(main_window, monkeypatch):
    calls = []
    monkeypatch.setattr(
        main_window.actions_handler, "open_generate_reports_dialog", lambda: calls.append(1)
    )
    main_window.ui_manager.set_export_enabled(False)
    main_window.results_bridge.openExport()
    assert calls == []
    main_window.ui_manager.set_export_enabled(True)
    main_window.results_bridge.openExport()
    assert calls == [1]
    assert main_window.results_bridge.exportEnabled is True


def test_set_ui_busy_drives_the_pages_export(main_window, lines_df):
    main_window.analysis_results_df = lines_df
    main_window.ui_manager.set_ui_busy(False)
    assert main_window.results_bridge.exportEnabled is True
    main_window.ui_manager.set_ui_busy(True)
    assert main_window.results_bridge.exportEnabled is False


def test_the_screen_menu_holds_add_product_and_undo(main_window):
    assert main_window.results_menu.actions() == [
        main_window.add_product_button_tab2,
        main_window.undo_button,
    ]


GUI = Path(__file__).resolve().parent.parent / "gui"
GONE = re.compile(
    r"tableView|proxy_model|order_detail_pane|tag_management_panel|filter_input"
    r"|filter_column_selector|case_sensitive_checkbox|tag_filter_combo|kpi_cards"
    r"|kpi_strip|update_results_table|update_kpi_strip|update_filter_count"
    r"|hidden_columns_indicator|configure_columns_button_tab2|_update_selection_bar_state"
)


def test_the_qt_results_screen_is_gone():
    hits = [
        f"{path.relative_to(GUI)}:{number}: {line.strip()}"
        for path in sorted(GUI.rglob("*.py"))
        if path.name != "session_browser_widget.py"  # its own filter_bar/selection_bar
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if GONE.search(line)
    ]
    assert hits == []
```

- [ ] **Step 2: Run to verify failure**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_results_screen.py -q`
Expected: 7 failed (`AttributeError: 'MainWindow' object has no attribute 'results_view'`, and a long hit list from the scan).

- [ ] **Step 3: `gui/ui_manager.py` — Tab 2 becomes the web view**

Replace the whole `_create_tab2_analysis_results` method with:

```python
    def _create_tab2_analysis_results(self):
        """Tab 2: the results document -- one QWebEngineView, no Qt inside.

        The page paints `surface` to its own edges (9.13's seam rule), so the
        view takes the whole tab with no margins. Everything drawn on this
        screen is in gui/web/; Bundle 12 spec section 7.
        """
        from PySide6.QtGui import QCursor
        from PySide6.QtWebEngineWidgets import QWebEngineView

        from gui.results_bridge import mount_results_page

        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Never shown. Its enabled state is the guard every existing call
        # site already drives, and the page's Export clicks it via the bridge.
        self.mw.generate_reports_button_tab2 = QPushButton("Generate Reports", tab)
        self.mw.generate_reports_button_tab2.setEnabled(False)
        self.mw.generate_reports_button_tab2.clicked.connect(
            lambda: (
                self.mw.actions_handler.open_generate_reports_dialog()
                if hasattr(self.mw, "actions_handler")
                else None
            )
        )
        self.mw.generate_reports_button_tab2.hide()

        self.mw.results_menu = self._create_results_overflow(tab)

        view = QWebEngineView(tab)
        self.mw.results_view = view
        bridge = mount_results_page(view)
        self.mw.results_bridge = bridge
        bridge.selectionChanged.connect(self.mw.selection_helper.set_selected_orders)
        bridge.exportRequested.connect(self.mw.generate_reports_button_tab2.click)
        # A QMenu is a top-level popup, so it paints above the web view.
        bridge.screenMenuRequested.connect(
            lambda: self.mw.results_menu.popup(QCursor.pos())
        )
        layout.addWidget(view, 1)
        return tab

    def set_export_enabled(self, enabled: bool) -> None:
        """The hidden generate-reports button stays the guard; the page mirrors it."""
        self.mw.generate_reports_button_tab2.setEnabled(enabled)
        self.mw.results_bridge.set_export_enabled(enabled)
```

Replace the whole `_create_results_overflow` method with:

```python
    def _create_results_overflow(self, parent):
        """The screen-level actions that are not the screen's one primary.

        A menu with no button of its own: the page's "⋯" asks for it through
        the bridge. The QActions keep their old attribute names, because every
        caller reaches them through setEnabled / setToolTip / setText.
        Configure Columns returns with the column manager (Bundle 13).
        """
        from PySide6.QtGui import QAction
        from PySide6.QtWidgets import QMenu

        menu = QMenu(parent)
        # Off by default in Qt, which would silently swallow every setToolTip
        # below -- including the undo tooltip actions_handler recomputes.
        menu.setToolTipsVisible(True)

        def action(label, slot, tooltip, enabled=False):
            item = QAction(label, menu)
            item.setToolTip(tooltip)
            item.setEnabled(enabled)
            item.triggered.connect(slot)
            menu.addAction(item)
            return item

        self.mw.add_product_button_tab2 = action(
            "Add Product to Order",
            lambda: (
                self.mw.actions_handler.show_add_product_dialog()
                if hasattr(self.mw, "actions_handler")
                else None
            ),
            "Manually add a product to an existing order",
        )
        self.mw.undo_button = action(
            "Undo", self.mw.undo_last_operation, "Undo last operation (Ctrl+Z)"
        )
        return menu
```

In `set_ui_busy`, replace
```python
        if hasattr(self.mw, "generate_reports_button_tab2"):
            self.mw.generate_reports_button_tab2.setEnabled(
                not is_busy and is_data_loaded
            )
```
with
```python
        if hasattr(self.mw, "results_bridge"):
            self.set_export_enabled(not is_busy and is_data_loaded)
```

Delete these methods whole:
- `_create_selection_bar`, `_create_kpi_strip`, `update_results_table`
- `_selected_order_numbers`, `_reselect_orders`, `results_view_frame`
- `_populate_tag_filter`, `_extract_unique_tags_from_dataframe`, `_group_tags_by_category`
- `_create_filter_controls`, `update_filter_count`, `_style_results_overflow`
- `_create_results_table`, `_setup_header_context_menu`, `_show_header_context_menu`, `_create_footer`
- `update_kpi_strip`, `update_hidden_columns_indicator`, `_show_hidden_columns_popup`
- `_restore_hidden_column`, `_restore_all_hidden_columns`

- [ ] **Step 4: `gui/main_window_pyside.py`**

1. Delete `from gui.pandas_model import FulfillmentFilterProxy`, the line `self.orders_df = None`, and the `# Models` block that creates `self.proxy_model`, including its comment.
2. Replace the `SelectionHelper(...)` construction with `self.selection_helper = SelectionHelper(main_window=self)`.
3. Delete the `# Table interactions` block (the `tableView` and `order_detail_pane` connections). Also delete the `# Filter input…` block, from `self._filter_debounce = QTimer(self)` through `self.tag_filter_combo.currentIndexChanged.connect(self.filter_table)`. Keep `self.actions_handler.data_changed.connect(self._update_all_views)`.
4. Replace `QShortcut(QKeySequence("Ctrl+F"), self, lambda: self.filter_input.setFocus())` with `QShortcut(QKeySequence("Ctrl+F"), self, self._focus_results_search)`, and add this method beside `_update_all_views`:
   ```python
   def _focus_results_search(self):
       """Ctrl+F: the search field lives in the results document now."""
       self.main_tabs.setCurrentIndex(1)
       self.results_view.setFocus()
       self.results_bridge.focusSearchRequested.emit()
   ```
5. In the client-switch block, replace
   ```python
                if hasattr(self, "generate_reports_button_tab2"):
                    self.generate_reports_button_tab2.setEnabled(False)
   ```
   with
   ```python
                if hasattr(self, "results_bridge"):
                    self.ui_manager.set_export_enabled(False)
   ```
6. In `update_ui_state`, replace
   ```python
        if hasattr(self, "generate_reports_button_tab2"):
            self.generate_reports_button_tab2.setEnabled(reports_enabled)
   ```
   with
   ```python
        if hasattr(self, "results_bridge"):
            self.ui_manager.set_export_enabled(reports_enabled)
   ```
   Delete the two `configure_columns_button_tab2` lines.
7. Replace the whole `_update_all_views` method with:
   ```python
   def _update_all_views(self):
       """Central slot to refresh every view after `analysis_results_df` changes.

       Statistics are recalculated here; the results document folds the line
       frame to orders and KPI numbers itself (gui/orders_view.py), so one
       push is the whole refresh.
       """
       if self.analysis_results_df is not None and not self.analysis_results_df.empty:
           try:
               self.analysis_stats = recalculate_statistics(self.analysis_results_df)
           except Exception:
               logger.exception("Failed to recalculate statistics")
               self.analysis_stats = None
       else:
           self.analysis_stats = None

       self.results_bridge.set_orders(self.analysis_results_df)
       self.ui_manager.set_ui_busy(False)
   ```
8. Delete these methods whole:
   - `add_internal_tag_to_order`, `remove_internal_tag_from_order`
   - `on_results_selection_changed`, `_pane_lines`, `open_column_config_dialog`
   - `_update_selection_bar_state`, `filter_table`
   - `on_table_double_clicked`, `show_context_menu`, `show_line_context_menu`

   First run `git grep -n "add_internal_tag_to_order\|remove_internal_tag_from_order" -- gui`. It must show only `main_window_pyside.py` and `ui_manager.py` hits, all inside code this task deletes. If anything else calls them, stop and record it in `state.md`.

- [ ] **Step 5: The remaining modules**

- `gui/selection_helper.py`:
  - The constructor becomes `def __init__(self, main_window):`, storing only `self.main_window` and `self.checked_rows`.
  - Delete `set_table_view`.
  - Drop `table_view` and `proxy_model` from the class and `__init__` docstrings, including the `Attributes:` entries.
- `tests/test_selection_helper.py:43` becomes `return SelectionHelper(main_window=_MainWindow())`.
- `tests/test_actions_handler.py:105`: drop the `table_view=` and `proxy_model=` keyword arguments from `SelectionHelper(`.
- `gui/actions_handler.py`: delete the three two-line `if hasattr(self.mw, "_update_selection_bar_state"): self.mw._update_selection_bar_state()` blocks.
- `gui/column_config_dialog.py`:
  - Delete lines 749–757, the comment plus the `if hasattr(self.parent_window, 'tableView') …` block.
  - At line 141, change the docstring to `main_window: MainWindow reference (for analysis_results_df)`.
- `gui/pandas_model.py`: delete the `FulfillmentFilterProxy` class. Keep `PandasModel`, `ROLE_STATUS`, `REPEAT_COLUMN`, `cell_search_text`, `cell_display_text` and `is_repeat`.
- `gui/components/__init__.py`: delete `from gui.components.statcard import KpiStrip, StatCard` and the two names from `__all__`.
- Delete the modules and tests in one command:
  ```
  /usr/bin/git rm gui/order_detail_pane.py gui/tag_management_panel.py gui/tag_delegate.py gui/components/statcard.py tests/test_analysis_results_1b_chrome.py tests/test_main_window_tags.py tests/test_components_statcard.py
  ```
- `tests/test_pandas_model.py`: delete the `FulfillmentFilterProxy` import and every test that uses it.
- `tests/test_selection_ring_renders.py`: delete the one test function that imports `TagDelegate`.
- `tests/test_analysis_results_1b.py`: delete every test that uses `OrderDetailPane`, `main_window.tableView`, `proxy_model`, `filter_input`, `ui_manager.results_view_frame`, `tag_management_panel` or `selection_bar`, plus the now-unused imports and fixtures. Keep any test that still passes on `orders_frame`/`order_lines` alone. If none remain, `/usr/bin/git rm` the file.
- Run `git grep -n -E "tableView|proxy_model|order_detail_pane|results_view_frame|FulfillmentFilterProxy|TagDelegate|KpiStrip|StatCard" -- tests` and fix every remaining hit the same way.

- [ ] **Step 6: Lint-fix, then run the whole suite**

Run: `.venv/bin/python -m ruff check gui tests --fix --exclude shared`
Expected: only unused-import fixes. Then run `.venv/bin/python -m ruff check . --exclude shared` and expect it to be clean.

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
Expected: all pass, including `tests/test_results_screen.py`. A failure that names a deleted symbol means a remaining caller: remove the caller when it served the Qt table, otherwise stop and record it in `state.md`.

- [ ] **Step 7: Commit**

```
/usr/bin/git add -A gui tests
/usr/bin/git commit -m "feat(results): the results screen is the web document; delete the Qt table screen"
```

---

### Task 7: The command bar — Run analysis as secondary, and the two session chips

**Files:**
- Modify: `gui/components/commandbar.py` (`__init__` near line 191, `set_action`, `bind_action`, `_refresh`), `gui/ui_manager.py` (`_SCREEN_ACTIONS`, the `_create_tabs` loop, `_bind_screen_action`, new `age_text` + `update_session_chips`), `gui/main_window_pyside.py` (`_update_all_views`)
- Test: `tests/test_results_screen.py` (append)

**Interfaces:**
- Consumes: `main_window.session_manager.get_session_info(path) -> dict | None` and `.get_input_dir(path) -> Path`. `session_info["analysis_completed_at"]` is an ISO string with an offset, written by `shopify_tool/core.py:1072`. The stock copy is `<input dir>/inventory.csv` (`core.py:482`, `shutil.copy2`, so it keeps the original mtime).
- Produces:
  - `CommandBar.bind_action(button, role="primary")`, `CommandBar.stock_chip`, `CommandBar.set_stock_age(text)`
  - `gui.ui_manager.age_text(delta: timedelta) -> str`, `UIManager.update_session_chips()`

- [ ] **Step 1: Write the failing tests** (append to `tests/test_results_screen.py`)

```python
def test_results_binds_run_analysis_as_the_secondary_action(main_window):
    from PySide6.QtWidgets import QApplication

    bar = main_window.command_bar
    main_window.main_tabs.setCurrentIndex(1)
    QApplication.processEvents()
    assert bar._bound_action is main_window.run_analysis_button
    assert bar.action_button.property("role") == "secondary"
    main_window.main_tabs.setCurrentIndex(0)
    QApplication.processEvents()
    assert bar.action_button.property("role") == "primary"


@pytest.mark.parametrize(
    "minutes, text",
    [(0, "0 min"), (59, "59 min"), (60, "1 h"), (47 * 60 + 59, "47 h"), (48 * 60, "2 d")],
)
def test_age_text(minutes, text):
    from datetime import timedelta

    from gui.ui_manager import age_text

    assert age_text(timedelta(minutes=minutes)) == text


def test_session_chips_read_the_analysis_and_the_stock_copy(main_window, tmp_path, monkeypatch):
    import os
    from datetime import datetime, timedelta

    analysed = datetime(2026, 9, 2, 9, 33).astimezone()
    stock = tmp_path / "input" / "inventory.csv"
    stock.parent.mkdir()
    stock.write_text("sku\n", encoding="utf-8")
    stamp = (analysed - timedelta(hours=19)).timestamp()
    os.utime(stock, (stamp, stamp))
    manager = main_window.session_manager
    monkeypatch.setattr(manager, "get_session_info",
                        lambda _path: {"analysis_completed_at": analysed.isoformat()})
    monkeypatch.setattr(manager, "get_input_dir", lambda _path: tmp_path / "input")
    main_window.session_path = str(tmp_path)

    main_window.ui_manager.update_session_chips()

    assert main_window.command_bar.status_chip.text() == "Analysed 09:33"
    assert main_window.command_bar.stock_chip.text() == "Stock file 19 h old"


def test_session_chips_blank_without_an_analysis(main_window, tmp_path, monkeypatch):
    monkeypatch.setattr(main_window.session_manager, "get_session_info", lambda _path: {})
    main_window.session_path = str(tmp_path)
    main_window.ui_manager.update_session_chips()
    assert main_window.command_bar.status_chip.text() == ""
    assert main_window.command_bar.stock_chip.text() == ""
```

- [ ] **Step 2: Run to verify failure**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_results_screen.py -q`
Expected: the new tests fail. The role is still `primary`, `age_text` does not exist, and there is no `stock_chip`.

- [ ] **Step 3: `gui/components/commandbar.py`**

After the three `status_chip` lines in `__init__`, add:
```python
        # W3's second chip: how old the stock file was when the analysis ran.
        self.stock_chip = StatusChip("text_secondary", "", theme, parent=self)
        self.stock_chip.hide()
        layout.addWidget(self.stock_chip)
```
After `set_status`, add:
```python
    def set_stock_age(self, text: str) -> None:
        self.stock_chip.set_status(
            "text_secondary", text, get_theme_manager().get_current_theme()
        )
        self.stock_chip.setVisible(bool(text))
```
In `set_action`, after `self._unbind()`, add `set_button_role(self.action_button, "primary")`.

Change the signature to `def bind_action(self, button: QPushButton | None, role: str = "primary") -> None:`. Add a sentence to its docstring: `role is the slot's button role: Results re-runs the analysis as a secondary action (W3).` In the non-`None` branch, directly after `self._bound_action = button`, add `set_button_role(self.action_button, role)`.

In `_refresh`, after the `self.status_chip.setVisible(...)` line, add:
```python
        self.stock_chip.setVisible(has_session and bool(self.stock_chip.text()))
```

- [ ] **Step 4: `gui/ui_manager.py`**

Replace the `_SCREEN_ACTIONS` dict and the comment line directly above it, `# Tab index -> (main_window attribute …`, with:
```python
# Tab index -> (main_window attribute holding that screen's command-bar action,
# whether that button lives on a screen and must stop painting itself, and the
# role the bar's slot takes). Results re-runs the analysis as a *secondary*
# action: its one primary, Export, is inside the results document (W3).
_SCREEN_ACTIONS = {
    0: ("run_analysis_button", True, "primary"),
    1: ("run_analysis_button", True, "secondary"),
}
```
Leave the paragraph about New Session under it unchanged.

In `_create_tabs`, change the loop header to `for attribute, hide_in_page, _role in _SCREEN_ACTIONS.values():`.

Replace the body of `_bind_screen_action` with:
```python
        entry = _SCREEN_ACTIONS.get(index)
        if entry is None:
            self.mw.command_bar.bind_action(None)
            return
        attribute, _hide_in_page, role = entry
        self.mw.command_bar.bind_action(getattr(self.mw, attribute), role)
```

Add this module-level function below `_SCREEN_ACTIONS`:
```python
def age_text(delta) -> str:
    """`19 h`, `45 min`, `3 d` -- the one age format the results screen uses."""
    minutes = max(0, int(delta.total_seconds() // 60))
    if minutes < 60:
        return f"{minutes} min"
    hours = minutes // 60
    if hours < 48:
        return f"{hours} h"
    return f"{hours // 24} d"
```

Add this method beside `set_export_enabled`:
```python
    def update_session_chips(self) -> None:
        """`Analysed 09:33` and `Stock file 19 h old` (W3's two command-bar chips).

        Stock age is measured at analysis time, not now: it qualifies the
        analysis. The stock copy in the session keeps the source file's mtime
        (shutil.copy2 in core.py).
        """
        bar = self.mw.command_bar
        session_path = getattr(self.mw, "session_path", None)
        info = self.mw.session_manager.get_session_info(session_path) if session_path else None
        try:
            analysed = datetime.fromisoformat((info or {}).get("analysis_completed_at") or "")
        except ValueError:
            analysed = None
        if analysed is None:
            bar.set_status("text_secondary", "")
            bar.set_stock_age("")
            return
        if analysed.tzinfo is None:
            analysed = analysed.astimezone()
        bar.set_status("text_secondary", f"Analysed {analysed.astimezone().strftime('%H:%M')}")
        stock = Path(self.mw.session_manager.get_input_dir(session_path)) / "inventory.csv"
        try:
            copied = datetime.fromtimestamp(stock.stat().st_mtime, tz=timezone.utc)
        except OSError:
            bar.set_stock_age("")
            return
        bar.set_stock_age(f"Stock file {age_text(analysed - copied)} old")
```
Add `from datetime import datetime, timezone` and `from pathlib import Path` to the imports **after** writing the code that uses them. This VM's write hook strips an import that has no usage yet.

- [ ] **Step 5: `gui/main_window_pyside.py`**

In `_update_all_views`, between `self.results_bridge.set_orders(self.analysis_results_df)` and `self.ui_manager.set_ui_busy(False)`, add `self.ui_manager.update_session_chips()`.

- [ ] **Step 6: Run the screen tests, the command-bar tests and the whole suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_results_screen.py tests/test_screen_primary_actions.py -q`
Then: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
Expected: all pass. A command-bar test that unpacks `_SCREEN_ACTIONS` values as pairs, or that expects screen 1 to bind `generate_reports_button_tab2`, is now stale. Update it to the three-tuple and to `run_analysis_button`.

- [ ] **Step 7: Commit**

```
/usr/bin/git add gui/components/commandbar.py gui/ui_manager.py gui/main_window_pyside.py tests/test_results_screen.py tests/test_screen_primary_actions.py
/usr/bin/git commit -m "feat(results): Run analysis as secondary on Results; Analysed and stock-age chips"
```

---

### Task 8: Verify the bundle

- [ ] **Step 1: Full gate**

Run each command and read its output. Do not claim a pass you have not seen.
- `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`: all pass, and none of the `test_results_*` tests are skipped.
- `.venv/bin/python -m ruff check . --exclude shared`: clean.

- [ ] **Step 2: The spec's "done when", item by item**

Record each result in `state.md` as a status line:
- 17 rows at 1310×692 and 28 at 1864×1004: `test_17_whole_rows_at_1366`, `test_28_whole_rows_at_1920`
- horizontal scroll only below the minimum: `test_no_horizontal_scroll_until_the_table_minimum`
- search, chip, sort and selection work, and the selection reaches `SelectionHelper`: `test_search_*`, `test_chips_*`, `test_sorting_*`, `test_a_page_selection_reaches_the_selection_helper`
- CUSTOMER and AGE show data when mapped: `test_customer_and_created_at_are_carried_and_filled_within_each_order` and `test_a_row_reads_as_the_order`
- the seam cannot be located in a screenshot: **manual, Stage C.** Say so in `state.md`; do not attempt it headless.

- [ ] **Step 3: Refresh the graph**

Run: `graphify update .`

- [ ] **Step 4: Push**

Run: `/usr/bin/git push -u origin worktree-phase9-bundle12-results-doc`
