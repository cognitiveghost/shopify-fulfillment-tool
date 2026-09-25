# Phase 14 Bundle 3: repeat detection and history — Implementation Plan

> **For agentic workers:** execute in-session with superpowers:executing-plans
> (the runner forbids subagents at Stage B). Steps use checkbox (`- [ ]`) syntax.

**Goal:** make the Repeat flag trustworthy. It compares sessions rather than
dates, history follows each session's saved state, the history file can't be
lost or clobbered, memory mode saves and never draws twice, and the mark
reaches the packing list, the results document and the Packer.

**Architecture:** a new deep module, `shopify_tool/fulfillment_history.py`,
owns the history file: path, load, lock, per-session replace and atomic write.
Detection (`analysis._detect_repeated_orders`) gets a per-row rule keyed on
`Session`/`Source`, fed by `packed_orders.load_session_signals`, which also
returns the live sessions. The run and `MainWindow.save_session_state` both
call `record_session`.

**Tech Stack:** Python 3, pandas, PySide6, pytest. packing-tool for the Packer chip.

**Spec:** `docs/superpowers/specs/2026-09-25-phase14-bundle3-repeat-history-design.md`
(read it in full first) and `docs/adr/0012-fulfillment-history-follows-the-session.md`.

## Global Constraints

- Work in worktree `.claude/worktrees/phase14-bundle3-repeat-history`, branch `phase14-bundle3-repeat-history`.
- Tests: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -p no:randomly -q`. Lint: `.venv/bin/ruff check .`.
- Branch from and compare against `origin/main`, never local `main`, which is stale.
- One plain `/usr/bin/git` command per Bash call. No `cd && git`, no heredocs in git calls. Commit with `git commit -F <file>`, with the message file under `$CLAUDE_JOB_DIR/tmp`.
- Never hand-edit `shared/`. This bundle needs no `shared/` change.
- Test mode means `orders_file_path is None`, and only that.
- History columns, exactly: `Order_Number, Execution_Date, Session`. The lock sidecar is `fulfillment_history.csv.lock`, with a 2.0 s timeout.
- Toast text, verbatim: `Fulfillment history couldn't be read, so this run didn't check or record repeats. Fix or restore fulfillment_history.csv in the client folder. Details are in Logs.`
- The packing-list cell text is `Repeat` (capital R, the rest lower case), and the column header is `Repeat`.
- Repeat test, the same everywhere: the note contains `"Repeat"` and doesn't start with `"Cannot fulfill"`.
- Every AUDIT-02 `xfail` marker in `tests/audit/test_02_repeat_orders.py` is removed by the end, and each test passes.
- Themes: no hardcoded colours. The Packer chip uses the existing `.chip--warning`.

## Review Focus

1. **The history file is mid-write, or locked by another PC, during an edit.** The edit must still save the session state. The history write logs a message and returns False, and the next edit heals it. This is pinned in Task 2 (`test_lock_timeout_returns_false_and_writes_nothing`) and Task 5 (`test_save_session_state_survives_history_failure`).
2. **The session index can't be read (network blip).** Sessioned history rows must still count. A failed index read must never hide every repeat. This is pinned in Task 3 (`test_live_sessions_none_filters_nothing`, `test_unreadable_index_returns_none_live_set`).
3. **A client with plain-digit order numbers, where history was written as numbers by the old build.** It must still match. This is pinned in Task 2 (`test_load_reads_order_numbers_as_text`) and Task 3 (`test_numeric_and_text_order_numbers_match`).
4. **An old history file with no `Session` column and blank or garbage dates.** It must load, and those rows must count as legacy. An unparseable date counts, and today doesn't. This is pinned in Task 2 (`test_legacy_file_without_session_loads`) and Task 3 (`test_legacy_row_with_garbage_date_counts`).
5. **Memory mode: editing an older session after a newer session has run.** It must not overwrite memory. This is pinned in Task 6 (`test_save_skips_memory_owned_by_another_session`).

---

### Task 1: Memory sums a SKU's rows (AUDIT-02-10)

**Files:**
- Modify: `shopify_tool/core.py` (`build_inventory_snapshot` ~l.938, `inventory_total_units` ~l.973)
- Test: `tests/audit/test_02_repeat_orders.py` (remove the xfail on `test_memory_seed_sums_a_sku_listed_on_several_rows`)

**Interfaces:** Produces `build_inventory_snapshot(final_df, stock_df) -> dict[str, float]` (sums the seed) and `inventory_total_units(stock_df) -> float` (sums). Task 6 relies on the first.

- [ ] **Step 1:** Remove the `@pytest.mark.xfail(...)` above `test_memory_seed_sums_a_sku_listed_on_several_rows`. Run it and expect FAIL (`{'A': 4.0, ...}`).
- [ ] **Step 2:** In `build_inventory_snapshot`, replace the seed block with:

```python
    if stock_df is not None and {"SKU", "Stock"} <= set(stock_df.columns):
        # A SKU on several rows (lots, locations) is their sum (Audit 01 §6).
        stock = pd.to_numeric(stock_df["Stock"], errors="coerce")
        snapshot = (
            stock.groupby(stock_df["SKU"]).sum(min_count=1)
            .dropna()
            .apply(lambda x: max(0.0, float(x)))
            .to_dict()
        )
```

  Leave the `Final_Stock` overlay on `.last()`. Final_Stock is already the SKU total. Update the docstring to match.
- [ ] **Step 3:** In `inventory_total_units`, replace the body after the guard with:

```python
    stock = pd.to_numeric(stock_df["Stock"], errors="coerce")
    per_sku = stock.groupby(stock_df["SKU"]).sum(min_count=1).dropna()
    return float(per_sku.clip(lower=0).sum())
```

  Rewrite its docstring: the snapshot and the loaded file both sum rows per SKU, and that's why they compare.
- [ ] **Step 4:** Run `tests/audit/test_02_repeat_orders.py::test_memory_seed_sums_a_sku_listed_on_several_rows tests/test_core.py tests/test_file_handler*.py -q`. Expect PASS. If a `test_core` test asserts the old `.last()` value, update it to the sum and say why in the commit.
- [ ] **Step 5:** Commit with the message `fix(memory): sum a SKU listed on several stock rows (AUDIT-02-10)`.

---

### Task 2: `fulfillment_history` module (AUDIT-02-6, -7 foundations)

**Files:**
- Create: `shopify_tool/fulfillment_history.py`
- Test: `tests/test_fulfillment_history.py`

**Interfaces (Produces):**
- `COLUMNS = ["Order_Number", "Execution_Date", "Session"]`
- `history_path(profile_manager, client_id) -> Path`
- `class HistoryUnreadable(Exception)`
- `load(path) -> pd.DataFrame`: all columns str, Session `""` for legacy. Raises `HistoryUnreadable`.
- `record_session(path, session: str | None, df, today: str | None = None) -> bool`
- `merge_earliest(history_df, new_rows) -> pd.DataFrame`: the old `core._merge_fulfillment_history`, moved.

- [ ] **Step 1: Write the failing tests** in `tests/test_fulfillment_history.py`:

```python
import pandas as pd
import pytest

from shopify_tool import fulfillment_history as fh


def frame(statuses):
    """statuses: {order: status}; one SKU line per order."""
    return pd.DataFrame(
        {
            "Order_Number": list(statuses),
            "SKU": ["A"] * len(statuses),
            "Order_Fulfillment_Status": list(statuses.values()),
        }
    )


def rows(path):
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    return sorted(map(tuple, df[fh.COLUMNS].values.tolist()))


def test_missing_file_loads_empty(tmp_path):
    df = fh.load(tmp_path / "h.csv")
    assert df.empty and list(df.columns) == fh.COLUMNS


def test_legacy_file_without_session_loads(tmp_path):
    p = tmp_path / "h.csv"
    p.write_text("Order_Number,Execution_Date\n#1,2026-01-05\n#2,\n", encoding="utf-8")
    df = fh.load(p)
    assert df["Session"].tolist() == ["", ""]
    assert df["Execution_Date"].tolist() == ["2026-01-05", ""]


def test_load_reads_order_numbers_as_text(tmp_path):
    p = tmp_path / "h.csv"
    p.write_text("Order_Number,Execution_Date\n12345,2026-01-05\n", encoding="utf-8")
    assert fh.load(p)["Order_Number"].tolist() == ["12345"]


def test_unreadable_file_raises_and_is_never_written(tmp_path):
    p = tmp_path / "h.csv"
    p.write_text("Order_Number,Execution_Date\n#1,2026-01-05\n#2,2026-01-05,stray\n", encoding="utf-8")
    before = p.read_bytes()
    with pytest.raises(fh.HistoryUnreadable):
        fh.load(p)
    assert fh.record_session(p, "S1", frame({"#9": "Fulfillable"})) is False
    assert p.read_bytes() == before


def test_record_replaces_only_this_sessions_rows(tmp_path):
    p = tmp_path / "h.csv"
    fh.record_session(p, "S0", frame({"#1": "Fulfillable"}), today="2026-01-01")
    fh.record_session(p, "S1", frame({"#1": "Fulfillable", "#2": "Fulfillable"}), today="2026-01-02")
    # A person holds #2 in S1.
    fh.record_session(p, "S1", frame({"#1": "Fulfillable", "#2": "Not Fulfillable"}), today="2026-01-03")
    assert rows(p) == [("#1", "2026-01-01", "S0"), ("#1", "2026-01-02", "S1")]


def test_record_keeps_the_sessions_first_date(tmp_path):
    p = tmp_path / "h.csv"
    fh.record_session(p, "S1", frame({"#1": "Fulfillable"}), today="2026-01-01")
    fh.record_session(p, "S1", frame({"#1": "Fulfillable"}), today="2026-01-05")
    assert rows(p) == [("#1", "2026-01-01", "S1")]


def test_legacy_record_merges_earliest_and_leaves_sessions(tmp_path):
    p = tmp_path / "h.csv"
    p.write_text("Order_Number,Execution_Date\n#1,2026-01-05\n", encoding="utf-8")
    fh.record_session(p, "S1", frame({"#1": "Fulfillable"}), today="2026-02-01")
    fh.record_session(p, None, frame({"#1": "Fulfillable", "#2": "Fulfillable"}), today="2026-02-02")
    assert rows(p) == [("#1", "2026-01-05", ""), ("#1", "2026-02-01", "S1"), ("#2", "2026-02-02", "")]


def test_record_leaves_no_temp_files(tmp_path):
    p = tmp_path / "h.csv"
    fh.record_session(p, "S1", frame({"#1": "Fulfillable"}))
    assert sorted(x.name for x in tmp_path.iterdir()) == ["h.csv", "h.csv.lock"]


def test_lock_timeout_returns_false_and_writes_nothing(tmp_path, monkeypatch):
    from shared.file_lock import FileLockError

    def refuse(*_a, **_k):
        raise FileLockError("held")

    monkeypatch.setattr(fh, "locked_file", refuse)
    p = tmp_path / "h.csv"
    assert fh.record_session(p, "S1", frame({"#1": "Fulfillable"})) is False
    assert not p.exists()
```

- [ ] **Step 2:** Run `.venv/bin/python -m pytest tests/test_fulfillment_history.py -q`. Expect FAIL (module missing).
- [ ] **Step 3: Implement** `shopify_tool/fulfillment_history.py`:

```python
"""Per-client fulfillment history: which orders each session currently ships.

One row per order per session (ADR 0012). A session's rows are replaced
whenever its state is saved, so history follows what the session ships, not
what its run proposed (AUDIT-02-3, -4). Rows written before sessions were
recorded have Session "" and keep the old date rule in detection.

The file is never written over when it can't be read (AUDIT-02-6), and every
write re-reads under a lock sidecar and replaces atomically, so two PCs don't
lose each other's rows (AUDIT-02-7).
"""

import logging
import os
import tempfile
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

from shared.file_lock import FileLockError, locked_file
from shopify_tool import stock_ledger
from shopify_tool.utils import get_persistent_data_path

logger = logging.getLogger(__name__)

COLUMNS = ["Order_Number", "Execution_Date", "Session"]
FILE_NAME = "fulfillment_history.csv"
LOCK_TIMEOUT = 2.0


class HistoryUnreadable(Exception):
    """The history file exists but can't be read; it must not be written over."""


def history_path(profile_manager, client_id) -> Path:
    if profile_manager and client_id:
        return Path(profile_manager.get_client_directory(client_id)) / FILE_NAME
    return Path(get_persistent_data_path(FILE_NAME))


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=COLUMNS)


def load(path) -> pd.DataFrame:
    try:
        df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    except FileNotFoundError:
        return _empty()
    except Exception as e:  # ParserError, UnicodeDecodeError, OSError on the share
        raise HistoryUnreadable(f"{path}: {e}") from e
    if "Order_Number" not in df.columns:
        raise HistoryUnreadable(f"{path}: no Order_Number column")
    df = df.reindex(columns=COLUMNS, fill_value="").fillna("")
    df["Order_Number"] = df["Order_Number"].str.strip()
    return df


def merge_earliest(history_df, new_rows) -> pd.DataFrame:
    """Earliest date per order; NaT sorts last (moved from core, unchanged)."""
    combined = pd.concat([history_df, new_rows])
    key = pd.to_datetime(combined["Execution_Date"], errors="coerce", format="mixed")
    combined = combined.assign(_k=key).sort_values("_k", na_position="last")
    return combined.drop_duplicates(subset=["Order_Number"], keep="first").drop(columns="_k")


def _replace(history, session, ships, today) -> pd.DataFrame:
    if session is None:
        legacy = history["Session"] == ""
        new = pd.DataFrame({"Order_Number": sorted(ships), "Execution_Date": today, "Session": ""})
        return pd.concat([history[~legacy], merge_earliest(history[legacy], new)])
    mine = history["Session"] == session
    first_seen = dict(zip(history.loc[mine, "Order_Number"], history.loc[mine, "Execution_Date"]))
    new = pd.DataFrame(
        {
            "Order_Number": sorted(ships),
            "Execution_Date": [first_seen.get(o) or today for o in sorted(ships)],
            "Session": session,
        }
    )
    return pd.concat([history[~mine], new])


def _write_atomic(path: Path, df: pd.DataFrame) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".fulfillment_history_tmp_", suffix=".csv")
    os.close(fd)
    try:
        df.to_csv(tmp, index=False, columns=COLUMNS)
        # Windows refuses to replace a file another PC has open; that's brief.
        for attempt in range(3):
            try:
                os.replace(tmp, path)
                break
            except PermissionError:
                if attempt == 2:
                    raise
                time.sleep(0.15)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def record_session(path, session, df, today=None) -> bool:
    """Replace `session`'s rows with the orders df ships. False = not written."""
    path = Path(path)
    today = today or datetime.now().astimezone().strftime("%Y-%m-%d")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path.with_name(path.name + ".lock"), "a+") as lock, locked_file(lock, timeout=LOCK_TIMEOUT):
            try:
                history = load(path)
            except HistoryUnreadable:
                logger.warning(f"Fulfillment history unreadable; not writing over it: {path}", exc_info=True)
                return False
            ships = stock_ledger.fulfillable_orders(df)
            _write_atomic(path, _replace(history, session, ships, today))
            return True
    except (FileLockError, OSError):
        logger.exception(f"Could not record fulfillment history for {session!r}")
        return False
```

  If `stock_ledger.fulfillable_orders` needs `Order_Fulfillment_Status` plus SKU lines, it does. The test frames give it both.
- [ ] **Step 4:** Run `tests/test_fulfillment_history.py -q`. Expect PASS. Run `.venv/bin/ruff check shopify_tool/fulfillment_history.py tests/test_fulfillment_history.py`.
- [ ] **Step 5:** Commit with the message `feat(history): per-session fulfillment history module (ADR 0012)`.

---

### Task 3: Detection compares sessions (AUDIT-02-1, -2, -5)

**Files:**
- Modify: `shopify_tool/analysis.py` (`_detect_repeated_orders` ~l.821-922, the call at ~l.1099, `run_analysis` ~l.1390 and its phase-6 call ~l.1544, the docstring ~l.1437)
- Modify: `shopify_tool/packed_orders.py` (rename `load_packed_orders` to `load_session_signals`, and change `union_history_with_packed`)
- Test: `tests/test_analysis.py` (`TestRepeatDetection`), `tests/test_packed_orders.py`

**Interfaces:**
- Produces: `analysis.run_analysis(stock_df, orders_df, history_df, column_mappings=None, courier_mappings=None, current_session=None, mode="multi_first")`
- Produces: `_detect_repeated_orders(final_df, history_df, current_session=None) -> pd.Series`
- Produces: `packed_orders.load_session_signals(profile_manager, client_id) -> tuple[pd.DataFrame, set[str] | None]`. The frame's columns are `[Order_Number, Execution_Date, Session]`.
- Produces: `packed_orders.union_history_with_packed(history_df, packed_df, live_sessions=None) -> pd.DataFrame`. The columns are `[Order_Number, Execution_Date, Session, Source]`.

- [ ] **Step 1: Write the failing tests.** In `tests/test_analysis.py`, replace `repeat_window_days=1` in the three existing tests with no argument (those tests must still pass). Then add these tests, which call the detector directly:

```python
import datetime  # module level; the file's existing tests import it locally

from shopify_tool.analysis import _detect_repeated_orders

TODAY = datetime.datetime.now().astimezone().strftime("%Y-%m-%d")
YESTERDAY = (datetime.datetime.now().astimezone() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")


def _flags(orders, rows, current=None):
    final = pd.DataFrame({"Order_Number": orders})
    hist = pd.DataFrame(rows, columns=["Order_Number", "Execution_Date", "Session", "Source"])
    return list(_detect_repeated_orders(final, hist, current_session=current) == "Repeat")


class TestRepeatRule:
    def test_history_from_another_session_today_counts(self):
        assert _flags(["#1"], [("#1", TODAY, "S0", "history")], current="S1") == [True]

    def test_history_from_this_session_never_counts(self):
        assert _flags(["#1"], [("#1", "2026-01-01", "S1", "history")], current="S1") == [False]

    def test_legacy_history_counts_before_today_only(self):
        assert _flags(["#1", "#2"], [("#1", YESTERDAY, "", "history"), ("#2", TODAY, "", "history")]) == [True, False]

    def test_legacy_row_with_garbage_date_counts(self):
        assert _flags(["#1"], [("#1", "garbage", "", "history")]) == [True]

    def test_packed_in_this_session_counts(self):
        assert _flags(["#1"], [("#1", TODAY, "S1", "packed")], current="S1") == [True]

    def test_numeric_and_text_order_numbers_match(self):
        final = pd.DataFrame({"Order_Number": [12345]})
        hist = pd.DataFrame({"Order_Number": ["12345 "], "Execution_Date": [YESTERDAY],
                             "Session": ["S0"], "Source": ["packed"]})
        assert list(_detect_repeated_orders(final, hist) == "Repeat") == [True]

    def test_plain_two_column_history_is_legacy(self):
        final = pd.DataFrame({"Order_Number": ["#1"]})
        hist = pd.DataFrame({"Order_Number": ["#1"], "Execution_Date": [YESTERDAY]})
        assert list(_detect_repeated_orders(final, hist) == "Repeat") == [True]
```

  In `tests/test_packed_orders.py`, rename every `load_packed_orders` to `load_session_signals` and unpack `(df, live)`. Add:

```python
def test_rows_carry_session_and_live_set_excludes_abandoned(...):
    # entries: S1 active with completed_orders ["#1"], S2 abandoned with ["#2"]
    df, live = load_session_signals(pm, "C")
    assert set(zip(df.Order_Number, df.Session)) == {("#1", "S1"), ("#2", "S2")}
    assert live == {"S1"}

def test_unreadable_index_returns_none_live_set(...):
    # list_client_sessions raises
    df, live = load_session_signals(pm, "C")
    assert df.empty and live is None

def test_union_drops_rows_of_dead_sessions():
    hist = pd.DataFrame({"Order_Number": ["#1", "#2", "#3"], "Execution_Date": ["2026-01-01"] * 3,
                         "Session": ["S1", "GONE", ""]})
    out = union_history_with_packed(hist, _empty_packed(), live_sessions={"S1"})
    assert set(out.Order_Number) == {"#1", "#3"} and set(out.Source) == {"history"}

def test_live_sessions_none_filters_nothing():
    hist = pd.DataFrame({"Order_Number": ["#1"], "Execution_Date": ["2026-01-01"], "Session": ["GONE"]})
    assert list(union_history_with_packed(hist, _empty_packed(), None).Order_Number) == ["#1"]
```

  Build the `pm`/entries fakes with the same helpers the file already uses for `list_client_sessions`. Each entry needs `session_name` and `status`.
- [ ] **Step 2:** Run both files. Expect FAIL (`current_session` unknown, `load_session_signals` missing).
- [ ] **Step 3: Implement detection.** Replace the body of `_detect_repeated_orders` after the logging line with:

```python
    if history_df is None or history_df.empty:
        return pd.Series("", index=final_df.index)
    h = history_df.copy()
    keys = h["Order_Number"].astype(str).str.strip()
    session = h["Session"].fillna("").astype(str) if "Session" in h.columns else pd.Series("", index=h.index)
    source = h["Source"] if "Source" in h.columns else pd.Series("history", index=h.index)
    if "Execution_Date" in h.columns:
        # Deliberately naive: pd.to_datetime yields tz-naive dates.
        today = pd.Timestamp(datetime.now().date())  # noqa: DTZ005
        dates = pd.to_datetime(h["Execution_Date"], errors="coerce", format="mixed").dt.normalize()
        before_today = dates.isna() | (dates < today)
    else:
        before_today = pd.Series(True, index=h.index)
    counts = (
        (source == "packed")
        | ((session != "") & (session != (current_session or "")))
        | ((session == "") & before_today)
    )
    repeated_orders = set(keys[counts])
    repeated = np.where(final_df["Order_Number"].astype(str).str.strip().isin(repeated_orders), "Repeat", "")
```

  Add `from datetime import datetime` at the top of `analysis.py` if it's not there (the old code imported it inside the function). Keep the final `logger.debug` and `return pd.Series(repeated, index=final_df.index)`. Delete the old window and cutoff code. Rewrite the docstring as the rule table from spec §2. Rename the parameter through `run_analysis` (signature, docstring and the phase-6 call) and at the ~l.1099 call site. `grep -n repeat_window_days shopify_tool` must return nothing.
- [ ] **Step 4: Implement signals.** In `packed_orders.py`, set `COLUMNS = ["Order_Number", "Execution_Date", "Session"]`. Rename `load_packed_orders` to `load_session_signals`, returning `(_empty(), None)` on the no-pm or exception paths. In `_load...`, after `entries = ...`:

```python
    live = {
        _session_name(e) for e in entries
        if isinstance(e, dict) and e.get("status") != "abandoned" and _session_name(e)
    }
```

  Add `Session: _session_name(entry)` to each row, and dedupe on `["Order_Number", "Session"]`. Return `(df, live)`. Add a helper:

```python
def _session_name(entry) -> str:
    name = entry.get("session_name") or Path(str(entry.get("session_path") or "")).name
    return str(name or "")
```

  In `union_history_with_packed(history_df, packed_df, live_sessions=None)`:
  - keep the legacy early return;
  - tag each frame with `Source` ("history" or "packed") and reindex to `COLUMNS + ["Source"]`, filling `Session` with `""`;
  - concat;
  - when `live_sessions is not None`, drop rows where `Session != ""` and `Session` isn't in `live_sessions`;
  - dedupe on `["Order_Number", "Session", "Source"]`, keeping the earliest by parsed date.

  Update the module and function docstrings: detection only, and the None-live rule.
- [ ] **Step 5:** Run `tests/test_analysis.py tests/test_packed_orders.py -q`. Expect PASS. core.py is broken until Task 4, so don't run the whole suite yet.
- [ ] **Step 6:** Commit with the message `feat(detection): compare sessions, not dates; live sessions only (AUDIT-02-1, -2, -5)`.

---

### Task 4: Core wiring: test mode, history load/write, current session, warning (AUDIT-02-1, -2, -5, -6, -7, -9 read and write)

**Files:**
- Modify: `shopify_tool/core.py`: imports (l.15), `_validate_and_prepare_inputs` (~l.478 copy block), `_load_history_data` (~l.710), `_run_analysis_and_rules` (~l.853), delete `_merge_fulfillment_history` (~l.909), `_save_results_and_reports` (~l.1071 and the history block ~l.1206-1245), `run_full_analysis` (~l.1360-1420)
- Modify: `tests/test_core.py`: point the `_merge_fulfillment_history` tests at `fulfillment_history.merge_earliest`, and patch `core.load_session_signals` returning `(df_or_empty, None)`. Where a test returned `None` for packed, return `(pd.DataFrame(columns=["Order_Number","Execution_Date","Session"]), None)`.
- Modify: `tests/audit/test_02_repeat_orders.py` (harness, and the -1, -2, -5, -6, -7, -9 markers)

**Interfaces:**
- Consumes: Task 2 (`fulfillment_history.*`), Task 3 (`load_session_signals`, `union_history_with_packed`, `run_analysis(current_session=)`).
- Produces: `stats["history_warning"]: str` (present only on a problem). `run_full_analysis` computes `current_session = Path(session_path).name if session_path else None` after step 1. Task 6 relies on a `session_path` local being in scope there.

- [ ] **Step 1: Harness.** In the audit test file:
  - add `from shopify_tool import fulfillment_history`;
  - in `Shop.__init__`, patch `fulfillment_history.get_persistent_data_path` (not core's) and `core.load_session_signals` → `lambda _pm, _cid: (self.packed, None)`;
  - change `packed(*orders, day=YESTERDAY, session="2026-01-01_1")` to add a `"Session"` column;
  - make `write_history` accept 2- or 3-tuples, writing `Session` `""` for 2-tuples;
  - make `history_rows()` return the earliest date per order across all rows:

```python
    def history_rows(self):
        h = pd.read_csv(self.history, dtype=str, keep_default_na=False).sort_values("Execution_Date")
        return dict(h.drop_duplicates("Order_Number")[["Order_Number", "Execution_Date"]].values.tolist())
```

  Remove the xfail markers on AUDIT-02-1, -2, -5, -6, -7 and both -9 tests. In `MemoryProfile.save_inventory_memory`, add `session=None`.
- [ ] **Step 2:** Run the audit file. Expect those 7 to FAIL, or error in core.
- [ ] **Step 3: Implement in core.**
  - Import: `from . import fulfillment_history` and `from .packed_orders import load_session_signals, union_history_with_packed`. Drop the `get_persistent_data_path` import if nothing else uses it (`grep`).
  - `_validate_and_prepare_inputs`: change `if use_session_mode and stock_file_path and orders_file_path:` to `if use_session_mode and orders_file_path:`. Copy stock only `if stock_file_path:`. Pass `{"orders_file": "orders_export.csv", "stock_file": "inventory.csv" if stock_file_path else None}`. Fix the docstrings ("None in memory mode").
  - `_load_history_data(orders_file_path, client_id, profile_manager, config) -> tuple[pd.DataFrame, bool]`: returns `(df, readable)`. Drop the `stock_file_path` parameter and update the caller.

```python
    if orders_file_path is None:  # test mode
        return config.get("test_history_df", pd.DataFrame({"Order_Number": []})), True
    path = fulfillment_history.history_path(profile_manager, client_id)
    try:
        df = fulfillment_history.load(path)
    except fulfillment_history.HistoryUnreadable:
        logger.warning("Fulfillment history unreadable; repeats not checked this run", exc_info=True)
        return pd.DataFrame(columns=fulfillment_history.COLUMNS), False
    logger.info(f"Loaded {len(df)} history rows from {path}")
    return df, True
```

  (History has no SKU column, so drop the SKU-normalisation branch.)
  - `_run_analysis_and_rules(orders_df, stock_df, history_df, config, current_session=None)`: delete the `repeat_window_days` read. Pass `current_session=current_session` to `analysis.run_analysis`.
  - Delete `_merge_fulfillment_history` (moved to `fulfillment_history.merge_earliest`).
  - `_save_results_and_reports`: add keyword parameters `current_session=None` and `history_readable=True`. Keep `stock_file_path`, which Task 6 reads to know whether the run had a stock file. The early return becomes `if orders_file_path is None:`. Replace the whole "Update fulfillment history" block with:

```python
    if history_readable:
        path = fulfillment_history.history_path(profile_manager, client_id)
        if not fulfillment_history.record_session(path, current_session, final_df):
            stats["history_warning"] = HISTORY_WARNING
    else:
        stats["history_warning"] = HISTORY_WARNING
```

  with a module constant holding the verbatim toast text from Global Constraints:

```python
HISTORY_WARNING = (
    "Fulfillment history couldn't be read, so this run didn't check or record repeats. "
    "Fix or restore fulfillment_history.csv in the client folder. Details are in Logs."
)
```

  This block must run **before** `analysis_stats.json` is written, so the file carries the warning. Move it above the "Save initial state files" block.
  - `run_full_analysis`: after step 1, `current_session = Path(session_path).name if session_path else None`. Then:

```python
        history_df, history_readable = _load_history_data(orders_file_path, client_id, profile_manager, config)
        packed_df, live_sessions = load_session_signals(profile_manager, client_id)
        detection_history_df = union_history_with_packed(history_df, packed_df, live_sessions)
```

  Pass `current_session` to `_run_analysis_and_rules`, and `current_session` and `history_readable` to `_save_results_and_reports`.
- [ ] **Step 4:** Run `tests/audit/test_02_repeat_orders.py tests/test_core.py tests/test_analysis.py tests/test_packed_orders.py -q`. The 7 unmarked audit tests must PASS, and the "verified correct" block must stay green, especially `test_rerunning_the_same_export_today_does_not_flag_its_own_orders` and `test_rerun_keeps_the_earliest_history_date`. `test_memory_mode_run_writes_memory_and_history` needs Task 6's memory write only if it fails on `pm.memory`. The run-end memory save already exists, so it should pass here. If it doesn't, leave its marker off, note it, and finish in Task 6.
- [ ] **Step 5:** Add a core test to `tests/test_core.py` that pins the warning:

```python
def test_unreadable_history_warns_and_is_left_alone(tmp_path, monkeypatch):
    from shopify_tool import fulfillment_history
    hist = tmp_path / "fulfillment_history.csv"
    hist.write_text("Order_Number,Execution_Date\n#1,2026-01-05,stray\n", encoding="utf-8")
    monkeypatch.setattr(fulfillment_history, "get_persistent_data_path", lambda _n: hist)
    monkeypatch.setattr(core, "load_session_signals", lambda *_: (pd.DataFrame(columns=["Order_Number", "Execution_Date", "Session"]), None))
    # build orders/stock CSVs the way the file's other run_full_analysis tests do
    ok, _msg, _df, stats = core.run_full_analysis(...)
    assert ok and stats["history_warning"] == core.HISTORY_WARNING
    assert "stray" in hist.read_text(encoding="utf-8")
```

- [ ] **Step 6:** Run the full suite. Expect everything green except tests owned by Tasks 5-8 (`test_settings_page_general`, if it asserts the key, is Task 5). Run `ruff check .`.
- [ ] **Step 7:** Commit with the message `fix(core): session-aware history load/write, explicit test mode (AUDIT-02-1,-2,-5,-6,-7,-9)`.

---

### Task 5: GUI: history follows every save, toast, window setting removed (AUDIT-02-3, -4, -2)

**Files:**
- Modify: `gui/main_window_pyside.py` `save_session_state` (~l.702-765)
- Modify: `gui/actions_handler.py` `on_analysis_complete` (~l.197-230)
- Modify: `gui/settings/general.py` (delete the repeat row ~l.75-88 and the `collect()` key ~l.99)
- Test: `tests/audit/test_02_repeat_orders.py` (AUDIT-02-3, -4), `tests/test_settings_page_general.py`, a new `tests/test_save_session_history.py`

**Interfaces:** Consumes `fulfillment_history.history_path`, `record_session` (Task 2) and `stats["history_warning"]` (Task 4).

- [ ] **Step 1: Proof tests.** Remove the xfail markers on `test_order_marked_fulfillable_by_a_person_is_flagged_next_day` and `test_order_held_after_analysis_is_not_a_repeat_next_day`, and edit them as follows. Run 1 passes `session_path=str(shop.dir / "2026-09-25_1")`. At the "call the real writer" comment (and at the same point in -4, after the toggle), add `fulfillment_history.record_session(shop.history, "2026-09-25_1", mw.analysis_results_df)`. Delete `shop.age_history()`. Run 2 passes `session_path=str(shop.dir / "2026-09-25_2")`. Run both and expect FAIL only if the rule is wrong. They may already pass on Tasks 2-4. That's fine: they pin the writer this task wires in.
- [ ] **Step 2: Save-path test**, `tests/test_save_session_history.py`:

```python
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd

from gui.main_window_pyside import MainWindow
from shopify_tool import fulfillment_history


def _mw(tmp_path, df):
    session = tmp_path / "CLIENT_X" / "2026-09-25_1"
    (session / "analysis").mkdir(parents=True)
    return SimpleNamespace(
        session_path=str(session), analysis_results_df=df, analysis_stats=None,
        _state_stamp=None, session_manager=None, current_client_id="X",
        profile_manager=SimpleNamespace(get_client_directory=lambda _c: tmp_path),
        active_profile_config={"inventory_memory": {"enabled": False}},
    )


def _df(status):
    return pd.DataFrame({"Order_Number": ["#1"], "SKU": ["A"], "Stock": [5], "Final_Stock": [4],
                         "Quantity": [1], "Order_Fulfillment_Status": [status]})


def test_save_session_state_records_this_sessions_orders(tmp_path):
    mw = _mw(tmp_path, _df("Fulfillable"))
    MainWindow.save_session_state(mw)
    h = fulfillment_history.load(tmp_path / "fulfillment_history.csv")
    assert h[["Order_Number", "Session"]].values.tolist() == [["#1", "2026-09-25_1"]]


def test_save_session_state_survives_history_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(fulfillment_history, "record_session", Mock(side_effect=RuntimeError("share")))
    mw = _mw(tmp_path, _df("Fulfillable"))
    MainWindow.save_session_state(mw)
    assert (Path(mw.session_path) / "analysis" / "current_state.pkl").exists()
```

  If `save_session_state` calls `show_error(self, ...)` on paths these tests don't hit, a `SimpleNamespace` is enough. If `MainWindow.save_session_state` touches other attributes, add them to `_mw`, not to production code.
- [ ] **Step 3:** Run it and expect FAIL (no history file).
- [ ] **Step 4: Implement.** In `save_session_state`, right after the successful `save_state` block and before the "backups" comment:

```python
        # History follows the saved state, not the run (ADR 0012). A failure
        # heals on the next save, which rewrites this session's rows whole.
        # ponytail: history write on the GUI thread; move to the threadpool with a
        # per-session coalescing queue if saves feel slow on the share
        try:
            fulfillment_history.record_session(
                fulfillment_history.history_path(self.profile_manager, self.current_client_id),
                Path(self.session_path).name,
                self.analysis_results_df,
            )
        except Exception:
            logger.exception("Failed to record fulfillment history")
```

  (Import `fulfillment_history` at module top: `from shopify_tool import fulfillment_history`.)
  In `on_analysis_complete`, after `self.data_changed.emit()`:

```python
            if stats and stats.get("history_warning"):
                self._results_toast(stats["history_warning"])
```

  In `gui/settings/general.py`, delete the `repeat_days_input` widget, its `section.add_row(...)`, and `"repeat_detection_days": ...` in `collect()`. Update `tests/test_settings_page_general.py`: drop the key from expected `collect()` output, and assert a saved `repeat_detection_days: 30` survives `collect()` untouched (the page updates `self._settings`, so a key it doesn't own is kept). Leave `tests/conftest.py:167` alone, since an unread config key is harmless.
- [ ] **Step 5:** Run `tests/test_save_session_history.py tests/audit/test_02_repeat_orders.py tests/test_settings_page_general.py -q`, then the full suite. Expect PASS.
- [ ] **Step 6:** Commit with the message `feat(gui): history follows every session save; warn on unreadable history; drop repeat window (AUDIT-02-3,-4,-2)`.

---

### Task 6: Memory baseline and memory following the session (AUDIT-02-9 follow-ons)

**Files:**
- Modify: `shopify_tool/core.py`: `_load_and_validate_files` (memory fallback ~l.680), `_save_results_and_reports` memory block (~l.1250), `run_full_analysis` (pass `session_path`)
- Modify: `shopify_tool/profile_manager.py` `save_inventory_memory` (~l.677)
- Modify: `gui/main_window_pyside.py` `save_session_state`
- Test: `tests/test_memory_baseline.py` (new), and `tests/test_save_session_history.py` (add the memory test)

**Interfaces:**
- Produces: `core.BASELINE_FILE = "memory_baseline.json"`, `core.read_memory_baseline(session_path) -> dict | None`, `core.baseline_stock_df(baseline: dict) -> pd.DataFrame` (columns `SKU, Product_Name, Stock`)
- Produces: `ProfileManager.save_inventory_memory(client_id, stock_dict, config=None, names_dict=None, session=None) -> bool`, which stores `inventory_memory["session"]`.

- [ ] **Step 1: Failing tests**, `tests/test_memory_baseline.py`. They use the audit file's `MemoryProfile` shape, copied in: a fake with `get_inventory_memory`, `load_shopify_config`, `load_client_config`, `get_client_directory` and `save_inventory_memory(..., session=None)`.

```python
def test_memory_mode_rerun_of_same_session_draws_once(tmp_path, monkeypatch):
    # memory A=10; orders #1 needs 2; session_path = tmp_path/"S1" (legacy mode, no session manager)
    run(...)            # memory -> A=8, baseline S1 = {A: 10}
    run(...)            # same session again
    assert pm.memory["skus"] == {"A": 8.0}
    assert pm.memory["session"] == "S1"


def test_stock_file_run_writes_summed_baseline(tmp_path, monkeypatch):
    # memory enabled, stock file lists A twice (3 + 4)
    run(..., stock_rows=[("A", 3), ("A", 4)])
    assert core.read_memory_baseline(tmp_path / "S1")["skus"] == {"A": 7.0}
```

  Run analyses the way `tests/audit/test_02_repeat_orders.py::Shop.run` does (write CSVs, call `core.run_full_analysis(..., client_id="C", profile_manager=pm, session_path=str(tmp_path/"S1"))`), and patch `core.load_session_signals` and `fulfillment_history.get_persistent_data_path` the same way.
  In `tests/test_save_session_history.py`, add:

```python
def test_save_rewrites_memory_owned_by_this_session(tmp_path): ...
    # baseline {A: 5}, memory session == "2026-09-25_1", df Final_Stock 4 -> after a toggle to Not Fulfillable
    # and with_stock_left, Final_Stock 5 -> memory A == 5.0

def test_save_skips_memory_owned_by_another_session(tmp_path): ...
    # memory session == "2026-09-25_2" -> save_inventory_memory not called
```

  In both, `active_profile_config={"inventory_memory": {"enabled": True}}`, and `profile_manager` is a fake with `get_inventory_memory`, `save_inventory_memory` (a Mock that records the call) and `get_client_directory`. Write the baseline file with `atomic_write_json(session/"analysis"/"memory_baseline.json", {"skus": {"A": 5}, "names": {}})`.
- [ ] **Step 2:** Run the tests and expect FAIL.
- [ ] **Step 3: Implement in core.**

```python
BASELINE_FILE = "memory_baseline.json"


def _baseline_path(session_path) -> Path:
    return Path(session_path) / "analysis" / BASELINE_FILE


def read_memory_baseline(session_path) -> dict | None:
    if not session_path:
        return None
    try:
        with open(_baseline_path(session_path), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data.get("skus"), dict) else None
    except (OSError, ValueError, AttributeError):
        return None


def baseline_stock_df(baseline: dict) -> pd.DataFrame:
    names = baseline.get("names") or {}
    return pd.DataFrame(
        [{"SKU": s, "Product_Name": names.get(s), "Stock": q} for s, q in baseline["skus"].items()],
        columns=["SKU", "Product_Name", "Stock"],
    )


def write_memory_baseline(session_path, skus: dict, names: dict | None) -> None:
    if session_path:
        atomic_write_json(_baseline_path(session_path), {"skus": skus, "names": names or {}})
```

  (`from shared.atomic_write import atomic_write_json` at the top of core.)
  - `_load_and_validate_files(..., config, session_path=None)`: in the memory fallback, `baseline = read_memory_baseline(session_path)`. If it's set, `stock_df = baseline_stock_df(baseline)`. Otherwise build from `inv_mem` as today, then `write_memory_baseline(session_path, skus, names)`. Keep `config["_stock_from_memory"] = True`.
  - The stock-file path: in `_save_results_and_reports`'s memory block (memory enabled), before saving memory, write `write_memory_baseline(session_path, build_inventory_snapshot(None, stock_df), names_dict)`, **only when `stock_file_path` is not None**. Add a `session_path=None` keyword parameter; don't use `working_path`, which is the output directory in legacy mode. `build_inventory_snapshot(None, stock_df)` gives the summed opening stock (Task 1).
  - Pass `session=current_session` to `profile_manager.save_inventory_memory(...)`. `run_full_analysis` passes `session_path` into `_load_and_validate_files` and `_save_results_and_reports`.
  - `ProfileManager.save_inventory_memory`: add `session: str | None = None`, and store `config["inventory_memory"]["session"] = session` next to the SKUs.
- [ ] **Step 4: Implement in the GUI.** In `save_session_state`, after the history block:

```python
        inv = (self.active_profile_config or {}).get("inventory_memory") or {}
        if inv.get("enabled"):
            try:
                follow_inventory_memory(self)
            except Exception:
                logger.exception("Failed to update inventory memory from the session")
```

  and a **module-level** function in `gui/main_window_pyside.py`. It's not a method, because the save-path tests call `MainWindow.save_session_state` on a `SimpleNamespace`, where `self._x()` wouldn't exist:

```python
def follow_inventory_memory(mw):
    """Memory follows this session's state only while this session owns it."""
    this = Path(mw.session_path).name
    memory = mw.profile_manager.get_inventory_memory(mw.current_client_id) or {}
    if memory.get("session") != this:
        logger.info(f"Inventory memory belongs to {memory.get('session')!r}; not rewriting it from {this}")
        return
    baseline = core.read_memory_baseline(mw.session_path)
    if baseline is None:
        return
    snapshot = core.build_inventory_snapshot(mw.analysis_results_df, core.baseline_stock_df(baseline))
    mw.profile_manager.save_inventory_memory(
        mw.current_client_id, snapshot, names_dict=baseline.get("names") or None, session=this
    )
```

  (Check how `main_window_pyside` imports core. Use the existing import, or add `from shopify_tool import core`.)
- [ ] **Step 5:** Run `tests/test_memory_baseline.py tests/test_save_session_history.py tests/audit/test_02_repeat_orders.py tests/test_core.py -q`, then the full suite. Expect PASS. Both AUDIT-02-9 tests must be unmarked and green.
- [ ] **Step 6:** Commit with the message `feat(memory): session baseline, no double draw on re-run, memory follows its session (AUDIT-02-9)`.

---

### Task 7: The Repeat mark on the packing list and in the results document (AUDIT-02-8, shopify side)

**Files:**
- Modify: `shopify_tool/packing_lists.py` (~l.160-215 layout, ~l.290 centred list, ~l.305 widths)
- Modify: `gui/web/columns.js:35`
- Modify: `gui/settings/report_editor.py` (~l.128 `offered`)
- Test: `tests/audit/test_02_repeat_orders.py::test_packing_list_marks_a_repeat_order`, `tests/test_packing_lists.py` (or the existing packing-list test file, found with `grep -l create_packing_list tests`)

- [ ] **Step 1:** Remove the xfail on `test_packing_list_marks_a_repeat_order`. Add to the packing-list tests:

```python
def test_repeat_column_in_lot_layout_marks_first_row_only(tmp_path):
    # two lines of #1 (System_note "Repeat"), Lot_Details present; #2 no note
    create_packing_list(df, str(out))
    sheet = pd.read_excel(out, dtype=str).fillna("")
    cols = list(sheet.columns)
    assert cols.index("Repeat") == cols.index("Order_Number") + 1
    assert sheet["Repeat"].tolist() == ["Repeat", "", ""]


def test_blocked_reason_note_is_not_a_repeat(tmp_path):
    # System_note "Cannot fulfill: Repeat SKU short" -> Repeat column empty
```

  Write the lot-layout fixture the way the file's existing lot tests do. Only `Warehouse_Name` and `Shipping_Provider` headers are renamed in the sheet, so `Order_Number` and `Repeat` keep their names.
- [ ] **Step 2:** Run them and expect FAIL.
- [ ] **Step 3: Implement.** In `create_packing_list`, just before `print_list = sorted_list[columns_for_print]` (after both branches, so lot rows are already expanded):

```python
        note = sorted_list.get("System_note", pd.Series("", index=sorted_list.index)).fillna("").astype(str)
        is_rep = note.str.contains("Repeat", regex=False) & ~note.str.startswith("Cannot fulfill")
        order_rep = is_rep.groupby(sorted_list["Order_Number"]).transform("any")
        first = ~sorted_list["Order_Number"].duplicated()
        sorted_list["Repeat"] = np.where(order_rep & first, "Repeat", "")
```

  Insert `"Repeat"` after `"Order_Number"` in both the lot `columns_for_print` and `default_columns`. The custom path keeps `[c for c in columns if c in sorted_list.columns]`, so a custom list naming `"Repeat"` gets it. Add `"Repeat"` to the centred list, and in the width loop add `elif original_col_name == "Repeat": max_len = 8`. Import numpy if the module lacks it.
  In `columns.js`, change the repeat entry to `{ key: "repeat", ..., width: 64, shown: true, text: ... }`.
  In `report_editor.py`, after `offered = report_filter_fields(analysis_df)`, add the line `if "Repeat" not in offered: offered.append("Repeat")`. This applies only in the packing-list column picker branch, so check that this block is the packing-list one. If the block is shared with stock exports, guard it on the report kind the editor already knows.
- [ ] **Step 4:** Run the packing-list tests, the audit file and any `tests/web`/JS column test (`grep -rl '"repeat"' tests`). Expect PASS. Then run the full suite.
- [ ] **Step 5:** Commit with the message `feat(packing-list): Repeat column in both layouts; Repeat shown by default (AUDIT-02-8)`.

---

### Task 8: Packer Repeat chip (packing-tool, AUDIT-02-8)

**Files (packing-tool repo):**
- Worktree (created at Stage A, `.venv` linked): `/home/gloopy/Desktop/Projects/packing-tool/.claude/worktrees/worktree-phase14-bundle3-repeat-chip`, branch `phase14-bundle3-repeat-chip`. Drive git with `git -C <that path>`, one command per call. Read packing-tool's CLAUDE.md for its test command.
- Modify: `gui/packer_bridge.py` `banner()` (~l.129-147)
- Modify: `gui/web/packer.js` `renderBanner()` (~l.112-121)
- Test: packing-tool's `tests/test_packer_bridge*.py` (`grep -l "def test.*banner\|banner(" tests`)

- [ ] **Step 1: Failing tests:**

```python
def test_banner_repeat_with_customer_note():
    b = banner("#1", {"notes": "Leave at door", "system_note": "Repeat"})
    assert b["repeat"] is True and b["notes"] == "Leave at door"

def test_banner_repeat_only_has_no_notes():
    b = banner("#1", {"system_note": "Repeat"})
    assert b["repeat"] is True and b["notes"] == ""

def test_banner_blocker_note_is_not_repeat():
    b = banner("#1", {"system_note": "Cannot fulfill: Repeat SKU short"})
    assert b["repeat"] is False and b["notes"] == "Cannot fulfill: Repeat SKU short"
```

  (Use the real name and signature of the banner function, `grep -n "def .*banner" gui/packer_bridge.py`.)
- [ ] **Step 2:** Run them and expect FAIL.
- [ ] **Step 3: Implement** in the banner function:

```python
    system_note = _clean(metadata.get("system_note"))
    repeat = "Repeat" in system_note and not system_note.startswith("Cannot fulfill")
    fallback = "" if system_note == "Repeat" else system_note
    return {
        "order": str(order_number),
        "chips": [c for c in chips if c],
        "repeat": repeat,
        "notes": _clean(metadata.get("notes")) or fallback,
    }
```

  In `packer.js` `renderBanner()`, after the order label line:

```js
  if (b.repeat) els.banner.appendChild(span("chip chip--warning", "Repeat"));
```

  Extend the `els.banner.hidden` condition with `&& !b.repeat`.
- [ ] **Step 4:** Run packing-tool's suite and lint. Expect PASS.
- [ ] **Step 5:** Commit in the packing-tool worktree with the message `feat(packer): Repeat chip independent of notes (shopify AUDIT-02-8)`.

---

### Task 9: Finish Stage B

- [ ] `grep -n "xfail" tests/audit/test_02_repeat_orders.py` must return nothing.
- [ ] `grep -rn "repeat_window_days\|load_packed_orders\|_merge_fulfillment_history" shopify_tool gui tests` must return nothing.
- [ ] Run the full shopify suite and `ruff check .`, and record the pass/xfail counts for `state.md`. Do the same for packing-tool.
- [ ] Run `graphify update .` in both repos.
- [ ] Push both branches (`git push -u origin <branch>`, one command per call). **Don't open PRs**: Stage C reviews and opens them.
- [ ] Set `next_stage: C` in `state.md`.
