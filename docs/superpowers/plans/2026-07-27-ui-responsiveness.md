# UI Responsiveness on Slow File Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the app's slow network file server from freezing the GUI on session-browser load, client switch, sidebar refresh, and config save.

**Architecture:** Two independent workstreams sharing one root cause (synchronous per-file-server-call IO). Workstream 1 adds an incrementally-maintained `session_index.json` per client so listing sessions costs one file read instead of one-per-session. Workstream 2 applies the existing `Worker`(`QRunnable`)/`QThreadPool` pattern to the remaining GUI-thread IO (client switch, sidebar refresh, config save) and closes two caching/dedup gaps found during investigation.

**Tech Stack:** Python, PySide6, pytest (`QT_QPA_PLATFORM=offscreen`). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-07-27-ui-responsiveness-design.md`

## Global Constraints

- No UI calls from background threads (`gui/*` widgets must never be constructed or mutated outside the GUI thread) — PySide6 crashes. Any code that builds/touches a `QWidget` runs only from a `Worker` `result`/`error` signal handler (main thread), never inside a `Worker`'s wrapped function.
- Never hand-edit anything under `shared/` — it's one-way synced from `../packing-tool/shared/` via `scripts/sync_shared.py`.
- No hardcoded colors in stylesheets — use `theme_manager`.
- Run tests with `QT_QPA_PLATFORM=offscreen python -m pytest`.
- After any code change, this repo's `CLAUDE.md` asks for `graphify update .` to be run (last step of this plan).

---

### Task 1: Session index — core read/write + wiring into every session_info.json writer

**Files:**
- Modify: `shopify_tool/session_manager.py`
- Test: `tests/test_session_manager.py`

**Interfaces:**
- Produces (used by Task 2): `SessionManager._read_index(client_sessions_dir: Path) -> list[dict] | None`, `SessionManager._rebuild_index(client_sessions_dir: Path) -> list[dict]`, `SessionManager.INDEX_FILENAME: str = "session_index.json"`.
- Each index entry is a `dict` shaped exactly like `get_session_info()`'s return value minus the `session_path` key, keyed by its own `session_name` field.

- [ ] **Step 1: Write the failing tests for index creation and per-write sync**

Add to `tests/test_session_manager.py`:

```python
class TestSessionIndex:
    def test_create_session_adds_index_entry(self, session_manager):
        session_path = Path(session_manager.create_session("M"))
        index_path = session_path.parent / SessionManager.INDEX_FILENAME
        assert index_path.exists()
        entries = json.loads(index_path.read_text())
        assert len(entries) == 1
        assert entries[0]["session_name"] == session_path.name
        assert entries[0]["status"] == "active"
        assert "session_path" not in entries[0]

    def test_update_session_status_updates_index_entry(self, session_manager):
        session_path = session_manager.create_session("M")
        session_manager.update_session_status(session_path, "completed")
        index_path = Path(session_path).parent / SessionManager.INDEX_FILENAME
        entries = json.loads(index_path.read_text())
        assert entries[0]["status"] == "completed"

    def test_update_session_info_updates_index_entry(self, session_manager):
        session_path = session_manager.create_session("M")
        session_manager.update_session_info(session_path, {"comments": "hi"})
        index_path = Path(session_path).parent / SessionManager.INDEX_FILENAME
        entries = json.loads(index_path.read_text())
        assert entries[0]["comments"] == "hi"

    def test_append_to_session_list_updates_index_entry(self, session_manager):
        session_path = session_manager.create_session("M")
        session_manager.append_to_session_list(session_path, "packing_lists_generated", "a.xlsx")
        index_path = Path(session_path).parent / SessionManager.INDEX_FILENAME
        entries = json.loads(index_path.read_text())
        assert entries[0]["packing_lists_generated"] == ["a.xlsx"]

    def test_second_session_appends_not_replaces_index(self, session_manager):
        session_manager.create_session("M")
        second_path = Path(session_manager.create_session("M"))
        index_path = second_path.parent / SessionManager.INDEX_FILENAME
        entries = json.loads(index_path.read_text())
        assert len(entries) == 2

    def test_rebuild_index_scans_directory_and_writes_index(self, session_manager):
        session_path = Path(session_manager.create_session("M"))
        index_path = session_path.parent / SessionManager.INDEX_FILENAME
        index_path.unlink()  # simulate pre-existing sessions with no index yet
        entries = session_manager._rebuild_index(session_path.parent)
        assert len(entries) == 1
        assert entries[0]["session_name"] == session_path.name
        assert index_path.exists()

    def test_read_index_returns_none_when_missing(self, session_manager, tmp_path):
        empty_dir = tmp_path / "CLIENT_NOINDEX"
        empty_dir.mkdir()
        assert session_manager._read_index(empty_dir) is None

    def test_index_write_failure_does_not_break_session_update(self, session_manager, monkeypatch):
        session_path = session_manager.create_session("M")
        monkeypatch.setattr(
            session_manager, "_upsert_index_entry",
            lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")),
        )
        # The primary session_info.json write must still succeed even if the
        # index-cache update fails.
        assert session_manager.update_session_status(session_path, "completed") is True
        info = session_manager.get_session_info(session_path)
        assert info["status"] == "completed"
```

Add `import json` at the top of `tests/test_session_manager.py` if not already present (check first — `get_session_info` tests may already import it indirectly; this file currently only imports `Path` and `pytest`, so add `import json`).

- [ ] **Step 2: Run tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_session_manager.py::TestSessionIndex -v`
Expected: FAIL — `AttributeError: 'SessionManager' object has no attribute '_read_index'` (or `INDEX_FILENAME` missing).

- [ ] **Step 3: Implement the index core in `shopify_tool/session_manager.py`**

Add `INDEX_FILENAME` as a class attribute next to `VALID_STATUSES` (around line 62):

```python
    # Per-client session index cache filename (see docs/superpowers/specs/2026-07-27-ui-responsiveness-design.md)
    INDEX_FILENAME: ClassVar[str] = "session_index.json"
```

Replace the existing `_locked_session_info` context manager (lines 249-276) with a generalized lock helper plus a thin wrapper, so the same locking primitive can guard the index file too:

```python
    @contextlib.contextmanager
    def _exclusive_lock(self, lock_path: Path):
        """Blocking exclusive lock on an arbitrary sidecar `.lock` file.

        Without this, two near-simultaneous read-modify-write cycles on the
        file `lock_path` guards each read the same on-disk snapshot before
        either writes back, and one update silently loses the other's change.
        """
        with open(lock_path, "a+") as lock_file:
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                yield
            finally:
                if os.name == "nt":
                    import msvcrt
                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    @contextlib.contextmanager
    def _locked_session_info(self, session_path_obj: Path):
        """Blocking exclusive lock spanning a session_info.json read-modify-write."""
        with self._exclusive_lock(session_path_obj / "session_info.json.lock"):
            yield
```

Add the index helpers right after `get_session_info()` (after line 312, before `update_session_status`):

```python
    def _index_lock_path(self, client_sessions_dir: Path) -> Path:
        return client_sessions_dir / f"{self.INDEX_FILENAME}.lock"

    def _read_index(self, client_sessions_dir: Path) -> list[dict] | None:
        """Read the raw index file, or None if it doesn't exist / is unreadable."""
        index_path = client_sessions_dir / self.INDEX_FILENAME
        if not index_path.exists():
            return None
        try:
            with open(index_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            logger.exception("Failed to read session index, treating as missing")
            return None

    def _write_index(self, client_sessions_dir: Path, entries: list[dict]) -> None:
        index_path = client_sessions_dir / self.INDEX_FILENAME
        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2)

    def _scan_sessions(self, client_sessions_dir: Path) -> list[dict]:
        """Full folder scan (the old list_client_sessions behavior) -- used only
        to build/rebuild the index, never on the normal read path."""
        entries = []
        for item in client_sessions_dir.iterdir():
            if not item.is_dir():
                continue
            info = self.get_session_info(str(item))
            if info:
                info.pop("session_path", None)
                entries.append(info)
        return entries

    def _rebuild_index(self, client_sessions_dir: Path) -> list[dict]:
        """Full scan + persist. Called when no index exists yet, or the
        directory count no longer matches the index (see list_client_sessions)."""
        entries = self._scan_sessions(client_sessions_dir)
        with self._exclusive_lock(self._index_lock_path(client_sessions_dir)):
            self._write_index(client_sessions_dir, entries)
        return entries

    def _upsert_index_entry(self, session_path_obj: Path, session_info: dict) -> None:
        """Insert or replace one session's entry in its client's index.

        Best-effort: index-write failures are logged, not raised, since the
        index is a read-side cache and must never block the session_info.json
        write it mirrors.
        """
        try:
            client_sessions_dir = session_path_obj.parent
            entry = dict(session_info)
            entry.pop("session_path", None)
            session_name = session_path_obj.name
            with self._exclusive_lock(self._index_lock_path(client_sessions_dir)):
                entries = self._read_index(client_sessions_dir) or []
                entries = [e for e in entries if e.get("session_name") != session_name]
                entries.append(entry)
                self._write_index(client_sessions_dir, entries)
        except Exception:
            logger.exception(f"Failed to update session index for {session_path_obj}")
```

Wire it into the four writers:

In `create_session()`, right before `return str(session_path)` (currently line 143), add:

```python
            self._upsert_index_entry(session_path, session_info)
            self.profile_manager.invalidate_metadata_cache(client_id)

            logger.info(f"Session created: CLIENT_{client_id}/{session_name}")
            return str(session_path)
```

(This replaces the existing `logger.info(...)` + `return` pair at lines 142-143 — keep the log line, just add the two new calls before it returns.)

In `update_session_status()`, immediately before `return True` (currently line 354), add:

```python
                self._upsert_index_entry(session_path_obj, session_info)
                logger.info(f"Session status updated to '{status}': {session_path}")
                return True
```

(replaces the existing `logger.info` + `return True` pair at lines 353-354)

In `update_session_info()`, immediately before `return True` (currently line 395), add the same pattern:

```python
                self._upsert_index_entry(session_path_obj, session_info)
                logger.info(f"Session info updated: {session_path}")
                return True
```

(replaces lines 394-395)

In `append_to_session_list()`, immediately before `return True` (currently line 438), add:

```python
                self._upsert_index_entry(session_path_obj, session_info)
                logger.info(f"Session info updated: appended '{value}' to '{field}'")
                return True
```

(replaces lines 437-438)

- [ ] **Step 4: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_session_manager.py::TestSessionIndex -v`
Expected: PASS (all 8 tests)

- [ ] **Step 5: Run the full session manager test suite to check nothing broke**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_session_manager.py -v`
Expected: PASS (all tests, including the pre-existing `TestAppendToSessionList` concurrency test)

- [ ] **Step 6: Commit**

```bash
git add shopify_tool/session_manager.py tests/test_session_manager.py
git commit -m "Add incrementally-maintained session index alongside session_info.json writes"
```

---

### Task 2: `list_client_sessions()` reads from the index instead of scanning every session

**Files:**
- Modify: `shopify_tool/session_manager.py:207-247`
- Test: `tests/test_session_manager.py`

**Interfaces:**
- Consumes (from Task 1): `SessionManager._read_index`, `SessionManager._rebuild_index`, `SessionManager.INDEX_FILENAME`.
- No change to `list_client_sessions()`'s public signature or return shape — same `list[dict]`, same fields, same sort order. Existing callers (`gui/session_browser_widget.py`, `gui/ui_manager.py:refresh_recent_sessions`) need no changes.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_session_manager.py`:

```python
class TestListClientSessionsUsesIndex:
    def test_list_matches_previous_full_scan_output(self, session_manager):
        p1 = Path(session_manager.create_session("M"))
        session_manager.update_session_status(p1, "completed")
        p2 = session_manager.create_session("M")
        sessions = session_manager.list_client_sessions("M")
        assert len(sessions) == 2
        names = {s["session_name"] for s in sessions}
        assert names == {p1.name, Path(p2).name}
        # sorted newest first
        assert sessions[0]["created_at"] >= sessions[1]["created_at"]

    def test_status_filter_still_works(self, session_manager):
        p1 = Path(session_manager.create_session("M"))
        session_manager.update_session_status(p1, "completed")
        session_manager.create_session("M")
        active_only = session_manager.list_client_sessions("M", status_filter="active")
        assert len(active_only) == 1

    def test_missing_index_is_built_transparently(self, session_manager):
        session_path = Path(session_manager.create_session("M"))
        index_path = session_path.parent / SessionManager.INDEX_FILENAME
        index_path.unlink()  # simulate a client dir from before this feature
        sessions = session_manager.list_client_sessions("M")
        assert len(sessions) == 1
        assert index_path.exists()  # self-healed

    def test_manually_added_session_folder_triggers_rebuild(self, session_manager):
        session_path = Path(session_manager.create_session("M"))
        # Simulate a session folder restored/copied in without going through
        # create_session (index has no entry for it).
        extra = session_path.parent / "2020-01-01_1"
        extra.mkdir()
        for subdir in SessionManager.SESSION_SUBDIRS:
            (extra / subdir).mkdir()
        (extra / "session_info.json").write_text(json.dumps({
            "session_name": "2020-01-01_1", "status": "active",
            "created_at": "2020-01-01T00:00:00", "client_id": "M",
        }))
        sessions = session_manager.list_client_sessions("M")
        assert len(sessions) == 2  # count mismatch caught it, rebuilt

    def test_no_sessions_dir_returns_empty_list(self, session_manager):
        assert session_manager.list_client_sessions("M") == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_session_manager.py::TestListClientSessionsUsesIndex -v`
Expected: `test_manually_added_session_folder_triggers_rebuild` fails (old code re-scans every call so it'd pass by accident) — actually all should currently pass under the OLD implementation since it always full-scans. Confirm this by running against the current code — this task's real regression check is Step 4 below, showing the same behavior after switching to index reads. Note this in the PR/commit description rather than expecting a red step here.

- [ ] **Step 3: Rewrite `list_client_sessions()` to use the index**

Replace lines 207-247 (`def list_client_sessions` through its `return sessions`):

```python
    def list_client_sessions(
        self,
        client_id: str,
        status_filter: str | None = None
    ) -> list[dict]:
        """List all sessions for a client.

        Reads the per-client session_index.json cache instead of opening every
        session's session_info.json (see docs/superpowers/specs/2026-07-27-ui-responsiveness-design.md).

        Args:
            client_id (str): Client ID
            status_filter (str, optional): Filter by status ("active", "completed", etc.)

        Returns:
            List[Dict]: List of session info dictionaries, sorted by creation date (newest first)
                Each dict contains session metadata including session_name, status, created_at
        """
        client_id = client_id.upper()
        client_sessions_dir = self.sessions_root / f"CLIENT_{client_id}"

        if not client_sessions_dir.exists():
            return []

        entries = self._read_index(client_sessions_dir)
        if entries is None:
            entries = self._rebuild_index(client_sessions_dir)
        else:
            actual_count = sum(1 for item in client_sessions_dir.iterdir() if item.is_dir())
            if actual_count != len(entries):
                entries = self._rebuild_index(client_sessions_dir)

        sessions = []
        for entry in entries:
            session_info = dict(entry)
            session_info["session_path"] = str(client_sessions_dir / session_info["session_name"])
            if status_filter and session_info.get("status") != status_filter:
                continue
            sessions.append(session_info)

        sessions.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return sessions
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_session_manager.py -v`
Expected: PASS (all tests in the file, including Task 1's and the pre-existing suite)

- [ ] **Step 5: Run the full test suite**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest -v`
Expected: PASS. Pay particular attention to any test that constructs a session folder by hand without going through `create_session()` (bypasses the index) — those should self-heal via the count-mismatch rebuild, but confirm no test asserts on `session_index.json` *not* existing.

- [ ] **Step 6: Commit**

```bash
git add shopify_tool/session_manager.py tests/test_session_manager.py
git commit -m "list_client_sessions: read from session index instead of scanning every session folder"
```

---

### Task 3: Session browser — default to last 30 days, "Show older" toggle, stop refetching on every show

**Files:**
- Modify: `gui/session_browser_widget.py`
- Test: `tests/test_session_browser_filter.py` (new — pure-function test, no Qt widgets needed)

**Interfaces:**
- Produces: module-level function `filter_sessions_by_age(sessions: list[dict], cutoff_days: int, now: datetime) -> list[dict]` in `gui/session_browser_widget.py`, used by `SessionBrowserWidget._populate_table()`.
- Consumes: `SessionBrowserWidget.sessions_data` (already exists, list of dicts with `created_at` ISO strings, same shape `list_client_sessions()` returns per Task 2).

- [ ] **Step 1: Write the failing test for the pure filter function**

Create `tests/test_session_browser_filter.py`:

```python
"""Session browser's 30-day default view filter (no Qt needed — pure data)."""
from datetime import datetime, timedelta

from gui.session_browser_widget import filter_sessions_by_age


def _session(days_old: int) -> dict:
    created = (datetime.now().astimezone() - timedelta(days=days_old)).isoformat()
    return {"session_name": f"session_{days_old}d", "created_at": created}


class TestFilterSessionsByAge:
    def test_keeps_sessions_within_cutoff(self):
        sessions = [_session(5), _session(10)]
        result = filter_sessions_by_age(sessions, cutoff_days=30, now=datetime.now().astimezone())
        assert len(result) == 2

    def test_drops_sessions_older_than_cutoff(self):
        sessions = [_session(5), _session(45)]
        result = filter_sessions_by_age(sessions, cutoff_days=30, now=datetime.now().astimezone())
        assert len(result) == 1
        assert result[0]["session_name"] == "session_5d"

    def test_missing_created_at_is_kept_not_dropped(self):
        # Never hide a session just because its date couldn't be parsed --
        # that would silently disappear real data from the default view.
        sessions = [{"session_name": "no_date"}]
        result = filter_sessions_by_age(sessions, cutoff_days=30, now=datetime.now().astimezone())
        assert len(result) == 1

    def test_cutoff_none_returns_all_sessions(self):
        sessions = [_session(5), _session(400)]
        result = filter_sessions_by_age(sessions, cutoff_days=None, now=datetime.now().astimezone())
        assert len(result) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_session_browser_filter.py -v`
Expected: FAIL with `ImportError: cannot import name 'filter_sessions_by_age'`

- [ ] **Step 3: Implement the filter function and wire it into the widget**

Add near the top of `gui/session_browser_widget.py`, after the imports (after line 30's `logger = ...`):

```python
DEFAULT_SESSION_AGE_CUTOFF_DAYS = 30


def filter_sessions_by_age(sessions: list, cutoff_days: int | None, now: datetime) -> list:
    """Keep sessions created within the last `cutoff_days`. `cutoff_days=None`
    disables filtering (the "Show older" state). Sessions with an unparsable
    or missing created_at are kept -- never hide real data because of a
    formatting issue in a single record.
    """
    if cutoff_days is None:
        return list(sessions)
    cutoff = now - timedelta(days=cutoff_days)
    kept = []
    for session in sessions:
        created_at = session.get("created_at", "")
        try:
            created = datetime.fromisoformat(created_at)
        except (ValueError, TypeError):
            kept.append(session)
            continue
        if created >= cutoff:
            kept.append(session)
    return kept
```

Add the `timedelta` import — change line 8 from `from datetime import datetime` to:

```python
from datetime import datetime, timedelta
```

Add a "Show older" toggle button next to `refresh_btn` in `_init_ui()` (after line 138's `filter_layout.addWidget(self.refresh_btn)`):

```python
        self.show_older_btn = QPushButton("Show Older (30+ days)")
        self.show_older_btn.setCheckable(True)
        self.show_older_btn.setToolTip("Show sessions older than 30 days")
        self.show_older_btn.toggled.connect(self._on_show_older_toggled)
        filter_layout.addWidget(self.show_older_btn)
```

Add the toggle handler and a dirty-flag mechanism. Add to `__init__` (after line 106's `self.worker = None`):

```python
        self._show_older = False
        self._is_dirty = True  # forces one load on first show
```

Add after `_apply_filter` (after line 432, before `_on_selection_changed`):

```python
    def _on_show_older_toggled(self, checked: bool):
        """Toggling this only re-filters the already-loaded self.sessions_data --
        no new file-server call, since the whole index is already in memory."""
        self._show_older = checked
        self._populate_table()

    def mark_dirty(self):
        """Call this whenever a session is created/updated for the client this
        widget is currently showing, so the next showEvent() actually refreshes
        instead of reusing a stale table."""
        self._is_dirty = True
```

Change `_populate_table()`'s first two lines (currently lines 326-329) to filter before rendering:

```python
    def _populate_table(self):
        """Populate the table with sessions data."""
        cutoff_days = None if self._show_older else DEFAULT_SESSION_AGE_CUTOFF_DAYS
        visible_sessions = filter_sessions_by_age(
            self.sessions_data, cutoff_days, datetime.now().astimezone()
        )
        self.sessions_table.setSortingEnabled(False)
        self.sessions_table.setRowCount(len(visible_sessions))

        for row, session_info in enumerate(visible_sessions):
```

(the rest of the method body is unchanged — it already iterates `enumerate(...)`, just now over `visible_sessions` instead of `self.sessions_data`)

Change `refresh_sessions()` to clear the dirty flag once a load starts (add right after the existing docstring, before the `if not self.current_client_id:` check at line 229):

```python
    def refresh_sessions(self):
        """Reload sessions from the session manager."""
        self._is_dirty = False
        if not self.current_client_id:
```

Change `showEvent()` (currently line 546) to only refresh when dirty:

```python
    def showEvent(self, event):
        """Refresh only if something changed since the last load -- avoids
        re-fetching from the file server every time this widget becomes
        visible with nothing new to show."""
        super().showEvent(event)
        if self._is_dirty:
            self.refresh_sessions()
```

(Read the existing `showEvent()` body first — `Read gui/session_browser_widget.py` around line 546-554 — and replace its unconditional refresh call with the above, preserving any existing `super().showEvent(event)` call already there.)

- [ ] **Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_session_browser_filter.py -v`
Expected: PASS (all 4 tests)

- [ ] **Step 5: Wire `mark_dirty()` where session data changes without the browser knowing**

Session creation (`gui/actions_handler.py:78-92`) already calls `self.mw.session_browser.refresh_sessions()` directly right after `create_session()` succeeds (line 92) — that path needs no `mark_dirty()` call, it already forces a fresh load regardless of the dirty flag.

The gap `mark_dirty()` actually closes: `gui/actions_handler.py:832-835` updates a session's `statistics.packing_lists_count`/`packing_lists` via `update_session_info()` after generating a packing-list report, but never tells the session browser — if that widget was already loaded and is later shown again (e.g. the user was on a different tab while the report was generated), it would display stale packing-list counts. Add the call right after the existing `update_session_info()` call:

```python
                            # Save updated statistics
                            self.mw.session_manager.update_session_info(
                                str(session_path), {"statistics": current_stats}
                            )
                            if hasattr(self.mw, "session_browser"):
                                self.mw.session_browser.mark_dirty()

                            self.log.info(
                                f"Updated session statistics: {len(packing_lists_files)} packing lists"
                            )
```

(This replaces lines 832-839, inserting the two new lines between the existing `update_session_info()` call and the existing `self.log.info(...)` line — no other lines in this block change.)

- [ ] **Step 6: Run the full test suite**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add gui/session_browser_widget.py gui/main_window_pyside.py tests/test_session_browser_filter.py
git commit -m "Session browser: default to last 30 days, add Show Older toggle, avoid refetch on every show"
```

---

### Task 4: Cache `load_client_config()` the same way `load_shopify_config()` is already cached

**Files:**
- Modify: `shopify_tool/profile_manager.py:881-925` (`load_client_config`), `:1477-1562` (`save_client_config`)
- Test: `tests/test_profile_manager.py`

**Interfaces:**
- No signature change to `load_client_config()` or `save_client_config()`. Uses the existing `_config_cache: ClassVar[dict[str, tuple[dict, float]]]` (already defined at `profile_manager.py:73`), with a new cache-key prefix `client_` (parallel to the existing `shopify_` prefix used by `load_shopify_config`).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_profile_manager.py`:

```python
class TestLoadClientConfigCaching:
    def test_second_load_is_served_from_cache(self, profile_manager, monkeypatch):
        profile_manager.create_client_profile("M", "Client")
        first = profile_manager.load_client_config("M")
        call_count = {"n": 0}
        original_open = open

        def counting_open(*args, **kwargs):
            if "client_config.json" in str(args[0]):
                call_count["n"] += 1
            return original_open(*args, **kwargs)

        monkeypatch.setattr("builtins.open", counting_open)
        second = profile_manager.load_client_config("M")
        assert second == first
        assert call_count["n"] == 0  # served from cache, file not reopened

    def test_cache_invalidated_after_save(self, profile_manager):
        profile_manager.create_client_profile("M", "Client")
        config = profile_manager.load_client_config("M")
        config["client_name"] = "Renamed"
        profile_manager.save_client_config("M", config)
        reloaded = profile_manager.load_client_config("M")
        assert reloaded["client_name"] == "Renamed"

    def test_cache_reflects_external_mtime_change(self, profile_manager):
        # Simulates another PC on the file server saving a change: same
        # mtime-based invalidation load_shopify_config already relies on.
        profile_manager.create_client_profile("M", "Client")
        profile_manager.load_client_config("M")  # warm the cache
        config_path = profile_manager.get_client_directory("M") / "client_config.json"
        data = json.loads(config_path.read_text())
        data["client_name"] = "Changed Externally"
        config_path.write_text(json.dumps(data))
        import os
        import time
        # Ensure a distinct mtime on filesystems with coarse mtime resolution.
        newer = os.path.getmtime(config_path) + 1
        os.utime(config_path, (newer, newer))
        reloaded = profile_manager.load_client_config("M")
        assert reloaded["client_name"] == "Changed Externally"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_profile_manager.py::TestLoadClientConfigCaching -v`
Expected: `test_second_load_is_served_from_cache` FAILS (`call_count["n"] == 1`, not 0) since there's no cache yet. The other two should pass already (harmless to include — they lock in behavior the cache must not break).

- [ ] **Step 3: Add mtime-based caching to `load_client_config()`, matching `load_shopify_config()`'s pattern**

Read `shopify_tool/profile_manager.py:927-1002` (`load_shopify_config`) first to copy its exact cache-check/cache-store shape. Replace `load_client_config()` (lines 881-925) with:

```python
    def load_client_config(self, client_id: str) -> dict | None:
        """Load general configuration for a client, with mtime-based caching.

        Cache is invalidated by file mtime rather than TTL: no stale reads after
        another PC saves a change, and no unnecessary re-reads while the file is
        stable. Mirrors load_shopify_config()'s cache exactly.

        Automatically migrates old configs to add ui_settings if missing.

        Args:
            client_id (str): Client ID

        Returns:
            Optional[Dict]: Configuration dictionary or None if not found
        """
        client_id = client_id.upper()
        cache_key = f"{self.base_path}::client_{client_id}"
        config_path = self.clients_dir / f"CLIENT_{client_id}" / "client_config.json"

        if not config_path.exists():
            logger.warning(f"Client config not found: CLIENT_{client_id}")
            return None

        try:
            current_mtime = config_path.stat().st_mtime
        except OSError:
            current_mtime = None

        if current_mtime is not None and cache_key in self._config_cache:
            cached_data, cached_mtime = self._config_cache[cache_key]
            if cached_mtime == current_mtime:
                logger.debug(f"Using cached client config for {client_id}")
                return cached_data.copy()

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)

            # Check if migrations are needed
            migrated = self._migrate_add_ui_settings(client_id, config)

            if migrated:
                # If config was migrated, save it immediately
                self.save_client_config(client_id, config)
                logger.info(f"Config migrations completed for CLIENT_{client_id}")
                # save_client_config() invalidates cache_key; re-stat so this
                # call still populates the cache with the post-migration mtime.
                try:
                    current_mtime = config_path.stat().st_mtime
                except OSError:
                    current_mtime = None

            if current_mtime is not None:
                self._config_cache[cache_key] = (config.copy(), current_mtime)

            return config

        except PermissionError:
            logger.exception(
                f"Permission denied reading client config for CLIENT_{client_id}"
            )
            return None
        except json.JSONDecodeError:
            logger.exception(f"Invalid JSON in client config for CLIENT_{client_id}")
            return None
        except Exception:
            logger.exception(
                f"Unexpected error loading client config for CLIENT_{client_id}",
            )
            return None
```

- [ ] **Step 4: Invalidate the cache in `save_client_config()`**

In `save_client_config()`, find the `if success:` block (currently lines 1532-1537) and add the cache invalidation, matching `save_shopify_config()`'s pattern at line 1069-1071:

```python
                if success:
                    # Invalidate cache
                    cache_key = f"{self.base_path}::client_{client_id}"
                    self._config_cache.pop(cache_key, None)

                    logger.info(
                        f"Client config saved successfully for CLIENT_{client_id} "
                        f"(attempt {attempt + 1}/{max_retries})"
                    )
                    return True
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_profile_manager.py -v`
Expected: PASS (all tests, including the new `TestLoadClientConfigCaching` class and every pre-existing test — this is a purely additive caching layer with no behavior change for callers)

- [ ] **Step 6: Run the full test suite**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest -v`
Expected: PASS. Watch specifically `tests/test_groups_manager.py` (its `get_clients_in_group()` calls `load_client_config()` per client — should still pass unchanged, just faster on repeat calls) and `tests/test_session_manager.py` (unaffected, different config file).

- [ ] **Step 7: Commit**

```bash
git add shopify_tool/profile_manager.py tests/test_profile_manager.py
git commit -m "Cache load_client_config() with the same mtime pattern load_shopify_config() already uses"
```

---

### Task 5: Move `on_client_changed()`'s IO off the GUI thread, drop the redundant duplicate load

**Files:**
- Modify: `gui/main_window_pyside.py:804-881`
- Test: manual (see Step 4) — this task wires GUI-thread scheduling around already-tested `profile_manager`/`table_config_manager` calls; no new pure logic to unit test. Per the "lazy code without its check is unfinished" rule, the runnable check here is the manual verification in Step 4, since this task has no branch/loop/parser logic of its own to assert on — it only reorders where already-tested calls happen.

**Interfaces:**
- Consumes: `gui.worker.Worker(fn, *args, **kwargs)` (existing, `gui/worker.py:22`), `self.threadpool` (existing `QThreadPool`, `main_window_pyside.py:86`), `profile_manager.load_shopify_config`, `table_config_manager.load_config` (both already covered by existing tests — unchanged).
- Produces: `MainWindow._load_client_data(client_id: str) -> tuple[dict | None, object]` — the new IO-only function run inside the `Worker`, returning `(shopify_config, table_config)`.

- [ ] **Step 1: Extract the IO into a plain function with no UI calls**

In `gui/main_window_pyside.py`, add a new method right before `on_client_changed` (before line 804):

```python
    def _load_client_data(self, client_id: str):
        """Pure IO for a client switch -- no UI calls, safe to run in a Worker.

        Returns (shopify_config, table_config). table_config is None if
        table_config_manager isn't set up yet (mirrors the existing
        `hasattr(self, "table_config_manager")` guard).
        """
        shopify_config = self.profile_manager.load_shopify_config(client_id)
        table_config = None
        if hasattr(self, "table_config_manager"):
            table_config = self.table_config_manager.load_config(client_id)
        return shopify_config, table_config
```

- [ ] **Step 2: Rewrite `on_client_changed()` to run that function in a `Worker`**

Replace `on_client_changed()` (lines 804-881) with:

```python
    def on_client_changed(self, client_id: str):
        """Handle client selection change.

        Args:
            client_id: Newly selected client ID
        """
        logger.info(f"Client changed to: {client_id}")

        if hasattr(self, "statusBar"):
            self.statusBar().showMessage(f"Loading CLIENT_{client_id}...", 5000)

        if hasattr(self, "client_sidebar"):
            self.client_sidebar.set_active_client(client_id)

        if hasattr(self, "current_client_label"):
            self.current_client_label.setText(f"CLIENT_{client_id}")

        self.current_client_id = client_id

        worker = Worker(self._load_client_data, client_id)
        worker.signals.result.connect(
            lambda result, cid=client_id: self._on_client_data_loaded(cid, result)
        )
        worker.signals.error.connect(self._on_client_data_load_error)
        self.threadpool.start(worker)

    def _on_client_data_loaded(self, client_id: str, result):
        """Apply client-switch IO results to the UI (main thread only)."""
        shopify_config, table_config = result

        if client_id != self.current_client_id:
            # User switched again before this load finished -- discard stale result.
            logger.debug(f"Discarding stale client-load result for {client_id}")
            return

        if not shopify_config:
            QMessageBox.warning(
                self,
                "Configuration Error",
                f"Failed to load configuration for client {client_id}",
            )
            return

        try:
            self.current_client_config = shopify_config
            if table_config is not None:
                logger.info(f"Table configuration loaded for CLIENT_{client_id}")

            # Clear currently loaded files (they're for different client)
            self.orders_file_path = None
            self.stock_file_path = None
            self.orders_file_path_label.setText("No file loaded")
            self.stock_file_path_label.setText("No file loaded")
            self.orders_file_status_label.setText("")
            self.stock_file_status_label.setText("")

            # Clear session
            self.session_path = None
            if hasattr(self, "undo_manager"):
                self.undo_manager.reset_for_session()
            self.update_session_info_label()

            # Update session browser to show this client's sessions
            self.session_browser.set_client(client_id, auto_refresh=False)

            # Update the Recent Sessions quick-pick in the right panel (Tab 1)
            self.ui_manager.refresh_recent_sessions(client_id)

            self.update_ui_state()

            logger.info(f"Client {client_id} loaded successfully")

            if hasattr(self, "statusBar"):
                self.statusBar().showMessage(f"CLIENT_{client_id} loaded", 2000)

        except Exception as e:
            logger.exception("Error applying loaded client data")
            QMessageBox.critical(self, "Error", f"Failed to change client: {e!s}")

    def _on_client_data_load_error(self, error):
        exctype, value, tb = error
        logger.error(f"Error loading client data: {value}\n{tb}")
        QMessageBox.critical(self, "Error", f"Failed to change client: {value!s}")
```

Note what was dropped versus the original: the second `self.load_client_config(client_id)` call (previously line 841, marked "for backward compatibility") is gone — `self.current_client_config` is now set directly from the `load_shopify_config()` result already fetched by `_load_client_data`, which is what that redundant call was duplicating.

Confirm `Worker` is imported in this file (`from gui.worker import Worker`) — add it near the top if it's not already there (check the existing import block first; `gui/actions_handler.py` already imports it as `from gui.worker import Worker`, use the same import path).

- [ ] **Step 3: Search for other callers of `self.load_client_config(` in this file**

Run: `grep -n "load_client_config" gui/main_window_pyside.py`

If `MainWindow.load_client_config()` (the method previously called for "backward compatibility") has no other callers left after this change, leave it in place (out of scope to remove unused methods not part of this task) — just confirm `on_client_changed`'s removal of the call doesn't break anything else that depended on a side effect of that call (read its body to check: does it set any instance attribute other threads/methods read? If yes, ensure `_on_client_data_loaded` sets that same attribute directly from `shopify_config` instead).

- [ ] **Step 4: Manual verification**

Run: `python gui_main.py` (or `python run_dev.py` against the dev fixture).
- Switch between at least two clients (e.g. CLIENT_ALMADERM, CLIENT_HERBAR from `dev-server/`).
- Confirm the client config, table columns, and recent-sessions list all update correctly for each.
- Confirm the GUI does not freeze during the switch (drag the window while switching, on a client with a large `shopify_config.json` like CLIENT_WATERDROP, to feel responsiveness).
- Switch clients twice in rapid succession; confirm no crash and the final UI state matches the *last* client selected (tests the stale-result guard in `_on_client_data_loaded`).

- [ ] **Step 5: Run the full test suite**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest -v`
Expected: PASS (no test directly calls `on_client_changed`, but confirm no import errors)

- [ ] **Step 6: Commit**

```bash
git add gui/main_window_pyside.py
git commit -m "Move client-switch IO off the GUI thread, drop redundant duplicate config load"
```

---

### Task 6: Move `ClientSidebar.refresh()`'s data gathering off the GUI thread

**Files:**
- Modify: `gui/client_sidebar.py:292-509`
- Test: manual (see Step 5) — same rationale as Task 5: this task reorders existing, already-covered profile_manager/groups_manager calls around a thread boundary; it introduces one new pure function (`_gather_refresh_data`) worth a direct test since it's plain data logic with no Qt dependency.
- Test: `tests/test_client_sidebar_refresh.py` (new)

**Interfaces:**
- Produces: `ClientSidebar._gather_refresh_data() -> dict` — no Qt objects, safe to run in a `Worker`. Shape:
  ```python
  {
      "special_groups": dict,       # from groups_manager.load_groups()
      "custom_groups": list[dict],  # from groups_manager.list_groups()
      "all_clients": list[str],     # from profile_manager.list_clients()
      "pinned_client_ids": set[str],
      "group_members": dict[str, list[str]],   # group_id -> client_ids
      "card_data": dict[str, dict], # client_id -> profile_manager.get_client_config_extended(client_id)
  }
  ```
- Consumes: `_create_pinned_section`, `_create_group_section`, `_create_all_section`, `_create_client_card` (all modified in this task to accept the gathered data instead of calling `profile_manager`/`groups_manager` themselves).

- [ ] **Step 1: Write the failing test for the data-gathering function**

Create `tests/test_client_sidebar_refresh.py`. This needs a real `QApplication` instance because `ClientSidebar` is a `QWidget` even though `_gather_refresh_data()` itself touches no Qt state — use the `qtbot`-free minimal pattern already used elsewhere in this test suite (check `tests/conftest.py` for an existing `qapp`/`QApplication` fixture first; if none exists, add one scoped to this file):

```python
"""ClientSidebar's pure data-gathering step (no widget construction --
must be safe to run off the GUI thread per this repo's threading rule)."""
import pytest
from PySide6.QtWidgets import QApplication

from gui.client_sidebar import ClientSidebar


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def sidebar(qapp, profile_manager, groups_manager):
    return ClientSidebar(profile_manager, groups_manager)


class TestGatherRefreshData:
    def test_gather_includes_all_clients(self, sidebar, profile_manager):
        profile_manager.create_client_profile("M", "Client M")
        profile_manager.create_client_profile("N", "Client N")
        data = sidebar._gather_refresh_data()
        assert set(data["all_clients"]) == {"M", "N"}

    def test_gather_flags_pinned_clients(self, sidebar, profile_manager):
        profile_manager.create_client_profile("M", "Client M")
        profile_manager.update_ui_settings("M", {"is_pinned": True})
        data = sidebar._gather_refresh_data()
        assert "M" in data["pinned_client_ids"]

    def test_gather_returns_no_qt_objects(self, sidebar, profile_manager):
        profile_manager.create_client_profile("M", "Client M")
        data = sidebar._gather_refresh_data()
        import json
        json.dumps(data, default=str)  # must be plain-data serializable
```

Confirmed signatures: `ClientSidebar.__init__(self, profile_manager: ProfileManager, groups_manager: GroupsManager, parent=None)` (`gui/client_sidebar.py:169-174`) and `GroupsManager.__init__(self, base_path: str)` (`shopify_tool/groups_manager.py:48`) — `GroupsManager` takes a base path, not a `profile_manager`. If `conftest.py` has no `groups_manager` fixture, add one:

```python
@pytest.fixture
def groups_manager(profile_manager):
    from shopify_tool.groups_manager import GroupsManager
    return GroupsManager(profile_manager.base_path)
```

Note `ClientSidebar.__init__` calls `self.refresh()` at the end of construction (`gui/client_sidebar.py:198`) — after this task, that means construction kicks off a background `Worker` rather than blocking; the widget starts with empty sections until the result arrives. This is expected (it's the whole point), just don't be surprised by it in the test or in Step 5's manual check.

- [ ] **Step 2: Run tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_client_sidebar_refresh.py -v`
Expected: FAIL — `AttributeError: 'ClientSidebar' object has no attribute '_gather_refresh_data'`

- [ ] **Step 3: Implement `_gather_refresh_data()` and rewire the `_create_*` methods**

Read `gui/client_sidebar.py:292-509` in full first (already read during planning — reproduced above) before editing, to preserve every existing line not called out below.

Add `_gather_refresh_data()` right before `refresh()` (before line 292):

```python
    def _gather_refresh_data(self) -> dict:
        """All the file-server IO refresh() needs, with zero Qt object
        construction -- safe to run in a background Worker.
        """
        groups_data = self.groups_manager.load_groups()
        special_groups = groups_data.get("special_groups", {})
        custom_groups = self.groups_manager.list_groups()
        all_clients = self.profile_manager.list_clients()

        pinned_client_ids = set()
        card_data = {}
        for client_id in all_clients:
            ui_settings = self.profile_manager.get_ui_settings(client_id)
            if ui_settings.get("is_pinned", False):
                pinned_client_ids.add(client_id)
            card_data[client_id] = self.profile_manager.get_client_config_extended(client_id)

        group_members = {}
        for group in custom_groups:
            group_id = group.get("id")
            group_members[group_id] = self.groups_manager.get_clients_in_group(
                group_id, self.profile_manager
            )

        return {
            "special_groups": special_groups,
            "custom_groups": custom_groups,
            "all_clients": all_clients,
            "pinned_client_ids": pinned_client_ids,
            "group_members": group_members,
            "card_data": card_data,
        }
```

Replace `refresh()` (lines 292-395) to start a `Worker` running `_gather_refresh_data`, and move the widget-building portion into a new `_apply_refresh_data()`:

```python
    def refresh(self):
        """Refresh client list and rebuild sections.

        Data gathering runs off the GUI thread (Worker); section/card widget
        construction stays on the GUI thread (Qt requirement) and happens in
        _apply_refresh_data() once the data is ready.
        """
        self.refresh_btn.setEnabled(False)
        worker = Worker(self._gather_refresh_data)
        worker.signals.result.connect(self._apply_refresh_data)
        worker.signals.error.connect(self._on_refresh_error)
        QThreadPool.globalInstance().start(worker)

    def _on_refresh_error(self, error):
        exctype, value, tb = error
        logger.error(f"Sidebar refresh failed: {value}\n{tb}")
        self.refresh_btn.setEnabled(True)
        QMessageBox.warning(self, "Refresh Error", f"Failed to refresh sidebar:\n{value!s}")

    def _apply_refresh_data(self, data: dict):
        """Build section/card widgets from already-fetched data (main thread only)."""
        import time

        theme = get_theme_manager().get_current_theme()

        try:
            overall_start = time.time()
            logger.info("Applying sidebar refresh data")

            self.setUpdatesEnabled(False)

            while self.sections_layout.count() > 1:
                item = self.sections_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            self.client_cards.clear()

            all_clients = data["all_clients"]
            special_groups = data["special_groups"]
            custom_groups = data["custom_groups"]
            clients_in_sections = set()

            # 1. Pinned section
            pinned_config = special_groups.get("pinned", {})
            pinned_section = self._create_pinned_section(all_clients, pinned_config, data)
            if pinned_section.card_count() > 0:
                self.sections_layout.insertWidget(self.sections_layout.count() - 1, pinned_section)
                clients_in_sections.update(self._get_section_client_ids(pinned_section))

            # 2. Custom groups
            for group in custom_groups:
                group_id = group.get("id")
                group_name = group.get("name", "Unknown")
                group_color = group.get("color", theme.accent_blue)
                group_section = self._create_group_section(group_id, group_name, group_color, all_clients, data)
                if group_section.card_count() > 0:
                    self.sections_layout.insertWidget(self.sections_layout.count() - 1, group_section)
                    clients_in_sections.update(self._get_section_client_ids(group_section))

            # 3. All Clients section
            all_config = special_groups.get("all", {})
            remaining_clients = [c for c in all_clients if c not in clients_in_sections]
            if remaining_clients:
                all_section = self._create_all_section(remaining_clients, all_config, data)
                self.sections_layout.insertWidget(self.sections_layout.count() - 1, all_section)

            self.setUpdatesEnabled(True)

            if self.active_client_id:
                self.set_active_client(self.active_client_id)

            overall_elapsed = (time.time() - overall_start) * 1000
            logger.info(
                f"Sidebar refresh applied: {len(all_clients)} clients, "
                f"{len(custom_groups)} groups in {overall_elapsed:.1f}ms"
            )

        except Exception as e:
            self.setUpdatesEnabled(True)
            logger.exception("Failed to apply sidebar refresh data")
            QMessageBox.warning(self, "Refresh Error", f"Failed to refresh sidebar:\n{e!s}")
        finally:
            self.refresh_btn.setEnabled(True)
```

Update `_create_pinned_section`, `_create_group_section`, `_create_all_section`, `_create_client_card` to take the pre-fetched `data` dict instead of calling `profile_manager`/`groups_manager`:

```python
    def _create_pinned_section(self, all_clients: list[str], config: dict, data: dict) -> SectionWidget:
        theme = get_theme_manager().get_current_theme()
        section = SectionWidget(
            config.get("name", "Pinned"),
            config.get("color", theme.accent_orange)
        )
        for client_id in all_clients:
            if client_id in data["pinned_client_ids"]:
                card = self._create_client_card(client_id, data)
                section.add_card(card)
        return section

    def _create_group_section(
        self,
        group_id: str,
        group_name: str,
        group_color: str,
        all_clients: list[str],
        data: dict,
    ) -> SectionWidget:
        section = SectionWidget(group_name, group_color)
        clients_in_group = data["group_members"].get(group_id, [])
        for client_id in clients_in_group:
            if client_id in all_clients:
                card = self._create_client_card(client_id, data)
                section.add_card(card)
        return section

    def _create_all_section(self, clients: list[str], config: dict, data: dict) -> SectionWidget:
        theme = get_theme_manager().get_current_theme()
        default_color = theme.border
        section = SectionWidget(
            config.get("name", "All Clients"),
            config.get("color", default_color)
        )
        for client_id in clients:
            card = self._create_client_card(client_id, data)
            section.add_card(card)
        return section

    def _create_client_card(self, client_id: str, data: dict) -> ClientCard:
        config = data["card_data"][client_id]

        client_name = config.get("client_name", f"CLIENT_{client_id}")
        metadata = config.get("metadata", {})
        ui_settings = config.get("ui_settings", {})

        is_active = (client_id == self.active_client_id)

        card = ClientCard(
            client_id=client_id,
            client_name=client_name,
            metadata=metadata,
            ui_settings=ui_settings,
            is_active=is_active
        )
        card.client_selected.connect(self.client_selected.emit)
        card.context_menu_requested.connect(self._show_context_menu)

        if client_id not in self.client_cards:
            self.client_cards[client_id] = []
        self.client_cards[client_id].append(card)

        return card
```

Confirmed via `grep -n "_create_client_card\|_create_pinned_section\|_create_group_section\|_create_all_section" gui/client_sidebar.py`: the only callers of these four methods are inside `refresh()`'s own body (now `_apply_refresh_data()`, already updated above) — no other call sites exist, so no further updates are needed elsewhere in the file.

Ensure `QThreadPool` and `Worker` are imported at the top of `gui/client_sidebar.py`:

```python
from PySide6.QtCore import QThreadPool
from gui.worker import Worker
```

(check existing imports first and merge rather than duplicate)

- [ ] **Step 4: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_client_sidebar_refresh.py -v`
Expected: PASS

- [ ] **Step 5: Manual verification**

Run: `python run_dev.py`.
- Confirm the sidebar populates correctly on startup (pinned/groups/all sections, correct client names and metadata).
- Pin/unpin a client, create a custom group and move a client into it, confirm sections update correctly after each action (each of these already calls `refresh()` per the existing code — confirm they still work through the new async path).
- Confirm no UI freeze (or a much shorter one) during refresh, and no crash/warning in the console about cross-thread widget access.

- [ ] **Step 6: Run the full test suite**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add gui/client_sidebar.py tests/test_client_sidebar_refresh.py
git commit -m "Move ClientSidebar.refresh() data gathering to a background Worker"
```

---

### Task 7: Wrap config save calls in a Worker so Save doesn't block on lock-retry

**Files:**
- Modify: `gui/client_settings_dialog.py:599-633` (`_save_and_accept`)
- Modify: `gui/settings_window_pyside.py:2975-3271` (`save_settings`)
- Test: manual (see Step 4) — both changes wrap already-tested `profile_manager.save_*` calls in a `Worker`; no new branching logic to unit test.

**Interfaces:**
- Consumes: `gui.worker.Worker`, `QThreadPool.globalInstance()` (matching the convention already used in `gui/barcode_generator_widget.py:390`, `gui/sku_label_widget.py:351`, `gui/reference_labels_widget.py:430`, `gui/client_reports_widget.py:290`).

- [ ] **Step 1: Wrap `client_settings_dialog.py`'s save call**

This dialog uses a `QDialogButtonBox` (`gui/client_settings_dialog.py:413-418`), not a standalone `QPushButton` — there is no `save_btn` attribute today. Confirmed via `grep -n "QDialogButtonBox\|_save_and_accept" gui/client_settings_dialog.py`:

```python
        button_box = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self._save_and_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
```

Change this block (still at construction time, lines 413-418) to keep a reference to the Save button so the new save handlers below can disable/relabel it:

```python
        button_box = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        self.save_button = button_box.button(QDialogButtonBox.Save)
        button_box.accepted.connect(self._save_and_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
```

Read `gui/client_settings_dialog.py:599-640` in full first (already read during planning) to preserve the exact surrounding structure. Replace `_save_and_accept()` (lines 599-633, plus whatever the `except` block at 635+ contains) with:

```python
    def _save_and_accept(self):
        """Gather form data on the GUI thread, save in the background."""
        try:
            self.config["client_name"] = self.client_name_input.text().strip()
            self.config["ui_settings"]["is_pinned"] = self.pin_checkbox.isChecked()
            self.config["ui_settings"]["group_id"] = self.group_combo.currentData()
            self.config["ui_settings"]["custom_color"] = self.current_color

            badges_text = self.badges_input.text().strip()
            if badges_text:
                badges = [b.strip() for b in badges_text.split(",") if b.strip()]
            else:
                badges = []
            self.config["ui_settings"]["custom_badges"] = badges

            self.save_button.setEnabled(False)
            self.save_button.setText("Saving...")

            worker = Worker(self.profile_manager.save_client_config, self.client_id, self.config)
            worker.signals.result.connect(self._on_save_result)
            worker.signals.error.connect(self._on_save_error)
            QThreadPool.globalInstance().start(worker)

        except Exception as e:
            logger.exception("Failed to save client settings")
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to save client settings:\n{e!s}",
            )

    def _on_save_result(self, success: bool):
        self.save_button.setEnabled(True)
        self.save_button.setText("Save")
        if success:
            QMessageBox.information(
                self,
                "Success",
                f"Settings for CLIENT_{self.client_id} saved successfully!"
            )
            self.accept()
        else:
            QMessageBox.warning(
                self,
                "Save Failed",
                "Failed to save client settings. Please try again."
            )

    def _on_save_error(self, error):
        exctype, value, tb = error
        logger.error(f"Failed to save client settings: {value}\n{tb}")
        self.save_button.setEnabled(True)
        self.save_button.setText("Save")
        QMessageBox.critical(self, "Error", f"Failed to save client settings:\n{value!s}")
```

Ensure imports at the top of the file include:

```python
from PySide6.QtCore import QThreadPool
from gui.worker import Worker
```

- [ ] **Step 2: Wrap `settings_window_pyside.py`'s save call**

This dialog also uses a `QDialogButtonBox` (`gui/settings_window_pyside.py:224-227`), no standalone Save `QPushButton`:

```python
        button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.save_settings)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)
```

Change it the same way, to keep a reference to the Save button:

```python
        button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.save_button = button_box.button(QDialogButtonBox.Save)
        button_box.accepted.connect(self.save_settings)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)
```

(There is a second, unrelated `QDialogButtonBox` at `gui/settings_window_pyside.py:3537` inside a different dialog class in the same file, for set-component validation — leave that one alone; it belongs to `_validate_and_save`, not `save_settings`.)

Read `gui/settings_window_pyside.py:2975-3271` in full first (the complete `save_settings()` method — most of it is synchronous form-gathering across many tabs, already read in part above). The only change needed: keep every existing form-gathering line (2975-3227) exactly as-is — all of that reads Qt widgets and must stay on the GUI thread — and change just the save+response section (lines 3225-3271, currently):

```python
            # ========================================
            # Save to server via ProfileManager
            # ========================================
            success = self.profile_manager.save_shopify_config(
                self.client_id,
                self.config_data
            )

            if success:
                QMessageBox.information(...)
                self.accept()
            else:
                ...(diagnostic QMessageBox)...

        except ValueError as e:
            ...
        except Exception as e:
            ...
```

to:

```python
            # ========================================
            # Save to server via ProfileManager (background -- avoids blocking
            # the GUI thread on the lock-contention retry sleep)
            # ========================================
            self.save_button.setEnabled(False)
            self.save_button.setText("Saving...")

            worker = Worker(self.profile_manager.save_shopify_config, self.client_id, self.config_data)
            worker.signals.result.connect(self._on_save_settings_result)
            worker.signals.error.connect(self._on_save_settings_error)
            QThreadPool.globalInstance().start(worker)

        except ValueError as e:
            QMessageBox.critical(
                self,
                "Validation Error",
                f"Invalid value entered:\n\n{e!s}\n\nPlease check your inputs."
            )
        except Exception as e:
            import traceback
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to save settings:\n\n{e!s}\n\n{traceback.format_exc()}"
            )

    def _on_save_settings_result(self, success: bool):
        self.save_button.setEnabled(True)
        self.save_button.setText("Save")
        if success:
            QMessageBox.information(self, "Success", "Settings saved successfully!")
            self.accept()
        else:
            import json
            config_size = len(json.dumps(self.config_data, ensure_ascii=False))
            num_sets = len(self.config_data.get("set_decoders", {}))
            QMessageBox.critical(
                self,
                "Save Error",
                f"Failed to save settings to server.\n\n"
                f"Configuration size: {config_size:,} bytes\n"
                f"Number of sets: {num_sets}\n\n"
                f"Possible causes:\n"
                f"• File is locked by another user\n"
                f"• Network connection issue\n"
                f"• Insufficient permissions\n\n"
                f"Please wait a few seconds and try again."
            )

    def _on_save_settings_error(self, error):
        exctype, value, tb = error
        logger.error(f"Failed to save settings: {value}\n{tb}")
        self.save_button.setEnabled(True)
        self.save_button.setText("Save")
        QMessageBox.critical(self, "Error", f"Failed to save settings:\n\n{value!s}")
```

Ensure `QThreadPool` and `Worker` are imported (check existing imports; `gui/settings_window_pyside.py` likely already imports several PySide6 QtCore names).

- [ ] **Step 3: Confirm `ValueError`/validation still happens before the async save starts**

Re-read the full pre-save portion of `save_settings()` (lines 2975-3224) to confirm no `ValueError` can be raised *after* the `Worker` is started (it shouldn't be, since all validation happens while gathering `self.config_data` from widgets, before the save call) — if any validation logic was interleaved after the old synchronous save call in the original code, move it before the `Worker` construction so it still runs on the GUI thread and still blocks accept() on failure.

- [ ] **Step 4: Manual verification**

Run: `python run_dev.py`.
- Open Client Settings for a client, change a value, click Save. Confirm the button shows "Saving..." briefly, then the dialog closes with the success message, and the GUI doesn't freeze during the save.
- Repeat for the full Settings window (`settings_window_pyside.py`) — change something on one tab, Save, confirm same behavior.
- Force a save conflict if feasible (e.g. hold `client_config.json.lock`/`shopify_config.json`'s lock open in another process) to confirm the retry-sleep now happens without freezing the window, and the error path still shows the diagnostic dialog correctly.

- [ ] **Step 5: Run the full test suite**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add gui/client_settings_dialog.py gui/settings_window_pyside.py
git commit -m "Run client/shopify config save in a background Worker instead of blocking the GUI thread"
```

---

### Task 8: Update the knowledge graph and do a final full-suite pass

**Files:** none (tooling only)

- [ ] **Step 1: Update the graphify knowledge graph**

Run: `graphify update .`

This repo's `CLAUDE.md` requires this after code changes — a stale graph silently returns wrong answers about file relationships in future sessions.

- [ ] **Step 2: Run the full test suite one final time**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest -v`
Expected: PASS, all tests across all 7 tasks.

- [ ] **Step 3: Run lint**

Check `.github/workflows/build_release.yml` for the exact lint command this repo's CI uses (mentioned in `CLAUDE.md`: "CI runs lint + this suite + a headless smoke test") and run it locally; fix any findings.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "Update graphify knowledge graph after UI responsiveness changes"
```
