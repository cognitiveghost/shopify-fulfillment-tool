# Phase 9 Bundle 7 — Info becomes Logs

**Date:** 2026-09-07
**Items:** 9.20 (Statistics deleted; `Info` → `Logs`), 9.21 (two log views become one viewer)
**Todoist:** bundle `6hQXj6mMJJQwgpmV`, items `6hQVj4wvPQM6WCW3` and `6hQVj528j3wWGW5V`
**Artboards:** D3, D4 — via the roadmap, not the canvas
(`docs/superpowers/plans/2026-09-03-phase9-roadmap.md` §§ 9.20, 9.21)

One destination, one rename, one PR. 9.20 empties the Information tab down to
its logs; 9.21 rebuilds what is left. Shipping 9.20 alone would leave a two-tab
Info that nobody wants and that 9.21 immediately deletes.

---

## 1. A correction to the brief

The roadmap describes Info › Statistics as "thirty-day history across clients"
and instructs that `shared/stats_manager.py` and `global_stats.json` be left
write-only. **Both halves of that are wrong about the shipped code**, and the
deletion was approved against that description.

What `_create_statistics_subtab` actually builds reads `self.analysis_stats`,
sourced from `analysis_stats.json` — **session-scoped, one client, one run**.
It has four blocks:

| Block | Contents |
|---|---|
| Session Totals | 4 cards: orders completed / not completed, items to write off / not |
| By Courier | per courier: orders assigned, repeated orders found |
| Tags Breakdown | two panels, fulfillable and not-fulfillable tag counts |
| SKU Summary | a sortable, searchable 6-column table: `#`, SKU, Product, Total Qty, Fulfillable, Not Fulfillable |

`global_stats.json` is **already** write-only: `record_analysis` writes it from
`actions_handler`, and no GUI code reads it back. That instruction therefore
describes the status quo and costs zero work — it is not a constraint to
engineer against, only one to avoid breaking.

**The consequence:** the deletion removes four working session-scoped views,
and Phase 9 gives none of them a home. 9.13's table is order-level; 9.14's pane
is one order at a time. There is no per-SKU rollup anywhere in the phase.

**Decision (user, 2026-09-07): delete all four.** The deletion stands as
approved. Per-SKU detail remains reachable one order at a time in the 9.14
pane, and `shopify_tool/stock_export.py` already produces a bulk per-SKU
export — in the ERP's column layout rather than this table's shape, so it is a
near substitute, not an exact one. This is recorded here rather than in an ADR
because the trade-off is not architectural: it is a scope call, already made,
and reversible by re-adding a page.

**Also corrected here:** `CONTEXT.md` says the web tier is "Analysis Results
and Info › Statistics only", while ADR 0001 already records that Info ›
Statistics was deleted. The glossary is stale against its own ADR. After this
bundle the web tier is **Analysis Results only**.

---

## 2. What 9.20 deletes, and what it must not

### Deleted — `gui/ui_manager.py`

- `_create_statistics_subtab` and the page it builds
- `_make_stat_card`, `_make_courier_card`, `_make_tag_card` — the statistics
  page is their only caller
- `_create_activity_log_subtab`, `_create_execution_log_subtab` — 9.21 replaces
  both with one widget

### Deleted — `gui/main_window_pyside.py`

- `update_statistics_tab`, `_clear_statistics_view`, `_on_sku_search_changed`
  and the three call sites in `_update_all_views`

### Deleted — elsewhere

- `tests/test_main_window_statistics.py` — the page it tests is gone
- three tests in `tests/test_components_card.py` covering the card helpers
- `gui/log_viewer.py` — dead CustomTkinter, zero importers (the path is reused
  by 9.21, see §3)

### Kept — and this is load-bearing

- **`self.analysis_stats`, `recalculate_statistics`, and the
  `analysis_stats.json` read/write** at `main_window_pyside.py` ~906 / ~956 /
  ~987. These are session persistence, not the deleted view. The file is a
  session artifact; a session reloaded from disk restores its stats from it.
  Deleting them because "statistics is gone" breaks session reload — the
  attribute simply becomes write-and-reload-only.
- **`shared/stats_manager.py` and `global_stats.json`** — untouched, already
  write-only. `shared/` is owned by `packing-tool` regardless.
- **`gui/components/statcard.py`** — `KpiStrip` already has its caller:
  `_create_kpi_strip` builds the Analysis Results strip today, and
  `update_kpi_strip` feeds it from `analysis_results_df`, not from
  `analysis_stats`. The roadmap's "becomes its only caller" is already true.
- `gui/components/card.py`'s module docstring names the three deleted helpers
  as the code `Card` was extracted from. Reword it; do not delete `Card`.

### The rename

Index 3 of three parallel tuples in `ui_manager.py`:

| Tuple | From | To |
|---|---|---|
| `_TAB_LABELS` | `"Information"` | `"Logs"` |
| `_RAIL_LABELS` | `"Info"` | `"Logs"` |
| `_TAB_TOOLTIPS` | `"Statistics and logs (Ctrl+4)"` | `"Activity and execution logs (Ctrl+4)"` |

`_create_tab4_information` → `_create_tab4_logs`, returning the `LogViewer`
directly. **No `QTabWidget`** — with one page left there is nothing to tab
between.

**Departure from the artboard: the rail icon stays `info.svg`.** Icons live in
`shared/assets/icons/`, owned by `packing-tool`, so a `scroll-text` glyph costs
an edit there, a `scripts/sync_shared.py` run, and guard-test updates in both
repos. The roadmap dropped 9.19's "last touched" proposal for exactly this
reason — it was "the only cross-repo cost in the set". The Done-when is that
*the rail reads Logs*, which the label satisfies. A better glyph is a
one-line follow-up whenever `packing-tool` is next open.

---

## 3. 9.21 — the viewer

`gui/log_viewer.py` is deleted and the path reused: same name, new content, a
widget that is finally what the filename always claimed.

### Terms

- **Log entry** — one line in the viewer. Four fields, whatever produced it.
- **Source** — which stream an entry came from: **Activity** (what the operator
  did) or **Execution** (what the program logged). The two shipped names are
  kept; renaming the destination and its two sources in one release is churn.
- **Follow-tail** — the viewer scrolling itself to the newest entry, on only
  while the user is already at the bottom.

### The unified row

Activity is `Time / Operation / Description` with no level. Execution is
`Time / Level / Message` from the root logger. They are unified as **one**
shape, four columns:

```
TIME | LEVEL | SOURCE | MESSAGE
```

Activity entries take level `INFO` and `source = op_type` — the existing
`"Session"`, `"Analysis"`, `"Report"`, `"Data Edit"` strings. Execution entries
take the record's real level and `source = record.name`, elided.

One model serves both, so the level filter and the error tint work on **both**
sources rather than only on Execution. The alternative — dropping the LEVEL
column and carrying level as colour alone — is rejected: it makes ERROR and
WARNING distinguishable only by hue, which is the precise failure 9.19 spent an
item removing from the session browser.

### Scope: this session only

The ring buffer is fed by the live handler and starts empty at launch, exactly
as both widgets behave today. `shared/logger.py`'s log **file** is not read.
Reading it would mean a potentially large read over the UNC share on every
visit to the page, plus a size cap and a tail strategy — real work and a new
failure mode on a slow server, for a capability neither widget offers now.
`Save as text` writes the buffer out.

### Modules

Five, each with a small interface over the behaviour behind it.

**`LogEntry`** — a frozen dataclass: `timestamp: datetime`, `level: int`
(a `logging` level number), `source: str`, `message: str`. Pure data, no Qt.

**`LogBufferModel(QAbstractTableModel)`** — two ring buffers, one per source,
and the model over whichever is selected. Interface: `append(entry)`,
`set_source(name)`, `clear()`, `entries()`. Capacity **5000 per source**;
eviction is oldest-first and invisible to callers, who never see an index, a
row count, or the wrap point.

Newest-first ordering, matching `log_activity`'s current `insertRow(0)`.

It answers `Qt.BackgroundRole` with `status_danger_bg` for `ERROR` and above,
and — the reuse that matters — it answers **`ROLE_STATUS`** with a theme role
token. That is the exact role `StatusEdgeDelegate.edge_token` already reads, so
the shipped delegate paints the 3px error edge **unmodified**. No new delegate
class; the row also gets the selection ring for free, which is correct here.

**`LogFilterProxy(QSortFilterProxyModel)`** — two independent filters: a level
floor (show this level and above) and a case-insensitive substring over
`source` and `message` together. No sorting; the model's order is the truth.

**`FollowState`** — a pure helper, no Qt, holding `following: bool` and
`pending: int`. Three inputs: `scrolled(at_bottom)`, `appended()`,
`jumped_to_latest()`. Extracted precisely so follow-tail is testable without
driving real scrollbar pixels, which is the part of this that would otherwise
be untested.

**`LogViewer(QWidget)`** — the page. A `QTreeView` with
`setRootIsDecorated(False)`, `ScrollPerPixel` on both axes, and no alternating
row colours (level colour and the danger tint already carry the row). Above it
one control row: the source switch, level filter buttons (`:checked`, per the
roadmap), a search field, and a `Wrap` toggle. `Save as text` is a ghost
button. **No primary button** — a log viewer has no committing action.

At the foot, a **layout row, not an overlay**: hidden while following; when the
user has scrolled up it reads `"12 new entries"` with a `Jump to latest` flat
button. Returning to the bottom resumes following and clears the count.

Wrapping is **off by default**: `setUniformRowHeights(True)` and the message
column elides right. `Wrap` on sets `setWordWrap(True)` and
`setUniformRowHeights(False)`, and the continuation keeps the message column's
indent. The setting is remembered.

### `QtLogHandler` becomes structured

`gui/log_handler.py` today formats a record to `"%(asctime)s - %(levelname)s -
%(message)s"` and emits a `str`. A level filter cannot read a level out of a
formatted string without parsing it back, so the handler emits the structure
instead:

```python
entry_received = Signal(object)   # a LogEntry
```

built in `emit()` from `record.levelno`, `record.name` and
`record.getMessage()`. `log_message_received` and the `setFormatter` call in
`main_window_pyside.py` are deleted — the widget had exactly one consumer.

### `log_activity` keeps its signature

`MainWindow.log_activity(op_type, desc)` has ten call sites in
`actions_handler.py`. All ten stay untouched; only the body changes, from three
`setItem` calls to one `append(LogEntry(...))` on the Activity buffer. The
change stays local to the one method that owns it.

---

## 4. Theme

No new tokens. The viewer reads `status_danger_bg` and `status_danger` (error
rows and the edge), `status_warning`, `status_info`, `text_secondary` (the
`TIME` and `SOURCE` columns), and the mono face for `TIME`. Both themes are
specified by the tokens themselves; the viewer hardcodes no colour and
subscribes to `theme_changed` through `on_theme_changed`, as the session
browser does.

---

## 5. Testing seams

| Seam | What it proves | Needs a widget? |
|---|---|---|
| `LogEntry` + `LogBufferModel` | eviction at capacity, newest-first, source switch keeps both buffers, `ROLE_STATUS` is `status_danger` at ERROR and `None` below | no |
| `LogFilterProxy` | level floor, substring over source **and** message, the two compose | no |
| `FollowState` | follow stops on scroll-up, counts arrivals, resets on jump | no |
| `QtLogHandler.emit` | a `LogRecord` maps to the right `LogEntry` fields | no |
| `LogViewer` | both sources render; a 300-character traceback survives both wrap modes | offscreen |
| Rename | rail label reads `Logs`, no statistics page is reachable | offscreen |
| Regression | `global_stats.json` still gains a record when an analysis runs | no |

Both themes are checked by rendering the widget to a `QImage` under
`QT_QPA_PLATFORM=offscreen` and looking at the PNG — the technique 9.19
established; no display needed.

---

## 6. Done when

**9.20** — the rail reads `Logs`, no statistics page is reachable, and
`global_stats.json` still gains a record when an analysis runs.

**9.21** — both sources render in one widget, a 300-character traceback
survives both wrap modes, and follow resumes correctly after a scroll-up.

**Bundle** — both hold, `QT_QPA_PLATFORM=offscreen python -m pytest` passes,
`ruff check . --exclude shared` is clean, and `graphify update .` has run.

---

## 7. Out of scope

- Any `shared/` change. No token is added and no icon is added, so
  `scripts/sync_shared.py` is not run.
- Reading `shared/logger.py`'s log file (§3, "this session only").
- Re-siting the deleted SKU Summary / By Courier / Tags Breakdown (§1).
- Deleting `analysis_stats.json` or `recalculate_statistics` (§2, "Kept").
