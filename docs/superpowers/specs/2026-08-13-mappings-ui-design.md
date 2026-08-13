# Mappings: better UI, expiry/lot fields in the Stock CSV mapping

Date: 2026-08-13
Todoist: Phase 6 subtask `6h8v4Vm8RGcFw2H3`
Branch: `worktree-mappings-ui`

## Why this is not only a UI ticket

The ticket reads as a redesign plus two new fields. Reading the code first turned up a
data-loss defect underneath it, which changes what the work has to be.

`ColumnMappingWidget.get_mappings()` builds its result by walking
`required_fields + optional_fields` and reading the matching input box
(`gui/column_mapping_widget.py:179-188`). Anything mapped in the client config whose
internal name is not in those two lists cannot be represented, so it is not returned.
`MappingsPage.collect()` then writes that result in as the whole `stock` sub-dict
(`gui/settings/mappings.py:206`).

`MappingsPage` declares `stock_optional = ["Product_Name"]` (`mappings.py:67`). The
default client config ships five stock mappings, two of which drive lot tracking
(`shopify_tool/profile_manager.py:386-391`):

```
"stock": {"Артикул": "SKU", "Име": "Product_Name",
          "Наличност": "Stock", "Годност": "Expiry_Date", "Партида": "Batch"}
```

So opening Settings and pressing Save destroys the `Expiry_Date` and `Batch` mappings.
Measured on this branch's base:

```
$ QT_QPA_PLATFORM=offscreen python -c "...MappingsPage(cm, {}).collect()..."
stock after save: {'Артикул': 'SKU', 'Наличност': 'Stock', 'Име': 'Product_Name'}
```

In production this is masked. `shopify_tool/analysis.py:219` re-injects the two
Bulgarian header names whenever they are absent from the mapping:

```python
missing = {k: v for k, v in _LOT_COLUMN_DEFAULTS.items() if k not in stock_mappings}
```

The mask only covers clients whose stock CSV uses the literal headers `Годност` and
`Партида`. A client who maps `Expiry` or `Exp date` loses FIFO lot allocation
permanently on the first Save, with no error — `_build_fifo_lots()` returns `None` the
moment neither column survives the rename (`analysis.py:96-99`), and the run silently
falls back to the legacy no-lot path.

Two reasons the existing guard test did not catch it. `test_no_page_silently_drops_a_field`
(`tests/test_settings_roundtrip.py:40`) compares each page's `collect()` output to a
pre-collect deepcopy, and it does bite for `MappingsPage` — but the fixture's stock
mapping is `{"Article": "SKU", "Available": "Stock"}` (`tests/conftest.py:163`), which
contains nothing droppable. And `tests/test_settings_page_mappings.py` round-trips only
mappings the widget already knows about.

This is also why the ticket exists in the shape it does: the 2026-07-29 lot data-model
spec explicitly deferred the mapping UI here, on the grounds that "the backend mapping
mechanism already supports this today" (`2026-07-29-tags-lot-data-model-design.md:117-122`).
It does support it. The settings window is what takes it away.

## What the Windows screenshots show

The user's 2026-08-13 Windows build screenshots (Todoist, epic `6hG88Vx9CgRHVgG3`) give
the visual half:

- **Two scrollbars.** `ColumnMappingWidget` wraps its rows in a `QScrollArea`
  (`column_mapping_widget.py:73`) and `MappingsPage` wraps the whole page in another
  (`mappings.py:34`). The inner one clips the Stock block to a few rows inside an
  already-scrolling page.
- **`"Your CSV Column:"` twelve times.** One fixed-width label per row
  (`column_mapping_widget.py:120`) saying the same thing the section title says once.
- **The `→` arrow and a right-hand `*` column** spend a third of the row width on
  decoration, pushing the actual inputs into the left half of a 1626px window.
- **Headers are typed from memory.** Nothing in the dialog can tell you what the CSV
  actually contains, so a typo produces a mapping that silently does not apply — the
  rename map skips columns not present in the DataFrame (`analysis.py:234-238`).

## Decisions taken with the user

| Question | Answer |
|---|---|
| CSV-column input | Free text, plus a **"Load headers from CSV…"** button per page. The picker reads the file and turns the row inputs into dropdowns of its real headers. |
| `Position` field | **Left out.** Nothing in the codebase reads one; it goes in the day a feature needs it. |
| UI scope | Rebuild the rows **and** split Orders and Stock into separate nav pages. |

## Design

### 1. Preserve unmanaged mappings (the defect fix)

`get_mappings()` starts from the mappings it was constructed with and replaces only the
internal names it manages:

```python
def get_mappings(self) -> dict:
    managed = set(self.required_fields) | set(self.optional_fields)
    # Entries for internal names this widget has no row for are carried through
    # untouched -- a field missing from the two lists must not silently delete
    # the client's mapping for it.
    mappings = {csv: internal for csv, internal
                in self.current_mappings.items() if internal not in managed}
    for internal_name in self.required_fields + self.optional_fields:
        csv_column = self.csv_column_inputs[internal_name].currentText().strip()
        if csv_column:
            mappings[csv_column] = internal_name
    return mappings
```

`currentText()`, not `text()`: the inputs become editable `QComboBox`es in §6.
`validate_mappings()` reads the same inputs (`column_mapping_widget.py:200`) and changes
with them, as does the `mappings_changed` wiring — `currentTextChanged` in place of
`textChanged` (`column_mapping_widget.py:133`).

Clearing a box still removes that mapping — the field is managed, so its old entry was
never carried over. Only genuinely unknown internal names survive.

This is the root-cause fix and it is deliberately independent of the field list below.
Adding `Expiry_Date`/`Batch` to `stock_optional` fixes the two fields we know about;
this fixes the class. Both land.

### 2. Expiry and Batch become real rows

```python
stock_optional = ["Product_Name", "Expiry_Date", "Batch"]
```

Nothing else is needed to make them work: `_build_fifo_lots()` already keys off the
internal names `Expiry_Date` and `Batch` (`analysis.py:96-97`), the default config
already maps them, and packing lists already expand per lot
(`shopify_tool/packing_lists.py:13-20`). The only missing piece was the GUI, exactly as
the lot spec predicted.

Both rows get tooltips explaining what the backend does with them — FIFO ordering by
expiry, batch shown per lot on the packing list — because a warehouse operator setting
this up has no other way to learn that.

### 3. `_LOT_COLUMN_DEFAULTS` stays, with one correction

The injection at `analysis.py:216-221` is kept. Every client who has ever opened Settings
and saved already has the mapping stripped from their stored config; removing the
fallback in the same change would break lot tracking for all of them at once.

It gains one condition — skip a default whose *internal name* is already mapped:

```python
mapped_internals = set(stock_mappings.values())
missing = {k: v for k, v in _LOT_COLUMN_DEFAULTS.items()
           if k not in stock_mappings and v not in mapped_internals}
```

Without this, a client who maps `Exp date → Expiry_Date` in the new UI also gets
`Годност → Expiry_Date` injected. Harmless today (the rename skips absent columns) but it
is two CSV headers claiming one internal name, which the widget's own duplicate check
would reject if it ever saw it.

The fallback becomes removable once configs have been re-saved through the fixed UI.
Marked with a `ponytail:` comment naming that, not scheduled here.

### 4. The page split

`MappingsPage` becomes two pages in `gui/settings/mappings.py`:

| Page | Nav entry | Owns |
|---|---|---|
| `OrdersMappingPage` | Data → Orders Mapping | `column_mappings["orders"]`, `courier_mappings` |
| `StockMappingPage` | Data → Stock Mapping | `column_mappings["stock"]` |

Courier mappings go with Orders because they resolve `Shipping_Method` values, which is
an orders column. A fifth nav entry for one small block is not worth the sidebar row.

**Both pages hold the same live `column_mappings` dict** and mutate only their own
sub-key in place:

```python
def collect(self) -> dict:
    self.column_mappings["version"] = 2
    self.column_mappings["orders"] = self.orders_mapping_widget.get_mappings()
    return {"column_mappings": self.column_mappings, "courier_mappings": ...}
```

No `clear()`. The current code clears and refills because one page owned the whole dict;
with two owners a `clear()` in the second page to run would wipe the first one's work.
In-place per-key assignment makes the result independent of `_pages` order, and both
pages returning the same object under the same key means the shell's
`config_data[key] = value` loop (`window.py:259-261`) is a no-op for the second one.

This is the live-dict contract `SettingsPage` already documents, and it carries the known
cost: `test_no_page_silently_drops_a_field` compares `collect()`'s value to a pre-collect
deepcopy, and the sub-dicts are rebuilt fresh inside a live parent, so it still bites at
the `column_mappings` level. Per-page key coverage is added anyway (§6) — the Settings Hub
review established that every page on this contract needs it.

Nav group becomes:

```python
("Data", ["General", "Orders Mapping", "Stock Mapping", "Column Config"]),
```

`_restore_nav_selection()` looks pages up by name and falls back to the first entry when
the stored name is gone (`window.py:221-233`), so a user whose last page was `"Mappings"`
lands on General instead of crashing. No migration needed.

### 5. The rebuilt row

`ColumnMappingWidget` keeps its class name and public API (`get_mappings`,
`validate_mappings`, `set_mappings`, `mappings_changed`) so `mappings.py` and the existing
tests keep working. `_setup_ui` and `_create_mapping_row` are replaced:

- Rows are built with `FormSection.add_row(label, widget, tooltip)` — the internal field
  name is the row label, the input is the widget. The `"Your CSV Column:"` label, the `→`
  arrow and the trailing `*` column all go.
- Required is marked on the label itself (`Order_Number *`) with the tooltip
  `FormSection.add_row` already propagates to both label and input.
- Two `FormSection`s per widget, `"Required"` and `"Optional"`, replacing the two
  `QGroupBox`es. The page keeps one outer `QScrollArea`; the widget's inner one is
  removed.

```
┌ Orders CSV Column Mapping ──────────────────────────┐
│ Map your CSV column names to internal fields.       │
│                            [ Load headers from CSV… ]│
│ Required                                            │
│   Order_Number *      [ Name                      ▾ ]│
│   SKU          *      [ Lineitem sku              ▾ ]│
│   Quantity     *      [ Lineitem quantity         ▾ ]│
│   Shipping_Method *   [ Shipping Method           ▾ ]│
│ Optional                                            │
│   Product_Name        [ Lineitem name             ▾ ]│
└─────────────────────────────────────────────────────┘
```

The `color: red` at `column_mapping_widget.py:153` disappears with the `*` column it
styled — one of the two hardcoded colours the Settings Hub review flagged as still
outstanding.

### 6. Loading headers

One button per page, above the sections. It opens a file picker, reads the header row and
hands the names to every input on that page.

New helper in `shopify_tool/csv_utils.py`, next to the delimiter detection it reuses:

```python
def read_csv_headers(file_path: str, encoding: str = "utf-8-sig") -> list[str]:
    """Return the column names of a CSV without loading its rows."""
    delimiter, _ = detect_csv_delimiter(file_path, encoding)
    return list(pd.read_csv(file_path, sep=delimiter, encoding=encoding, nrows=0).columns)
```

`detect_csv_delimiter` already exists and already has a three-method fallback chain
(`csv_utils.py:30`), so the page needs no delimiter plumbing and no dependency on which
delimiter the General page is currently showing. `nrows=0` reads the header line only —
this stays fast on a large stock export over a network share.

Backend, not GUI, so it is testable without Qt.

The row inputs are **editable `QComboBox`es from the start**, empty until headers are
loaded, with the current mapping as their text and `"Enter column name…"` as placeholder.
One widget type and one code path beats swapping `QLineEdit` for `QComboBox` at runtime
and re-wiring every signal. `setInsertPolicy(NoInsert)` so typing does not append to the
list. Typed text survives loading headers — `addItems` does not disturb the line edit.

A header that is already used by another row is still offered; the existing duplicate
checks in `validate_mappings()` (`column_mapping_widget.py:204-214`) catch it on Save,
which is where the error belongs.

If the file cannot be read the page shows a `QMessageBox.warning` with the exception text
and leaves the inputs as they are. `WeightPage._import_skus_from_csv` sets this pattern
(`gui/settings/weight.py:425-455`) — a file picker, a read, a warning box on failure.

### 7. Testing

| Test | Bites when |
|---|---|
| `tests/conftest.py`: fixture stock mapping gains `Годност`/`Партида` | The existing `test_no_page_silently_drops_a_field` fails on today's code — this alone is the regression test for the defect |
| `get_mappings()` carries through an unmanaged internal name | The §1 fix is reverted or a field is dropped from the lists |
| `StockMappingPage.collect()` emits every key of `column_mappings["stock"]` it was built with, after detaching the page from the live dict | A field vanishes from `stock_optional`; covers the live-dict blind spot §4 names |
| `OrdersMappingPage` and `StockMappingPage` collect in either order without losing the other's sub-key | Someone reintroduces `clear()` or rebuilds `column_mappings` fresh |
| `read_csv_headers()` on a `;`-delimited and a `,`-delimited fixture | Delimiter detection or the `nrows=0` read regresses |
| Loading headers populates every combo and preserves typed text | The header wiring breaks |
| `_LOT_COLUMN_DEFAULTS` is not injected when `Expiry_Date` is already mapped to another header | The §3 condition is dropped |

Existing `tests/test_settings_page_mappings.py` is updated for the two new classes; its
three cases stay meaningful.

## Non-goals

- **`Position`.** Excluded by decision. Nothing reads it; add it with the feature.
- **A per-client expiry date format setting.** The `ponytail:` comment at
  `analysis.py:32-35` already tracks it; no evidence yet of real ambiguity.
- **Removing `_LOT_COLUMN_DEFAULTS`.** Kept as the back-compat path (§3).
- **Touching the standalone Column Config dialog, or `shared/`.**
- **The other three Phase 6 panels.** Rules, Tag Categories and Packing List/Stock Export
  each keep their own ticket. This change does not move them into the pattern; it
  establishes it.

## Files

| File | Change |
|---|---|
| `gui/column_mapping_widget.py` | `get_mappings()` preserves unmanaged entries; rows rebuilt on `FormSection`; inner `QScrollArea` and the `*` column removed; `set_available_headers()` added |
| `gui/settings/mappings.py` | `MappingsPage` → `OrdersMappingPage` + `StockMappingPage`; lot fields; per-key in-place collect; header button |
| `gui/settings/window.py` | Two `_add_page` calls; nav group updated |
| `shopify_tool/csv_utils.py` | `read_csv_headers()` |
| `shopify_tool/analysis.py` | Injection skips already-mapped internal names |
| `tests/conftest.py` | Fixture stock mapping gains the lot columns |
| `tests/test_settings_page_mappings.py` | Updated for the split; new coverage per §7 |
| `tests/test_csv_utils.py` | `read_csv_headers()` |

## Open question for the user

The Windows screenshots are the first look at Tracks 1-4 on the real platform and they
answer the visual-check question that PR #273 left open. One thing they surface that is
outside this ticket: in **Column Config**, both in the Hub and in the standalone "Manage
Table Columns" dialog, the *Columns* list and the *Additional CSV Columns* list are each
collapsed to about two visible rows while the page has vertical space to spare. That is a
stretch-factor problem in `ColumnConfigPanel`, not in the Mappings page, and it looks like
its own small ticket rather than something to fold in here. Flagging it rather than fixing
it.
