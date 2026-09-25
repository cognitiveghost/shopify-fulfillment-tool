# Phase 14 Bundle 2: Session Safety and Atomic Writes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (the runner forbids subagents at Stage B). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix AUDIT-05-1 … 05-8 and AUDIT-01-12, so that no session is deleted, leaked, silently overwritten, torn or saved without the operator being told.

**Architecture:** A new deep module, `shopify_tool/session_state.py`, owns `current_state.pkl`: a stamp, a stale check, and an atomic, locked, check-then-replace save. `MainWindow` keeps one `_state_stamp` and runs every save through that module. It also gets one `_reset_session_state()` for every way into a session. The JSON writers move to `shared.atomic_write.atomic_write_json`, whose fd bug is fixed in packing-tool first.

**Tech Stack:** Python 3, PySide6, pandas, pytest (offscreen).

**Spec:** `docs/superpowers/specs/2026-09-25-phase14-bundle2-session-safety-design.md`. Read it first. ADR: `docs/adr/0011-a-stale-session-state-is-refused-not-locked.md`.

## Where things are

- Shopify worktree (this branch): `/home/gloopy/Desktop/Projects/shopify-fulfillment-tool/.claude/worktrees/phase14-bundle2-session-safety`, branch `worktree-phase14-bundle2-session-safety`.
- Packing-tool worktree (Task 1 only): `/home/gloopy/Desktop/Projects/packing-tool/.claude/worktrees/worktree-phase14-bundle2-atomic-write`, branch `worktree-phase14-bundle2-atomic-write`. It already exists, and its `.venv` is linked.
- Tests: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -p no:randomly -q <path>`
- Lint: `.venv/bin/ruff check .`
- VM guard: use `/usr/bin/git`, one plain git command per Bash call, no heredocs, and commit with `git commit -F <file>`, writing the message file with the Write tool into `$CLAUDE_JOB_DIR/tmp`. Never hand-edit `shared/` in this repo.

## Global Constraints

- Every message to the operator goes through `show_error(source_widget, headline, what_to_do)` from `gui.components`. Use the exact copy strings below, word for word.
- Stale save: headline `"Another PC changed this session"`, body `"Your change wasn't saved. Reopen the session from Sessions to load their changes, then make it again."`
- Failed save: headline `"Your last change wasn't saved"`, body `"Check the connection to the server. Your next change saves everything on screen. Details are in Logs."`
- Stale export: headline `"Another PC changed this session"`, body `"Nothing was exported. Reopen the session from Sessions to load their changes, then export again."`
- Stale-check failure: headline `"The session couldn't be checked"`, body `"Check the connection to the server, then export again."`
- Comment save failure: headline `"The comment wasn't saved"`, body `"Details are in Logs."`
- No new dependency. No `pyproject.toml`. No hardcoded colours (there is no UI styling in this bundle).
- Done = all nine strict-xfail markers in `tests/audit/test_05_sessions_sweep.py` removed, with those tests passing, plus ruff clean and the full suite green.

## Review Focus

1. **A session analysed on this PC, then edited.** `core.run_full_analysis` writes `current_state.pkl` itself. If `on_analysis_complete` doesn't re-stamp, the first edit after every analysis is refused as stale. Pinned in Task 3 (`test_an_edit_after_analysis_saves`).
2. **Existing tests that write `current_state.pkl` behind the window's back** and then save through `MainWindow`. They will now be refused. If the full suite shows these, fix the *test*: re-stamp with `mw._state_stamp = session_state.state_stamp(path)` after its direct write. Don't weaken the check.
3. **Temp files beside the state.** `.current_state_tmp_*.pkl` and `current_state.pkl.lock` now appear in `analysis/`. Grep for any `glob("*.pkl")` or `iterdir()` over `analysis/` (for example in `stock_export.py` and `session_manager.calculate_session_statistics`) that would pick them up. Pinned in Task 2 (`test_a_save_leaves_no_temp_file`).
4. **Server unreachable during an export's stale check.** `stat` raises `OSError`. The export is refused with the "couldn't be checked" copy and doesn't crash. Pinned in Task 5.
5. **New session fails** (`create_session` raises). The open session and its orders must stay as they were, so the reset runs only after success. Pinned in Task 4.

---

### Task 1: AUDIT-05-8, the `atomic_write_json` double close (packing-tool, then sync)

**Files:**
- Modify: packing-tool worktree `shared/atomic_write.py`
- Test: packing-tool worktree `tests/test_atomic_write.py`
- Then sync into this repo: `shared/atomic_write.py`. Remove the xfail on `test_atomic_write_reports_the_real_error` in `tests/audit/test_05_sessions_sweep.py`.

**Interfaces:** Produces the fixed `atomic_write_json(path, data, *, indent=2, ensure_ascii=False, retries=3, retry_delay=0.15)`, with an unchanged signature. When `json.dump` fails, it raises the real error.

- [ ] **Step 1: Write the failing test** (append to packing-tool `tests/test_atomic_write.py`)

```python
def test_atomic_write_json_raises_the_real_error_not_ebadf(tmp_path):
    # object() isn't JSON-serialisable: json.dump fails inside the fdopen block,
    # which has already closed the fd. A second os.close() used to replace the
    # TypeError with OSError(EBADF).
    with pytest.raises(TypeError):
        atomic_write_json(tmp_path / "x.json", {"a": object()}, retries=1)
    assert not list(tmp_path.glob(".*_tmp_*"))
```

Check the file's existing imports (`pytest`, `atomic_write_json`) and add whichever is missing.

- [ ] **Step 2: Run it and confirm it fails** (from the packing-tool worktree)

Run: `.venv/bin/python -m pytest -q tests/test_atomic_write.py::test_atomic_write_json_raises_the_real_error_not_ebadf`
Expected: FAIL, `OSError: [Errno 9] Bad file descriptor`.

- [ ] **Step 3: Fix.** In packing-tool `shared/atomic_write.py`, replace

```python
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=indent, ensure_ascii=ensure_ascii)
            except Exception:
                os.close(fd)
                raise
```

with

```python
            # fdopen owns fd from here: its `with` closes it on success and on
            # failure, so a second os.close() would raise EBADF over the real
            # error, or close another thread's newly opened file.
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=indent, ensure_ascii=ensure_ascii)
```

- [ ] **Step 4: Run packing-tool's atomic-write tests and the whole packing-tool suite.** Check that suite's own CLAUDE.md for its exact test command. Expected: all pass.

- [ ] **Step 5: Commit in packing-tool** (`git -C <packing-tool worktree> add shared/atomic_write.py tests/test_atomic_write.py`, then commit). Message: `shared/atomic_write: don't close the fd twice when json.dump fails (AUDIT-05-8)`. Push with `git -C <packing-tool worktree> push -u origin worktree-phase14-bundle2-atomic-write`. Don't open the PR; Stage C does that.

- [ ] **Step 6: Sync into this repo** (from the shopify worktree): `.venv/bin/python scripts/sync_shared.py /home/gloopy/Desktop/Projects/packing-tool/.claude/worktrees/worktree-phase14-bundle2-atomic-write`. Then run `/usr/bin/git diff --stat shared/`. Expected: only `shared/atomic_write.py` changes.

- [ ] **Step 7:** Remove the `@pytest.mark.xfail(...)` block above `test_atomic_write_reports_the_real_error`. Run `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -p no:randomly -q tests/audit/test_05_sessions_sweep.py::test_atomic_write_reports_the_real_error`. Expected: PASS.

- [ ] **Step 8: Commit** `shared/atomic_write.py` and the test file. Message: `shared/: atomic_write fd fix (synced from packing-tool, AUDIT-05-8)`.

---

### Task 2: `shopify_tool/session_state.py`

**Files:**
- Create: `shopify_tool/session_state.py`
- Test: `tests/test_session_state.py` (new)

**Interfaces:** Produces:
- `STATE_FILE = "current_state.pkl"`
- `class StaleSessionError(Exception)`
- `state_stamp(session_path) -> tuple[int, int] | None`
- `is_stale(session_path, loaded_stamp) -> bool`
- `save_state(session_path, df: pd.DataFrame, loaded_stamp) -> tuple[int, int]`
- `order_counts(df) -> dict`, with keys `total_orders`, `fulfillable_orders`, `not_fulfillable_orders`

`session_path` is a `str` or a `Path` to the session folder (not the `analysis/` folder).

- [ ] **Step 1: Write the failing tests** in `tests/test_session_state.py`

```python
"""session_state owns current_state.pkl: stamp, stale check, atomic save."""

import pandas as pd
import pytest

from shopify_tool import session_state
from shopify_tool.session_state import StaleSessionError


def _df(*statuses, order_numbers=None):
    n = len(statuses)
    return pd.DataFrame(
        {
            "Order_Number": order_numbers or [f"#{1001 + i}" for i in range(n)],
            "SKU": [f"SKU-{i}" for i in range(n)],
            "Quantity": [1] * n,
            "Order_Fulfillment_Status": list(statuses),
        }
    )


def test_a_session_without_state_has_no_stamp(tmp_path):
    assert session_state.state_stamp(tmp_path) is None


def test_save_returns_the_stamp_now_on_disk(tmp_path):
    stamp = session_state.save_state(tmp_path, _df("Fulfillable"), None)
    assert stamp == session_state.state_stamp(tmp_path)
    assert pd.read_pickle(tmp_path / "analysis" / "current_state.pkl").equals(_df("Fulfillable"))


def test_a_save_from_a_stale_stamp_is_refused_and_writes_nothing(tmp_path):
    first = session_state.save_state(tmp_path, _df("Fulfillable"), None)
    session_state.save_state(tmp_path, _df("Not Fulfillable"), first)  # another PC
    with pytest.raises(StaleSessionError):
        session_state.save_state(tmp_path, _df("Fulfillable", "Fulfillable"), first)
    saved = pd.read_pickle(tmp_path / "analysis" / "current_state.pkl")
    assert saved["Order_Fulfillment_Status"].tolist() == ["Not Fulfillable"]


def test_state_created_by_another_pc_makes_a_none_stamp_stale(tmp_path):
    session_state.save_state(tmp_path, _df("Fulfillable"), None)
    assert session_state.is_stale(tmp_path, None)
    with pytest.raises(StaleSessionError):
        session_state.save_state(tmp_path, _df("Fulfillable"), None)


def test_a_failed_write_keeps_the_old_state(tmp_path, monkeypatch):
    stamp = session_state.save_state(tmp_path, _df("Fulfillable"), None)

    def share_went_away(*_a, **_k):
        raise OSError("The specified network name is no longer available")

    monkeypatch.setattr(pd.DataFrame, "to_pickle", share_went_away)
    with pytest.raises(OSError):
        session_state.save_state(tmp_path, _df("Not Fulfillable"), stamp)
    assert session_state.state_stamp(tmp_path) == stamp
    assert not list((tmp_path / "analysis").glob(".current_state_tmp_*"))


def test_a_save_leaves_no_temp_file(tmp_path):
    stamp = session_state.save_state(tmp_path, _df("Fulfillable"), None)
    session_state.save_state(tmp_path, _df("Not Fulfillable"), stamp)
    pkl = sorted(p.name for p in (tmp_path / "analysis").glob("*.pkl"))
    assert pkl == ["current_state.pkl"]


def test_order_counts_count_orders_not_lines(tmp_path):
    # #1001 has one blocked SKU line, so the whole order is blocked (R1).
    df = _df(
        "Fulfillable", "Not Fulfillable", "Fulfillable",
        order_numbers=["#1001", "#1001", "#1002"],
    )
    assert session_state.order_counts(df) == {
        "total_orders": 2,
        "fulfillable_orders": 1,
        "not_fulfillable_orders": 1,
    }
```

- [ ] **Step 2: Run them and confirm they fail:** `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -p no:randomly -q tests/test_session_state.py`. Expected: ImportError.

- [ ] **Step 3: Implement** `shopify_tool/session_state.py`

```python
"""A session's saved state (analysis/current_state.pkl) and its stale check.

Every edit rewrites the whole state from one PC's memory, so a PC that loaded
it before another PC saved would silently undo that PC's edits (AUDIT-05-3).
Each PC keeps the stamp it last loaded or saved; a save against a different
file on disk is refused. ADR 0011.
"""

import os
import tempfile
from pathlib import Path

from shared.file_lock import locked_file
from shopify_tool import stock_ledger

STATE_FILE = "current_state.pkl"


class StaleSessionError(Exception):
    """Another PC saved this session's state after this PC loaded it."""


def _state_path(session_path) -> Path:
    return Path(session_path) / "analysis" / STATE_FILE


def state_stamp(session_path):
    """(mtime_ns, size) of the saved state, or None when there is none yet.

    ponytail: two same-size saves inside one file-time tick share a stamp;
    upgrade to a version token written with the state if that ever shows up.
    """
    try:
        st = _state_path(session_path).stat()
    except FileNotFoundError:
        return None
    return (st.st_mtime_ns, st.st_size)


def is_stale(session_path, loaded_stamp) -> bool:
    return state_stamp(session_path) != loaded_stamp


def save_state(session_path, df, loaded_stamp):
    """Write df as the session's state, atomically; return the new stamp.

    Raises StaleSessionError, writing nothing, when the state on disk is not
    the one this PC loaded or last saved. The lock spans only the check and
    the replace, so two PCs can't both pass the check and both write.
    """
    path = _state_path(session_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path.with_name(STATE_FILE + ".lock"), "a+") as lock, locked_file(lock):
        if is_stale(session_path, loaded_stamp):
            raise StaleSessionError(str(path))
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".current_state_tmp_", suffix=".pkl")
        os.close(fd)
        try:
            df.to_pickle(tmp)
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        return state_stamp(session_path)


def order_counts(df) -> dict:
    """The session_info.json order counts, by order (R1), for the browser."""
    total = df["Order_Number"].astype(str).str.strip().nunique()
    fulfillable = len(stock_ledger.fulfillable_orders(df))
    return {
        "total_orders": total,
        "fulfillable_orders": fulfillable,
        "not_fulfillable_orders": total - fulfillable,
    }
```

Check that `locked_file` is a context manager taking an open handle: `shared/file_lock.py:26`, and see how `tests/audit/test_05_sessions_sweep.py::test_packing_tools_lock_excludes_our_session_info_writes` uses it.

- [ ] **Step 4: Run the tests.** Expected: all 7 pass.

- [ ] **Step 5: Commit.** Message: `session_state: stamp, stale check and atomic save for current_state.pkl`.

---

### Task 3: `save_session_state` and the stamp (AUDIT-05-3, 05-5, 05-6)

**Files:**
- Modify: `gui/main_window_pyside.py`: `__init__` (near the `self.analysis_results_df = None` at about line 89), `save_session_state` (about line 710), `_load_session_analysis` (about line 762)
- Modify: `gui/actions_handler.py`: `on_analysis_complete` (about line 189)
- Modify: `tests/audit/test_05_sessions_sweep.py` (harness plus markers for 05-3, 05-5 and 05-6)
- Test: `tests/test_stale_session.py` (new)

**Interfaces:** Consumes everything Task 2 produces. Produces `MainWindow._state_stamp` (a tuple or `None`), which Tasks 4 and 5 read and reset.

- [ ] **Step 1: Adjust the audit harness (not the assertions).** In `tests/audit/test_05_sessions_sweep.py`, replace `_reopen` with:

```python
def _open_on_a_pc(session_path):
    """One PC opening the session: the loaded namespace, stamp included."""
    pc = _pc(session_path, None)
    assert MainWindow._load_session_analysis(pc, session_path)
    return pc


def _reopen(session_path):
    return _open_on_a_pc(session_path).analysis_results_df
```

Then change the 05-3 test's body to:

```python
def test_a_hold_made_on_one_pc_survives_a_save_from_another(sessions, monkeypatch):
    told = []
    monkeypatch.setattr(main_window_module, "show_error", lambda *a, **k: told.append(a))
    path = sessions.create_session("M")
    MainWindow.save_session_state(_pc(path, _orders("Fulfillable", "Fulfillable")))

    pc_a = _open_on_a_pc(path)
    pc_b = _open_on_a_pc(path)

    pc_a.analysis_results_df.loc[0, "Order_Fulfillment_Status"] = "Not Fulfillable"
    MainWindow.save_session_state(pc_a)  # PC A holds #1001
    pc_b.analysis_results_df.loc[1, "Order_Fulfillment_Status"] = "Not Fulfillable"
    MainWindow.save_session_state(pc_b)  # PC B holds #1002, unaware of A

    saved = _reopen(path).set_index("Order_Number")["Order_Fulfillment_Status"]
    assert saved["#1001"] == "Not Fulfillable"
    assert told and told[-1][1] == "Another PC changed this session"
```

Remove the xfail markers on this test, on `test_a_failed_save_of_an_edit_reaches_the_person` (05-5) and on `test_blocked_count_follows_edits` (05-6).

- [ ] **Step 2: Write the new GUI test** `tests/test_stale_session.py` (Task 5 appends to it)

```python
"""The stamp's life cycle on a real MainWindow (ADR 0011)."""

import pandas as pd
import pytest
from PySide6.QtWidgets import QApplication

import gui.actions_handler as actions_module
import gui.main_window_pyside as main_window_module
import gui.session_browser_widget as browser_module
from gui.main_window_pyside import MainWindow
from shopify_tool import session_state


@pytest.fixture
def main_window(tmp_path, monkeypatch, qapp):
    monkeypatch.setenv("FULFILLMENT_SERVER_PATH", str(tmp_path))
    monkeypatch.setattr(browser_module.SessionBrowserWidget, "USE_ASYNC", False)
    win = MainWindow()
    win.show()
    QApplication.processEvents()
    win.profile_manager.create_client_profile("acme", "Client Acme")
    win.current_client_id = "acme"
    win.load_client_config("acme")
    yield win
    win.close()


@pytest.fixture
def told(monkeypatch):
    got = []
    record = lambda *a, **k: got.append(a[1])  # noqa: E731 -- headline only
    monkeypatch.setattr(main_window_module, "show_error", record)
    monkeypatch.setattr(actions_module, "show_error", record)
    return got


def _orders(*statuses):
    return pd.DataFrame(
        {
            "Order_Number": [f"#{1001 + i}" for i in range(len(statuses))],
            "SKU": [f"SKU-{i}" for i in range(len(statuses))],
            "Quantity": [1] * len(statuses),
            "Stock": [5] * len(statuses),
            "Order_Fulfillment_Status": list(statuses),
        }
    )


def _open_with_state(win, df):
    path = win.session_manager.create_session("acme")
    session_state.save_state(path, df, None)
    win.load_existing_session(path)
    return path


def _another_pc_saves(path, df):
    session_state.save_state(path, df, session_state.state_stamp(path))


def test_an_edit_after_analysis_saves(main_window, told):
    path = main_window.session_manager.create_session("acme")
    main_window.session_path = path
    df = _orders("Fulfillable", "Fulfillable")
    session_state.save_state(path, df, None)  # what core.run_full_analysis writes
    main_window.actions_handler.on_analysis_complete((True, "report.xlsx", df, {}))

    main_window.analysis_results_df.loc[0, "Order_Fulfillment_Status"] = "Not Fulfillable"
    main_window.save_session_state()

    assert told == []
    assert main_window._state_stamp == session_state.state_stamp(path)


def test_two_edits_in_a_row_both_save(main_window, told):
    path = _open_with_state(main_window, _orders("Fulfillable", "Fulfillable"))
    for i in (0, 1):
        main_window.analysis_results_df.loc[i, "Order_Fulfillment_Status"] = "Not Fulfillable"
        main_window.save_session_state()
    assert told == []
    saved = pd.read_pickle(main_window.session_manager.get_analysis_dir(path) / "current_state.pkl")
    assert saved["Order_Fulfillment_Status"].tolist() == ["Not Fulfillable"] * 2


def test_a_save_after_another_pc_saved_is_refused(main_window, told):
    path = _open_with_state(main_window, _orders("Fulfillable", "Fulfillable"))
    _another_pc_saves(path, _orders("Not Fulfillable", "Fulfillable"))

    main_window.analysis_results_df.loc[1, "Order_Fulfillment_Status"] = "Not Fulfillable"
    main_window.save_session_state()

    assert told == ["Another PC changed this session"]
```

If `on_analysis_complete` needs more stubbing offscreen (for example `_record_analysis_stats_async`), monkeypatch that method on `main_window.actions_handler` to a no-op in this test only. Check `get_analysis_dir` exists on `SessionManager` (the audit test uses it). If the `Stock` column trips anything in `with_stock_left`, drop it.

- [ ] **Step 3: Run it and confirm it fails:** `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -p no:randomly -q tests/test_stale_session.py tests/audit/test_05_sessions_sweep.py`. Expected: the new tests and the three unmarked audit tests fail.

- [ ] **Step 4: Implement.** In `gui/main_window_pyside.py`:

Add the imports (check the ones already there first; `show_error` and `toast` are already imported):

```python
from shared.atomic_write import atomic_write_json
from shopify_tool import session_state
```

In `__init__`, next to `self.analysis_results_df = None`:

```python
        # current_state.pkl as this PC last loaded or saved it (ADR 0011).
        self._state_stamp = None
```

Replace the body of `save_session_state` after its two early-return guards, keeping the docstring and guards, with:

```python
        from pathlib import Path

        try:
            self._state_stamp = session_state.save_state(
                self.session_path,
                self.analysis_results_df,
                getattr(self, "_state_stamp", None),
            )
        except session_state.StaleSessionError:
            logger.warning(f"Refused a stale save to {self.session_path}")
            show_error(
                self,
                "Another PC changed this session",
                "Your change wasn't saved. Reopen the session from Sessions to "
                "load their changes, then make it again.",
            )
            return
        except Exception:
            logger.exception("Failed to save session state")
            show_error(
                self,
                "Your last change wasn't saved",
                "Check the connection to the server. Your next change saves "
                "everything on screen. Details are in Logs.",
            )
            return

        # current_state.pkl above is the state; these only mirror it, so a
        # failure here is logged, not shown.
        analysis_dir = Path(self.session_path) / "analysis"
        try:
            self.analysis_results_df.to_excel(analysis_dir / "current_state.xlsx", index=False)
            if self.analysis_stats:
                atomic_write_json(analysis_dir / "analysis_stats.json", self.analysis_stats)
        except Exception:
            logger.exception("Failed to write the session state backups")

        # The browser's Blocked column reads these counts (AUDIT-05-6).
        session_manager = getattr(self, "session_manager", None)
        if session_manager is not None:
            try:
                session_manager.update_session_info(
                    self.session_path, session_state.order_counts(self.analysis_results_df)
                )
            except Exception:
                logger.exception("Failed to update the session's order counts")
```

Update the docstring to say that a stale or failed save is refused or reported (ADR 0011). Remove `import json` from the module only if ruff reports it unused.

In `_load_session_analysis`, as the first statement inside `try:` (before the pickle is read):

```python
            # Before the read: a write landing between the two makes the next
            # save refuse needlessly, never overwrite (ADR 0011).
            self._state_stamp = session_state.state_stamp(session_path)
```

In `gui/actions_handler.py` `on_analysis_complete`, right after `self.mw.analysis_stats = stats`:

```python
            # run_full_analysis just rewrote current_state.pkl; without this
            # the first edit after every analysis is refused as stale.
            if self.mw.session_path:
                self.mw._state_stamp = session_state.state_stamp(self.mw.session_path)
```

Add `session_state` to the `from shopify_tool import ...` line.

- [ ] **Step 5: Run the two files from Step 3.** Expected: all pass.

- [ ] **Step 6: Run the full suite.** Handle Review Focus item 2 here if it comes up.

- [ ] **Step 7: Commit.** Message: `Refuse a stale session save; report a failed one; counts follow edits (AUDIT-05-3, -5, -6)`.

---

### Task 4: `_reset_session_state` (AUDIT-05-2)

**Files:**
- Modify: `gui/main_window_pyside.py`: new method next to `load_existing_session`, a call at the top of `load_existing_session`, and a replacement for the inline reset in `load_client_config` (about lines 213-225)
- Modify: `gui/actions_handler.py` `create_new_session` (about line 89)
- Modify: `tests/audit/test_05_sessions_sweep.py` (remove both 05-2 markers)
- Test: `tests/test_stale_session.py`

**Interfaces:** Consumes `_state_stamp` from Task 3. Produces `MainWindow._reset_session_state() -> None`.

- [ ] **Step 1: Write the failing test** (append to `tests/test_stale_session.py`)

```python
def test_a_failed_new_session_keeps_the_open_one(main_window, told, monkeypatch):
    from shopify_tool.session_manager import SessionManagerError

    path = _open_with_state(main_window, _orders("Fulfillable"))

    def refuse(_client):
        raise SessionManagerError("share is read-only")

    monkeypatch.setattr(main_window.session_manager, "create_session", refuse)
    main_window.actions_handler.create_new_session()

    assert main_window.session_path == path
    assert main_window.analysis_results_df is not None
```

Also remove the xfail markers on `test_opening_a_session_without_analysis_drops_the_previous_orders` and `test_a_new_session_starts_without_the_previous_orders`.

- [ ] **Step 2: Run it and confirm the two audit tests fail** (the new test may already pass; it guards the call's position).

- [ ] **Step 3: Implement.** In `gui/main_window_pyside.py`, add:

```python
    def _reset_session_state(self):
        """Forget the open session's orders, inputs, undo history and stamp.

        Every way into a session calls this first (AUDIT-05-2); without it the
        previous session's orders stayed loaded and exportable, and the next
        edit saved them into the new session. Leaves session_path to the
        caller.
        """
        self.analysis_results_df = None
        self.analysis_stats = None
        self._state_stamp = None
        self.orders_file_path = None
        self.stock_file_path = None
        self.orders_slot.clear()
        self.stock_slot.clear()
        if hasattr(self, "undo_manager"):
            self.undo_manager.reset_for_session()
        self._update_all_views()
```

In `load_client_config`, replace

```python
                self.analysis_results_df = None
                self.analysis_stats = None
                self.session_path = None
```

and the later `undo_manager.reset_for_session()` / `_update_all_views()` lines of that same block with a single `self._reset_session_state()`, followed by `self.session_path = None`. Keep the lines in between (`command_bar.set_state`, `_refresh_setup_panel`, `setup_stack`) in their original order.

In `load_existing_session`, make `self._reset_session_state()` the first statement inside `try:`, before `self.session_path = session_path`.

In `actions_handler.create_new_session`, immediately before `self.mw.session_path = session_path` (that is, after `create_session` returned):

```python
            # Only now: a failed create keeps the open session as it was.
            self.mw._reset_session_state()
```

- [ ] **Step 4: Run `tests/test_stale_session.py` and `tests/audit/test_05_sessions_sweep.py`.** Expected: all pass. Then run the full suite; `tests/test_session_restore.py` and the browser tests are the ones most likely to notice.

- [ ] **Step 5: Commit.** Message: `Every way into a session starts from an empty state (AUDIT-05-2)`.

---

### Task 5: Refuse a stale export (owner decision 2, 2026-09-25)

**Files:**
- Modify: `gui/actions_handler.py`: new `_refuse_stale_export`, plus calls in `open_generate_reports_dialog` and `bulk_export_selection`
- Test: `tests/test_stale_session.py`

**Interfaces:** Consumes `session_state.is_stale` and `MainWindow._state_stamp`. Produces `ActionsHandler._refuse_stale_export() -> bool`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_stale_session.py`)

```python
def test_generate_reports_is_refused_when_stale(main_window, told, monkeypatch):
    path = _open_with_state(main_window, _orders("Fulfillable", "Fulfillable"))
    _another_pc_saves(path, _orders("Not Fulfillable", "Fulfillable"))
    loaded = []
    # Stands in for everything after the check; returning None also stops a
    # regression from opening the modal dialog and hanging the test.
    monkeypatch.setattr(
        main_window.profile_manager, "load_shopify_config", lambda *a: loaded.append(a)
    )

    main_window.actions_handler.open_generate_reports_dialog()

    assert told == ["Another PC changed this session"]
    assert loaded == []


def test_export_selection_is_refused_when_stale(main_window, told, monkeypatch):
    path = _open_with_state(main_window, _orders("Fulfillable", "Fulfillable"))
    _another_pc_saves(path, _orders("Not Fulfillable", "Fulfillable"))
    asked = []
    monkeypatch.setattr(
        actions_module.QFileDialog,
        "getSaveFileName",
        lambda *a, **k: asked.append(a) or ("", ""),
    )

    main_window.actions_handler.bulk_export_selection(["#1001"], "csv")

    assert told == ["Another PC changed this session"]
    assert asked == []


def test_an_export_that_cannot_check_is_refused(main_window, told, monkeypatch):
    _open_with_state(main_window, _orders("Fulfillable"))

    def unreachable(_path):
        raise OSError("The network path was not found")

    monkeypatch.setattr(actions_module.session_state, "state_stamp", unreachable)
    monkeypatch.setattr(
        actions_module.QFileDialog, "getSaveFileName", lambda *a, **k: ("", "")
    )

    main_window.actions_handler.bulk_export_selection(["#1001"], "csv")

    assert told == ["The session couldn't be checked"]


def test_a_fresh_session_exports(main_window, told, monkeypatch):
    _open_with_state(main_window, _orders("Fulfillable"))
    asked = []
    monkeypatch.setattr(
        actions_module.QFileDialog,
        "getSaveFileName",
        lambda *a, **k: asked.append(a) or ("", ""),
    )

    main_window.actions_handler.bulk_export_selection(["#1001"], "csv")

    assert told == [] and len(asked) == 1
```

- [ ] **Step 2: Run them and confirm the three refusal tests fail.**

- [ ] **Step 3: Implement** in `gui/actions_handler.py`

```python
    def _refuse_stale_export(self) -> bool:
        """True, after telling the operator, when this PC's copy is stale.

        An export ships what is on screen, so a PC that loaded the session
        before another PC held an order would ship it (ADR 0011). Fails safe:
        a check that can't reach the server refuses too.
        """
        try:
            stale = session_state.is_stale(self.mw.session_path, self.mw._state_stamp)
        except OSError:
            self.log.exception("Could not check the session state before exporting")
            show_error(
                self.mw,
                "The session couldn't be checked",
                "Check the connection to the server, then export again.",
            )
            return True
        if stale:
            show_error(
                self.mw,
                "Another PC changed this session",
                "Nothing was exported. Reopen the session from Sessions to load "
                "their changes, then export again.",
            )
        return stale
```

In `open_generate_reports_dialog`, right after the `if not session_path: ... return` block:

```python
        if self._refuse_stale_export():
            return
```

In `bulk_export_selection`, right after `if selected_df.empty: return`:

```python
        if self.mw.session_path and self._refuse_stale_export():
            return
```

- [ ] **Step 4: Run `tests/test_stale_session.py`.** Expected: all pass.

- [ ] **Step 5: Commit.** Message: `Refuse exports from a stale session (AUDIT-05-3, owner decision 2026-09-25)`.

---

### Task 6: Session-name collision (AUDIT-05-1)

**Files:**
- Modify: `shopify_tool/session_manager.py` `create_session` (about lines 105-161)
- Modify: `tests/audit/test_05_sessions_sweep.py` (remove the 05-1 marker)
- Test: `tests/test_session_manager.py`

- [ ] **Step 1: Write the failing tests** (append to `tests/test_session_manager.py`, reusing that file's existing SessionManager fixture. Read its top first and match the fixture name; `session_manager` and a client `"M"` are assumed below.)

```python
def test_a_name_taken_since_the_listing_moves_to_the_next_number(session_manager, monkeypatch):
    first = session_manager.create_session("M")
    monkeypatch.setattr(
        session_manager, "_generate_unique_session_name", lambda _d: Path(first).name
    )
    second = session_manager.create_session("M")
    assert Path(second).name.endswith("_2")
    assert session_manager.get_session_info(first) is not None


def test_create_session_gives_up_without_deleting_anything(session_manager, monkeypatch):
    first = Path(session_manager.create_session("M"))
    date = first.name.rpartition("_")[0]
    for n in range(2, 12):
        (first.parent / f"{date}_{n}").mkdir()
    monkeypatch.setattr(
        session_manager, "_generate_unique_session_name", lambda _d: first.name
    )
    with pytest.raises(SessionManagerError):
        session_manager.create_session("M")
    assert all((first.parent / f"{date}_{n}").is_dir() for n in range(1, 12))
```

Also remove the xfail marker on `test_a_session_name_another_pc_just_took_is_never_deleted`.

- [ ] **Step 2: Run them and confirm they fail.**

- [ ] **Step 3: Implement.** In `create_session`, replace

```python
        session_name = self._generate_unique_session_name(client_sessions_dir)
        session_path = client_sessions_dir / session_name

        try:
            # Create session directory
            session_path.mkdir(parents=True)
```

with

```python
        # mkdir without exist_ok is the claim. Two PCs can derive one name
        # from a stale listing (SMB caches it ~10 s) and only one mkdir wins;
        # the loser takes the next number rather than touching that folder
        # (AUDIT-05-1). Counting on from the name, not re-listing, because
        # the listing is what was stale.
        date, _, number = self._generate_unique_session_name(
            client_sessions_dir
        ).rpartition("_")
        for n in range(int(number), int(number) + 10):
            session_path = client_sessions_dir / f"{date}_{n}"
            try:
                session_path.mkdir()
                break
            except FileExistsError:
                continue
        else:
            raise SessionManagerError(
                f"No free session name for CLIENT_{client_id} on {date}"
            )
        session_name = session_path.name

        # Past this point the folder is ours, so the cleanup below can only
        # ever remove what this call created.
        try:
```

Leave the rest of the `try` (subdirectories, session_info, index) and its `except` cleanup as they are. Task 7 converts the JSON write.

- [ ] **Step 4: Run `tests/test_session_manager.py` and `tests/audit/test_05_sessions_sweep.py`.** Expected: all pass.

- [ ] **Step 5: Commit.** Message: `create_session never deletes a folder it didn't create (AUDIT-05-1)`.

---

### Task 7: Atomic JSON writers (AUDIT-05-4, AUDIT-01-12)

**Files:**
- Modify: `shopify_tool/session_manager.py`: four writers (`create_session`, `update_session_status`, `update_session_info`, `append_to_session_list`)
- Modify: `shopify_tool/undo_manager.py` `_save_history` (about line 454)
- Modify: `gui/actions_handler.py` `_save_manual_addition` (about line 1410)
- Modify: `shopify_tool/sequential_order.py` `_write_sequential_order_map` (about line 51)
- Modify: `shopify_tool/barcode_history.py` `_save_history` (about line 57)
- Modify: `tests/audit/test_05_sessions_sweep.py` (remove the 05-4 marker)

- [ ] **Step 1:** Remove the xfail marker on `test_a_failed_session_info_write_keeps_the_old_file`. Run it and confirm it fails.

- [ ] **Step 2: Implement.** In each of the four `session_manager.py` writers, replace

```python
with open(session_info_path, 'w', encoding='utf-8') as f:
    json.dump(session_info, f, indent=2)
```

with

```python
atomic_write_json(session_info_path, session_info, indent=2)
```

`atomic_write_json` is already imported there. In the other four files, replace the `with open(..., 'w', ...) as f: json.dump(data, f, indent=2, ensure_ascii=False)` pair with `atomic_write_json(<same path>, <same data>, indent=2)`, and add `from shared.atomic_write import atomic_write_json` where it's missing. Keep each caller's existing `try/except` exactly as it is. Then drop any `import json` that ruff now reports unused.

Verify with: `grep -n "json.dump(" shopify_tool/session_manager.py shopify_tool/undo_manager.py shopify_tool/sequential_order.py shopify_tool/barcode_history.py` (expect nothing), and `grep -n "json.dump(" gui/actions_handler.py` (only the packing-list JSON in `_generate_single_report` should remain; it's out of scope per the spec).

- [ ] **Step 3: Run the full suite.** A test that patches `builtins.open` to simulate a write failure in one of these files needs to patch `atomic_write_json` in that module instead (see `test_bulk_status_updates_write_atomically` for the pattern).

- [ ] **Step 4: Commit.** Message: `Write session_info and the other session JSON files atomically (AUDIT-05-4, AUDIT-01-12)`.

---

### Task 8: A failed comment save is reported (AUDIT-05-7)

**Files:**
- Modify: `gui/session_browser_widget.py` `_on_comments_changed` (about line 924)
- Modify: `tests/audit/test_05_sessions_sweep.py` (remove the 05-7 marker)

- [ ] **Step 1:** Remove the xfail marker on `test_a_comment_that_fails_to_save_is_reported`. Run it and confirm it fails.

- [ ] **Step 2: Implement.** Replace the `except` body:

```python
        except Exception:
            logger.exception("Failed to update comments")
            show_error(self, "The comment wasn't saved", "Details are in Logs.")
```

`show_error` is already imported in that module (the audit test patches `browser_module.show_error`).

- [ ] **Step 3: Run the audit file.** Expected: all pass, with no xfail left in it (`grep -c xfail tests/audit/test_05_sessions_sweep.py` shows only the docstring mention).

- [ ] **Step 4: Commit.** Message: `Report a comment that fails to save (AUDIT-05-7)`.

---

### Task 9: Gate

- [ ] `.venv/bin/ruff check .`: clean.
- [ ] `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -p no:randomly -q`: 0 failed. Record the pass/xfail counts in state.md. The baseline after #339 was 1863 passed, 53 xfailed. Expect about 9 fewer xfailed, with the new tests added to passed.
- [ ] `diff -r shared /home/gloopy/Desktop/Projects/packing-tool/.claude/worktrees/worktree-phase14-bundle2-atomic-write/shared`: no differences (ignoring `__pycache__`).
- [ ] `graphify update .` in this worktree and in the packing-tool worktree.
- [ ] Push this branch: `/usr/bin/git push -u origin worktree-phase14-bundle2-session-safety`. No PRs; Stage C opens both, packing-tool's first, and the shopify PR body says to merge packing-tool first.
