# Session Browser Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. (The runner's Stage B declines the subagent-driven variant and stays in-session.)

**Goal:** Make the Session Browser show how much of each session Packing Tool has finished, advance session status automatically when it is all packed, and archive sessions older than 30 days.

**Architecture:** All the rules live in one new pure module, `shopify_tool/session_lifecycle.py`, operating on the entry dicts `SessionManager.list_client_sessions()` already returns — no I/O, no Qt, so the rules are testable without a file server or a `QApplication`. `SessionManager` gains one batched writer so a backlog of status changes costs one index rewrite instead of N. The background session-loading worker calls derive-then-apply before emitting, and the widget gains one read-only column and loses its display-time age filter.

**Tech Stack:** Python 3, PySide6, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-08-24-session-browser-overhaul-design.md`

## Global Constraints

- Windows 10/11 is the production target; development is on Ubuntu. Run tests with `QT_QPA_PLATFORM=offscreen`.
- **Never hand-edit anything under `shared/`** — it is one-way synced from `../packing-tool`.
- **No UI calls from background threads.** The derive/apply pass runs in `SessionLoaderWorker.run()` and must touch files only, never widgets.
- **No hardcoded colors** in stylesheets — use `theme_manager` tokens. (This plan adds no styling; the pre-existing hardcoded status colors are deliberately left for Phase 8.)
- Nothing in this feature may raise into the session-refresh path. Every value read comes from a file another tool writes; a session list that will not load is far worse than one carrying a stale status.
- Full gate before finishing: `QT_QPA_PLATFORM=offscreen python -m pytest` and `ruff check . --exclude shared`.
- Use `.venv/bin/python` — bare `python` is not on PATH on this machine.
- Baseline on this branch before any changes: **765 passed** (verified by running the suite, not estimated). Expect **806** at the end: +27 (Task 1) +8 (Task 2) +4 (Task 3) +7 (Task 4), −5 deleted with `test_session_browser_filter.py`.

---

### Task 1: The lifecycle rules (pure module)

**Files:**
- Create: `shopify_tool/session_lifecycle.py`
- Test: `tests/test_session_lifecycle.py`

**Interfaces:**
- Consumes: nothing — this task is self-contained.
- Produces: `FULL_SESSION_KEY: str`, `AUTO_ARCHIVE_AFTER_DAYS: int`, `packing_completion(entry: dict) -> tuple[int, int]`, `is_fully_packed(entry: dict) -> bool`, `parse_created_at(value) -> datetime | None`, `derive_status_updates(entries, now: datetime) -> dict[str, str]`. Tasks 3 and 4 import these.

Every assertion in Step 1 below was run against a working prototype before this plan was written — they pass as written. Do not "fix" them if they fail; a failure means the implementation in Step 3 was mistyped.

- [ ] **Step 1: Write the failing test**

Create `tests/test_session_lifecycle.py`:

```python
"""Session status derivation from packing progress and age (pure -- no Qt, no file server)."""
from datetime import datetime, timedelta

from shopify_tool.session_lifecycle import (
    derive_status_updates,
    is_fully_packed,
    packing_completion,
    parse_created_at,
)

NOW = datetime.now().astimezone()


def _entry(name="s", status="active", lists=None, progress=None, created=None, manual=None):
    entry = {
        "session_name": name,
        "status": status,
        "statistics": {"packing_lists": lists if lists is not None else []},
    }
    if progress is not None:
        entry["packing_progress"] = progress
    if created is not None:
        entry["created_at"] = created
    if manual is not None:
        entry["status_manually_set"] = manual
    return entry


def _done(*names):
    return {n: {"status": "completed"} for n in names}


class TestPackingCompletion:
    def test_counts_completed_lists(self):
        assert packing_completion(_entry(lists=["a", "b", "c"], progress=_done("a", "b"))) == (2, 3)

    def test_session_with_no_packing_lists_is_zero_of_zero(self):
        assert packing_completion(_entry(lists=[], progress={})) == (0, 0)

    def test_full_session_key_covers_every_list(self):
        # Packing Tool's whole-session mode records progress under the literal
        # key "full_session", which matches no list's file stem. Two of the 29
        # real sessions carrying packing_progress already use it; without this
        # they would read 0/N forever despite being entirely packed.
        assert packing_completion(_entry(lists=["a", "b"], progress=_done("full_session"))) == (2, 2)

    def test_full_session_with_no_lists_on_disk_reads_one_of_one(self):
        assert packing_completion(_entry(lists=[], progress=_done("full_session"))) == (1, 1)

    def test_incomplete_full_session_does_not_count(self):
        entry = _entry(lists=["a"], progress={"full_session": {"status": "in_progress"}})
        assert packing_completion(entry) == (0, 1)

    def test_progress_key_with_no_file_on_disk_cannot_block_completion(self):
        assert packing_completion(_entry(lists=["a"], progress=_done("a", "ghost"))) == (1, 1)

    def test_only_completed_counts_not_paused(self):
        assert packing_completion(_entry(lists=["a"], progress={"a": {"status": "paused"}})) == (0, 1)

    def test_malformed_shapes_do_not_raise(self):
        # Every value here comes from a file another tool writes.
        assert packing_completion({"packing_progress": "nonsense"}) == (0, 0)
        assert packing_completion({"statistics": "nonsense"}) == (0, 0)
        assert packing_completion(_entry(lists=["a"], progress={"a": ["not", "a", "dict"]})) == (0, 1)
        assert packing_completion(_entry(lists=["a"], progress={"a": {}})) == (0, 1)
        assert packing_completion({}) == (0, 0)


class TestIsFullyPacked:
    def test_all_lists_complete(self):
        assert is_fully_packed(_entry(lists=["a"], progress=_done("a"))) is True

    def test_empty_session_is_never_complete(self):
        # Vacuous truth would mark all 9 real list-less sessions complete.
        assert is_fully_packed(_entry(lists=[], progress={})) is False

    def test_partial_is_not_complete(self):
        assert is_fully_packed(_entry(lists=["a", "b"], progress=_done("a"))) is False


class TestParseCreatedAt:
    def test_naive_timestamp_becomes_local_aware(self):
        # created_at only became offset-aware on 2026-07-27 (PR #253), so every
        # session old enough to archive predates the fix. Skipping naive stamps
        # would archive nothing at all, forever.
        assert parse_created_at("2026-07-20T10:00:00").tzinfo is not None

    def test_aware_timestamp_instant_is_preserved(self):
        aware = "2026-08-20T10:00:00+03:00"
        assert parse_created_at(aware) == datetime.fromisoformat(aware)

    def test_unreadable_values_return_none_and_never_raise(self):
        # A naive stamp once crashed the whole refresh and left the widget
        # stuck on "Loading..." forever. Nothing here may raise.
        assert parse_created_at("garbage") is None
        assert parse_created_at("") is None
        assert parse_created_at(None) is None
        assert parse_created_at(12345) is None


class TestDeriveStatusUpdates:
    def setup_method(self):
        self.old = (NOW - timedelta(days=45)).isoformat()
        self.recent = (NOW - timedelta(days=5)).isoformat()

    def test_fully_packed_active_session_is_completed(self):
        entries = [_entry(created=self.recent, lists=["a"], progress=_done("a"))]
        assert derive_status_updates(entries, NOW) == {"s": "completed"}

    def test_empty_session_is_not_completed(self):
        assert derive_status_updates([_entry(created=self.recent, lists=[], progress={})], NOW) == {}

    def test_abandoned_session_is_not_completed(self):
        entries = [_entry(status="abandoned", created=self.recent, lists=["a"], progress=_done("a"))]
        assert derive_status_updates(entries, NOW) == {}

    def test_old_active_session_is_archived(self):
        assert derive_status_updates([_entry(created=self.old)], NOW) == {"s": "archived"}

    def test_old_completed_session_is_archived(self):
        assert derive_status_updates([_entry(status="completed", created=self.old)], NOW) == {"s": "archived"}

    def test_abandoned_is_an_explicit_human_judgment_and_is_left_alone(self):
        assert derive_status_updates([_entry(status="abandoned", created=self.old)], NOW) == {}

    def test_already_archived_is_terminal(self):
        assert derive_status_updates([_entry(status="archived", created=self.old)], NOW) == {}

    def test_archive_beats_complete(self):
        entries = [_entry(created=self.old, lists=["a"], progress=_done("a"))]
        assert derive_status_updates(entries, NOW) == {"s": "archived"}

    def test_manual_edit_wins_permanently(self):
        # Without this the automation fights the user: they un-archive an old
        # session and the next refresh archives it straight back.
        assert derive_status_updates([_entry(created=self.old, manual=True)], NOW) == {}
        packed = _entry(created=self.recent, lists=["a"], progress=_done("a"), manual=True)
        assert derive_status_updates([packed], NOW) == {}

    def test_unreadable_date_is_never_archived(self):
        assert derive_status_updates([_entry(created="garbage")], NOW) == {}
        assert derive_status_updates([_entry()], NOW) == {}

    def test_legacy_naive_stamp_older_than_cutoff_does_archive(self):
        # The whole point: this is the entire existing backlog.
        assert derive_status_updates([_entry(created="2026-07-01T09:00:00")], NOW) == {"s": "archived"}

    def test_steady_state_writes_nothing(self):
        entries = [_entry(status="completed", created=self.recent, lists=["a"], progress=_done("a"))]
        assert derive_status_updates(entries, NOW) == {}

    def test_junk_entries_do_not_raise(self):
        assert derive_status_updates([None, "nope", {}, {"session_name": ""}], NOW) == {}
        assert derive_status_updates(None, NOW) == {}
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_session_lifecycle.py -q
```

Expected: collection error — `ModuleNotFoundError: No module named 'shopify_tool.session_lifecycle'`.

- [ ] **Step 3: Write the implementation**

Create `shopify_tool/session_lifecycle.py` with exactly this content:

```python
"""Derive session status from packing progress and age.

Pure functions over the entry dicts `SessionManager.list_client_sessions()`
returns. No I/O and no Qt, so the rules can be tested without a file server
or a QApplication.

Every value read here comes from a file another tool writes, so no shape it
can take may raise -- a session list that will not load is far worse than one
carrying a stale status.
"""

import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Packing Tool's whole-session mode records progress under this literal key
# instead of a packing list's file stem (packing-tool src/main.py:2249). It
# can never match a stem, so a plain "are all lists completed?" check scores
# such a session 0/N forever even though every order in it was packed.
FULL_SESSION_KEY = "full_session"

AUTO_ARCHIVE_AFTER_DAYS = 30

# Statuses the automation is allowed to move a session out of. "abandoned" is
# an explicit human judgment and "archived" is already terminal.
_ARCHIVABLE_FROM = ("active", "completed")


def packing_completion(entry: dict) -> tuple[int, int]:
    """(packed, total) packing lists for one session entry.

    total == 0 means the session has nothing to pack, which is never
    "complete" -- vacuous truth would mark every empty session done.
    """
    stats = entry.get("statistics")
    lists = stats.get("packing_lists") if isinstance(stats, dict) else None
    if not isinstance(lists, list):
        lists = []
    names = [n for n in lists if isinstance(n, str)]

    progress = entry.get("packing_progress")
    if not isinstance(progress, dict):
        progress = {}

    def _done(key: str) -> bool:
        block = progress.get(key)
        # Only "completed" counts; "in_progress" and "paused" do not.
        return isinstance(block, dict) and block.get("status") == "completed"

    total = len(names)
    if _done(FULL_SESSION_KEY):
        # The whole session was packed in one go. Report it as covering every
        # list, and as 1/1 when the lists were never written to disk.
        return (total, total) if total else (1, 1)

    # Denominator is the lists actually on disk, so a progress key with no
    # matching file is ignored rather than able to block completion.
    return sum(1 for name in names if _done(name)), total


def is_fully_packed(entry: dict) -> bool:
    """True only when the session has packing lists and every one is done."""
    packed, total = packing_completion(entry)
    return total > 0 and packed == total


def parse_created_at(value) -> datetime | None:
    """ISO timestamp -> aware datetime, or None if unreadable.

    `.astimezone()` with no argument does both cases in one call: on a naive
    datetime Python attaches the local offset (DST-correctly), and on an
    already-aware one it preserves the instant.

    Reading naive stamps as local rather than skipping them is load-bearing.
    created_at only became offset-aware on 2026-07-27 (PR #253), so every
    session old enough to archive predates the fix -- skipping them would
    archive nothing at all, forever.
    """
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value).astimezone()
    except (ValueError, TypeError, OSError):
        return None


def derive_status_updates(entries, now: datetime) -> dict:
    """{session_name: new_status} for sessions whose status should change.

    Returns only actual changes, so a steady state writes nothing and the
    pass is self-limiting: the first refresh clears the backlog, every later
    one derives an empty set.
    """
    cutoff = now - timedelta(days=AUTO_ARCHIVE_AFTER_DAYS)
    updates = {}

    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        name = entry.get("session_name")
        if not isinstance(name, str) or not name:
            continue
        # Once a human sets a status by hand, this stops managing that session
        # -- otherwise un-archiving an old session just re-archives it.
        if entry.get("status_manually_set"):
            continue

        status = entry.get("status")

        # Archive beats complete: "archived" means get this out of my default
        # view, and the Packing column still shows it was fully packed.
        if status in _ARCHIVABLE_FROM:
            created = parse_created_at(entry.get("created_at"))
            # Never act on a date that could not be read.
            if created is not None and created < cutoff:
                updates[name] = "archived"
                continue

        if status == "active" and is_fully_packed(entry):
            updates[name] = "completed"

    return updates
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_session_lifecycle.py -q
```

Expected: **27 passed**. (This test file was extracted from this plan and run verbatim against the Step 3 implementation before the plan was written — it passes as-is, and `ruff` is clean on both files.)

- [ ] **Step 5: Lint and commit**

```bash
.venv/bin/ruff check shopify_tool/session_lifecycle.py tests/test_session_lifecycle.py --fix
git add shopify_tool/session_lifecycle.py tests/test_session_lifecycle.py
git commit -m "$(cat <<'EOF'
feat: derive session status from packing progress and age

Pure rules module, no I/O and no Qt. Handles Packing Tool's "full_session"
key, which matches no packing list's file stem and would otherwise score a
fully packed session 0/N forever.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01AHLdS7T8RJJP8mDqrtzpLc
EOF
)"
```

---

### Task 2: Batched status writes in SessionManager

**Files:**
- Modify: `shopify_tool/session_manager.py` (add `apply_status_updates`; add a `manual` parameter to `update_session_status` at line 436)
- Test: `tests/test_session_manager.py` (append a new test class)

**Interfaces:**
- Consumes: nothing from Task 1 — this task is independent and can be done in either order.
- Produces: `SessionManager.apply_status_updates(client_id: str, updates: dict[str, str]) -> int` and `SessionManager.update_session_status(session_path: str, status: str, manual: bool = False) -> bool`. Task 3 calls the first; Task 4 calls the second with `manual=True`.

**Why batching is required, not an optimisation:** `update_session_status()` calls `_upsert_index_entry()`, which takes the index lock, reads the whole index, and rewrites it. On the current data **41 of 42 sessions qualify for archiving on the first run**, and the index runs ~1 KB per session — so the per-session path would take 41 locks and write ~34 MB to a UNC share to set 41 strings. The index also now grows with order volume (`completed_orders`), so it gets worse over time.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_session_manager.py`:

```python
class TestBatchStatusUpdates:
    def test_applies_every_update_to_session_info(self, session_manager):
        first = Path(session_manager.create_session("M"))
        second = Path(session_manager.create_session("M"))

        applied = session_manager.apply_status_updates(
            "M", {first.name: "archived", second.name: "completed"}
        )

        assert applied == 2
        assert session_manager.get_session_info(str(first))["status"] == "archived"
        assert session_manager.get_session_info(str(second))["status"] == "completed"

    def test_rewrites_the_index_exactly_once(self, session_manager, monkeypatch):
        # The whole point of the batch path. A test that only checks the
        # resulting statuses passes just as happily with the per-session
        # implementation, which rewrites the entire index once per session.
        names = [Path(session_manager.create_session("M")).name for _ in range(3)]

        calls = []
        original = SessionManager._write_index
        def counting(self, client_sessions_dir, entries):
            calls.append(client_sessions_dir)
            return original(self, client_sessions_dir, entries)
        monkeypatch.setattr(SessionManager, "_write_index", counting)

        session_manager.apply_status_updates("M", dict.fromkeys(names, "archived"))

        assert len(calls) == 1

    def test_index_reflects_the_new_statuses(self, session_manager):
        session_path = Path(session_manager.create_session("M"))

        session_manager.apply_status_updates("M", {session_path.name: "archived"})

        sessions = session_manager.list_client_sessions("M")
        assert [s["status"] for s in sessions] == ["archived"]

    def test_one_bad_session_does_not_stop_the_others(self, session_manager):
        good = Path(session_manager.create_session("M"))

        applied = session_manager.apply_status_updates(
            "M", {"does_not_exist": "archived", good.name: "archived"}
        )

        assert applied == 1
        assert session_manager.get_session_info(str(good))["status"] == "archived"

    def test_empty_updates_writes_nothing(self, session_manager, monkeypatch):
        session_manager.create_session("M")
        monkeypatch.setattr(
            SessionManager, "_write_index",
            lambda *a, **k: pytest.fail("must not touch the index for an empty update set"),
        )
        assert session_manager.apply_status_updates("M", {}) == 0

    def test_invalid_status_is_skipped_not_raised(self, session_manager):
        session_path = Path(session_manager.create_session("M"))
        assert session_manager.apply_status_updates("M", {session_path.name: "bogus"}) == 0
        assert session_manager.get_session_info(str(session_path))["status"] == "active"


class TestManualStatusFlag:
    def test_manual_update_records_the_flag(self, session_manager):
        session_path = session_manager.create_session("M")
        session_manager.update_session_status(session_path, "active", manual=True)
        assert session_manager.get_session_info(session_path)["status_manually_set"] is True

    def test_automatic_update_does_not_set_the_flag(self, session_manager):
        session_path = session_manager.create_session("M")
        session_manager.update_session_status(session_path, "completed")
        assert "status_manually_set" not in session_manager.get_session_info(session_path)
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_session_manager.py -k "BatchStatusUpdates or ManualStatusFlag" -q
```

Expected: FAIL — `AttributeError: 'SessionManager' object has no attribute 'apply_status_updates'`, and `TypeError: update_session_status() got an unexpected keyword argument 'manual'`.

- [ ] **Step 3: Add the `manual` parameter to `update_session_status`**

In `shopify_tool/session_manager.py`, change the signature at line 436 and the body that sets the status. Replace:

```python
    def update_session_status(self, session_path: str, status: str) -> bool:
```

with:

```python
    def update_session_status(self, session_path: str, status: str, manual: bool = False) -> bool:
```

Add to its docstring's `Args:` block, after the `status` line:

```
            manual (bool): True when a human set this status. Records
                `status_manually_set`, which stops session_lifecycle from
                ever managing this session's status again.
```

Then, immediately after the line `session_info["status_updated_at"] = datetime.now().astimezone().isoformat()`, add:

```python
            if manual:
                session_info["status_manually_set"] = True
```

- [ ] **Step 4: Add the batch writer**

Insert this method directly after `update_session_status` (before `update_session_info`):

```python
    def apply_status_updates(self, client_id: str, updates: dict) -> int:
        """Set many sessions' statuses with a single index rewrite.

        `update_session_status` rewrites the whole client index per call, so
        applying a backlog one session at a time is O(N^2) in bytes written
        over a UNC share. Each session_info.json still takes its own lock,
        but the index is written once.

        CORRECTION (applied at Stage C review): this docstring originally
        claimed the per-session lock protects against Packing Tool. It does
        not. Packing Tool's update_session_metadata() read-modify-writes the
        same file WITHOUT taking the sidecar lock, so the lock serializes
        this class against itself only. See the shipped docstring in
        session_manager.py for the accurate wording.

        Best-effort per session: one unwritable session is logged and skipped
        and the rest still apply. Never raises; a session list that will not
        load is worse than one carrying a stale status.

        Returns the number of sessions actually updated.
        """
        if not updates:
            return 0

        client_sessions_dir = self.sessions_root / f"CLIENT_{client_id.upper()}"
        applied = {}

        for session_name, status in updates.items():
            if status not in self.VALID_STATUSES:
                logger.warning(f"Skipping invalid status '{status}' for {session_name}")
                continue
            session_path_obj = client_sessions_dir / session_name
            try:
                with self._locked_session_info(session_path_obj):
                    session_info = self.get_session_info(str(session_path_obj))
                    if not session_info:
                        logger.warning(f"Skipping missing session: {session_path_obj}")
                        continue
                    session_info["status"] = status
                    session_info["status_updated_at"] = datetime.now().astimezone().isoformat()
                    session_info.pop("session_path", None)
                    with open(session_path_obj / "session_info.json", "w", encoding="utf-8") as f:
                        json.dump(session_info, f, indent=2)
                applied[session_name] = session_info
            except Exception:
                logger.exception(f"Failed to apply status to {session_path_obj}")

        if not applied:
            return 0

        # One lock, one rewrite -- the reason this method exists.
        try:
            with self._exclusive_lock(self._index_lock_path(client_sessions_dir)):
                entries = self._read_index(client_sessions_dir) or []
                entries = [e for e in entries if e.get("session_name") not in applied]
                entries.extend(applied.values())
                self._write_index(client_sessions_dir, entries)
        except Exception:
            logger.exception(f"Failed to rewrite session index for CLIENT_{client_id}")

        logger.info(f"Applied {len(applied)} automatic status updates for CLIENT_{client_id}")
        return len(applied)
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_session_manager.py -q
```

Expected: the whole file passes, **8 new tests** included.

- [ ] **Step 6: Ablate the batching to prove the test pins it**

Temporarily change the index block in `apply_status_updates` to call `self._upsert_index_entry(client_sessions_dir / name, info)` in a loop over `applied.items()` instead. Re-run:

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_session_manager.py -k rewrites_the_index_exactly_once -q
```

Expected: **FAIL** with `assert 3 == 1`. Then revert the ablation and confirm it passes again. If it passed while ablated, the test pins nothing and must be fixed before moving on.

- [ ] **Step 7: Lint and commit**

```bash
.venv/bin/ruff check shopify_tool/session_manager.py tests/test_session_manager.py --fix
git add shopify_tool/session_manager.py tests/test_session_manager.py
git commit -m "$(cat <<'EOF'
feat: batch session status writes into one index rewrite

Applying a backlog via update_session_status rewrites the whole client index
once per session. On the current data 41 of 42 sessions archive on first run,
which would write ~34 MB to the share to set 41 strings.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01AHLdS7T8RJJP8mDqrtzpLc
EOF
)"
```

---

### Task 3: Run the sync on the background loader

**Files:**
- Modify: `gui/session_browser_widget.py` (the `SessionLoaderWorker` class, lines 61–103)
- Test: `tests/test_session_browser_lifecycle_sync.py` (create)

**Interfaces:**
- Consumes: `derive_status_updates` from Task 1; `SessionManager.apply_status_updates` from Task 2.
- Produces: a `SessionLoaderWorker` that emits entries whose `status` already reflects the applied updates. Task 4's widget renders those entries unchanged.

This runs on the background thread and touches files only — no widget access — per the repo's hard rule about UI calls off the main thread.

- [ ] **Step 1: Write the failing test**

Create `tests/test_session_browser_lifecycle_sync.py`:

```python
"""The session loader applies automatic status updates before emitting."""
from unittest.mock import Mock

from gui.session_browser_widget import SessionLoaderWorker


def _old_session(name):
    return {
        "session_name": name,
        "status": "active",
        "created_at": "2026-07-01T09:00:00",
        "statistics": {"packing_lists": []},
    }


def test_applies_derived_updates_and_emits_the_new_status():
    manager = Mock()
    manager.list_client_sessions.return_value = [_old_session("2026-07-01_1")]
    worker = SessionLoaderWorker(manager, "M")
    emitted = []
    worker.finished_with_data.connect(emitted.append)

    worker.run()

    manager.apply_status_updates.assert_called_once_with("M", {"2026-07-01_1": "archived"})
    assert emitted[0][0]["status"] == "archived"


def test_no_changes_means_no_write():
    manager = Mock()
    manager.list_client_sessions.return_value = [
        {"session_name": "s", "status": "active", "created_at": "", "statistics": {"packing_lists": []}}
    ]
    worker = SessionLoaderWorker(manager, "M")

    worker.run()

    manager.apply_status_updates.assert_not_called()


def test_a_failing_write_still_emits_the_session_list():
    # A stale status is survivable; a session list that will not load is not.
    manager = Mock()
    manager.list_client_sessions.return_value = [_old_session("2026-07-01_1")]
    manager.apply_status_updates.side_effect = OSError("share unreachable")
    worker = SessionLoaderWorker(manager, "M")
    emitted = []
    worker.finished_with_data.connect(emitted.append)

    worker.run()

    assert len(emitted) == 1
    assert emitted[0][0]["session_name"] == "2026-07-01_1"


def test_cancelled_worker_does_not_write():
    manager = Mock()
    manager.list_client_sessions.return_value = [_old_session("2026-07-01_1")]
    worker = SessionLoaderWorker(manager, "M")
    worker._is_cancelled = True

    worker.run()

    manager.apply_status_updates.assert_not_called()
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_session_browser_lifecycle_sync.py -q
```

Expected: FAIL on the first test — `apply_status_updates` was never called (`Expected 'apply_status_updates' to be called once. Called 0 times.`).

- [ ] **Step 3: Write the implementation**

In `gui/session_browser_widget.py`, add to the imports (after the `from gui.wheel_ignore_combobox import WheelIgnoreComboBox` line):

```python
from shopify_tool.session_lifecycle import derive_status_updates
```

Then in `SessionLoaderWorker.run()`, replace this block:

```python
            if not self._is_cancelled:
                self.finished_with_data.emit(sessions)
                logger.debug(
                    f"Loaded {len(sessions)} sessions for CLIENT_{self.client_id}"
                )
```

with:

```python
            if self._is_cancelled:
                return

            sessions = self._sync_statuses(sessions)

            self.finished_with_data.emit(sessions)
            logger.debug(
                f"Loaded {len(sessions)} sessions for CLIENT_{self.client_id}"
            )
```

and add this method to `SessionLoaderWorker`, directly after `run()`:

```python
    def _sync_statuses(self, sessions):
        """Apply automatic status changes, then reflect them into `sessions`.

        File I/O only -- this runs on a background thread and must never
        touch a widget. Failures are swallowed: a stale status is survivable,
        a session list that will not load is not.
        """
        try:
            updates = derive_status_updates(sessions, datetime.now().astimezone())
            if not updates:
                return sessions
            self.session_manager.apply_status_updates(self.client_id, updates)
            for session in sessions:
                new_status = updates.get(session.get("session_name"))
                if new_status:
                    session["status"] = new_status
        except Exception:
            logger.exception("Automatic session status sync failed; showing stored statuses")
        return sessions
```

`datetime` is already imported at the top of this file.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_session_browser_lifecycle_sync.py -q
```

Expected: **4 passed**.

- [ ] **Step 5: Commit**

```bash
.venv/bin/ruff check gui/session_browser_widget.py tests/test_session_browser_lifecycle_sync.py --fix
git add gui/session_browser_widget.py tests/test_session_browser_lifecycle_sync.py
git commit -m "$(cat <<'EOF'
feat: apply automatic session status updates on the loader thread

Derive-then-apply runs after list_client_sessions and before the emit, so the
write cost stays off the UI thread and the table shows the applied statuses.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01AHLdS7T8RJJP8mDqrtzpLc
EOF
)"
```

---

### Task 4: The Packing column, and retiring the age filter

**Files:**
- Modify: `gui/session_browser_widget.py`
- Delete: `tests/test_session_browser_filter.py`
- Test: `tests/test_session_browser_columns.py` (create)

**Interfaces:**
- Consumes: `packing_completion` from Task 1; `SessionManager.update_session_status(..., manual=True)` from Task 2.
- Produces: nothing further depends on this task.

The display-time age filter is deleted because a persisted, visible, user-editable `archived` status now does its job. That deletion is what pays for the feature.

- [ ] **Step 1: Write the failing test**

Create `tests/test_session_browser_columns.py`:

```python
"""Packing column + archived visibility in the Session Browser."""
from unittest.mock import Mock

import pytest
from PySide6.QtWidgets import QApplication

from gui.session_browser_widget import SessionBrowserWidget


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def widget(qapp):
    w = SessionBrowserWidget(Mock(), parent=None)
    w.current_client_id = "M"
    return w


def _session(name, status="active", lists=(), progress=None):
    return {
        "session_name": name,
        "status": status,
        "created_at": "",
        "statistics": {"packing_lists": list(lists)},
        "packing_progress": progress or {},
    }


def _column_text(widget, header):
    col = next(
        c for c in range(widget.sessions_table.columnCount())
        if widget.sessions_table.horizontalHeaderItem(c).text() == header
    )
    return [widget.sessions_table.item(r, col).text() for r in range(widget.sessions_table.rowCount())]


def _names(widget):
    return [widget.sessions_table.item(r, 0).text() for r in range(widget.sessions_table.rowCount())]


class TestPackingColumn:
    def test_shows_packed_over_total(self, widget):
        widget.sessions_data = [
            _session("s1", lists=["a", "b"], progress={"a": {"status": "completed"}})
        ]
        widget._populate_table()
        assert _column_text(widget, "Packing") == ["1/2"]

    def test_session_with_no_packing_lists_shows_a_dash(self, widget):
        widget.sessions_data = [_session("s1")]
        widget._populate_table()
        assert _column_text(widget, "Packing") == ["—"]

    def test_full_session_key_reads_as_complete(self, widget):
        widget.sessions_data = [
            _session("s1", lists=["a", "b"], progress={"full_session": {"status": "completed"}})
        ]
        widget._populate_table()
        assert _column_text(widget, "Packing") == ["2/2"]


class TestArchivedVisibility:
    def test_archived_sessions_are_hidden_by_default(self, widget):
        widget.sessions_data = [_session("keep"), _session("gone", status="archived")]
        widget._populate_table()
        assert _names(widget) == ["keep"]

    def test_show_archived_toggle_reveals_them(self, widget):
        widget.sessions_data = [_session("keep"), _session("gone", status="archived")]
        widget.show_archived_btn.setChecked(True)
        assert sorted(_names(widget)) == ["gone", "keep"]

    def test_explicit_archived_status_filter_shows_them_with_toggle_off(self, widget):
        # The status filter is server-side: that path returns only archived
        # rows, so hiding them would leave the user staring at an empty table.
        widget.status_filter.setCurrentText("Archived")
        widget.sessions_data = [_session("gone", status="archived")]
        widget._populate_table()
        assert _names(widget) == ["gone"]


def test_manual_status_edit_is_recorded_as_manual(widget):
    widget._on_status_changed("/some/session", "Abandoned")
    widget.session_manager.update_session_status.assert_called_once_with(
        "/some/session", "abandoned", manual=True
    )
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_session_browser_columns.py -q
```

Expected: FAIL — `StopIteration` on the missing "Packing" header, and `AttributeError: 'SessionBrowserWidget' object has no attribute 'show_archived_btn'`.

- [ ] **Step 3: Delete the age filter**

In `gui/session_browser_widget.py`, delete the constant `DEFAULT_SESSION_AGE_CUTOFF_DAYS = 30` and the entire `filter_sessions_by_age` function (lines 32–58), plus the now-unused `timedelta` import (change `from datetime import datetime, timedelta` to `from datetime import datetime`).

Add `packing_completion` to the lifecycle import from Task 3:

```python
from shopify_tool.session_lifecycle import derive_status_updates, packing_completion
```

- [ ] **Step 4: Swap the toggle**

In `__init__`, replace `self._show_older = False` with `self._show_archived = False`.

In `_init_ui`, replace the `show_older_btn` block:

```python
        self.show_older_btn = QPushButton("Show Older (30+ days)")
        self.show_older_btn.setCheckable(True)
        self.show_older_btn.setToolTip("Show sessions older than 30 days")
        self.show_older_btn.toggled.connect(self._on_show_older_toggled)
        filter_layout.addWidget(self.show_older_btn)
```

with:

```python
        self.show_archived_btn = QPushButton("Show Archived")
        self.show_archived_btn.setCheckable(True)
        self.show_archived_btn.setToolTip(
            "Show archived sessions (sessions are archived automatically after 30 days)"
        )
        self.show_archived_btn.toggled.connect(self._on_show_archived_toggled)
        filter_layout.addWidget(self.show_archived_btn)
```

and replace the `_on_show_older_toggled` method:

```python
    def _on_show_older_toggled(self, checked: bool):
        """Toggling this only re-filters the already-loaded self.sessions_data --
        no new file-server call, since the whole index is already in memory."""
        self._show_older = checked
        self._populate_table()
```

with:

```python
    def _on_show_archived_toggled(self, checked: bool):
        """Toggling this only re-filters the already-loaded self.sessions_data --
        no new file-server call, since the whole index is already in memory."""
        self._show_archived = checked
        self._populate_table()
```

- [ ] **Step 5: Add the column and the archived filter**

In `_init_ui`, change `setColumnCount(7)` to `setColumnCount(8)` and the header labels to:

```python
            [
                "Session Name",
                "Created",
                "Status",
                "Orders",
                "Items",
                "Packing Lists",
                "Packing",
                "Comments",
            ]
```

Insert a width rule for the new column before the Comments stretch rule, and move Comments to index 7:

```python
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(6, 90)  # Packing
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)  # Comments
```

In `_populate_table`, replace the age-filter opening:

```python
        cutoff_days = None if self._show_older else DEFAULT_SESSION_AGE_CUTOFF_DAYS
        visible_sessions = filter_sessions_by_age(
            self.sessions_data, cutoff_days, datetime.now().astimezone()
        )
```

with:

```python
        # Archived sessions are hidden unless asked for. When the user picks
        # "Archived" in the status filter the server-side query already
        # returned only archived rows, so hiding them here would leave an
        # empty table.
        showing_archived_explicitly = self.status_filter.currentText().lower() == "archived"
        if self._show_archived or showing_archived_explicitly:
            visible_sessions = list(self.sessions_data)
        else:
            visible_sessions = [
                s for s in self.sessions_data if s.get("status") != "archived"
            ]
```

Add the new cell, immediately after the Column 5 (Packing Lists) block and before Column 6 (Comments):

```python
            # Column 6: Packing progress from Packing Tool (READ-ONLY)
            packed, total = packing_completion(session_info)
            packing_item = QTableWidgetItem(f"{packed}/{total}" if total else "—")
            packing_item.setTextAlignment(Qt.AlignCenter)
            self.sessions_table.setItem(row, 6, packing_item)
```

Change the Comments block's column index from 6 to 7:

```python
            self.sessions_table.setCellWidget(row, 7, comments_edit)
```

Extend the tooltip — replace the `Packing Lists (...)` line and add a packed line:

```python
Packing Lists ({packing_lists_count}): {packing_lists_str}
Packed: {packed}/{total} lists completed in Packing Tool
```

and widen the tooltip loop from `range(7)` to `range(8)`.

- [ ] **Step 6: Record manual status edits**

In `_on_status_changed`, change:

```python
            self.session_manager.update_session_status(session_path, status)
```

to:

```python
            # manual=True stops session_lifecycle from ever managing this
            # session's status again -- otherwise un-archiving an old session
            # would just re-archive it on the next refresh.
            self.session_manager.update_session_status(session_path, status, manual=True)
```

- [ ] **Step 7: Delete the obsolete test file**

```bash
git rm tests/test_session_browser_filter.py
```

Its five cases are re-expressed against `session_lifecycle` in Task 1 — the naive-timestamp regression it guarded is covered by `TestParseCreatedAt::test_unreadable_values_return_none_and_never_raise` and `test_naive_timestamp_becomes_local_aware`.

- [ ] **Step 8: Run the tests to verify they pass**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_session_browser_columns.py tests/test_session_browser_reload.py -q
```

Expected: **11 passed** (7 new + 4 pre-existing reload tests still green).

- [ ] **Step 9: Commit**

```bash
.venv/bin/ruff check gui/session_browser_widget.py tests/test_session_browser_columns.py --fix
git add gui/session_browser_widget.py tests/test_session_browser_columns.py tests/test_session_browser_filter.py
git commit -m "$(cat <<'EOF'
feat: show Packing Tool progress per session; retire the age filter

The 30-day display filter is replaced by a persisted archived status the user
can see and change. The old filter was a no-op on every existing session
anyway: created_at only became offset-aware after those sessions were written.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01AHLdS7T8RJJP8mDqrtzpLc
EOF
)"
```

---

### Task 5: Record the accepted first-run cost, and run the gate

**Files:**
- Modify: `gui/session_browser_widget.py` (one comment)

- [ ] **Step 1: Add the ponytail comment**

At the top of `SessionLoaderWorker._sync_statuses`, directly under the docstring, add:

```python
        # ponytail: the first refresh after this shipped clears the whole
        # backlog in one pass -- 41 of 42 sessions on the data this was built
        # against. It is one-time (the derive returns empty forever after) and
        # runs off the UI thread, so no progress UI or first-run prompt is
        # built. If it drags on the production share, bound the pass to the N
        # oldest sessions per refresh.
```

- [ ] **Step 2: Run the full gate**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
```

Expected: **806 passed** (765 baseline + 46 new − 5 deleted).

```bash
.venv/bin/ruff check . --exclude shared
```

Expected: `All checks passed!`

If the pytest count differs, do not adjust the number to match — find which test changed and why. A pre-existing test breaking is the signal this plan missed an assumption.

- [ ] **Step 3: Verify against the real session data**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -c "
import json
from datetime import datetime
from pathlib import Path
from shopify_tool.session_lifecycle import derive_status_updates, packing_completion
root = Path('../../../dev-server/Sessions')
now = datetime.now().astimezone()
for c in sorted(p for p in root.iterdir() if p.is_dir()):
    entries = [json.loads((s/'session_info.json').read_text()) for s in sorted(c.iterdir()) if (s/'session_info.json').exists()]
    updates = derive_status_updates(entries, now)
    print(c.name, len(entries), 'sessions ->', len(updates), 'updates')
    for e in entries:
        e['status'] = updates.get(e['session_name'], e['status'])
    assert derive_status_updates(entries, now) == {}, 'second pass must be a no-op'
print('idempotent on real data')
"
```

Expected: three clients listed, then `idempotent on real data`. This is the property that makes the pass self-limiting — if a second run produces updates, the automation will rewrite the index on every single refresh forever.

- [ ] **Step 4: Update the knowledge graph and commit**

```bash
graphify update .
git add gui/session_browser_widget.py
git commit -m "$(cat <<'EOF'
docs: record the accepted one-time cost of the first archive pass

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01AHLdS7T8RJJP8mDqrtzpLc
EOF
)"
```

---

## Notes for the implementer

- **`graphify update .` runs AST-only here** — no `GEMINI_API_KEY` is configured on this machine, so it produces code nodes and edges but no doc/image semantic nodes. That is expected, not a failure.
- **Do not `git add -A`** in this worktree — the repo does not ignore `.venv`. Name the files, and check `git show --stat HEAD` after each commit.
- **`../packing-tool` is not modified by this plan.** Everything it needs to provide already shipped in its PR #160. If you find yourself editing it, stop — something in the design was misread.
- The two `full_session` sessions in the real data (`2026-07-01_2`, incomplete; `2026-07-25_1`, complete) are the live fixtures for the trap Task 1 handles. If a change makes them read `0/N`, the `FULL_SESSION_KEY` branch broke.
