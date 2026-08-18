# Repeat Detection: Union of Analysis History and Packed Orders — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mark an order "Repeat" when it was seen at least N days ago in *either* SFT's analysis history *or* Packing Tool's completed orders, and stop re-analysis from destroying the original fulfilment date.

**Architecture:** Packing Tool records completed order numbers into the `packing_progress` block it already writes into SFT's `session_info.json`; SFT reads them back from the per-client `session_index.json` it already caches, unions them with `fulfillment_history.csv` (earliest date per order wins), and feeds the union to the existing `_detect_repeated_orders`, which does not change. The union is used for detection only and is never written back to `fulfillment_history.csv`.

**Tech Stack:** Python 3, pandas, pytest. PySide6 is not involved — no GUI code changes.

**Spec:** `docs/superpowers/specs/2026-08-18-repeat-detection-packing-sync-design.md`

## Global Constraints

- Two repos. Tasks 1–3 are in `shopify-fulfillment-tool`; Task 4 is in `../packing-tool`. They ship as **two separate PRs**.
- **Never hand-edit `shared/`** in `shopify-fulfillment-tool` — it is one-way synced from `../packing-tool`. This plan does not change `shared/` in either repo.
- Order numbers are **strings** and are **not numeric** (`#11019512`, and `#BG1086` for CLIENT_WATERDROP). Never coerce them to int. No normalisation is needed — the format is already identical on both sides.
- Reading the packing signal is **best-effort**: any failure logs and yields an empty result. Analysis must never fail because Packing Tool data is missing or malformed.
- Gate for `shopify-fulfillment-tool`, run from the worktree root:
  `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest` and `.venv/bin/ruff check . --exclude shared`
- Gate for `packing-tool`: `python -m pytest` (see its own `CLAUDE.md`).
- Baseline before this plan: **727 passed** on `worktree-repeat-detection-packing-sync`.
- Every commit ends with these two trailers, verbatim:

```
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_011ryEQFDt4aqFcUeFFhkz9c
```

- `python` and `ruff` are **not** on PATH on this machine. Always use `.venv/bin/python` and `.venv/bin/ruff`.
- After the last task in a repo, run `graphify update .` in that repo.

---

## File Structure

| File | Repo | Responsibility |
|---|---|---|
| `shopify_tool/core.py` | SFT | Modify: extract `_merge_fulfillment_history`, fix the clobber, wire the union into the analysis call |
| `shopify_tool/packed_orders.py` | SFT | **Create**: read Packing Tool's completed orders; union them with analysis history |
| `tests/test_core.py` | SFT | Modify: regression test pinning the preserved `Execution_Date` |
| `tests/test_packed_orders.py` | SFT | **Create**: loader and union tests |
| `src/session_manager.py` | packing-tool | Modify: `update_session_metadata` records order numbers under a lock |
| `src/main.py` | packing-tool | Modify: pass packed order numbers at the one `'completed'` call site |
| `tests/test_session_metadata_orders.py` | packing-tool | **Create**: writer tests |

---

## Task 1: Stop re-analysis destroying the original fulfilment date

Independent of everything else — fixes a live data-loss bug and ships value on its own.

**Files:**
- Modify: `shopify_tool/core.py` (the history write in `_save_results_and_reports`, currently at `:1041-1049`)
- Test: `tests/test_core.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `shopify_tool.core._merge_fulfillment_history(history_df: pd.DataFrame, newly_fulfilled: pd.DataFrame) -> pd.DataFrame` — used by no later task, but Task 3's reviewer will compare it against the union helper.

**Why extract a helper for a one-word fix:** the current merge is buried inside `_save_results_and_reports`, which takes 13 arguments and performs Excel/JSON/session file IO. There is no seam to test the merge through. A four-line pure helper makes a permanent-data-loss path unit-testable; that is the reason to extract it, and the only reason.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_core.py`:

```python
class TestFulfillmentHistoryMerge:
    """The merge must preserve each order's ORIGINAL Execution_Date.

    fulfillment_history.csv is the only record of when an order was first
    fulfilled. Overwriting that date loses it permanently and silently
    clears the order's "Repeat" flag.
    """

    def test_reanalysis_preserves_original_execution_date(self):
        from shopify_tool.core import _merge_fulfillment_history

        history = pd.DataFrame({
            "Order_Number": ["#11014590", "#11014599"],
            "Execution_Date": ["2025-11-27", "2025-11-27"],
        })
        # A re-analysis today finds #11014590 still Fulfillable.
        newly_fulfilled = pd.DataFrame({
            "Order_Number": ["#11014590"],
            "Execution_Date": ["2026-08-18"],
        })

        merged = _merge_fulfillment_history(history, newly_fulfilled)
        dates = dict(zip(merged["Order_Number"], merged["Execution_Date"]))

        assert dates["#11014590"] == "2025-11-27", (
            "re-analysis overwrote the original fulfilment date"
        )
        assert dates["#11014599"] == "2025-11-27"

    def test_genuinely_new_order_is_added(self):
        from shopify_tool.core import _merge_fulfillment_history

        history = pd.DataFrame({
            "Order_Number": ["#11014590"],
            "Execution_Date": ["2025-11-27"],
        })
        newly_fulfilled = pd.DataFrame({
            "Order_Number": ["#99999"],
            "Execution_Date": ["2026-08-18"],
        })

        merged = _merge_fulfillment_history(history, newly_fulfilled)
        dates = dict(zip(merged["Order_Number"], merged["Execution_Date"]))

        assert dates["#99999"] == "2026-08-18"
        assert dates["#11014590"] == "2025-11-27"

    def test_empty_history_accepts_all_new_orders(self):
        from shopify_tool.core import _merge_fulfillment_history

        history = pd.DataFrame(columns=["Order_Number", "Execution_Date"])
        newly_fulfilled = pd.DataFrame({
            "Order_Number": ["#1", "#2"],
            "Execution_Date": ["2026-08-18", "2026-08-18"],
        })

        merged = _merge_fulfillment_history(history, newly_fulfilled)
        assert set(merged["Order_Number"]) == {"#1", "#2"}
```

`tests/test_core.py` already imports pandas as `pd`; confirm before adding.

- [ ] **Step 2: Run the test to verify it fails**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_core.py::TestFulfillmentHistoryMerge -v
```

Expected: FAIL — `ImportError: cannot import name '_merge_fulfillment_history'`.

- [ ] **Step 3: Add the helper**

Add to `shopify_tool/core.py`, immediately above `_save_results_and_reports`:

```python
def _merge_fulfillment_history(
    history_df: pd.DataFrame, newly_fulfilled: pd.DataFrame
) -> pd.DataFrame:
    """Merge newly fulfilled orders into history, keeping the ORIGINAL date.

    keep="first" is load-bearing. `newly_fulfilled` is concatenated after
    `history_df` and carries today's date, so keep="last" would overwrite
    each order's original Execution_Date on every re-analysis -- destroying
    the only record of when it was first fulfilled, and silently clearing
    its "Repeat" flag.
    """
    return pd.concat([history_df, newly_fulfilled]).drop_duplicates(
        subset=["Order_Number"], keep="first"
    )
```

- [ ] **Step 4: Call it from the write path**

In `_save_results_and_reports`, replace:

```python
        updated_history = pd.concat([history_df, newly_fulfilled]).drop_duplicates(
            subset=["Order_Number"], keep="last"
        )
```

with:

```python
        updated_history = _merge_fulfillment_history(history_df, newly_fulfilled)
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_core.py -v
```

Expected: PASS, including the three new tests.

- [ ] **Step 6: Run the full suite**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest
```

Expected: 730 passed. If anything else fails, a pre-existing test encoded the old clobber behaviour — read it before changing it, and say so in the commit.

- [ ] **Step 7: Commit**

```bash
git add shopify_tool/core.py tests/test_core.py
git commit -F - <<'EOF'
Fix: re-analysis destroyed each order's original fulfilment date

The history merge used drop_duplicates(keep="last"). newly_fulfilled is
concatenated after history_df and carries today's date, so every
re-analysis overwrote the original Execution_Date of every order still
Fulfillable. fulfillment_history.csv is the only record of that date, so
the loss was permanent -- and _detect_repeated_orders then saw a fresh
date and silently dropped the order's "Repeat" flag.

Extracted the merge into _merge_fulfillment_history so the path has a
test seam at all; it previously sat inside a 13-argument function that
also does Excel and session file IO.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_011ryEQFDt4aqFcUeFFhkz9c
EOF
```

---

## Task 2: Read Packing Tool's completed orders

**Files:**
- Create: `shopify_tool/packed_orders.py`
- Test: `tests/test_packed_orders.py`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces:
  - `load_packed_orders(profile_manager, client_id: str) -> pd.DataFrame` — columns `["Order_Number", "Execution_Date"]`, `Execution_Date` as `YYYY-MM-DD` strings. Returns an empty frame with those columns on any failure. Never raises.
  - `union_history_with_packed(history_df: pd.DataFrame, packed_df: pd.DataFrame) -> pd.DataFrame` — same columns; earliest date per order wins. Used by Task 3.

**Shape of the data being read.** Confirmed against live server data. Each client has `Sessions/CLIENT_<ID>/session_index.json` containing a JSON **list** of session entries. An entry that has been packed carries:

```json
{
  "session_name": "2026-07-26_2",
  "packing_progress": {
    "ALL_ORDERS_ALMADERM": {
      "started_at": "2026-07-26T18:25:33.932024+00:00",
      "status": "completed",
      "updated_at": "2026-07-26T18:41:02.115000+00:00",
      "completed_orders": ["#11019512", "#11019513"]
    }
  }
}
```

`completed_orders` is written by Task 4. Entries written before Task 4 ships have a `packing_progress` block with **no** `completed_orders` key — that is the normal case at first run, not an error.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_packed_orders.py`:

```python
import json

import pandas as pd
import pytest

from shopify_tool.packed_orders import load_packed_orders, union_history_with_packed


class _FakeProfileManager:
    """Minimal stand-in exposing only what load_packed_orders uses."""

    def __init__(self, sessions_root):
        self._sessions_root = sessions_root

    def get_sessions_root(self):
        return self._sessions_root


def _write_index(tmp_path, client_id, entries):
    client_dir = tmp_path / f"CLIENT_{client_id}"
    client_dir.mkdir(parents=True, exist_ok=True)
    (client_dir / "session_index.json").write_text(
        json.dumps(entries), encoding="utf-8"
    )
    return _FakeProfileManager(tmp_path)


class TestLoadPackedOrders:
    def test_reads_completed_orders_with_packing_date(self, tmp_path):
        pm = _write_index(tmp_path, "ALMADERM", [
            {
                "session_name": "2026-07-26_2",
                "packing_progress": {
                    "ALL_ORDERS": {
                        "started_at": "2026-07-26T18:25:33+00:00",
                        "updated_at": "2026-07-28T09:10:00+00:00",
                        "status": "completed",
                        "completed_orders": ["#11019512", "#11019513"],
                    }
                },
            }
        ])

        df = load_packed_orders(pm, "ALMADERM")

        assert list(df.columns) == ["Order_Number", "Execution_Date"]
        assert dict(zip(df["Order_Number"], df["Execution_Date"])) == {
            "#11019512": "2026-07-28",
            "#11019513": "2026-07-28",
        }

    def test_falls_back_to_started_at_when_no_updated_at(self, tmp_path):
        pm = _write_index(tmp_path, "ALMADERM", [
            {
                "session_name": "2026-07-26_2",
                "packing_progress": {
                    "ALL_ORDERS": {
                        "started_at": "2026-07-26T18:25:33+00:00",
                        "status": "completed",
                        "completed_orders": ["#A"],
                    }
                },
            }
        ])

        df = load_packed_orders(pm, "ALMADERM")
        assert df.iloc[0]["Execution_Date"] == "2026-07-26"

    def test_collects_across_sessions_and_packing_lists(self, tmp_path):
        pm = _write_index(tmp_path, "ALMADERM", [
            {
                "session_name": "2026-07-01_1",
                "packing_progress": {
                    "LIST_A": {"updated_at": "2026-07-01T10:00:00+00:00",
                               "completed_orders": ["#A"]},
                    "LIST_B": {"updated_at": "2026-07-01T11:00:00+00:00",
                               "completed_orders": ["#B"]},
                },
            },
            {
                "session_name": "2026-07-02_1",
                "packing_progress": {
                    "LIST_C": {"updated_at": "2026-07-02T10:00:00+00:00",
                               "completed_orders": ["#C"]},
                },
            },
        ])

        df = load_packed_orders(pm, "ALMADERM")
        assert set(df["Order_Number"]) == {"#A", "#B", "#C"}

    def test_same_order_packed_twice_keeps_earliest(self, tmp_path):
        pm = _write_index(tmp_path, "ALMADERM", [
            {"session_name": "2026-07-05_1", "packing_progress": {
                "L": {"updated_at": "2026-07-05T10:00:00+00:00",
                      "completed_orders": ["#A"]}}},
            {"session_name": "2026-07-01_1", "packing_progress": {
                "L": {"updated_at": "2026-07-01T10:00:00+00:00",
                      "completed_orders": ["#A"]}}},
        ])

        df = load_packed_orders(pm, "ALMADERM")
        assert len(df) == 1
        assert df.iloc[0]["Execution_Date"] == "2026-07-01"

    # --- degradation: each of these must return empty, not raise ---

    def test_entry_without_completed_orders_key_is_skipped(self, tmp_path):
        """The normal case before Task 4 ships -- not an error."""
        pm = _write_index(tmp_path, "ALMADERM", [
            {
                "session_name": "2026-07-26_2",
                "packing_progress": {
                    "ALL_ORDERS": {
                        "started_at": "2026-07-26T18:25:33+00:00",
                        "status": "in_progress",
                    }
                },
            }
        ])

        df = load_packed_orders(pm, "ALMADERM")
        assert df.empty
        assert list(df.columns) == ["Order_Number", "Execution_Date"]

    def test_entry_without_packing_progress_is_skipped(self, tmp_path):
        pm = _write_index(tmp_path, "ALMADERM", [
            {"session_name": "2026-07-26_1", "status": "active"}
        ])
        assert load_packed_orders(pm, "ALMADERM").empty

    def test_missing_index_file_returns_empty(self, tmp_path):
        assert load_packed_orders(_FakeProfileManager(tmp_path), "NOSUCH").empty

    def test_malformed_json_returns_empty(self, tmp_path):
        client_dir = tmp_path / "CLIENT_ALMADERM"
        client_dir.mkdir(parents=True)
        (client_dir / "session_index.json").write_text("{not json", encoding="utf-8")

        assert load_packed_orders(_FakeProfileManager(tmp_path), "ALMADERM").empty

    def test_unparseable_timestamp_is_skipped_without_raising(self, tmp_path):
        pm = _write_index(tmp_path, "ALMADERM", [
            {"session_name": "s", "packing_progress": {
                "L": {"updated_at": "not-a-date", "completed_orders": ["#A"]}}},
        ])
        assert load_packed_orders(pm, "ALMADERM").empty

    def test_client_id_is_case_insensitive(self, tmp_path):
        pm = _write_index(tmp_path, "ALMADERM", [
            {"session_name": "s", "packing_progress": {
                "L": {"updated_at": "2026-07-01T10:00:00+00:00",
                      "completed_orders": ["#A"]}}},
        ])
        assert not load_packed_orders(pm, "almaderm").empty


class TestUnionHistoryWithPacked:
    def test_order_in_both_sources_keeps_earlier_date(self):
        history = pd.DataFrame({"Order_Number": ["#A"], "Execution_Date": ["2026-07-10"]})
        packed = pd.DataFrame({"Order_Number": ["#A"], "Execution_Date": ["2026-07-01"]})

        out = union_history_with_packed(history, packed)
        assert len(out) == 1
        assert out.iloc[0]["Execution_Date"] == "2026-07-01"

    def test_order_in_both_sources_keeps_earlier_date_when_history_is_earlier(self):
        history = pd.DataFrame({"Order_Number": ["#A"], "Execution_Date": ["2026-07-01"]})
        packed = pd.DataFrame({"Order_Number": ["#A"], "Execution_Date": ["2026-07-10"]})

        out = union_history_with_packed(history, packed)
        assert len(out) == 1
        assert out.iloc[0]["Execution_Date"] == "2026-07-01"

    def test_packed_only_order_is_included(self):
        history = pd.DataFrame(columns=["Order_Number", "Execution_Date"])
        packed = pd.DataFrame({"Order_Number": ["#A"], "Execution_Date": ["2026-07-01"]})

        out = union_history_with_packed(history, packed)
        assert set(out["Order_Number"]) == {"#A"}

    def test_history_only_order_survives_empty_packed(self):
        """The no-cliff guarantee: the analysis signal keeps working when
        Packing Tool has contributed nothing yet."""
        history = pd.DataFrame({"Order_Number": ["#A"], "Execution_Date": ["2026-07-01"]})
        packed = pd.DataFrame(columns=["Order_Number", "Execution_Date"])

        out = union_history_with_packed(history, packed)
        assert dict(zip(out["Order_Number"], out["Execution_Date"])) == {"#A": "2026-07-01"}

    def test_both_empty_returns_empty_with_expected_columns(self):
        empty = pd.DataFrame(columns=["Order_Number", "Execution_Date"])
        out = union_history_with_packed(empty, empty)
        assert out.empty
        assert list(out.columns) == ["Order_Number", "Execution_Date"]
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_packed_orders.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'shopify_tool.packed_orders'`.

- [ ] **Step 3: Write the implementation**

Create `shopify_tool/packed_orders.py`:

```python
"""Read the orders Packing Tool has finished packing.

Packing Tool records the order numbers it completed into the
`packing_progress` block of each session's `session_info.json`, which this
repo mirrors into the per-client `session_index.json` cache. Reading that
one file per client avoids walking the session tree on the network share.

Everything here is best-effort by contract: a missing file, malformed JSON
or an old-format entry yields an empty result and a log line. Repeat
detection then degrades to using analysis history alone. An analysis must
never fail because the packing signal is unavailable -- the warehouse can
still ship.
"""

import json
import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

COLUMNS = ["Order_Number", "Execution_Date"]

INDEX_FILENAME = "session_index.json"


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=COLUMNS)


def load_packed_orders(profile_manager, client_id: str) -> pd.DataFrame:
    """Order numbers Packing Tool has completed, with the date packed.

    Args:
        profile_manager: provides get_sessions_root()
        client_id: client identifier, case-insensitive

    Returns:
        DataFrame with columns [Order_Number, Execution_Date] (dates as
        YYYY-MM-DD strings), earliest date per order. Empty on any failure.
    """
    if not profile_manager or not client_id:
        return _empty()

    try:
        sessions_root = Path(profile_manager.get_sessions_root())
        index_path = sessions_root / f"CLIENT_{client_id.upper()}" / INDEX_FILENAME
        if not index_path.exists():
            logger.debug(f"No session index for packed orders: {index_path}")
            return _empty()
        entries = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, AttributeError):
        logger.exception("Could not read packed orders; repeat detection will use analysis history only")
        return _empty()

    if not isinstance(entries, list):
        logger.warning("Session index is not a list; ignoring packed orders")
        return _empty()

    rows = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        progress = entry.get("packing_progress")
        if not isinstance(progress, dict):
            continue
        for block in progress.values():
            if not isinstance(block, dict):
                continue
            orders = block.get("completed_orders")
            if not orders:
                # Written before completed_orders existed, or nothing packed.
                continue
            packed_date = _to_date(block.get("updated_at") or block.get("started_at"))
            if packed_date is None:
                continue
            rows.extend(
                {"Order_Number": str(o), "Execution_Date": packed_date}
                for o in orders
                if o
            )

    if not rows:
        return _empty()

    df = pd.DataFrame(rows, columns=COLUMNS)
    df = df.sort_values("Execution_Date").drop_duplicates(
        subset=["Order_Number"], keep="first"
    )
    logger.info(f"Loaded {len(df)} packed orders for repeat detection ({client_id})")
    return df.reset_index(drop=True)


def _to_date(timestamp) -> str | None:
    """ISO timestamp -> 'YYYY-MM-DD', or None if unparseable."""
    if not timestamp:
        return None
    parsed = pd.to_datetime(timestamp, errors="coerce", utc=True)
    if pd.isna(parsed):
        return None
    return parsed.strftime("%Y-%m-%d")


def union_history_with_packed(
    history_df: pd.DataFrame, packed_df: pd.DataFrame
) -> pd.DataFrame:
    """Combine analysis history with packed orders, earliest date per order.

    An order is a repeat if it was seen at least N days ago in EITHER
    source, so the earliest sighting is the one that matters. The result is
    for detection only -- it must never be written to
    fulfillment_history.csv, which is this repo's own record of what it
    analyzed.
    """
    frames = [f for f in (history_df, packed_df) if f is not None and not f.empty]
    if not frames:
        return _empty()

    combined = pd.concat(frames, ignore_index=True)[COLUMNS]
    combined = combined.sort_values("Execution_Date").drop_duplicates(
        subset=["Order_Number"], keep="first"
    )
    return combined.reset_index(drop=True)
```

**Note on `sort_values` for date strings:** `YYYY-MM-DD` sorts correctly lexicographically, so no datetime conversion is needed here. `_to_date` guarantees that format; `fulfillment_history.csv` uses it too (verified in live data).

- [ ] **Step 4: Run the tests to verify they pass**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_packed_orders.py -v
```

Expected: PASS, all of them.

- [ ] **Step 5: Re-confirm the fake matches the real ProfileManager API**

A fake that drifts from the real API gives green tests over broken production code:

```bash
grep -n "def get_sessions_root" shopify_tool/profile_manager.py
```

Expected: one match at `:1423`, `def get_sessions_root(self) -> Path:` (verified while
writing this plan). If it has moved or been renamed, fix `packed_orders.py` **and**
`_FakeProfileManager` together, then re-run Step 4.

- [ ] **Step 6: Lint and commit**

```bash
.venv/bin/ruff check . --exclude shared
git add shopify_tool/packed_orders.py tests/test_packed_orders.py
git commit -F - <<'EOF'
Add packed-orders reader for repeat detection

Reads the order numbers Packing Tool completed from the per-client
session_index.json this repo already caches, rather than walking
*/packing/*/packing_state.json across the network share.

Best-effort by contract: a missing file, malformed JSON, an unparseable
timestamp or an entry predating completed_orders all yield an empty frame
and a log line, so an analysis never fails because the packing signal is
unavailable.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_011ryEQFDt4aqFcUeFFhkz9c
EOF
```

---

## Task 3: Feed the union into repeat detection

**Files:**
- Modify: `shopify_tool/core.py` (around `:1216-1252`)
- Test: `tests/test_analysis.py` (verify unchanged), `tests/test_packed_orders.py` (already covers the union)

**Interfaces:**
- Consumes: `load_packed_orders`, `union_history_with_packed` from Task 2.
- Produces: nothing for later tasks.

**The critical constraint:** `history_df` feeds **two** consumers in `run_full_analysis` — `_run_analysis_and_rules` (detection) and `_save_results_and_reports` (the CSV write-back). Only the **detection** one gets the union. Passing the union to the writer would write packing-derived rows into `fulfillment_history.csv`, changing what that file means and letting one tool's data silently become the other's.

- [ ] **Step 1: Add the import**

At the top of `shopify_tool/core.py`, with the other `shopify_tool` imports:

```python
from shopify_tool.packed_orders import load_packed_orders, union_history_with_packed
```

Match the existing import style in that file — check whether siblings use `from shopify_tool.x import` or `from .x import` and follow it.

- [ ] **Step 2: Build the union and pass it to analysis only**

In `run_full_analysis`, after the `history_df = _load_history_data(...)` block (Step 3, around `:1218`), add:

```python
        # Repeat detection also counts orders Packing Tool has already packed.
        # Detection only -- history_df below is what gets written back to
        # fulfillment_history.csv, and must stay this repo's own record.
        packed_df = load_packed_orders(profile_manager, client_id)
        detection_history_df = union_history_with_packed(history_df, packed_df)
```

Then change the analysis call (around `:1251`) from:

```python
            _run_analysis_and_rules(orders_df, stock_df, history_df, config)
```

to:

```python
            _run_analysis_and_rules(orders_df, stock_df, detection_history_df, config)
```

**Leave the `history_df` argument to `_save_results_and_reports` (around `:1262`) exactly as it is.**

- [ ] **Step 3: Verify the write-back still receives the un-unioned frame**

```bash
grep -n "detection_history_df\|history_df," shopify_tool/core.py | sed -n '1,40p'
```

Confirm by eye: `_run_analysis_and_rules` gets `detection_history_df`; `_save_results_and_reports` gets `history_df`. This is the single most important line in the task — a reviewer should be able to check it in one glance.

- [ ] **Step 4: Run the existing repeat-detection tests unmodified**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_analysis.py::TestRepeatDetection -v
```

Expected: PASS, with **no edits** to those tests. They are the proof the analysis path is unchanged. If one fails, stop — the union changed behaviour for the analysis-only case, which it must not.

- [ ] **Step 5: Run the full suite**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest
```

Expected: 745 passed (727 baseline + 3 from Task 1 + 15 from Task 2).

- [ ] **Step 6: Lint, update the graph, and commit**

```bash
.venv/bin/ruff check . --exclude shared
graphify update .
git add shopify_tool/core.py
git commit -F - <<'EOF'
Count packed orders when detecting repeats

run_full_analysis now unions Packing Tool's completed orders into the
frame handed to _detect_repeated_orders, so an order counts as a repeat
if it was seen >= N days ago in either source.

_detect_repeated_orders is unchanged -- it already takes an
[Order_Number, Execution_Date] frame, so the union needs no new parameter
and no second code path.

The union is detection-only. _save_results_and_reports still receives the
un-unioned history_df: fulfillment_history.csv stays this repo's own
record of what it analyzed.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_011ryEQFDt4aqFcUeFFhkz9c
EOF
```

---

## Task 4: Packing Tool records the order numbers it packed

**Repo: `../packing-tool`.** Separate branch, separate PR. Until this ships, Tasks 1–3 run correctly and simply find no packed orders.

**Files:**
- Modify: `src/session_manager.py:671-714` (`update_session_metadata`)
- Modify: `src/main.py:1767` (the one `'completed'` call site)
- Test: `tests/test_session_metadata_orders.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: `completed_orders: list[str]` inside `session_info.json`'s `packing_progress[<list name>]`, which Task 2's `load_packed_orders` reads.

**Two pre-verified constraints:**

1. **The new parameter must be optional.** `tests/test_metadata_utils.py:81` calls `update_session_metadata(str(tmp_path), "DHL_Orders", "in_progress")` with exactly three positional arguments. A required fourth breaks it.
2. **Only the `'completed'` call site passes orders.** `src/main.py:1438` and `:2346` fire at list-load time with `'in_progress'` — nothing is packed yet. Leave both unchanged.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_session_metadata_orders.py`:

```python
import json

from session_manager import SessionManager


def _mgr():
    return SessionManager(
        client_id="ALMADERM",
        profile_manager=None,
        lock_manager=None,
        worker_id="worker_001",
        worker_name="test",
    )


def _seed_session_info(tmp_path):
    (tmp_path / "session_info.json").write_text(
        json.dumps({"session_name": "2026-08-18_1", "client_id": "ALMADERM"}),
        encoding="utf-8",
    )


def _read(tmp_path):
    return json.loads((tmp_path / "session_info.json").read_text(encoding="utf-8"))


def test_completed_orders_are_recorded(tmp_path):
    _seed_session_info(tmp_path)

    _mgr().update_session_metadata(
        str(tmp_path), "ALL_ORDERS", "completed",
        completed_orders=["#11019512", "#11019513"],
    )

    block = _read(tmp_path)["packing_progress"]["ALL_ORDERS"]
    assert block["completed_orders"] == ["#11019512", "#11019513"]
    assert block["status"] == "completed"


def test_call_without_orders_still_works(tmp_path):
    """Pre-existing three-argument callers must keep working."""
    _seed_session_info(tmp_path)

    _mgr().update_session_metadata(str(tmp_path), "ALL_ORDERS", "in_progress")

    block = _read(tmp_path)["packing_progress"]["ALL_ORDERS"]
    assert block["status"] == "in_progress"
    assert "completed_orders" not in block


def test_orders_are_merged_not_replaced_across_calls(tmp_path):
    """A resumed session must not lose orders packed before the resume."""
    _seed_session_info(tmp_path)
    mgr = _mgr()

    mgr.update_session_metadata(
        str(tmp_path), "ALL_ORDERS", "completed", completed_orders=["#A"]
    )
    mgr.update_session_metadata(
        str(tmp_path), "ALL_ORDERS", "completed", completed_orders=["#B"]
    )

    block = _read(tmp_path)["packing_progress"]["ALL_ORDERS"]
    assert sorted(block["completed_orders"]) == ["#A", "#B"]


def test_other_keys_in_session_info_are_preserved(tmp_path):
    _seed_session_info(tmp_path)

    _mgr().update_session_metadata(
        str(tmp_path), "ALL_ORDERS", "completed", completed_orders=["#A"]
    )

    data = _read(tmp_path)
    assert data["session_name"] == "2026-08-18_1"
    assert data["client_id"] == "ALMADERM"


def test_missing_session_info_does_not_raise(tmp_path):
    _mgr().update_session_metadata(
        str(tmp_path), "ALL_ORDERS", "completed", completed_orders=["#A"]
    )
    assert not (tmp_path / "session_info.json").exists()
```

Check `SessionManager.__init__`'s real signature before running — adjust `_mgr()` to match if it differs.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/test_session_metadata_orders.py -v
```

Expected: FAIL — `update_session_metadata() got an unexpected keyword argument 'completed_orders'`.

- [ ] **Step 3: Extend `update_session_metadata`**

In `src/session_manager.py`, change the signature and body. Add `completed_orders` as an **optional keyword argument**, merge rather than replace, and take the same lock SFT uses on this file:

```python
    def update_session_metadata(
        self,
        session_path: str,
        packing_list_name: str,
        status: str,
        completed_orders: list[str] | None = None,
    ):
        """
        Update Shopify session metadata with packing progress.

        Updates session_info.json with packing status for tracking.
        This is a non-critical operation - failures are logged but don't stop execution.

        Args:
            session_path: Path to Shopify session
            packing_list_name: Name of packing list
            status: Status ('in_progress', 'completed', 'paused')
            completed_orders: Order numbers packed in this session, if any.
                The Shopify tool reads these back for repeat-order detection.
                Merged with any already recorded, so resuming a session does
                not drop orders packed before the resume.
        """
        session_info_file = Path(session_path) / SESSION_INFO_FILE

        if not session_info_file.exists():
            logger.warning(f"session_info.json not found: {session_path}")
            return

        try:
            # The Shopify tool guards this same file with an exclusive lock on
            # the sidecar .lock (its SessionManager._locked_session_info). Take
            # the same lock: without it, its read-modify-write and ours can
            # interleave and silently drop one side's changes.
            lock_path = session_info_file.with_name(SESSION_INFO_FILE + ".lock")
            with open(lock_path, "a+") as lock_handle, locked_file(lock_handle):
                with open(session_info_file, 'r', encoding='utf-8') as f:
                    session_info = json.load(f)

                if 'packing_progress' not in session_info:
                    session_info['packing_progress'] = {}

                block = session_info['packing_progress'].setdefault(
                    packing_list_name, {'started_at': get_current_timestamp()}
                )
                block['status'] = status
                block['updated_at'] = get_current_timestamp()

                if completed_orders:
                    merged = list(block.get('completed_orders', []))
                    merged.extend(o for o in completed_orders if o not in merged)
                    block['completed_orders'] = merged

                atomic_write_json(
                    session_info_file, session_info, indent=2, ensure_ascii=False
                )

            logger.info(f"Updated session metadata: {packing_list_name} -> {status}")

        except Exception as e:
            logger.warning(f"Could not update session metadata: {e}")
```

Add the import at the top of `src/session_manager.py` if not already present:

```python
from shared.file_lock import locked_file
```

`locked_file` is a `@contextmanager` taking an already-open file handle (verified in
`shared/file_lock.py:26`). It raises `FileLockError` if the lock is not acquired within
5 seconds; the surrounding `except Exception` turns that into a warning, so a contended
lock degrades to "metadata not updated" and never interrupts packing. That is the right
trade here — the packer must keep working — but it means a lost update is still possible
under sustained contention. Acceptable: the analysis signal covers those orders.

**Behaviour change to note in review:** the original only set `started_at` on first write and only set `updated_at` on subsequent writes. The version above always sets `updated_at`, which `load_packed_orders` prefers when dating packed orders. `started_at` is still written once, on creation.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python -m pytest tests/test_session_metadata_orders.py -v
```

Expected: PASS.

- [ ] **Step 5: Confirm the pre-existing three-argument test still passes**

```bash
python -m pytest tests/test_metadata_utils.py -v
```

Expected: PASS, unmodified. It pins that `update_session_metadata` writes a timezone-aware timestamp — `get_current_timestamp()` is still used, so this must stay green.

- [ ] **Step 6: Pass the order numbers at the `'completed'` call site**

In `src/main.py` around `:1767`, change:

```python
                            _sess_mgr.update_session_metadata(
                                _cur_sess_path, _cur_pack_list, 'completed'
                            )
```

to:

```python
                            _sess_mgr.update_session_metadata(
                                _cur_sess_path,
                                _cur_pack_list,
                                'completed',
                                completed_orders=list(
                                    _logic_ref.session_packing_state.get(
                                        'completed_orders', []
                                    )
                                ) if _logic_ref else None,
                            )
```

`_logic_ref` is bound to `self.logic` at `:1679`, in scope here. `packer_logic._load_session_state()` normalises `session_packing_state['completed_orders']` to a list of order-number **strings** in all three of its format branches, so no format handling is needed here.

**Do not touch `:1438` or `:2346`** — both fire with `'in_progress'` before anything is packed.

- [ ] **Step 7: Run the full packing-tool suite**

```bash
python -m pytest
```

Expected: all pass. Record the count for the PR body.

- [ ] **Step 8: Update the graph and commit**

```bash
graphify update .
git add src/session_manager.py src/main.py tests/test_session_metadata_orders.py
git commit -F - <<'EOF'
Record packed order numbers for the Shopify tool's repeat detection

update_session_metadata now accepts the order numbers packed in a session
and stores them in the packing_progress block it already writes into the
Shopify tool's session_info.json. That tool reads them back to flag an
order as a repeat when it was actually packed, not merely analyzed.

The parameter is optional: the two 'in_progress' call sites fire before
anything is packed and are unchanged, and the existing three-argument
test keeps passing.

Orders are merged rather than replaced, so resuming a session does not
drop orders packed before the resume.

Also takes the sidecar .lock around the read-modify-write. The Shopify
tool already guards this same file that way; without it the two tools'
updates can interleave and silently drop one side's changes -- which now
costs order numbers, not just a status field.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_011ryEQFDt4aqFcUeFFhkz9c
EOF
```

---

## Self-review notes for the implementer

- **Grep for stragglers after every edit.** The "Files" table above is a best
  effort, not proof of the full surface area. After Task 3, run
  `grep -rn "history_df" shopify_tool/` and confirm every call site got the
  frame it should have.
- **Run the full suite after every task, not just the task's own tests.** A
  pre-existing test can encode an assumption a change deliberately breaks;
  that has happened on this repo before.
- **Do not "fix" `_detect_repeated_orders`.** Its docstring contains a
  visible "Wait, correction based on user requirement:" mid-sentence and some
  confusing worked examples. It is ugly and it is out of scope — the function's
  behaviour is pinned by `TestRepeatDetection` and must not change in this plan.
