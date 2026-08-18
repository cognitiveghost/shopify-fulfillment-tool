# Repeat detection: union of analysis history and Packing Tool's packed orders

Date: 2026-08-18
Roadmap: Phase 7, subtask `6h8v4Vj4P6qXHh93`
Status: approved (semantics chosen by the user 2026-08-18)

## Problem

"Repeat" marks an order the warehouse has already seen, so staff can catch a
duplicate shipment. Today it is derived from one source, and that source has two
independent defects.

### Defect 1 — the flag is destroyed by re-analysis (data loss)

`shopify_tool/core.py:1047`:

```python
updated_history = pd.concat([history_df, newly_fulfilled]).drop_duplicates(
    subset=["Order_Number"], keep="last"
)
```

`newly_fulfilled` is concatenated *after* the loaded history and carries today's
date, so `keep="last"` makes today's row win. Every re-analysis **overwrites the
order's original `Execution_Date` with today**, for every order still
`Fulfillable`.

`_detect_repeated_orders` flags an order when its `Execution_Date` is older than
the cutoff, so the flag disappears on the next run. The loss is permanent —
`fulfillment_history.csv` is the only record of the first-fulfillment date, and
it has just been rewritten.

Verified in the interpreter against the real file's schema
(`Order_Number,Execution_Date`):

| `keep` | resulting `Execution_Date` for an order first seen 2025-11-27 |
|---|---|
| `"last"` (today) | `2026-08-18` — original date gone |
| `"first"` (fix) | `2025-11-27` — preserved |

`keep="first"` still admits genuinely new orders (confirmed: an order absent from
history is inserted with today's date).

### Defect 2 — analysis is not fulfilment

The history records that an order was *analyzed as Fulfillable*, not that it was
ever picked, packed and shipped. An order analyzed and then cancelled counts as
history forever. This is the gap the roadmap item names: the authoritative record
of what physically left the warehouse lives in Packing Tool.

## Decision: union semantics

**Repeat = the order was seen at least N days ago in *either* SFT's analysis
history *or* Packing Tool's completed orders.** (N = `repeat_detection_days`,
default 1, unchanged.)

Chosen by the user over two alternatives:

- *Packing Tool only* (the roadmap item's literal wording) — cleanest semantics,
  but no per-order packing history exists today, so nothing would flag as Repeat
  until packing history accumulates, and orders shipped without going through
  Packing Tool would never flag at all.
- *Fix the clobber only* — one line, fixes the reported symptom, but leaves
  Defect 2 and defers the cross-repo item.

Repeat is a duplicate-shipment warning: a false negative (missing a genuine
repeat) is worse than a false positive. The union minimises the failure that
matters and has no migration cliff — the analysis signal keeps working from day
one while the packing signal accumulates behind it.

## Transport: extend the channel that already exists

No new file and no directory walk are needed. The plumbing is already in place:

```
Packing Tool                     shared file server                SFT
──────────────────────────────────────────────────────────────────────────────
update_session_metadata()  ──►  <session>/session_info.json
  (src/session_manager.py:672)     ["packing_progress"][list]
                                          │
                                          ▼
                                  CLIENT_<id>/session_index.json  ──►  SFT reads
                                    (SFT-owned per-client cache)       (cached)
```

Packing Tool already writes a `packing_progress` block into SFT's
`session_info.json` on every status change, and SFT already mirrors that into a
per-client `session_index.json` which `list_client_sessions()` reads instead of
walking the session tree. Confirmed present in live server data:

```json
"packing_progress": {
  "ALL_ORDERS_ALMADERM": {"started_at": "...", "status": "in_progress"}
}
```

The change is to carry the completed order numbers in that same block. SFT then
reads one already-cached file per client.

Alternatives rejected:

- **SFT walks `*/packing/*/packing_state.json`.** Needs no Packing Tool change,
  but costs one network read per (session × packing list) on a slow UNC share,
  unbounded backwards in time. `session_registry_manager.py`'s own docstring
  records that a full scan took 15–20 minutes; the registry exists specifically
  to avoid this.
- **A new per-client `packed_orders.json`.** Clean, but a new file, a new
  writer and a migration, to carry data an existing block can hold.

### Order-number format

No normalisation is needed. Verified identical across all three surfaces in live
data: `completed[].order_number` in `packing_state.json`, `orders[].order_number`
in SFT's packing-list JSON, and `Order_Number` in `fulfillment_history.csv` all
spell it `#11019512`. Order numbers are **not** numeric — `CLIENT_WATERDROP` uses
`#BG1086` — so nothing may coerce them to int.

## Components

### 1. Packing Tool — record completed order numbers

`src/session_manager.py::update_session_metadata()` gains the packed order
numbers and writes them into the `packing_progress[packing_list_name]` block it
already maintains:

```json
"packing_progress": {
  "ALL_ORDERS_ALMADERM": {
    "started_at": "...",
    "status": "completed",
    "updated_at": "...",
    "completed_orders": ["#11019512", "#11019513"]
  }
}
```

The caller passes the order numbers; `update_session_metadata` stays a dumb
writer. Verified call sites in `src/main.py`:

| line | status | change |
|---|---|---|
| 1438 | `'in_progress'` (list loaded) | none — nothing packed yet |
| 2346 | `'in_progress'` (list loaded) | none — nothing packed yet |
| 1767 | `'completed'` (session end) | pass the packed order numbers |

At line 1767 the numbers are in scope as
`_logic_ref.session_packing_state.get('completed_orders', [])` — `_logic_ref` is
bound to `self.logic` at line 1679. `packer_logic._load_session_state()`
normalises that key to a **list of order-number strings** in all three of its
format branches (new `completed[]` dicts, a legacy `completed` string list, and
the old top-level `completed_orders`), so the caller needs no format handling.

**The new parameter must be optional.** `tests/test_metadata_utils.py:81` calls
`update_session_metadata(path, name, status)` with exactly three positional
arguments; a required fourth breaks it.

**Known limitation, accepted.** A session abandoned without reaching the
session-end path records no order numbers, even though `packing_state.json` on
disk still holds them. No reconciliation is built for this: the analysis signal
already covers those orders, which is the point of the union.

`shared/` is not touched — it is one-way synced from packing-tool and neither
side needs a change there.

### 2. Packing Tool — close the lost-update window on `session_info.json`

`update_session_metadata()` does an unlocked read–modify–write of
`session_info.json`, while SFT guards the same file with `_locked_session_info()`
(an exclusive lock on the sidecar `session_info.json.lock`, which is already
present on the server). A concurrent SFT update and Packing Tool update can
therefore lose one another's changes.

This is pre-existing, but it sits directly in the path this design writes more
data through, and a lost update now silently costs Repeat flags. Both repos
already ship `shared/file_lock.py::locked_file()`, so the fix is to take the same
lock around the existing read–modify–write. Separable from the rest if review
disagrees.

### 3. SFT — `shopify_tool/packed_orders.py` (new)

One public function:

```python
def load_packed_orders(profile_manager, client_id) -> pd.DataFrame:
    """Order numbers Packing Tool has completed, with the date they were packed.

    Returns a DataFrame with columns [Order_Number, Execution_Date], empty on
    any failure. Never raises.
    """
```

Reads the client's `session_index.json` via the existing session-listing path,
walks each entry's `packing_progress` blocks, and emits one row per completed
order number dated by that block's `updated_at` (falling back to `started_at`).

**Best-effort by contract.** A missing file, malformed JSON, an unreachable
server or an old-format entry logs and yields an empty frame. Repeat detection
then degrades to exactly today's behaviour. Analysis must never fail because the
packing signal is unavailable — the warehouse can still ship.

### 4. SFT — `core.py` wiring

Two changes, both at the existing call sites:

1. `keep="last"` → `keep="first"` at line 1047 (Defect 1).
2. Between `history_df = _load_history_data(...)` (line 1218) and
   `_run_analysis_and_rules(orders_df, stock_df, history_df, config)` (line
   1252), build the union and pass **that** to analysis:

```python
detection_history_df = union_history_with_packed(history_df, packed_df)
```

`_run_analysis_and_rules` receives `detection_history_df`; the write-back path
(line 1262) keeps the original `history_df`.

**The union is for detection only and is never persisted.**
`fulfillment_history.csv` remains SFT's own record of what it analyzed. Writing
packing-derived rows into it would change the file's meaning and let one
tool's data silently become the other's.

Union rule: concatenate, sort by `Execution_Date` ascending, then
`drop_duplicates(subset=["Order_Number"], keep="first")` — **earliest date per
order wins**. Consistent with the `keep="first"` fix, and correct for the
purpose: the earliest sighting is what makes an order a repeat.

### 5. `_detect_repeated_orders` — unchanged

It already takes a `[Order_Number, Execution_Date]` frame and applies the cutoff.
Feeding it a unioned frame needs no new parameter, no new branch, and no second
code path. Its existing tests keep passing unmodified.

## Data flow

```
fulfillment_history.csv ──┐
  (analysis signal)       ├──► detection_history_df ──► _detect_repeated_orders
session_index.json ───────┘      (earliest date wins)         │
  packing_progress[].              detection only,            ▼
  completed_orders                 never written back    System_note = "Repeat"

fulfillment_history.csv ◄── updated_history (keep="first")  ← history_df only
```

## Testing

Unit, `QT_QPA_PLATFORM=offscreen python -m pytest`, no GUI needed.

**Defect 1 (regression pin).** No existing test covers the history write-back, so
the clobber is currently unpinned. Add one asserting an order already in history
keeps its original `Execution_Date` after a re-analysis that finds it
`Fulfillable` — this test must fail on `keep="last"`.

**`load_packed_orders`.** Fixture `session_index.json` files: a well-formed one
with two entries; one with a `packing_progress` block predating this change (no
`completed_orders` key); a malformed one; and a missing file. The last three must
each return an empty frame and log, not raise.

**Union.** An order in both sources with different dates keeps the earlier one.
An order only in packing history is flagged when old enough. An order only in
analysis history is still flagged — this is the no-cliff guarantee and is the
test most worth having.

**Fixture warning.** Per the lesson from PR #288, each test's fixture must be
able to produce the failure it claims to catch: the union tests need genuinely
differing dates across the two sources, not the same date in both.

Existing `TestRepeatDetection` in `tests/test_analysis.py` must pass unmodified —
it is the proof the analysis path is unchanged.

## Out of scope

- Retroactive backfill of packing history. Sessions completed before this ships
  have no `completed_orders` recorded; they contribute nothing. Acceptable
  because the analysis signal covers them.
- Session Browser completion sync and the 30-day archive — Phase 7 subtask
  `6h8v4VvC2G5XjrqV`, a separate cycle. This design deliberately keeps the
  registry (`registry_index.json`) untouched so that item stays free to change it.
- The `Repeat` rendering in `pandas_model.py` and the column config. Unchanged.
