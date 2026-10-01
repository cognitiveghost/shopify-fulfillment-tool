# UI refresh phase 4: Browse on the web tier. Implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Qt session tree on Browse with a web page drawn to the approved mockup, in its own
`QWebEngineView`, with status tabs, search, the two groups, a selection bar with Status and Comment, and an
Undo for every status and comment change.

**Architecture:** Python words every fact about a session. One pure function, `browse_state(...)`
(`gui/browse_state.py`), builds a dict with one record per session; `BrowseBridge` (`gui/browse_bridge.py`)
carries it to the page as one `state` property; `gui/web/browse.js` draws it. The page owns only the view
state (the tab, the search text, the checked rows, Show archived, the open popover) and names sessions by name
through the bridge's slots. `SessionBrowserWidget` keeps its name, signals and public methods and becomes the
controller: it hosts the view, loads the list on a thread, performs the writes, and remembers one Undo.

**Tech Stack:** Python 3.14, PySide6 (Qt widgets, QtWebEngine, QWebChannel), plain CSS and JavaScript (no build
step, no framework), pytest + pytest-qt driving a real Chromium offscreen.

**Spec:** `docs/superpowers/specs/2026-10-01-ui-refresh-phase4-browse-web-design.md`. Read it whole before
starting; this plan argues from it. Copy (every panel, note and toast) is in spec §5 and §6.2 and is verbatim.
Mockup: `docs/design/ui-refresh/mockups/browse.html` (render: `mockups/renders/browse.png`). To read exact
values, unpack the bundle with the script in `docs/design/ui-refresh/mockups/README.md`.

**Every code block in this plan was run before the plan was written**, against a scratch copy of the modules:
the tests in Tasks 1 to 7 passed there. If a block fails for you, suspect a typo in transcription or a change on
`main` since b589a18 before you suspect the design, and say what differed.

## Global Constraints

- Work in `/home/gloopy/Desktop/Projects/shopify-fulfillment-tool/.claude/worktrees/dr-16` on branch
  `dr/16-ui-refresh-phase-4-move-browse-to-the-we`. Never `cd` anywhere else. If `.venv` is missing, run
  `./scripts/setup_venv.sh`.
- Run tests only as `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q <paths>`. A hook blocks any other
  Bash text containing the word "pytest", so write test files with Write/Edit, never with heredocs.
- Git: `/usr/bin/git`, one plain command per Bash call, with no `;`, `&&` or `$VAR`. Commit with
  `/usr/bin/git commit -F <absolute path to a message file>`; write the message file under your job's tmp dir.
  End every message with the attribution lines your session is given.
- **Baseline:** see "Baseline" just below this list. Every test that passes there must pass after every task,
  unless the task rewrites or deletes it and says so.
- No hex, colour name, `rgb()`, px font size (that includes the `font:` shorthand), `transition`, `transform`,
  gradient or `opacity` in any file under `gui/` (`shared/style_lint.py`, enforced by
  `tests/test_style_literals_guard.py`). `box-shadow` only as `var(--card-shadow)`, `var(--overlay-shadow)` or
  `none`, and only in a `.css` file. Never set `element.style.*` to a colour from JavaScript: use a class.
- The lint reads a colour word after a colour property up to the next `;`. So every CSS declaration ends
  with `;`, including the last one in a rule: `border: 0` followed by `white-space: nowrap` on the next line
  reads as the colour `white`.
- The lint reads `#` followed by three or six hex digits as a colour, in CSS and in JavaScript strings. An id
  such as `#add-row` or `#bad` is a finding. The ids in this plan are safe; do not rename them.
- CSS custom properties from the theme are hyphenated: the token `surface_raised` is `var(--surface-raised)`.
  Type sizes are `var(--type-caption-size)`, `--type-body-size`, `--type-label-size`, `--type-heading-size`.
  The mono face is `var(--font-family-mono)`. Row and control heights are `var(--row-height)` and
  `var(--control-height)`.
- ADR 0018: a decorative line (card edge, divider) is `--border-subtle`. The edge of a button, an input or a
  tab is `--border`.
- Nothing in `shared/` changes in this plan. `gui/web/kit.css` does not change. Never touch `packing-tool/`.
- No `pyproject.toml`, no new dependency, no unused import (`.venv/bin/ruff check .` must pass). If ruff reports
  import order (I001) in a file you wrote, run `.venv/bin/ruff check --fix <that file>` and keep its order.
- No UI call from a worker thread. `SessionLoaderWorker` reaches the UI only by emitting a Qt signal.
- Never mark a Chromium test skip, and never delete a test without a replacement that pins the new behaviour.
  The test files this plan deletes are named in Task 6, with what replaces them.
- The page names a session by its name. Python never uses anything the page sends as a path.
- The implementer writes no "TODO". A step that cannot be finished is a stop: say what failed.

**Baseline.** Before Task 1, run `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` and write down the
pass and fail counts. On this branch at d952bbe (code identical to `origin/main` at b589a18) the run gave 2660 passed and 3 failed in about seven minutes. The three failures are `tests/test_label_printing.py::TestImageToZpl` (`test_black_pixels_become_set_bits`, `test_invert_flips_the_polarity`, `test_rotate_and_invert_compose`); they are not this task's and the PR body mentions them.

## Review Focus

1. **A session name or a comment carrying quotes, angle brackets or spaces** (a folder someone copied by
   hand, a comment pasted from an email). It is drawn as text, the row can still be checked, focus survives
   the redraw, and Python is given the name exactly (tests in Task 5). *Corrected in review (Stage C):* a
   row's click no longer redraws the list, because the redraw swallowed a real double-click (spec §5.6).
2. **Checked rows that leave the tab** (archiving two sessions on All). The selection bar goes, an open menu
   closes, and nothing acts on rows the operator can no longer see (test in Task 5).
3. **Packing Tool or another PC writes the session between a change and its Undo.** Undo puts back only the
   five fields the change could alter; packing progress written in between survives (test in Task 6).
   *Corrected in review (Stage C):* the code below restored all five fields from the loaded list, whatever
   the change. Undo now restores only the fields its change stamps, read from the file just before the
   write; spec §6.3 has the rule. The Task 6 widget code and its Undo tests in this plan are superseded.
4. **A session folder that left the share between the load and a write.** It is counted and reported in the
   banner, the other sessions are written, and the list reloads without it (test in Task 6).
5. **A narrow window.** The count label goes under 980px, the card keeps a 780px minimum and the page
   scrolls sideways under it; no column overlaps another (test in Task 5).

## File structure

| File | Task | Responsibility |
|---|---|---|
| `shopify_tool/session_lifecycle.py` | 1, 6 | `age_cell`, `IN_FLIGHT`; `age_label` goes in Task 6 |
| `shopify_tool/session_manager.py` | 2 | `restore_session_fields` |
| `gui/browse_state.py` (new) | 3 | `browse_state` and its row builder. No Qt |
| `gui/browse_bridge.py` (new) | 4 | `BrowseBridge`, `mount_browse_page` |
| `gui/web/browse.html`, `browse.css`, `browse.js` (new) | 5 | The page |
| `gui/session_browser_widget.py` | 6 | The view, the loader, the writes, Undo |
| `gui/session_row_delegates.py`, `gui/components/selectionbar.py` | 6 | Deleted |
| `gui/ui_manager.py`, `gui/main_window_pyside.py`, `gui/shortcuts_dialog.py` | 7 | Inset, toast router, F5, where a session opens |
| Docs, CI, renders | 8 | Spec §11, the visual check, the gate |

---

### Task 1: The Age cell and the in-flight states (`shopify_tool/session_lifecycle.py`)

**Files:**
- Modify: `shopify_tool/session_lifecycle.py`
- Test: `tests/test_session_lifecycle.py`

**Interfaces:**
- Produces: `age_cell(entry: dict, now: datetime) -> tuple[str, str, bool]` (cell, tooltip, warn);
  `IN_FLIGHT: tuple[str, ...]` (was `_IN_FLIGHT`).
- `age_label` stays until Task 6: the Qt widget still calls it.

- [ ] **Step 1: Write the failing tests**

In `tests/test_session_lifecycle.py`:

1. Add `import pytest` as the third line group, so the top of the file reads:

```python
"""Session status derivation from packing progress and age (pure -- no Qt, no file server)."""
from datetime import datetime, timedelta

import pytest

from shopify_tool.session_lifecycle import (
    ARCHIVE_WARNING_DAYS,
    DISPLAY_STATUSES,
    IN_FLIGHT,
    age_cell,
    age_label,
    blocked_orders,
    derive_status_updates,
    display_status,
    is_fully_packed,
    needs_attention,
    packing_completion,
    parse_created_at,
)
```

2. Append at the end of the file:

```python
def _aged(age, **fields):
    """An entry created `age` ago; active unless a field says otherwise."""
    return {"created_at": (NOW - age).isoformat(), "status": "active", **fields}


class TestAgeCell:
    def test_under_an_hour(self):
        assert age_cell(_aged(timedelta(minutes=20)), NOW)[0] == "<1 h"

    def test_hours_under_a_day(self):
        assert age_cell(_aged(timedelta(hours=6)), NOW)[0] == "6 h"
        assert age_cell(_aged(timedelta(hours=23, minutes=59)), NOW)[0] == "23 h"

    def test_days_from_the_first_day(self):
        assert age_cell(_aged(timedelta(hours=24)), NOW)[0] == "1 d"
        assert age_cell(_aged(timedelta(days=3)), NOW)[0] == "3 d"

    def test_days_never_roll_up_into_weeks_or_months(self):
        assert age_cell(_aged(timedelta(days=52)), NOW)[0] == "52 d"

    def test_a_date_ahead_of_this_clock_reads_as_just_now(self):
        assert age_cell(_aged(timedelta(hours=-5)), NOW)[0] == "<1 h"

    def test_the_tooltip_carries_the_absolute_stamp(self):
        created = NOW - timedelta(days=3)
        assert age_cell(_aged(timedelta(days=3)), NOW)[1] == f"Created {created:%Y-%m-%d %H:%M}"

    @pytest.mark.parametrize("entry", [{"created_at": "nope"}, {}, None, "text"])
    def test_an_unreadable_date_says_so(self, entry):
        assert age_cell(entry, NOW) == ("—", "Created date unreadable", False)

    @pytest.mark.parametrize("status", ["active", "completed"])
    @pytest.mark.parametrize("days", [23, 26, 29])
    def test_the_countdown_runs_for_the_last_seven_days(self, status, days):
        cell, tooltip, warn = age_cell(_aged(timedelta(days=days), status=status), NOW)
        assert cell == f"{days} d"
        assert warn is True
        assert tooltip.endswith(f" · Archives in {30 - days} d")

    @pytest.mark.parametrize("days", [22, 30, 40])
    def test_no_countdown_outside_the_window(self, days):
        _cell, tooltip, warn = age_cell(_aged(timedelta(days=days)), NOW)
        assert warn is False
        assert "Archives" not in tooltip

    @pytest.mark.parametrize(
        "fields",
        [
            {"status": "abandoned"},
            {"status": "archived"},
            {"status": "active", "status_manually_set": True},
            {"status": None},
        ],
    )
    def test_a_session_the_automation_will_not_archive_never_counts_down(self, fields):
        _cell, tooltip, warn = age_cell(_aged(timedelta(days=26), **fields), NOW)
        assert warn is False
        assert "Archives" not in tooltip

    def test_the_warning_window_is_derived_not_typed(self):
        assert ARCHIVE_WARNING_DAYS == 7


def test_the_in_flight_states_are_the_four_before_a_session_closes():
    assert IN_FLIGHT == ("not_started", "in_progress", "paused", "stale")
```

- [ ] **Step 2: Run them and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_session_lifecycle.py`
Expected: an `ImportError` for `IN_FLIGHT` (or `age_cell`) at collection.

- [ ] **Step 3: Implement**

In `shopify_tool/session_lifecycle.py`:

1. Rename `_IN_FLIGHT` to `IN_FLIGHT` in both places it appears: its definition and the last line of
   `needs_attention` (`return bool(blocked) and state in IN_FLIGHT`).
2. Add this function directly after `age_label` (before `needs_attention`):

```python
def age_cell(entry: dict, now: datetime) -> tuple[str, str, bool]:
    """(cell, tooltip, warn) for the Age column.

    The cell is short: hours under a day, days after that, never weeks or
    months. The absolute stamp goes in the tooltip. `warn` is True when the
    automation will archive this session within ARCHIVE_WARNING_DAYS, and the
    tooltip then carries the countdown. It asks the two questions
    derive_status_updates asks, so a session that will never be archived --
    abandoned, already archived, or set by hand -- never counts down.
    """
    created = parse_created_at(entry.get("created_at")) if isinstance(entry, dict) else None
    if created is None:
        return ("—", "Created date unreadable", False)

    # A created_at ahead of this PC's clock reads as "just now", not as a
    # negative age.
    age = max(now - created, timedelta(0))
    hours = int(age.total_seconds() // 3600)
    if hours < 1:
        cell = "<1 h"
    elif hours < 24:
        cell = f"{hours} h"
    else:
        cell = f"{age.days} d"

    tooltip = f"Created {created:%Y-%m-%d %H:%M}"
    remaining = AUTO_ARCHIVE_AFTER_DAYS - age.days
    warn = (
        entry.get("status") in _ARCHIVABLE_FROM
        and not entry.get("status_manually_set")
        and 0 < remaining <= ARCHIVE_WARNING_DAYS
    )
    if warn:
        tooltip += f" · Archives in {remaining} d"
    return (cell, tooltip, warn)
```

- [ ] **Step 4: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_session_lifecycle.py`
Expected: all pass.

- [ ] **Step 5: Commit**

`/usr/bin/git add shopify_tool/session_lifecycle.py tests/test_session_lifecycle.py`, then commit with:

```
Age cell: a short age, and a countdown only where the archive is real

age_cell replaces what the Browse page will draw: hours under a day, days
after, and a warning in the last seven days before the automatic archive.
It asks what derive_status_updates asks, so an abandoned or hand-set session
never counts down. _IN_FLIGHT becomes IN_FLIGHT for browse_state to read.
```

---

### Task 2: Undo's write (`SessionManager.restore_session_fields`)

**Files:**
- Modify: `shopify_tool/session_manager.py`
- Test: `tests/test_session_manager.py`

**Interfaces:**
- Produces: `SessionManager.restore_session_fields(session_path: str, fields: dict) -> bool`. Each key is set
  to its value; a value of `None` removes the key. It stamps nothing. Raises `SessionManagerError` for an
  unknown `status`, a folder with no `session_info.json`, or a failed write.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_session_manager.py` (it already imports `json`, `Path`, `pytest`, `SessionManager`,
`SessionManagerError` and has the `session_manager` fixture):

```python
class TestRestoreSessionFields:
    """The Browse page's Undo (phase 4 spec section 6.3)."""

    @staticmethod
    def _stored(session_path):
        return json.loads((Path(session_path) / "session_info.json").read_text())

    def test_sets_values_and_removes_the_keys_given_as_none(self, session_manager):
        path = session_manager.create_session("M")
        session_manager.update_session_status(path, "archived", manual=True)

        session_manager.restore_session_fields(
            path, {"status": "active", "status_manually_set": None, "comments": "kept"}
        )

        stored = self._stored(path)
        assert stored["status"] == "active"
        assert "status_manually_set" not in stored
        assert stored["comments"] == "kept"

    def test_it_stamps_nothing_and_leaves_every_other_key_alone(self, session_manager):
        path = session_manager.create_session("M")
        session_manager.update_session_info(path, {"comments": "before"})
        before = self._stored(path)

        session_manager.restore_session_fields(path, {"comments": "after"})

        assert self._stored(path) == {**before, "comments": "after"}

    def test_removing_a_key_that_is_not_there_is_fine(self, session_manager):
        path = session_manager.create_session("M")
        before = self._stored(path)
        session_manager.restore_session_fields(path, {"status_manually_set": None})
        assert self._stored(path) == before

    def test_the_index_entry_follows(self, session_manager):
        path = session_manager.create_session("M")
        session_manager.update_session_status(path, "archived")

        session_manager.restore_session_fields(path, {"status": "active"})

        index_path = Path(path).parent / SessionManager.INDEX_FILENAME
        entries = json.loads(index_path.read_text())
        assert entries[0]["status"] == "active"

    def test_an_unknown_status_is_refused_and_nothing_is_written(self, session_manager):
        path = session_manager.create_session("M")
        before = self._stored(path)
        with pytest.raises(SessionManagerError):
            session_manager.restore_session_fields(path, {"status": "frozen"})
        assert self._stored(path) == before

    def test_a_folder_that_is_not_a_session_raises(self, session_manager, tmp_path):
        ghost = tmp_path / "ghost"
        ghost.mkdir()
        with pytest.raises(SessionManagerError):
            session_manager.restore_session_fields(str(ghost), {"comments": "x"})
```

- [ ] **Step 2: Run them and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_session_manager.py`
Expected: six failures, `AttributeError: 'SessionManager' object has no attribute 'restore_session_fields'`.

- [ ] **Step 3: Implement**

In `shopify_tool/session_manager.py`, add this method directly above `def update_session_info(`:

```python
    def restore_session_fields(self, session_path: str, fields: dict) -> bool:
        """Put stored fields back exactly: the Browse page's Undo.

        Each key in `fields` is set to its value; a value of None removes the
        key. Nothing is stamped, so `last_updated` and `status_updated_at` end
        up as the caller hands them in -- a session that was Stale before the
        change is Stale again after the Undo.

        Args:
            session_path (str): Full path to session directory
            fields (Dict): The fields to restore; None removes a key

        Returns:
            bool: True if restored successfully

        Raises:
            SessionManagerError: If a status is invalid, the session is not
                found, or the write fails
        """
        status = fields.get("status")
        if status is not None and status not in self.VALID_STATUSES:
            raise SessionManagerError(
                f"Invalid status: {status}. Must be one of {self.VALID_STATUSES}"
            )

        session_path_obj = Path(session_path)

        with self._locked_session_info(session_path_obj):
            session_info = self.get_session_info(session_path)
            if not session_info:
                raise SessionManagerError(f"Session not found: {session_path}")

            for key, value in fields.items():
                if value is None:
                    session_info.pop(key, None)
                else:
                    session_info[key] = value

            try:
                # Remove computed fields
                session_info.pop("session_path", None)

                atomic_write_json(
                    session_path_obj / "session_info.json", session_info, indent=2
                )
                self._upsert_index_entry(session_path_obj, session_info)
                logger.info(f"Session fields restored: {session_path}")
                return True

            except Exception as e:
                logger.exception("Failed to restore session fields")
                raise SessionManagerError(f"Failed to restore session fields: {e}")
```

- [ ] **Step 4: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_session_manager.py`
Expected: all pass.

- [ ] **Step 5: Commit**

`/usr/bin/git add shopify_tool/session_manager.py tests/test_session_manager.py`, then commit with:

```
SessionManager.restore_session_fields: put stored fields back exactly

The write behind the Browse page's Undo. It sets the given keys, removes the
ones given as None, and stamps nothing, so a restored session's timestamps
are what they were.
```

---

### Task 3: The state (`gui/browse_state.py`)

**Files:**
- Create: `gui/browse_state.py`, `tests/test_browse_state.py`

**Interfaces:**
- Consumes: `session_lifecycle.age_cell`, `IN_FLIGHT`, `DISPLAY_STATUSES`, `display_status`, `blocked_orders`,
  `needs_attention`, `packing_completion`; `SessionManager.VALID_STATUSES`.
- Produces: `browse_state(*, client: str, loading: bool, failed: bool, sessions: list, now: datetime) -> dict`
  returning `{"view": "no_client" | "failed" | "loading" | "empty" | "list", "client": str, "rows": [row]}`.
  A row has exactly these keys: `name`, `age`, `age_title`, `age_warn`, `status`, `label`, `tone`, `dot`,
  `tab`, `orders`, `items`, `blocked`, `blocked_alert`, `pack`, `pack_pct`, `pack_tone`, `pack_title`,
  `comment`, `why` (spec §4.2).
- `tests/test_browse_state.py` also produces the helpers Task 5 imports: `session(...)`, `make_state(...)`,
  `NOW`, `H`, `D`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_browse_state.py`:

```python
"""browse_state: the one map the Browse page draws (phase 4 spec section 4).

Pure: no Qt and no file server.
"""

from datetime import datetime, timedelta

import pytest

from gui.browse_state import browse_state

NOW = datetime(2026, 9, 30, 14, 0).astimezone()
H = timedelta(hours=1)
D = timedelta(days=1)


def session(
    name="2026-09-30_1",
    *,
    status="active",
    age=6 * H,
    orders=197,
    items=402,
    blocked=None,
    lists=0,
    done=0,
    paused=False,
    idle=H,
    comment="",
    **extra,
):
    """One entry shaped like SessionManager.list_client_sessions() returns it.

    `lists` packing lists, of which `done` are completed. `paused` pauses the
    next one. `idle` is how long ago Packing Tool last wrote progress.
    """
    names = [f"list{i}" for i in range(lists)]
    stamp = (NOW - idle).isoformat()
    progress = {n: {"status": "completed", "updated_at": stamp} for n in names[:done]}
    if paused:
        progress[names[done]] = {"status": "paused", "updated_at": stamp}
    entry = {
        "session_name": name,
        "session_path": f"/srv/Sessions/CLIENT_ACME/{name}",
        "created_at": (NOW - age).isoformat(),
        "status": status,
        "statistics": {
            "total_orders": orders,
            "total_items": items,
            "packing_lists": names,
        },
        "packing_progress": progress,
        "comments": comment,
    }
    if blocked is not None:
        entry["not_fulfillable_orders"] = blocked
    entry.update(extra)
    return entry


def make_state(sessions=(), **overrides):
    args = {"client": "ACME", "loading": False, "failed": False, "sessions": list(sessions), "now": NOW}
    args.update(overrides)
    return browse_state(**args)


def row(**kwargs):
    return make_state([session(**kwargs)])["rows"][0]


# --- views -------------------------------------------------------------------


def test_no_client_wins_over_everything():
    state = make_state([session()], client="", loading=True, failed=True)
    assert state == {"view": "no_client", "client": "", "rows": []}


def test_a_failed_load_wins_over_a_load_in_flight():
    assert make_state([session()], failed=True, loading=True)["view"] == "failed"


def test_a_loud_load_shows_loading_and_no_rows():
    state = make_state([session()], loading=True)
    assert state == {"view": "loading", "client": "ACME", "rows": []}


def test_a_client_with_no_sessions_is_empty():
    assert make_state([]) == {"view": "empty", "client": "ACME", "rows": []}


def test_sessions_make_a_list_in_the_order_given():
    state = make_state([session("b"), session("c"), session("a")])
    assert state["view"] == "list"
    assert [r["name"] for r in state["rows"]] == ["b", "c", "a"]


def test_an_entry_that_is_not_a_session_is_skipped():
    junk = [None, "text", {"status": "active"}, {"session_name": ""}, {"session_name": 7}]
    assert [r["name"] for r in make_state([*junk, session("ok")])["rows"]] == ["ok"]
    assert make_state(junk)["view"] == "empty"


def test_no_session_list_at_all_is_empty():
    state = browse_state(client="ACME", loading=False, failed=False, sessions=None, now=NOW)
    assert state["view"] == "empty"


# --- the status --------------------------------------------------------------


@pytest.mark.parametrize(
    ("kwargs", "status", "label", "tone", "dot", "tab"),
    [
        ({"lists": 2}, "not_started", "Not started", "neutral", "hollow", "active"),
        ({"lists": 3, "done": 1}, "in_progress", "In progress", "info", "half", "active"),
        ({"lists": 2, "paused": True}, "paused", "Paused", "warning", "half", "active"),
        ({"lists": 3, "done": 1, "idle": 8 * D}, "stale", "Stale", "warning", "half", "active"),
        ({"status": "completed", "lists": 2, "done": 2}, "completed", "Completed", "success", "solid", "completed"),
        ({"status": "completed", "lists": 5, "done": 4}, "incomplete", "Incomplete", "danger", "solid", "completed"),
        ({"status": "abandoned"}, "abandoned", "Abandoned", "neutral", "solid", "abandoned"),
        ({"status": "archived"}, "archived", "Archived", "neutral", "solid", "archived"),
        ({"status": "frozen"}, "frozen", "Frozen", "neutral", "hollow", ""),
    ],
)
def test_each_status_has_its_label_tone_dot_and_tab(kwargs, status, label, tone, dot, tab):
    r = row(**kwargs)
    assert (r["status"], r["label"], r["tone"], r["dot"], r["tab"]) == (
        status,
        label,
        tone,
        dot,
        tab,
    )


@pytest.mark.parametrize("stored", [None, "", 7])
def test_a_missing_status_reads_active(stored):
    r = row(status=stored)
    assert r["tab"] == "active"
    assert r["status"] == "not_started"


# --- the numbers -------------------------------------------------------------


def test_counts_carry_a_comma_for_thousands():
    r = row(orders=1204, items=12402)
    assert (r["orders"], r["items"]) == ("1,204", "12,402")


@pytest.mark.parametrize("value", [0, None, "12", True, -3])
def test_a_count_that_is_zero_or_unreadable_is_empty(value):
    r = row(orders=value, items=value)
    assert (r["orders"], r["items"]) == ("", "")


def test_missing_statistics_leave_the_counts_empty():
    r = row(statistics="oops")
    assert (r["orders"], r["items"], r["pack"]) == ("", "", "")


def test_blocked_is_empty_at_zero_and_when_never_analysed():
    assert row(blocked=0)["blocked"] == ""
    assert row()["blocked"] == ""
    assert row()["blocked_alert"] is False


@pytest.mark.parametrize(
    ("kwargs", "alert", "why"),
    [
        ({"lists": 3, "done": 1}, True, "blocked"),
        ({"lists": 2}, True, "blocked"),
        ({"lists": 2, "paused": True}, True, "paused"),
        ({"lists": 3, "done": 1, "idle": 8 * D}, True, "stale"),
        ({"status": "completed", "lists": 5, "done": 4}, False, "incomplete"),
        ({"status": "completed", "lists": 2, "done": 2}, False, ""),
        ({"status": "abandoned"}, False, ""),
        ({"status": "archived"}, False, ""),
    ],
)
def test_blocked_orders_alert_only_while_the_session_is_in_flight(kwargs, alert, why):
    r = row(blocked=9, **kwargs)
    assert r["blocked"] == "9"
    assert r["blocked_alert"] is alert
    assert r["why"] == why


@pytest.mark.parametrize(
    ("kwargs", "why"),
    [
        ({"lists": 3, "done": 1}, ""),
        ({"lists": 2}, ""),
        ({"lists": 2, "paused": True}, "paused"),
        ({"lists": 3, "done": 1, "idle": 8 * D}, "stale"),
        ({"status": "completed", "lists": 5, "done": 4}, "incomplete"),
        ({"status": "completed", "lists": 2, "done": 2}, ""),
    ],
)
def test_why_names_the_reason_a_session_needs_attention(kwargs, why):
    assert row(**kwargs)["why"] == why


# --- packing -----------------------------------------------------------------


def test_a_session_with_no_packing_lists_has_no_packing():
    r = row()
    assert (r["pack"], r["pack_pct"], r["pack_tone"], r["pack_title"]) == ("", 0, "", "")


def test_packing_in_progress():
    r = row(lists=3, done=2)
    assert (r["pack"], r["pack_pct"], r["pack_tone"]) == ("2 / 3", 67, "")
    assert r["pack_title"] == "2 of 3 packing lists completed in Packing Tool"


def test_packing_finished_is_success():
    r = row(status="completed", lists=3, done=3)
    assert (r["pack"], r["pack_pct"], r["pack_tone"]) == ("3 / 3", 100, "success")


def test_packing_closed_unfinished_is_danger():
    r = row(status="completed", lists=5, done=4)
    assert (r["pack"], r["pack_pct"], r["pack_tone"]) == ("4 / 5", 80, "danger")


def test_an_abandoned_session_shows_no_packing():
    r = row(status="abandoned", lists=3, done=1)
    assert (r["pack"], r["pack_pct"], r["pack_title"]) == ("", 0, "")


# --- age and comment ---------------------------------------------------------


def test_the_age_is_short_and_its_title_carries_the_stamp():
    r = row(age=6 * H)
    assert r["age"] == "6 h"
    assert r["age_title"].startswith("Created ")
    assert r["age_warn"] is False


def test_the_age_warns_before_the_auto_archive():
    r = row(status="completed", lists=1, done=1, age=26 * D)
    assert r["age"] == "26 d"
    assert r["age_warn"] is True
    assert r["age_title"].endswith(" · Archives in 4 d")


def test_the_comment_is_trimmed_and_a_non_string_is_empty():
    assert row(comment="  call courier \n")["comment"] == "call courier"
    assert row(comments=None)["comment"] == ""
    assert row(comments=5)["comment"] == ""


def test_no_shape_of_entry_raises():
    r = row(statistics=None, packing_progress="x", comments=5, created_at="nope",
            not_fulfillable_orders="many")
    assert r["age"] == "—"
    assert r["blocked"] == ""
```

- [ ] **Step 2: Run them and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_browse_state.py`
Expected: `ModuleNotFoundError: No module named 'gui.browse_state'`.

- [ ] **Step 3: Implement**

Create `gui/browse_state.py`:

```python
"""What the Browse page draws (phase 4 spec section 4).

One pure function: the loaded sessions in, one map out. No Qt and no I/O.
Every fact about a session is worded here; the page filters, counts and
groups the rows it is given and decides none of them.
"""

from datetime import datetime

from shopify_tool.session_lifecycle import (
    DISPLAY_STATUSES,
    IN_FLIGHT,
    age_cell,
    blocked_orders,
    display_status,
    needs_attention,
    packing_completion,
)
from shopify_tool.session_manager import SessionManager

# A status with no entry here is neutral: not started, abandoned, archived,
# and any status this build has never heard of.
_TONES = {
    "in_progress": "info",
    "paused": "warning",
    "stale": "warning",
    "completed": "success",
    "incomplete": "danger",
}
_HALF_DOT = ("in_progress", "paused", "stale")
# The states that are themselves a request for someone.
_ATTENTION_STATES = ("paused", "stale", "incomplete")


def _number(value) -> str:
    """A positive count with a comma for thousands, or "" for anything else."""
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return ""
    return f"{value:,}"


def _dot(status: str) -> str:
    """How far the session has come: hollow, half or solid."""
    if status in _HALF_DOT:
        return "half"
    if status == "not_started" or status not in DISPLAY_STATUSES:
        return "hollow"
    return "solid"


def _tab(entry: dict) -> str:
    """The stored status, which is what a tab filters on."""
    stored = entry.get("status")
    if not isinstance(stored, str) or not stored:
        stored = "active"  # as display_status reads a missing status
    return stored if stored in SessionManager.VALID_STATUSES else ""


def _row(entry: dict, now: datetime) -> dict:
    status = display_status(entry, now)
    blocked = blocked_orders(entry) or 0
    packed, total = packing_completion(entry)
    has_pack = total > 0 and status != "abandoned"
    stats = entry.get("statistics")
    if not isinstance(stats, dict):
        stats = {}
    comment = entry.get("comments")
    age, age_title, age_warn = age_cell(entry, now)

    if status in _ATTENTION_STATES:
        why = status
    elif needs_attention(status, blocked):
        why = "blocked"
    else:
        why = ""

    if not has_pack:
        pack_tone = ""
    elif packed >= total:
        pack_tone = "success"
    elif status == "incomplete":
        pack_tone = "danger"
    else:
        pack_tone = ""

    return {
        "name": entry["session_name"],
        "age": age,
        "age_title": age_title,
        "age_warn": age_warn,
        "status": status,
        "label": status.replace("_", " ").capitalize(),
        "tone": _TONES.get(status, "neutral"),
        "dot": _dot(status),
        "tab": _tab(entry),
        "orders": _number(stats.get("total_orders")),
        "items": _number(stats.get("total_items")),
        "blocked": _number(blocked),
        "blocked_alert": blocked > 0 and status in IN_FLIGHT,
        "pack": f"{packed} / {total}" if has_pack else "",
        "pack_pct": round(packed / total * 100) if has_pack else 0,
        "pack_tone": pack_tone,
        "pack_title": (
            f"{packed} of {total} packing lists completed in Packing Tool"
            if has_pack
            else ""
        ),
        "comment": comment.strip() if isinstance(comment, str) else "",
        "why": why,
    }


def browse_state(
    *, client: str, loading: bool, failed: bool, sessions: list, now: datetime
) -> dict:
    """The map the Browse page draws. `sessions` stays in the order given."""
    rows = []
    if not client:
        view = "no_client"
    elif failed:
        view = "failed"
    elif loading:
        view = "loading"
    else:
        rows = [
            _row(entry, now)
            for entry in sessions or []
            if isinstance(entry, dict)
            and isinstance(entry.get("session_name"), str)
            and entry["session_name"]
        ]
        view = "list" if rows else "empty"
    return {"view": view, "client": client or "", "rows": rows}
```

- [ ] **Step 4: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_browse_state.py`
Expected: 50 passed.

- [ ] **Step 5: Commit**

`/usr/bin/git add gui/browse_state.py tests/test_browse_state.py`, then commit with:

```
browse_state: every fact a session row shows, built in one pure function

The map the Browse page will draw: which view shows, and one record per
session with its age, badge, counts, packing and attention reason already
worded. No Qt, so the whole rule set runs without a QApplication.
```

---

### Task 4: The bridge (`gui/browse_bridge.py`)

**Files:**
- Create: `gui/browse_bridge.py`, `tests/test_browse_bridge.py`

**Interfaces:**
- Consumes: `gui.web_page.PageBridge`, `mount_page`, `WEB_DIR`.
- Produces: `PAGE = WEB_DIR / "browse.html"`, `CHANNEL_NAME = "browse"`,
  `class BrowseBridge(PageBridge)` with `state` (Property `QVariantMap`, notify `stateChanged`),
  `set_state(state: dict) -> None`, the slots `refresh()`, `openSession(name)`, `setStatus(names, status)`,
  `setComment(names, text)`, `exportCombined(names)`, `newSession()`, `undo()`, and the Python-facing signals
  `refreshRequested()`, `openRequested(str)`, `statusRequested(list, str)`, `commentRequested(list, str)`,
  `exportRequested(list)`, `newSessionRequested()`, `undoRequested()`;
  `mount_browse_page(view: QWebEngineView) -> BrowseBridge`.
- The catalogue is spec §3.2. `mount_browse_page` is exercised in Task 5, once the page exists.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_browse_bridge.py`:

```python
"""The Browse page's bridge: every message is its own named member (ADR 0001)."""

import pytest
from PySide6.QtWidgets import QApplication

from gui.browse_bridge import BrowseBridge
from gui.web_page import PageBridge
from shopify_tool.session_manager import SessionManager


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


def _caught(signal):
    seen = []
    signal.connect(lambda *args: seen.append(args))
    return seen


def test_it_is_a_page_bridge():
    assert issubclass(BrowseBridge, PageBridge)


@pytest.mark.parametrize(
    ("slot", "signal"),
    [
        ("refresh", "refreshRequested"),
        ("newSession", "newSessionRequested"),
        ("undo", "undoRequested"),
    ],
)
def test_a_plain_command_emits_its_signal(slot, signal):
    bridge = BrowseBridge()
    seen = _caught(getattr(bridge, signal))
    getattr(bridge, slot)()
    assert seen == [()]


def test_open_carries_the_session_name_and_drops_an_empty_one():
    bridge = BrowseBridge()
    seen = _caught(bridge.openRequested)
    bridge.openSession("2026-09-30_1")
    bridge.openSession("")
    assert seen == [("2026-09-30_1",)]


def test_a_status_is_one_of_the_four_a_person_can_set():
    bridge = BrowseBridge()
    seen = _caught(bridge.statusRequested)
    for status in [*SessionManager.VALID_STATUSES, "frozen", "in_progress", ""]:
        bridge.setStatus(["a", "b"], status)
    assert seen == [(["a", "b"], status) for status in SessionManager.VALID_STATUSES]


def test_names_that_are_not_strings_are_dropped():
    bridge = BrowseBridge()
    seen = _caught(bridge.statusRequested)
    bridge.setStatus(["a", 7, "", None, "b"], "archived")
    bridge.setStatus([], "archived")
    bridge.setStatus([7, None], "archived")
    bridge.setStatus("2026-09-30_1", "archived")
    assert seen == [(["a", "b"], "archived")]


def test_a_comment_carries_its_text_and_an_empty_one_clears():
    bridge = BrowseBridge()
    seen = _caught(bridge.commentRequested)
    bridge.setComment(["a"], "late van")
    bridge.setComment(["a", "b"], "")
    bridge.setComment([], "nobody")
    assert seen == [(["a"], "late van"), (["a", "b"], "")]


def test_a_combined_export_needs_two_sessions():
    bridge = BrowseBridge()
    seen = _caught(bridge.exportRequested)
    bridge.exportCombined(["a"])
    bridge.exportCombined(["a", ""])
    bridge.exportCombined(["a", "b"])
    assert seen == [(["a", "b"],)]


def test_a_state_is_announced_when_it_changes_and_only_then():
    bridge = BrowseBridge()
    seen = _caught(bridge.stateChanged)
    bridge.set_state({"view": "no_client"})
    bridge.set_state({"view": "no_client"})
    bridge.set_state({"view": "loading"})
    assert len(seen) == 2
    assert bridge.state == {"view": "loading"}
```

- [ ] **Step 2: Run them and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_browse_bridge.py`
Expected: `ModuleNotFoundError: No module named 'gui.browse_bridge'`.

- [ ] **Step 3: Implement**

Create `gui/browse_bridge.py`:

```python
"""The Browse page's bridge (phase 4 spec section 3.2).

Python pushes one `state` map, built by gui/browse_state.py; the page draws
it and reports what the operator asks for through the named slots below. The
catalogue is the spec's section 3.2: add a member there before adding it here.

The page names a session by its name. Nothing it sends is used as a path.
"""

from PySide6.QtCore import Property, Signal, Slot
from PySide6.QtWebEngineWidgets import QWebEngineView

from gui.web_page import WEB_DIR, PageBridge, mount_page
from shopify_tool.session_manager import SessionManager

PAGE = WEB_DIR / "browse.html"
CHANNEL_NAME = "browse"


def _names(values) -> list[str]:
    """The session names in a list from the page; anything else is dropped."""
    if not isinstance(values, (list, tuple)):
        return []
    return [value for value in values if isinstance(value, str) and value]


class BrowseBridge(PageBridge):
    """The Browse page's one channel object."""

    stateChanged = Signal()
    # Python-facing. JS reports through the slots below and never connects to
    # these, so nothing it sends can echo back into the page.
    refreshRequested = Signal()
    openRequested = Signal(str)
    statusRequested = Signal(list, str)
    commentRequested = Signal(list, str)
    exportRequested = Signal(list)
    newSessionRequested = Signal()
    undoRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state: dict = {}

    # --- out: Python -> JS -------------------------------------------------

    def _get_state(self) -> dict:
        return self._state

    state = Property("QVariantMap", _get_state, notify=stateChanged)

    def set_state(self, state: dict) -> None:
        if state == self._state:
            return
        self._state = state
        self.stateChanged.emit()

    # --- in: JS -> Python --------------------------------------------------

    @Slot()
    def refresh(self) -> None:
        self.refreshRequested.emit()

    @Slot(str)
    def openSession(self, name) -> None:
        if isinstance(name, str) and name:
            self.openRequested.emit(name)

    @Slot("QVariantList", str)
    def setStatus(self, names, status) -> None:
        names = _names(names)
        # A name, not a verb: an unknown status is dropped rather than guessed.
        if names and status in SessionManager.VALID_STATUSES:
            self.statusRequested.emit(names, status)

    @Slot("QVariantList", str)
    def setComment(self, names, text) -> None:
        names = _names(names)
        if names:
            self.commentRequested.emit(names, str(text))

    @Slot("QVariantList")
    def exportCombined(self, names) -> None:
        names = _names(names)
        if len(names) >= 2:
            self.exportRequested.emit(names)

    @Slot()
    def newSession(self) -> None:
        self.newSessionRequested.emit()

    @Slot()
    def undo(self) -> None:
        self.undoRequested.emit()


def mount_browse_page(view: QWebEngineView) -> BrowseBridge:
    """Load the Browse page into `view` and return the bridge it talks to."""
    bridge = BrowseBridge(view)
    mount_page(view, bridge, PAGE, CHANNEL_NAME)
    return bridge
```

- [ ] **Step 4: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_browse_bridge.py`
Expected: 10 passed.

- [ ] **Step 5: Commit**

`/usr/bin/git add gui/browse_bridge.py tests/test_browse_bridge.py`, then commit with:

```
BrowseBridge: the Browse page's named messages

One state map out; refresh, open, status, comment, combined export, new
session and undo in. Sessions cross as names, never as paths, and an unknown
status or an empty name list is dropped at the bridge.
```

---

### Task 5: The page (`gui/web/browse.html`, `browse.css`, `browse.js`)

**Files:**
- Create: `gui/web/browse.html`, `gui/web/browse.css`, `gui/web/browse.js`, `tests/test_browse_page.py`

**Interfaces:**
- Consumes: `gui.browse_bridge.PAGE`, `mount_browse_page`, `BrowseBridge` (Task 4); `browse_state` and the
  test helpers `session`, `make_state`, `H`, `D` from `tests/test_browse_state.py` (Task 3);
  `_eval`, `_rgb`, `_until_js` from `tests/test_results_bridge.py` (they exist).
- Produces, for the tests and for Task 8's render script:
  - `document.documentElement.dataset.bridge === "ready"` once the channel is up, and
    `document.documentElement.dataset.renders` (a counter) after every render;
  - `#browse[data-view]`; `#panel` (the three panels) and `#card` (the list), one of them `hidden`;
  - `.tab[data-tab]` with `aria-selected`, each holding a `.segment-count`; `#search`; `#count`; `#refresh`;
  - `#head` with `#head-check`; `#selbar` with `#sel-check`, `#sel-count`, `#sel-open`, `#status-button`,
    `#status-menu` (`#status-title`, four `.status-item[data-status]`), `#comment-button`, `#comment-pop`
    (`#comment-title`, `#comment-text`, `#comment-note`, `#comment-cancel`, `#comment-save`), `#sel-export`;
  - `#list` holding `.group-head[data-group]` and `.row[data-row]`, or `.sk-row`, or a `.state` panel;
  - `#footer` with `#archived-count` and a `[data-act="toggle-archived"]` link;
  - `#toast`, `#toast-text`, `#toast-undo`, `#toast-dismiss`;
  - `window.browseBridge`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_browse_page.py`:

```python
"""The Browse page, driven through a real Chromium (phase 4 spec section 5).

Every test pushes a state built by browse_state() and reads the DOM back.
1166x720 is the page a 1366x768 window gives. Never mark skip.
"""

import json

import pytest
from PySide6.QtWebEngineWidgets import QWebEngineView
from test_browse_state import D, H, make_state, session
from test_results_bridge import _eval, _rgb, _until_js

from gui.browse_bridge import PAGE, mount_browse_page
from gui.theme_manager import get_theme_manager
from gui.web_page import THEME_MARKER

# Newest first, as SessionManager.list_client_sessions returns them.
SESSIONS = [
    session("2026-09-30_2", age=3 * H, orders=64, items=131),
    session(
        "2026-09-30_1", age=6 * H, orders=1197, items=2402, blocked=9, lists=4, done=3,
        comment="Morning wave, DHL pickup 15:00",
    ),
    session("2026-09-29_2", age=1 * D, orders=142, items=296, lists=3, done=2, comment="Evening wave"),
    session("2026-09-29_1", age=1 * D, status="completed", lists=3, done=3),
    session("2026-09-28_1", age=2 * D, blocked=3, lists=2, paused=True, comment="Waiting on SRM-30ML restock"),
    session("2026-09-26_2", age=4 * D, status="completed", lists=5, done=4, comment="8 orders back on shelf"),
    session("2026-09-24_1", age=6 * D, status="abandoned", comment="Duplicate import of 09-23"),
    session("2026-09-23_1", age=9 * D, lists=3, done=1, idle=8 * D),
    session("2026-09-05_1", age=26 * D, status="completed", lists=2, done=2),
    session("2026-08-20_1", age=41 * D, status="archived", lists=2, done=2),
    session("2026-08-18_1", age=43 * D, status="archived", lists=2, done=2),
]
ALL = [s["session_name"] for s in SESSIONS[:9]]
ATTENTION = ["2026-09-30_1", "2026-09-28_1", "2026-09-26_2", "2026-09-23_1"]


@pytest.fixture
def page(qtbot):
    view = QWebEngineView()
    qtbot.addWidget(view)
    bridge = mount_browse_page(view)
    view.resize(1166, 720)
    view.show()
    _until_js(qtbot, view, "document.documentElement.dataset.bridge === 'ready'")
    return view, bridge


def _renders(qtbot, view):
    return _eval(qtbot, view, "Number(document.documentElement.dataset.renders || 0)")


def _show(qtbot, view, bridge, state):
    """Push a state and wait for the page to have drawn it."""
    before = _renders(qtbot, view)
    bridge.set_state(state)
    _until_js(qtbot, view, f"Number(document.documentElement.dataset.renders) > {before}")


@pytest.fixture
def listed(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state(SESSIONS))
    return view, bridge


def _json(qtbot, view, expr):
    """A list or an object from the page: runJavaScript hands back only scalars."""
    return json.loads(_eval(qtbot, view, f"JSON.stringify({expr})"))


def _text(qtbot, view, selector):
    return _eval(
        qtbot,
        view,
        f"document.querySelector({selector!r}).textContent.replace(/\\s+/g, ' ').trim()",
    )


def _texts(qtbot, view, selector):
    return _json(
        qtbot,
        view,
        f"Array.from(document.querySelectorAll({selector!r}))"
        ".map(e => e.textContent.replace(/\\s+/g, ' ').trim())",
    )


def _count(qtbot, view, selector):
    return _eval(qtbot, view, f"document.querySelectorAll({selector!r}).length")


def _click(qtbot, view, selector):
    _eval(qtbot, view, f"document.querySelector({selector!r}).click(); true")


def _hidden(qtbot, view, element_id):
    return _eval(qtbot, view, f"document.getElementById({element_id!r}).hidden")


def _style(qtbot, view, selector, prop):
    return _eval(qtbot, view, f"getComputedStyle(document.querySelector({selector!r})).{prop}")


def _rows(qtbot, view):
    """The session names drawn, top to bottom."""
    return _json(qtbot, view, "Array.from(document.querySelectorAll('.row')).map(r => r.dataset.row)")


def _row(name):
    return f'[data-row="{name}"]'


def _check(qtbot, view, *names):
    for name in names:
        _click(qtbot, view, _row(name))


def _search(qtbot, view, text):
    _eval(
        qtbot,
        view,
        f"(function () {{ var s = document.getElementById('search'); s.value = {text!r};"
        " s.dispatchEvent(new Event('input')); return true; })()",
    )


def _key(qtbot, view, selector, key, ctrl=False):
    _eval(
        qtbot,
        view,
        f"document.querySelector({selector!r}).dispatchEvent(new KeyboardEvent('keydown',"
        f" {{key: {key!r}, ctrlKey: {str(ctrl).lower()}, bubbles: true, cancelable: true}})); true",
    )


def _focused(qtbot, view):
    return _eval(qtbot, view, "(document.activeElement.dataset.key || document.activeElement.id)")


def _never(qtbot, signal):
    """Give a signal that must not fire the time to fire."""
    with qtbot.assertNotEmitted(signal, wait=300):
        pass


def test_the_page_carries_the_theme_marker_exactly_once():
    assert PAGE.read_text(encoding="utf-8").count(THEME_MARKER) == 1


def test_the_page_links_the_kit_before_its_own_stylesheet():
    html = PAGE.read_text(encoding="utf-8")
    assert html.index('href="kit.css"') < html.index('href="browse.css"')


# --- views -------------------------------------------------------------------


def test_no_client_shows_one_panel_and_no_list(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state(client=""))
    assert _eval(qtbot, view, "document.getElementById('browse').dataset.view") == "no_client"
    assert _text(qtbot, view, "#panel .state-title") == "Choose a client"
    assert _text(qtbot, view, "#panel .state-text") == (
        "Pick a client in the bar above to see its sessions."
    )
    assert _count(qtbot, view, "#panel .btn") == 0
    assert _hidden(qtbot, view, "card") is True


def test_a_client_with_no_sessions_offers_a_new_one(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state([]))
    assert _text(qtbot, view, "#panel .state-title") == "No sessions yet"
    assert _text(qtbot, view, "#panel .state-text") == (
        "CLIENT_ACME has no sessions on the file server."
    )
    assert "primary" in _eval(
        qtbot, view, "document.querySelector(\"[data-act='new-session']\").className"
    )
    with qtbot.waitSignal(bridge.newSessionRequested, timeout=5000):
        _click(qtbot, view, "[data-act='new-session']")


def test_a_failed_load_says_so_and_offers_to_try_again(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state(failed=True))
    assert _text(qtbot, view, "#panel .state-title") == "Sessions didn't load"
    assert _text(qtbot, view, "#panel .state-text") == "Details are in Logs."
    with qtbot.waitSignal(bridge.refreshRequested, timeout=5000):
        _click(qtbot, view, "[data-act='refresh']")


def test_loading_shows_the_skeleton_and_quiet_controls(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state(SESSIONS, loading=True))
    assert _hidden(qtbot, view, "card") is False
    assert _count(qtbot, view, ".sk-row") == 10
    assert _count(qtbot, view, ".row") == 0
    assert _text(qtbot, view, ".loading-line") == "Reading sessions from the server…"
    assert _texts(qtbot, view, ".tab .segment-count") == ["–"] * 5
    assert _text(qtbot, view, "#count") == "Reading…"
    assert _eval(qtbot, view, "document.getElementById('refresh').disabled") is True
    assert _eval(qtbot, view, "document.getElementById('head-check').disabled") is True
    assert _count(qtbot, view, "#footer [data-act]") == 0


def test_refresh_asks_python(qtbot, listed):
    view, bridge = listed
    assert _eval(qtbot, view, "document.getElementById('refresh').title") == "Refresh  F5"
    with qtbot.waitSignal(bridge.refreshRequested, timeout=5000):
        _click(qtbot, view, "#refresh")


# --- tabs and search ---------------------------------------------------------


def test_the_tabs_count_their_sessions(qtbot, listed):
    view, _bridge = listed
    assert _texts(qtbot, view, ".tab") == [
        "All9", "Active5", "Completed3", "Abandoned1", "Archived2",
    ]
    assert _eval(qtbot, view, "document.querySelector('[data-tab=\"all\"]').getAttribute('aria-selected')") == "true"
    assert _text(qtbot, view, "#count") == "9 sessions"
    assert _rows(qtbot, view) == ATTENTION + [n for n in ALL if n not in ATTENTION]


def test_a_tab_filters_by_the_stored_status_and_unchecks(qtbot, listed):
    view, _bridge = listed
    _check(qtbot, view, "2026-09-29_1")
    assert _hidden(qtbot, view, "selbar") is False

    _click(qtbot, view, '[data-tab="completed"]')

    assert _rows(qtbot, view) == ["2026-09-26_2", "2026-09-29_1", "2026-09-05_1"]
    assert _text(qtbot, view, "#count") == "3 sessions"
    assert _hidden(qtbot, view, "selbar") is True
    assert _count(qtbot, view, ".row.checked") == 0
    _click(qtbot, view, '[data-tab="archived"]')
    assert _rows(qtbot, view) == ["2026-08-20_1", "2026-08-18_1"]


def test_arrow_keys_walk_the_tabs(qtbot, listed):
    view, _bridge = listed
    _eval(qtbot, view, "document.querySelector('[data-tab=\"all\"]').focus(); true")
    _key(qtbot, view, "#tabs .tab[aria-selected='true']", "ArrowRight")
    assert _focused(qtbot, view) == "tab-active"
    assert _text(qtbot, view, "#count") == "5 sessions"
    _key(qtbot, view, "#tabs .tab[aria-selected='true']", "ArrowLeft")
    _key(qtbot, view, "#tabs .tab[aria-selected='true']", "ArrowLeft")
    assert _focused(qtbot, view) == "tab-archived"


def test_search_matches_a_name_or_a_comment(qtbot, listed):
    view, _bridge = listed
    _search(qtbot, view, "DHL ")
    assert _rows(qtbot, view) == ["2026-09-30_1"]
    assert _text(qtbot, view, "#count") == "1 of 9 sessions"
    _search(qtbot, view, "09-29")
    assert _rows(qtbot, view) == ["2026-09-29_2", "2026-09-29_1"]
    assert _texts(qtbot, view, ".tab .segment-count") == ["9", "5", "3", "1", "2"]


def test_typing_in_search_unchecks(qtbot, listed):
    view, _bridge = listed
    _check(qtbot, view, "2026-09-29_1")
    _search(qtbot, view, "09")
    assert _hidden(qtbot, view, "selbar") is True


def test_one_session_is_counted_in_the_singular(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state(SESSIONS[:1]))
    assert _text(qtbot, view, "#count") == "1 session"


def test_a_search_with_no_match_offers_to_clear_it(qtbot, listed):
    view, _bridge = listed
    _search(qtbot, view, "2025-12")
    assert _count(qtbot, view, ".row") == 0
    assert _text(qtbot, view, "#list .state-title") == "No sessions match"
    assert _text(qtbot, view, "#list .state-text") == (
        "Nothing in All has “2025-12” in its name or comment."
    )
    assert _text(qtbot, view, "#count") == "0 of 9 sessions"

    _click(qtbot, view, "[data-act='clear-search']")

    assert _eval(qtbot, view, "document.getElementById('search').value") == ""
    assert len(_rows(qtbot, view)) == 9


def test_the_search_text_is_quoted_as_text(qtbot, listed):
    view, _bridge = listed
    _search(qtbot, view, '<b>"X"</b>')
    assert _text(qtbot, view, "#list .state-text") == (
        'Nothing in All has “<b>"X"</b>” in its name or comment.'
    )
    assert _count(qtbot, view, "#list b") == 0


def test_an_empty_tab_says_so_and_offers_nothing(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state([s for s in SESSIONS if s["status"] != "abandoned"]))
    _click(qtbot, view, '[data-tab="abandoned"]')
    assert _text(qtbot, view, "#list .state-title") == "Nothing in Abandoned"
    assert _text(qtbot, view, "#list .state-text") == "No session of this client is abandoned."
    assert _count(qtbot, view, "#list .btn") == 0


def test_a_client_whose_sessions_are_all_archived_offers_to_show_them(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state(SESSIONS[9:]))
    assert _text(qtbot, view, "#list .state-title") == "Nothing in All"
    assert _text(qtbot, view, "#list .state-text") == "Every session of this client is archived."

    _click(qtbot, view, "#list [data-act='toggle-archived']")

    assert _rows(qtbot, view) == ["2026-08-20_1", "2026-08-18_1"]


# --- groups and rows ---------------------------------------------------------


def test_needs_attention_comes_first_and_says_why(qtbot, listed):
    view, _bridge = listed
    assert _texts(qtbot, view, ".group-label") == ["Needs attention", "Everything else"]
    assert _texts(qtbot, view, ".group-count") == ["4", "5"]
    assert _texts(qtbot, view, ".group-note") == [
        "1 paused · 1 stale · 1 incomplete · 1 with blocked orders",
        "",
    ]
    assert _count(qtbot, view, "[data-group='attention'] .group-dot") == 1
    assert _count(qtbot, view, "[data-group='rest'] .group-dot") == 0
    theme = get_theme_manager().get_current_theme()
    assert _style(qtbot, view, ".group-dot", "backgroundColor") == _rgb(theme.status_warning)


def test_with_nothing_needing_attention_the_one_group_takes_the_tabs_name(qtbot, listed):
    view, _bridge = listed
    _click(qtbot, view, '[data-tab="abandoned"]')
    assert _texts(qtbot, view, ".group-label") == ["Abandoned"]
    _click(qtbot, view, '[data-tab="completed"]')
    assert _texts(qtbot, view, ".group-label") == ["Needs attention", "Everything else"]
    assert _texts(qtbot, view, ".group-note")[0] == "1 incomplete"


def test_a_row_draws_its_badge_with_its_tone_and_dot(qtbot, listed):
    view, _bridge = listed
    theme = get_theme_manager().get_current_theme()
    cases = {
        "2026-09-30_2": ("Not started", "neutral", "hollow"),
        "2026-09-30_1": ("In progress", "info", "half"),
        "2026-09-28_1": ("Paused", "warning", "half"),
        "2026-09-23_1": ("Stale", "warning", "half"),
        "2026-09-29_1": ("Completed", "success", "solid"),
        "2026-09-26_2": ("Incomplete", "danger", "solid"),
        "2026-09-24_1": ("Abandoned", "neutral", "solid"),
    }
    for name, (label, tone, dot) in cases.items():
        assert _text(qtbot, view, f"{_row(name)} .badge") == label
        classes = _eval(qtbot, view, f"document.querySelector('{_row(name)} .badge').className")
        assert tone in classes.split()
        dots = _eval(qtbot, view, f"document.querySelector('{_row(name)} .badge-dot').className")
        assert dot in dots.split()
    assert _style(qtbot, view, f"{_row('2026-09-30_1')} .badge", "backgroundColor") == _rgb(
        theme.status_info_bg
    )
    assert _style(qtbot, view, f"{_row('2026-09-26_2')} .badge", "color") == _rgb(
        theme.status_danger
    )


def test_the_cells_of_a_row(qtbot, listed):
    view, _bridge = listed
    row = _row("2026-09-30_1")
    assert _text(qtbot, view, f"{row} .cell-name") == "2026-09-30_1"
    assert _text(qtbot, view, f"{row} .cell-age") == "6 h"
    assert _texts(qtbot, view, f"{row} .cell-num") == ["1,197", "2,402", "9"]
    assert _text(qtbot, view, f"{row} .pack-text") == "3 / 4"
    assert _eval(qtbot, view, f"document.querySelector('{row} .cell-pack').title") == (
        "3 of 4 packing lists completed in Packing Tool"
    )
    assert _text(qtbot, view, f"{row} .cell-comment") == "Morning wave, DHL pickup 15:00"
    assert _eval(qtbot, view, f"document.querySelector('{row} .cell-comment').title") == (
        "Morning wave, DHL pickup 15:00"
    )


def test_empty_cells_draw_a_dash(qtbot, listed):
    view, _bridge = listed
    theme = get_theme_manager().get_current_theme()
    row = _row("2026-09-30_2")
    assert _texts(qtbot, view, f"{row} .none") == ["—", "—", "—"]  # blocked, packing, comment
    assert _count(qtbot, view, f"{row} .pack-track") == 0
    assert _style(qtbot, view, f"{row} .cell-comment", "color") == _rgb(theme.text_disabled)


def test_blocked_is_red_only_while_the_session_is_in_flight(qtbot, page):
    view, bridge = page
    sessions = [
        session("in-flight", blocked=9, lists=3, done=1),
        session("closed", status="completed", blocked=4, lists=2, done=2),
    ]
    _show(qtbot, view, bridge, make_state(sessions))
    theme = get_theme_manager().get_current_theme()
    assert _style(qtbot, view, f"{_row('in-flight')} .cell-num.alert", "color") == _rgb(
        theme.status_danger
    )
    assert _count(qtbot, view, f"{_row('closed')} .cell-num.alert") == 0
    assert _texts(qtbot, view, f"{_row('closed')} .cell-num")[2] == "4"


def test_the_age_warns_before_the_auto_archive(qtbot, listed):
    view, _bridge = listed
    theme = get_theme_manager().get_current_theme()
    age = f"{_row('2026-09-05_1')} .cell-age"
    assert _text(qtbot, view, age) == "26 d"
    assert _style(qtbot, view, age, "color") == _rgb(theme.status_warning)
    assert _eval(qtbot, view, f"document.querySelector('{age}').title").endswith(
        " · Archives in 4 d"
    )
    assert _style(qtbot, view, f"{_row('2026-09-29_1')} .cell-age", "color") == _rgb(
        theme.text_secondary
    )


def test_the_packing_bar_fills_and_takes_its_tone(qtbot, listed):
    view, _bridge = listed
    theme = get_theme_manager().get_current_theme()

    def fill(name):
        selector = f"{_row(name)} .pack-fill"
        return (
            _eval(qtbot, view, f"document.querySelector('{selector}').style.width"),
            _style(qtbot, view, selector, "backgroundColor"),
        )

    assert fill("2026-09-29_1") == ("100%", _rgb(theme.status_success_dot))
    assert fill("2026-09-26_2") == ("80%", _rgb(theme.status_danger_dot))
    assert fill("2026-09-29_2") == ("67%", _rgb(theme.text_secondary))


def test_a_comment_is_drawn_as_text_never_as_markup(qtbot, page):
    view, bridge = page
    nasty = '<b>bold</b> "quoted" & <img src=x onerror=alert(1)>'
    _show(qtbot, view, bridge, make_state([session("s1", comment=nasty)]))
    assert _text(qtbot, view, f"{_row('s1')} .cell-comment") == nasty
    assert _count(qtbot, view, ".row b, .row img") == 0


def test_a_name_with_quotes_and_brackets_is_drawn_as_text_and_named_exactly(qtbot, page):
    view, bridge = page
    odd = 'copy of "2026-09-30_1" <old>'
    _show(qtbot, view, bridge, make_state([session(odd, lists=1), session("plain")]))
    assert _texts(qtbot, view, ".cell-name") == [odd, "plain"]

    _eval(
        qtbot,
        view,
        "document.querySelectorAll('.row input')[0].focus();"
        " document.querySelectorAll('.row')[0].click(); true",
    )

    assert _text(qtbot, view, "#sel-count") == "1 selected"
    assert _eval(qtbot, view, "document.activeElement.dataset.key") == f"row-{odd}"
    _click(qtbot, view, "#status-button")
    with qtbot.waitSignal(bridge.statusRequested, timeout=5000) as asked:
        _click(qtbot, view, '[data-status="completed"]')
    assert asked.args == [[odd], "completed"]


def test_a_long_comment_keeps_the_row_one_line_high(qtbot, page):
    view, bridge = page
    long = "word " * 80
    _show(qtbot, view, bridge, make_state([session("a", comment=long), session("b")]))
    heights = _json(
        qtbot, view, "Array.from(document.querySelectorAll('.row')).map(r => r.offsetHeight)"
    )
    assert heights[0] == heights[1]
    assert _eval(
        qtbot, view, "document.querySelector('.cell-comment').title"
    ) == long.strip()


# --- selection ---------------------------------------------------------------


def test_a_click_checks_the_row_and_the_bar_takes_the_headers_place(qtbot, listed):
    view, _bridge = listed
    assert _hidden(qtbot, view, "selbar") is True
    assert _hidden(qtbot, view, "head") is False

    _check(qtbot, view, "2026-09-29_2")

    assert _hidden(qtbot, view, "selbar") is False
    assert _hidden(qtbot, view, "head") is True
    assert _text(qtbot, view, "#sel-count") == "1 selected"
    assert _hidden(qtbot, view, "sel-open") is False
    assert _hidden(qtbot, view, "sel-export") is True
    assert _eval(qtbot, view, f"document.querySelector('{_row('2026-09-29_2')} input').checked") is True
    theme = get_theme_manager().get_current_theme()
    assert _style(qtbot, view, _row("2026-09-29_2"), "backgroundColor") == _rgb(theme.selection_bg)

    _check(qtbot, view, "2026-09-26_2")
    assert _text(qtbot, view, "#sel-count") == "2 selected"
    assert _hidden(qtbot, view, "sel-open") is True
    assert _hidden(qtbot, view, "sel-export") is False

    _check(qtbot, view, "2026-09-29_2", "2026-09-26_2")
    assert _hidden(qtbot, view, "selbar") is True


def test_the_header_checkbox_checks_every_visible_row_and_the_bars_clears(qtbot, listed):
    view, _bridge = listed
    _search(qtbot, view, "09-29")
    _click(qtbot, view, "#head-check")
    assert _text(qtbot, view, "#sel-count") == "2 selected"
    assert _eval(qtbot, view, "document.getElementById('sel-check').checked") is True

    _click(qtbot, view, "#sel-check")

    assert _hidden(qtbot, view, "selbar") is True
    assert _count(qtbot, view, ".row.checked") == 0


def test_open_and_export_name_the_checked_sessions(qtbot, listed):
    view, bridge = listed
    _check(qtbot, view, "2026-09-29_2")
    with qtbot.waitSignal(bridge.openRequested, timeout=5000) as opened:
        _click(qtbot, view, "#sel-open")
    assert opened.args == ["2026-09-29_2"]

    _check(qtbot, view, "2026-09-26_2")
    with qtbot.waitSignal(bridge.exportRequested, timeout=5000) as exported:
        _click(qtbot, view, "#sel-export")
    assert exported.args == [["2026-09-29_2", "2026-09-26_2"]]


def test_double_click_and_enter_open_the_session(qtbot, listed):
    view, bridge = listed
    with qtbot.waitSignal(bridge.openRequested, timeout=5000) as opened:
        _eval(
            qtbot,
            view,
            f"document.querySelector('{_row('2026-09-29_1')}')"
            ".dispatchEvent(new MouseEvent('dblclick', {bubbles: true})); true",
        )
    assert opened.args == ["2026-09-29_1"]

    with qtbot.waitSignal(bridge.openRequested, timeout=5000) as opened:
        _key(qtbot, view, f"{_row('2026-09-28_1')} input", "Enter")
    assert opened.args == ["2026-09-28_1"]


def test_up_and_down_walk_the_rows_across_groups(qtbot, listed):
    view, _bridge = listed
    last_attention = f"{_row('2026-09-23_1')} input"
    _eval(qtbot, view, f"document.querySelector('{last_attention}').focus(); true")
    _key(qtbot, view, last_attention, "ArrowDown")
    assert _focused(qtbot, view) == "row-2026-09-30_2"
    _key(qtbot, view, f"{_row('2026-09-30_2')} input", "ArrowUp")
    assert _focused(qtbot, view) == "row-2026-09-23_1"


def test_a_checked_checkbox_keeps_focus_through_the_redraw(qtbot, listed):
    view, _bridge = listed
    box = f"{_row('2026-09-29_1')} input"
    _eval(qtbot, view, f"document.querySelector('{box}').focus(); true")
    _click(qtbot, view, box)
    assert _focused(qtbot, view) == "row-2026-09-29_1"
    assert _eval(qtbot, view, f"document.querySelector('{box}').checked") is True


def test_another_clients_rows_never_inherit_the_view_state(qtbot, listed):
    view, bridge = listed
    _click(qtbot, view, '[data-tab="active"]')
    _search(qtbot, view, "09-30")
    _check(qtbot, view, "2026-09-30_1")

    _show(qtbot, view, bridge, make_state(SESSIONS, client="BETA"))

    assert _eval(qtbot, view, "document.getElementById('search').value") == ""
    assert _eval(qtbot, view, "document.querySelector('[data-tab=\"all\"]').getAttribute('aria-selected')") == "true"
    assert _count(qtbot, view, ".row.checked") == 0
    assert len(_rows(qtbot, view)) == 9


def test_a_loud_reload_unchecks_and_a_quiet_one_does_not(qtbot, listed):
    view, bridge = listed
    _check(qtbot, view, "2026-09-29_1")
    _show(qtbot, view, bridge, make_state(SESSIONS[1:]))  # a quiet reload: new rows
    assert _text(qtbot, view, "#sel-count") == "1 selected"

    _show(qtbot, view, bridge, make_state(SESSIONS, loading=True))
    _show(qtbot, view, bridge, make_state(SESSIONS))

    assert _hidden(qtbot, view, "selbar") is True


def test_rows_that_leave_the_tab_stop_being_acted_on(qtbot, listed):
    view, bridge = listed
    gone = ("2026-09-29_2", "2026-09-29_1")
    _check(qtbot, view, *gone)
    _click(qtbot, view, "#status-button")

    archived = [
        dict(s, status="archived") if s["session_name"] in gone else s for s in SESSIONS
    ]
    _show(qtbot, view, bridge, make_state(archived))

    assert _hidden(qtbot, view, "selbar") is True
    assert _hidden(qtbot, view, "head") is False
    assert _hidden(qtbot, view, "status-menu") is True
    assert _text(qtbot, view, "#archived-count") == "4 archived"


# --- the Status menu ---------------------------------------------------------


def test_the_status_menu_offers_the_four_and_says_what_each_resolves_to(qtbot, listed):
    view, _bridge = listed
    _check(qtbot, view, "2026-09-29_2")
    assert _hidden(qtbot, view, "status-menu") is True

    _click(qtbot, view, "#status-button")

    assert _hidden(qtbot, view, "status-menu") is False
    assert _eval(qtbot, view, "document.getElementById('status-button').getAttribute('aria-expanded')") == "true"
    assert _text(qtbot, view, "#status-title") == "Set status for 2026-09-29_2"
    assert _texts(qtbot, view, ".status-item .badge") == [
        "Active", "Completed", "Abandoned", "Archived",
    ]
    assert _texts(qtbot, view, ".status-note") == [
        "Shows as Not started, In progress, Paused or Stale from activity",
        "Shows as Incomplete if packing is not finished",
        "Kept on the server. Repeat-order checks ignore it",
        "Hidden from All until you choose Show",
    ]


def test_choosing_a_status_names_every_checked_session(qtbot, listed):
    view, bridge = listed
    _check(qtbot, view, "2026-09-29_2", "2026-09-26_2")
    _click(qtbot, view, "#status-button")
    assert _text(qtbot, view, "#status-title") == "Set status for 2 sessions"

    with qtbot.waitSignal(bridge.statusRequested, timeout=5000) as asked:
        _click(qtbot, view, '[data-status="archived"]')

    assert asked.args == [["2026-09-29_2", "2026-09-26_2"], "archived"]
    assert _hidden(qtbot, view, "status-menu") is True
    assert _text(qtbot, view, "#sel-count") == "2 selected"  # still checked


def test_escape_closes_the_menu_and_returns_focus_to_its_button(qtbot, listed):
    view, bridge = listed
    _check(qtbot, view, "2026-09-29_2")
    _click(qtbot, view, "#status-button")
    _key(qtbot, view, "#status-menu", "Escape")
    assert _hidden(qtbot, view, "status-menu") is True
    assert _focused(qtbot, view) == "status-button"
    _never(qtbot, bridge.statusRequested)


def test_a_press_outside_closes_the_menu(qtbot, listed):
    view, _bridge = listed
    _check(qtbot, view, "2026-09-29_2")
    _click(qtbot, view, "#status-button")
    _eval(
        qtbot,
        view,
        "document.getElementById('footer').dispatchEvent(new MouseEvent('mousedown', {bubbles: true})); true",
    )
    assert _hidden(qtbot, view, "status-menu") is True


# --- the Comment popover -----------------------------------------------------


def test_the_comment_popover_opens_with_the_sessions_comment(qtbot, listed):
    view, bridge = listed
    _check(qtbot, view, "2026-09-29_2")
    _click(qtbot, view, "#comment-button")

    assert _hidden(qtbot, view, "comment-pop") is False
    assert _text(qtbot, view, "#comment-title") == "Comment on 2026-09-29_2"
    assert _eval(qtbot, view, "document.getElementById('comment-text').value") == "Evening wave"
    assert _text(qtbot, view, "#comment-note") == "Shown in the Comment column."
    assert _focused(qtbot, view) == "comment-text"

    _eval(qtbot, view, "document.getElementById('comment-text').value = '  late van  '; true")
    with qtbot.waitSignal(bridge.commentRequested, timeout=5000) as asked:
        _click(qtbot, view, "#comment-save")

    assert asked.args == [["2026-09-29_2"], "late van"]
    assert _hidden(qtbot, view, "comment-pop") is True


def test_a_comment_on_several_starts_empty_and_says_what_it_replaces(qtbot, listed):
    view, bridge = listed
    _check(qtbot, view, "2026-09-29_2", "2026-09-26_2")
    _click(qtbot, view, "#comment-button")
    assert _text(qtbot, view, "#comment-title") == "Comment on 2 sessions"
    assert _eval(qtbot, view, "document.getElementById('comment-text').value") == ""
    assert _text(qtbot, view, "#comment-note") == (
        "Replaces the comment on 2026-09-29_2, 2026-09-26_2."
    )

    with qtbot.waitSignal(bridge.commentRequested, timeout=5000) as asked:
        _key(qtbot, view, "#comment-text", "Enter", ctrl=True)

    assert asked.args == [["2026-09-29_2", "2026-09-26_2"], ""]


def test_more_than_three_names_are_summarised(qtbot, listed):
    view, _bridge = listed
    _click(qtbot, view, "#head-check")
    _click(qtbot, view, "#comment-button")
    assert _text(qtbot, view, "#comment-note") == (
        "Replaces the comment on 2026-09-30_2, 2026-09-30_1 and 7 more."
    )


def test_cancel_and_escape_close_the_popover_without_saving(qtbot, listed):
    view, bridge = listed
    _check(qtbot, view, "2026-09-29_2")
    _click(qtbot, view, "#comment-button")
    _click(qtbot, view, "#comment-cancel")
    assert _hidden(qtbot, view, "comment-pop") is True

    _click(qtbot, view, "#comment-button")
    _key(qtbot, view, "#comment-text", "Escape")
    assert _hidden(qtbot, view, "comment-pop") is True
    assert _focused(qtbot, view) == "comment-button"
    _never(qtbot, bridge.commentRequested)


def test_a_state_push_leaves_an_open_popover_and_its_draft_alone(qtbot, listed):
    view, bridge = listed
    _check(qtbot, view, "2026-09-29_2")
    _click(qtbot, view, "#comment-button")
    _eval(qtbot, view, "document.getElementById('comment-text').value = 'half typed'; true")

    _show(qtbot, view, bridge, make_state(SESSIONS[1:]))

    assert _hidden(qtbot, view, "comment-pop") is False
    assert _eval(qtbot, view, "document.getElementById('comment-text').value") == "half typed"


def test_only_one_of_the_menu_and_the_popover_is_open(qtbot, listed):
    view, _bridge = listed
    _check(qtbot, view, "2026-09-29_2")
    _click(qtbot, view, "#status-button")
    _click(qtbot, view, "#comment-button")
    assert _hidden(qtbot, view, "status-menu") is True
    assert _hidden(qtbot, view, "comment-pop") is False


def test_unchecking_the_last_row_closes_an_open_popover(qtbot, listed):
    view, _bridge = listed
    _check(qtbot, view, "2026-09-29_2")
    _click(qtbot, view, "#comment-button")
    _check(qtbot, view, "2026-09-29_2")
    assert _hidden(qtbot, view, "comment-pop") is True


# --- footer ------------------------------------------------------------------


def test_the_footer_counts_the_archived_and_shows_them_on_request(qtbot, listed):
    view, _bridge = listed
    assert _text(qtbot, view, "#archived-count") == "2 archived"
    assert _text(qtbot, view, "#footer [data-act='toggle-archived']") == "Show"
    assert _text(qtbot, view, "#footer").endswith("Double-click a session to open it")

    _click(qtbot, view, "#footer [data-act='toggle-archived']")

    assert len(_rows(qtbot, view)) == 11
    assert _text(qtbot, view, "#archived-count") == "2 archived shown"
    assert _text(qtbot, view, "#footer [data-act='toggle-archived']") == "Hide"
    assert _text(qtbot, view, "#count") == "11 sessions"
    assert _texts(qtbot, view, ".tab .segment-count")[0] == "9"  # All never counts them

    _click(qtbot, view, "#footer [data-act='toggle-archived']")
    assert len(_rows(qtbot, view)) == 9


def test_the_archived_line_is_on_all_only_and_only_with_archived_sessions(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state(SESSIONS))
    _click(qtbot, view, '[data-tab="active"]')
    assert _count(qtbot, view, "#footer [data-act]") == 0

    _show(qtbot, view, bridge, make_state(SESSIONS[:9]))
    _click(qtbot, view, '[data-tab="all"]')
    assert _count(qtbot, view, "#footer [data-act]") == 0


# --- toast -------------------------------------------------------------------


def test_an_undoable_toast_offers_undo(qtbot, listed):
    view, bridge = listed
    bridge.raise_toast("Set 2 sessions to Archived", True)
    _until_js(qtbot, view, "document.getElementById('toast').hidden === false")
    assert _text(qtbot, view, "#toast-text") == "Set 2 sessions to Archived"
    assert _hidden(qtbot, view, "toast-undo") is False

    with qtbot.waitSignal(bridge.undoRequested, timeout=5000):
        _click(qtbot, view, "#toast-undo")
    assert _hidden(qtbot, view, "toast") is True


def test_a_plain_toast_has_no_undo_and_can_be_dismissed(qtbot, listed):
    view, bridge = listed
    bridge.raise_toast("Combined stock export saved: stock.xlsx.")
    _until_js(qtbot, view, "document.getElementById('toast').hidden === false")
    assert _hidden(qtbot, view, "toast-undo") is True
    _click(qtbot, view, "#toast-dismiss")
    assert _hidden(qtbot, view, "toast") is True


# --- the card fits the page --------------------------------------------------


def test_the_card_fills_the_page_and_the_list_scrolls_inside_it(qtbot, page):
    view, bridge = page
    many = [session(f"2026-07-{d:02d}_1", age=(60 + d) * D, status="completed", lists=1, done=1) for d in range(1, 31)]
    _show(qtbot, view, bridge, make_state(SESSIONS + many))
    box = _json(
        qtbot,
        view,
        "(function () { var c = document.getElementById('card').getBoundingClientRect();"
        " var l = document.getElementById('list');"
        " return {top: c.top, bottom: c.bottom, left: c.left, right: c.right,"
        " scrolls: l.scrollHeight > l.clientHeight, page: document.documentElement.scrollHeight}; })()",
    )
    assert (box["top"], box["left"], box["right"], box["bottom"]) == (16, 24, 1142, 700)
    assert box["scrolls"] is True
    assert box["page"] == 720


def test_a_narrow_window_drops_the_count_then_scrolls_sideways(qtbot, listed):
    view, _bridge = listed
    view.resize(900, 720)
    _until_js(qtbot, view, "window.innerWidth === 900")
    assert _style(qtbot, view, "#count", "display") == "none"

    view.resize(700, 720)
    _until_js(qtbot, view, "window.innerWidth === 700")
    box = _json(
        qtbot,
        view,
        "(function () { var b = document.getElementById('browse');"
        " return {card: document.getElementById('card').offsetWidth,"
        " scrolls: b.scrollWidth > b.clientWidth}; })()",
    )
    assert box == {"card": 780, "scrolls": True}
```

- [ ] **Step 2: Run them and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_browse_page.py`
Expected: every test fails or errors with `FileNotFoundError` for `gui/web/browse.html`.

- [ ] **Step 3: The document**

Create `gui/web/browse.html`:

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Browse</title>
<!-- gui/web_page.py writes theme_css_vars() over the marker before the page
     loads, then browse.js keeps it current from the bridge. -->
<style id="theme-vars">/* theme-vars */</style>
<link rel="stylesheet" href="kit.css">
<link rel="stylesheet" href="browse.css">
<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
<script src="browse.js" defer></script>
</head>
<body>
<main id="browse" data-view="">
  <section id="panel" class="card" hidden></section>
  <section id="card" class="card" hidden>
    <div class="toolbar">
      <div id="tabs" class="tabs" role="tablist" aria-label="Session status"></div>
      <span class="spacer"></span>
      <label id="search-box" class="input search">
        <input id="search" type="search" placeholder="Search sessions" aria-label="Search sessions">
      </label>
      <span id="count" class="count"></span>
      <button id="refresh" class="btn secondary" type="button" title="Refresh  F5"></button>
    </div>
    <div id="head" class="list-head grid">
      <span class="cell-check"><input id="head-check" type="checkbox" aria-label="Select every session shown"></span>
      <span>Session</span>
      <span class="num">Age</span>
      <span>Status</span>
      <span class="num">Orders</span>
      <span class="num">Items</span>
      <span class="num">Blocked</span>
      <span>Packing</span>
      <span>Comment</span>
    </div>
    <div id="selbar" class="selbar" hidden>
      <span class="cell-check"><input id="sel-check" type="checkbox" aria-label="Clear selection" title="Clear selection"></span>
      <span id="sel-count" class="sel-count"></span>
      <button id="sel-open" class="btn secondary compact" type="button">Open</button>
      <div class="menu-anchor">
        <button id="status-button" class="btn secondary compact" type="button" aria-haspopup="menu" aria-expanded="false"></button>
        <div id="status-menu" class="menu status-menu" role="menu" hidden></div>
      </div>
      <div class="menu-anchor">
        <button id="comment-button" class="btn secondary compact" type="button" aria-haspopup="dialog" aria-expanded="false">Comment…</button>
        <div id="comment-pop" class="popover comment-pop" role="dialog" aria-labelledby="comment-title" hidden>
          <div class="comment-body">
            <span id="comment-title" class="comment-title"></span>
            <textarea id="comment-text" class="comment-text" rows="3" placeholder="Visible to everyone who opens this client"></textarea>
            <span id="comment-note" class="comment-note"></span>
          </div>
          <div class="comment-foot">
            <button id="comment-cancel" class="btn secondary" type="button">Cancel</button>
            <button id="comment-save" class="btn primary" type="button">Save</button>
          </div>
        </div>
      </div>
      <button id="sel-export" class="btn secondary compact" type="button">Export combined stock</button>
    </div>
    <div id="list" class="list"></div>
    <div id="footer" class="footer"></div>
  </section>
</main>
<div id="toast" class="toast" role="status" aria-live="polite" hidden>
  <span id="toast-text"></span>
  <button id="toast-undo" class="toast-action" type="button" hidden>Undo</button>
  <button id="toast-dismiss" class="toast-close" type="button" aria-label="Dismiss"></button>
</div>
</body>
</html>
```

- [ ] **Step 4: The stylesheet**

Create `gui/web/browse.css`:

```css
/* The Browse page (phase 4 spec section 5). Layout, and the three components
   only this page draws: the tab, the badge dot and the skeleton bar. Every
   colour is a token from theme_css_vars(). A divider is --border-subtle, the
   edge of a control is --border (ADR 0018). */

#browse {
  height: 100%;
  overflow-x: auto;
  overflow-y: hidden;
  display: flex;
  flex-direction: column;
  padding: 16px 24px 20px;
}
#browse > .card {
  flex: 1;
  min-width: 780px;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

/* --- the three panels ---------------------------------------------------- */

#panel { align-items: center; justify-content: center; }
#panel .state { gap: 8px; }
#panel .state-glyph { width: 28px; height: 28px; }
#panel .state-title { font-size: var(--type-heading-size); }

/* --- toolbar ------------------------------------------------------------- */

.toolbar {
  flex: none;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px;
  border-bottom: 1px solid var(--border-subtle);
}
.tabs { display: flex; align-items: center; gap: 2px; }
.tab {
  display: flex;
  align-items: center;
  gap: 6px;
  height: var(--control-height);
  padding: 0 10px;
  border: 1px solid transparent;
  border-radius: var(--kit-radius);
  background: transparent;
  color: var(--text-secondary);
  white-space: nowrap;
  cursor: pointer;
}
.tab:hover { background: var(--hover); }
.tab[aria-selected="true"] {
  border-color: var(--border);
  background: var(--surface-raised);
  color: var(--text);
  font-weight: 700;
}
.tab:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 1px; }
.search { flex: 0 1 260px; min-width: 150px; }
.count {
  min-width: 84px;
  font-size: var(--type-caption-size);
  color: var(--text-secondary);
  text-align: right;
  white-space: nowrap;
}

/* --- the row grid: header row, rows and skeleton rows share it ----------- */

.grid {
  display: grid;
  grid-template-columns: 36px 150px 64px 124px 72px 72px 72px 150px minmax(0, 1fr);
  align-items: center;
}
.grid > * { min-width: 0; padding: 0 8px; }
.cell-check { display: grid; place-items: center; }
.grid > .cell-check { padding: 0; }
.num { text-align: right; }

.list-head, .selbar {
  flex: none;
  height: 36px;
  background: var(--surface-raised);
  border-bottom: 1px solid var(--border-subtle);
}
.list-head {
  font-size: var(--type-caption-size);
  font-weight: 700;
  color: var(--text-secondary);
}

/* --- selection bar ------------------------------------------------------- */

.selbar { display: flex; align-items: center; gap: 6px; padding-right: 8px; }
.selbar .cell-check { flex: none; width: 36px; }
.sel-count { margin-right: 6px; font-weight: 700; white-space: nowrap; }

.status-menu { width: 300px; }
.status-item {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 1px;
  width: 100%;
  padding: 6px 10px;
  border: 0;
  border-radius: var(--radius-md);
  background: transparent;
  text-align: left;
  cursor: pointer;
}
.status-item:hover { background: var(--hover); }
.status-item:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 1px; }
.status-note { font-size: var(--type-caption-size); color: var(--text-secondary); }

.comment-pop { width: 340px; }
.comment-body { display: flex; flex-direction: column; gap: 8px; padding: 12px 14px; }
.comment-title { font-size: var(--type-label-size); font-weight: 700; }
.comment-text {
  resize: none;
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: var(--kit-radius);
  background: var(--surface);
  color: var(--text);
  font: inherit;
}
.comment-text::placeholder { color: var(--text-placeholder); }
.comment-text:focus { outline: 2px solid var(--focus-ring); outline-offset: -1px; }
.comment-note { font-size: var(--type-caption-size); color: var(--text-secondary); }
.comment-foot {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 10px 14px;
  border-top: 1px solid var(--border-subtle);
}

/* --- the list ------------------------------------------------------------ */

.list { flex: 1; min-height: 0; overflow: auto; }
.list > .state { padding: 80px 24px; }

.group-head {
  display: flex;
  align-items: center;
  gap: 8px;
  height: var(--row-height);
  padding: 0 12px;
  background: var(--surface-sunken);
  border-bottom: 1px solid var(--border-subtle);
}
.group-dot {
  flex: none;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--status-warning);
}
.group-label { font-weight: 700; }
.group-count, .group-note { font-size: var(--type-caption-size); color: var(--text-secondary); }
.group-count { font-family: var(--font-family-mono); }

.row {
  position: relative;
  height: var(--row-height);
  border-bottom: 1px solid var(--border-subtle);
  cursor: default;
  user-select: none;
}
.row:hover { background: var(--hover); }
.row.checked { background: var(--selection-bg); }
/* The checked row's edge. A strip, not a shadow: only the theme's two shadow
   tokens may be a box-shadow (ADR 0016). */
.row.checked::before {
  content: "";
  position: absolute;
  top: 0;
  bottom: 0;
  left: 0;
  width: 3px;
  background: var(--selection-border);
}

.cell-name, .cell-age, .cell-num, .pack-text { font-family: var(--font-family-mono); white-space: nowrap; }
.cell-name { overflow: hidden; font-weight: 700; text-overflow: ellipsis; }
.cell-age { color: var(--text-secondary); text-align: right; }
.cell-age.warn { color: var(--status-warning); }
.cell-num { text-align: right; }
.cell-num.alert { color: var(--status-danger); font-weight: 700; }
.cell-pack { display: flex; align-items: center; gap: 8px; }
.pack-text { flex: none; width: 72px; }
.pack-track {
  flex: 1;
  max-width: 48px;
  height: 4px;
  overflow: hidden;
  border-radius: 2px;
  background: var(--border);
}
.pack-fill { display: block; height: 100%; border-radius: 2px; background: var(--text-secondary); }
.pack-fill.success { background: var(--status-success-dot); }
.pack-fill.danger { background: var(--status-danger-dot); }
.grid > .cell-comment {
  overflow: hidden;
  padding-right: 12px;
  color: var(--text-secondary);
  white-space: nowrap;
  text-overflow: ellipsis;
}
/* The dash of an empty cell. After the cells, so it wins at equal weight. */
.grid .none { color: var(--text-disabled); }

/* How far a session has come. The half is a clipped block: the web tier may
   not draw a gradient (ADR 0016). */
.badge-dot {
  flex: none;
  position: relative;
  width: 6px;
  height: 6px;
  overflow: hidden;
  border: 1px solid currentColor;
  border-radius: 50%;
}
.badge-dot.solid { background: currentColor; }
.badge-dot.half::after {
  content: "";
  position: absolute;
  top: 0;
  bottom: 0;
  left: 0;
  width: 50%;
  background: currentColor;
}

/* --- loading ------------------------------------------------------------- */

.loading-line {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 40px;
  padding: 0 12px;
  border-bottom: 1px solid var(--border-subtle);
  color: var(--text-secondary);
}
.sk-row { height: var(--row-height); border-bottom: 1px solid var(--border-subtle); }
.sk { display: block; height: 8px; border-radius: 4px; background: var(--border-subtle); }

/* --- footer -------------------------------------------------------------- */

.footer {
  flex: none;
  display: flex;
  align-items: center;
  gap: 6px;
  height: 36px;
  padding: 0 12px;
  border-top: 1px solid var(--border-subtle);
  font-size: var(--type-caption-size);
  color: var(--text-secondary);
}
.footer .btn.link { color: var(--text); }

/* --- a narrow page ------------------------------------------------------- */

@media (max-width: 980px) {
  .count { display: none; }
}
```

- [ ] **Step 5: The script**

Create `gui/web/browse.js`:

```js
// The Browse page (phase 4 spec section 5). Python words every fact about a
// session (gui/browse_state.py) and sends the rows as bridge.state. This file
// owns the view state only: the tab, the search text, the checked rows,
// whether archived rows are shown and which popover is open. It filters,
// counts and groups rows it already holds, and reports what the operator asks
// for through the bridge's named slots, always by session name.
//
// ponytail: the list is redrawn whole on every change, with no row windowing.
// A client has tens of sessions and archived ones are hidden by default.
// Window the rows, as results.js does, if a client ever shows thousands.
"use strict";

const TOAST_MS = 4000;
const SKELETON_ROWS = 10;

// Lucide glyphs, each as one path.
const GLYPH = {
  folder: "m6 14 1.5-2.9A2 2 0 0 1 9.24 10H20a2 2 0 0 1 1.94 2.5l-1.54 6a2 2 0 0 1-1.95 1.5H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.69.9l.81 1.2a2 2 0 0 0 1.67.9H18a2 2 0 0 1 2 2v2",
  alert: "m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3M12 9v4M12 17h.01",
  plus: "M5 12h14M12 5v14",
  search: "M19 11a8 8 0 1 1-16 0 8 8 0 0 1 16 0zM21 21l-4.3-4.3",
  searchX: "M19 11a8 8 0 1 1-16 0 8 8 0 0 1 16 0zM21 21l-4.3-4.3M13.5 8.5l-5 5M8.5 8.5l5 5",
  refresh: "M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8M21 3v5h-5M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16M8 16H3v5",
  loader: "M21 12a9 9 0 1 1-6.22-8.56",
  chevron: "m6 9 6 6 6-6",
  x: "M18 6 6 18M6 6l12 12",
};

const TABS = [
  { key: "all", label: "All" },
  { key: "active", label: "Active" },
  { key: "completed", label: "Completed" },
  { key: "abandoned", label: "Abandoned" },
  { key: "archived", label: "Archived" },
];

// The four statuses a person can set, and what each one resolves to.
const STATUS_ITEMS = [
  { status: "active", label: "Active", tone: "info", dot: "half", note: "Shows as Not started, In progress, Paused or Stale from activity" },
  { status: "completed", label: "Completed", tone: "success", dot: "solid", note: "Shows as Incomplete if packing is not finished" },
  { status: "abandoned", label: "Abandoned", tone: "neutral", dot: "solid", note: "Kept on the server. Repeat-order checks ignore it" },
  { status: "archived", label: "Archived", tone: "neutral", dot: "solid", note: "Hidden from All until you choose Show" },
];

// The Needs attention note, in the order it reads.
const REASONS = [
  ["paused", "paused"],
  ["stale", "stale"],
  ["incomplete", "incomplete"],
  ["blocked", "with blocked orders"],
];

const els = {};
const page = { bridge: null, state: { view: "", client: "", rows: [] }, client: "", renders: 0, toastTimer: null };
const view = { tab: "all", query: "", checked: new Set(), showArchived: false, open: null };

function esc(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function svg(path, cls) {
  return `<svg class="${cls}" viewBox="0 0 24 24" aria-hidden="true"><path d="${path}"/></svg>`;
}

function sessions(n) {
  return n === 1 ? "1 session" : `${n} sessions`;
}

function badge(tone, dot, label) {
  return `<span class="badge ${esc(tone)}"><span class="badge-dot ${esc(dot)}"></span>${esc(label)}</span>`;
}

// --- what the view state selects ---------------------------------------------

function allRows() {
  return (page.state && page.state.rows) || [];
}

function inTab(row, key) {
  if (key === "all") return row.tab !== "archived" || view.showArchived;
  return row.tab === key;
}

// All never counts archived rows, shown or not: the footer counts those.
function tabCount(key) {
  return allRows().filter((row) => (key === "all" ? row.tab !== "archived" : row.tab === key)).length;
}

function visibleRows() {
  const q = view.query;
  return allRows().filter(
    (row) =>
      inTab(row, view.tab) &&
      (!q || row.name.toLowerCase().includes(q) || row.comment.toLowerCase().includes(q)),
  );
}

// A row hidden by the tab or the search is never acted on.
function checkedNames(visible) {
  return visible.filter((row) => view.checked.has(row.name)).map((row) => row.name);
}

function tabLabel() {
  return TABS.find((tab) => tab.key === view.tab).label;
}

// --- the three panels --------------------------------------------------------

function panel(s) {
  if (s.view === "failed") {
    return `<div class="state">
      ${svg(GLYPH.alert, "state-glyph")}
      <p class="state-title">Sessions didn't load</p>
      <p class="state-text">Details are in Logs.</p>
      <button class="btn secondary" type="button" data-act="refresh" data-key="try-again">Try again</button>
    </div>`;
  }
  if (s.view === "empty") {
    return `<div class="state">
      ${svg(GLYPH.folder, "state-glyph")}
      <p class="state-title">No sessions yet</p>
      <p class="state-text">CLIENT_${esc(s.client)} has no sessions on the file server.</p>
      <button class="btn primary" type="button" data-act="new-session" data-key="new-session">${svg(GLYPH.plus, "glyph")}New session</button>
    </div>`;
  }
  return `<div class="state">
    ${svg(GLYPH.folder, "state-glyph")}
    <p class="state-title">Choose a client</p>
    <p class="state-text">Pick a client in the bar above to see its sessions.</p>
  </div>`;
}

// --- toolbar -----------------------------------------------------------------

function renderTabs(loading) {
  els.tabs.innerHTML = TABS.map((tab) => {
    const on = tab.key === view.tab;
    const count = loading ? "–" : tabCount(tab.key);
    return `<button class="tab" type="button" role="tab" aria-selected="${on}" tabindex="${on ? 0 : -1}" data-tab="${tab.key}" data-key="tab-${tab.key}">${tab.label}<span class="segment-count">${count}</span></button>`;
  }).join("");
}

function countLabel(loading, visible) {
  if (loading) return "Reading…";
  const inThisTab = allRows().filter((row) => inTab(row, view.tab)).length;
  return view.query ? `${visible.length} of ${sessions(inThisTab)}` : sessions(inThisTab);
}

// --- header row and selection bar --------------------------------------------

function renderBar(loading, visible) {
  const n = checkedNames(visible).length;
  els.head.hidden = n > 0;
  els.selbar.hidden = n === 0;
  if (n === 0) {
    closePopover();
    els.headCheck.checked = false;
    els.headCheck.disabled = loading || visible.length === 0;
    return;
  }
  els.selCheck.checked = n === visible.length;
  els.selCheck.indeterminate = n < visible.length;
  els.selCount.textContent = `${n} selected`;
  els.selOpen.hidden = n !== 1;
  els.selExport.hidden = n < 2;
}

// --- the list ----------------------------------------------------------------

function num(value, alert) {
  if (!value) return `<span class="cell-num none">—</span>`;
  return `<span class="cell-num${alert ? " alert" : ""}">${esc(value)}</span>`;
}

function rowHtml(row) {
  const on = view.checked.has(row.name);
  const name = esc(row.name);
  const pack = row.pack
    ? `<span class="pack-text">${esc(row.pack)}</span><span class="pack-track"><span class="pack-fill ${esc(row.pack_tone)}" style="width:${Number(row.pack_pct) || 0}%"></span></span>`
    : `<span class="pack-text none">—</span>`;
  const comment = row.comment
    ? `<span class="cell-comment" title="${esc(row.comment)}">${esc(row.comment)}</span>`
    : `<span class="cell-comment none">—</span>`;
  return `<div class="row grid${on ? " checked" : ""}" data-row="${name}">
    <span class="cell-check"><input type="checkbox" data-key="row-${name}" aria-label="Select ${name}"${on ? " checked" : ""}></span>
    <span class="cell-name">${name}</span>
    <span class="cell-age${row.age_warn ? " warn" : ""}" title="${esc(row.age_title)}">${esc(row.age)}</span>
    <span>${badge(row.tone, row.dot, row.label)}</span>
    ${num(row.orders)}${num(row.items)}${num(row.blocked, row.blocked_alert)}
    <span class="cell-pack" title="${esc(row.pack_title)}">${pack}</span>
    ${comment}
  </div>`;
}

function groupHtml(label, rows, note, attention) {
  return `<div class="group-head" data-group="${attention ? "attention" : "rest"}">
    ${attention ? `<span class="group-dot"></span>` : ""}
    <span class="group-label">${label}</span>
    <span class="group-count">${rows.length}</span>
    <span class="group-note">${note}</span>
  </div>${rows.map(rowHtml).join("")}`;
}

function attentionNote(rows) {
  return REASONS.map(([why, words]) => {
    const n = rows.filter((row) => row.why === why).length;
    return n ? `${n} ${words}` : "";
  })
    .filter(Boolean)
    .join(" · ");
}

function skeleton() {
  const bar = (width) => `<span><span class="sk" style="width:${width}px"></span></span>`;
  let rows = "";
  for (let i = 0; i < SKELETON_ROWS; i += 1) {
    const mid = 64 + (i % 3) * 8;
    rows += `<div class="sk-row grid"><span></span>${bar(96)}${bar(28)}${bar(mid)}${bar(28)}${bar(28)}${bar(28)}${bar(mid)}${bar(60 + ((i * 37) % 120))}</div>`;
  }
  return `<div class="loading-line">${svg(GLYPH.loader, "glyph")}<span>Reading sessions from the server…</span></div>${rows}`;
}

// A panel names its cause and offers the act that resolves it.
function noRows() {
  if (view.query) {
    return `<div class="state">
      ${svg(GLYPH.searchX, "state-glyph")}
      <p class="state-title">No sessions match</p>
      <p class="state-text">Nothing in ${tabLabel()} has “${esc(els.search.value.trim())}” in its name or comment.</p>
      <button class="btn secondary" type="button" data-act="clear-search" data-key="clear-search">Clear search</button>
    </div>`;
  }
  if (view.tab === "all") {
    return `<div class="state">
      ${svg(GLYPH.folder, "state-glyph")}
      <p class="state-title">Nothing in All</p>
      <p class="state-text">Every session of this client is archived.</p>
      <button class="btn secondary" type="button" data-act="toggle-archived" data-key="show-archived">Show archived</button>
    </div>`;
  }
  return `<div class="state">
    ${svg(GLYPH.folder, "state-glyph")}
    <p class="state-title">Nothing in ${tabLabel()}</p>
    <p class="state-text">No session of this client is ${tabLabel().toLowerCase()}.</p>
  </div>`;
}

function renderList(loading, visible) {
  if (loading) {
    els.list.innerHTML = skeleton();
    return;
  }
  if (!visible.length) {
    els.list.innerHTML = noRows();
    return;
  }
  const attention = visible.filter((row) => row.why);
  const rest = visible.filter((row) => !row.why);
  let html = "";
  if (attention.length) html += groupHtml("Needs attention", attention, attentionNote(attention), true);
  if (rest.length) html += groupHtml(attention.length ? "Everything else" : tabLabel(), rest, "", false);
  els.list.innerHTML = html;
}

function renderFooter(loading) {
  const archived = allRows().filter((row) => row.tab === "archived").length;
  const line =
    view.tab === "all" && archived > 0 && !loading
      ? `<span id="archived-count">${archived} archived${view.showArchived ? " shown" : ""}</span><span>·</span><button class="btn link" type="button" data-act="toggle-archived" data-key="toggle-archived">${view.showArchived ? "Hide" : "Show"}</button>`
      : "";
  els.footer.innerHTML = `${line}<span class="spacer"></span><span>Double-click a session to open it</span>`;
}

// --- render ------------------------------------------------------------------

function render() {
  const s = page.state || {};
  const active = document.activeElement;
  const key = active && active.dataset ? active.dataset.key : "";
  const isCard = s.view === "list" || s.view === "loading";

  els.browse.dataset.view = s.view || "";
  els.panel.hidden = isCard || !s.view;
  els.card.hidden = !isCard;
  if (isCard) {
    const loading = s.view === "loading";
    const visible = loading ? [] : visibleRows();
    renderTabs(loading);
    els.count.textContent = countLabel(loading, visible);
    els.refresh.disabled = loading;
    renderBar(loading, visible);
    renderList(loading, visible);
    renderFooter(loading);
  } else {
    closePopover();
    els.panel.innerHTML = s.view ? panel(s) : "";
  }

  // Redrawing replaces the element that had focus; hand focus to its twin.
  if (key && !document.contains(active)) {
    const again = document.querySelector(`[data-key="${CSS.escape(key)}"]`);
    if (again && !again.disabled) again.focus();
  }
  page.renders += 1;
  document.documentElement.dataset.renders = String(page.renders);
}

// A new state from Python. Session names repeat between clients (they are
// dates), so another client's rows never inherit this one's view state.
function onState() {
  const s = page.state || {};
  if ((s.client || "") !== page.client) {
    page.client = s.client || "";
    view.tab = "all";
    view.query = "";
    view.showArchived = false;
    els.search.value = "";
    uncheckAll();
  } else if (s.view === "loading") {
    uncheckAll();
  }
  render();
}

function uncheckAll() {
  view.checked.clear();
  closePopover();
}

// --- menu and popover --------------------------------------------------------

function syncPopover() {
  els.statusMenu.hidden = view.open !== "status";
  els.commentPop.hidden = view.open !== "comment";
  els.statusButton.setAttribute("aria-expanded", String(view.open === "status"));
  els.commentButton.setAttribute("aria-expanded", String(view.open === "comment"));
}

function closePopover() {
  if (view.open === null) return;
  view.open = null;
  syncPopover();
}

function namesList(names) {
  if (names.length <= 3) return names.join(", ");
  return `${names.slice(0, 2).join(", ")} and ${names.length - 2} more`;
}

function openPopover(which) {
  const names = checkedNames(visibleRows());
  if (!names.length) return;
  const what = names.length === 1 ? names[0] : `${names.length} sessions`;
  view.open = which;
  if (which === "status") {
    els.statusTitle.textContent = `Set status for ${what}`;
  } else {
    const row = allRows().find((r) => r.name === names[0]);
    els.commentTitle.textContent = `Comment on ${what}`;
    els.commentText.value = names.length === 1 && row ? row.comment : "";
    els.commentNote.textContent =
      names.length === 1 ? "Shown in the Comment column." : `Replaces the comment on ${namesList(names)}.`;
  }
  syncPopover();
  if (which === "status") els.statusMenu.querySelector(".status-item").focus();
  else els.commentText.focus();
}

function togglePopover(which) {
  if (view.open === which) closePopover();
  else openPopover(which);
}

function saveComment() {
  const names = checkedNames(visibleRows());
  const text = els.commentText.value.trim();
  closePopover();
  if (names.length && page.bridge) page.bridge.setComment(names, text);
}

// --- input -------------------------------------------------------------------

function chooseTab(key) {
  view.tab = key;
  uncheckAll();
  render();
}

function onTabsKey(event) {
  if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
  const index = TABS.findIndex((tab) => tab.key === view.tab);
  const next = TABS[(index + (event.key === "ArrowLeft" ? -1 : 1) + TABS.length) % TABS.length];
  event.preventDefault();
  chooseTab(next.key);
  els.tabs.querySelector(`[data-tab="${next.key}"]`).focus();
}

function onAct(event) {
  const el = event.target.closest("[data-act]");
  if (!el || el.disabled) return;
  switch (el.dataset.act) {
    case "refresh":
      if (page.bridge) page.bridge.refresh();
      break;
    case "new-session":
      if (page.bridge) page.bridge.newSession();
      break;
    case "clear-search":
      els.search.value = "";
      view.query = "";
      render();
      els.search.focus();
      break;
    case "toggle-archived":
      view.showArchived = !view.showArchived;
      uncheckAll();
      render();
      break;
  }
}

function onListClick(event) {
  const row = event.target.closest(".row");
  if (!row) return;
  const name = row.dataset.row;
  if (view.checked.has(name)) view.checked.delete(name);
  else view.checked.add(name);
  render();
}

function onListDoubleClick(event) {
  const row = event.target.closest(".row");
  if (row && page.bridge) page.bridge.openSession(row.dataset.row);
}

// Up and Down walk the rows' checkboxes; Enter opens. Space is the checkbox's own.
function onListKey(event) {
  const row = event.target.closest(".row");
  if (!row) return;
  if (event.key === "Enter") {
    event.preventDefault();
    if (page.bridge) page.bridge.openSession(row.dataset.row);
    return;
  }
  if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
  const boxes = Array.from(els.list.querySelectorAll(".row input"));
  const next = boxes[boxes.indexOf(event.target) + (event.key === "ArrowUp" ? -1 : 1)];
  event.preventDefault();
  if (next) next.focus();
}

function onHeadCheck() {
  const visible = visibleRows();
  const every = visible.length > 0 && visible.every((row) => view.checked.has(row.name));
  if (every) view.checked.clear();
  else visible.forEach((row) => view.checked.add(row.name));
  render();
}

function onStatusChoice(event) {
  const item = event.target.closest("[data-status]");
  if (!item) return;
  const names = checkedNames(visibleRows());
  closePopover();
  if (names.length && page.bridge) page.bridge.setStatus(names, item.dataset.status);
}

// --- toast (ADR 0007: a web page draws its own) --------------------------------

function raiseToast(text, undoable) {
  els.toastText.textContent = text;
  els.toastUndo.hidden = !undoable;
  els.toast.hidden = false;
  if (page.toastTimer !== null) clearTimeout(page.toastTimer);
  page.toastTimer = setTimeout(dismissToast, TOAST_MS);
}

function dismissToast() {
  if (page.toastTimer !== null) clearTimeout(page.toastTimer);
  page.toastTimer = null;
  els.toast.hidden = true;
}

// --- boot --------------------------------------------------------------------

function bind() {
  const ids = {
    browse: "browse", panel: "panel", card: "card", tabs: "tabs", searchBox: "search-box",
    search: "search", count: "count", refresh: "refresh", head: "head", headCheck: "head-check",
    selbar: "selbar", selCheck: "sel-check", selCount: "sel-count", selOpen: "sel-open",
    selExport: "sel-export", statusButton: "status-button", statusMenu: "status-menu",
    commentButton: "comment-button", commentPop: "comment-pop", commentTitle: "comment-title",
    commentText: "comment-text", commentNote: "comment-note", commentCancel: "comment-cancel",
    commentSave: "comment-save", list: "list", footer: "footer", themeVars: "theme-vars",
    toast: "toast", toastText: "toast-text", toastUndo: "toast-undo", toastDismiss: "toast-dismiss",
  };
  for (const name of Object.keys(ids)) els[name] = document.getElementById(ids[name]);

  // The fixed parts of the page: glyphs, and the Status menu's four choices.
  els.searchBox.insertAdjacentHTML("afterbegin", svg(GLYPH.search, "glyph"));
  els.refresh.innerHTML = `${svg(GLYPH.refresh, "glyph")}Refresh`;
  els.statusButton.innerHTML = `Status${svg(GLYPH.chevron, "glyph")}`;
  els.toastDismiss.innerHTML = svg(GLYPH.x, "glyph");
  els.statusMenu.innerHTML =
    `<div id="status-title" class="menu-group"></div>` +
    STATUS_ITEMS.map(
      (item) =>
        `<button class="status-item" type="button" role="menuitem" data-status="${item.status}">${badge(item.tone, item.dot, item.label)}<span class="status-note">${item.note}</span></button>`,
    ).join("");
  els.statusTitle = document.getElementById("status-title");

  els.tabs.addEventListener("click", (event) => {
    const tab = event.target.closest("[data-tab]");
    if (tab) chooseTab(tab.dataset.tab);
  });
  els.tabs.addEventListener("keydown", onTabsKey);
  els.search.addEventListener("input", () => {
    view.query = els.search.value.trim().toLowerCase();
    uncheckAll();
    render();
  });
  els.refresh.addEventListener("click", () => page.bridge && page.bridge.refresh());
  els.browse.addEventListener("click", onAct);
  els.headCheck.addEventListener("click", onHeadCheck);
  els.selCheck.addEventListener("click", () => {
    uncheckAll();
    render();
  });
  els.selOpen.addEventListener("click", () => {
    const names = checkedNames(visibleRows());
    if (names.length === 1 && page.bridge) page.bridge.openSession(names[0]);
  });
  els.selExport.addEventListener("click", () => {
    const names = checkedNames(visibleRows());
    if (names.length >= 2 && page.bridge) page.bridge.exportCombined(names);
  });
  els.statusButton.addEventListener("click", () => togglePopover("status"));
  els.commentButton.addEventListener("click", () => togglePopover("comment"));
  els.statusMenu.addEventListener("click", onStatusChoice);
  els.commentCancel.addEventListener("click", closePopover);
  els.commentSave.addEventListener("click", saveComment);
  els.commentText.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && event.ctrlKey) {
      event.preventDefault();
      saveComment();
    }
  });
  els.list.addEventListener("click", onListClick);
  els.list.addEventListener("dblclick", onListDoubleClick);
  els.list.addEventListener("keydown", onListKey);
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || view.open === null) return;
    const button = view.open === "status" ? els.statusButton : els.commentButton;
    closePopover();
    button.focus();
  });
  document.addEventListener("mousedown", (event) => {
    if (view.open !== null && !event.target.closest(".menu-anchor")) closePopover();
  });
  els.toastUndo.addEventListener("click", () => {
    dismissToast();
    if (page.bridge) page.bridge.undo();
  });
  els.toastDismiss.addEventListener("click", dismissToast);
}

bind();

new QWebChannel(qt.webChannelTransport, function (channel) {
  const bridge = channel.objects.browse;
  page.bridge = bridge;
  els.themeVars.textContent = bridge.themeCss;
  bridge.themeCssChanged.connect(() => { els.themeVars.textContent = bridge.themeCss; });
  bridge.stateChanged.connect(() => { page.state = bridge.state; onState(); });
  bridge.toastRaised.connect((text, undoable) => raiseToast(text, undoable));
  page.state = bridge.state;
  onState();
  window.browseBridge = bridge;
  document.documentElement.dataset.bridge = "ready";
});
```

Notes on why it is shaped this way, for whoever changes it:

- The toolbar, the selection bar, the Status menu and the Comment popover are fixed elements in
  `browse.html`. Only `#tabs`, `#list`, `#footer` and `#panel` are redrawn. That is why the search box keeps
  its caret and an open popover keeps its draft when Python pushes a new state.
- `checkedNames(visible)` is the only way the checked set is read. A row the tab or the search hides stays in
  `view.checked` until something clears it, and is never acted on.
- `_show` in the tests waits for the render counter, so pushing a state equal to the previous one never
  returns. Each test pushes a state that differs from the last.
- A row's click and its checkbox's click are one handler: the redraw sets `checked` from `view.checked`, so
  the checkbox's own toggle does not matter. A double-click fires two clicks first, which cancel out.

- [ ] **Step 6: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_browse_page.py tests/test_style_literals_guard.py`
Expected: 54 passed in `test_browse_page.py`, and the lint guard passes with the three new assets.

- [ ] **Step 7: Commit**

`/usr/bin/git add gui/web/browse.html gui/web/browse.css gui/web/browse.js tests/test_browse_page.py`, then
commit with:

```
The Browse page: tabs, search, two groups, a selection bar, Undo

Drawn to browse.html on the web kit. Python sends one row per session; the
page filters, counts and groups them and owns only the view state. Status
and Comment act on every checked row and name sessions by name.
```

---

### Task 6: The widget hosts the page (`gui/session_browser_widget.py`), and the Qt tree goes

**Files:**
- Rewrite: `gui/session_browser_widget.py`
- Create: `tests/test_session_browser_widget.py`
- Rewrite: `tests/test_session_browser_reload.py`, `tests/test_status_channels.py`
- Modify: `gui/components/__init__.py`, `shopify_tool/session_lifecycle.py`, `tests/test_session_lifecycle.py`,
  `tests/test_status_edge_delegate.py`, `tests/audit/test_05_sessions_sweep.py`
- Delete: `gui/session_row_delegates.py`, `gui/components/selectionbar.py`, `tests/test_session_browser_1e.py`,
  `tests/test_session_browser_columns.py`, `tests/test_components_selectionbar.py`

**Interfaces:**
- Consumes: `mount_browse_page`, `BrowseBridge` (Task 4); `browse_state` (Task 3);
  `SessionManager.restore_session_fields` (Task 2); `update_session_status(path, status, manual=True)` and
  `update_session_info(path, {"comments": text})` (they exist); `gui.components.show_error`.
- Produces (unchanged for the rest of the app): `SessionBrowserWidget(session_manager, parent=None)` with
  signals `session_selected(str)`, `multi_export_requested(list)`, `new_session_requested()`, the class flag
  `USE_ASYNC`, and `set_client(client_id, auto_refresh=True)`, `refresh_sessions(quiet=False)`, `mark_dirty()`.
  New attributes: `view: QWebEngineView`, `bridge: BrowseBridge`. `SessionLoaderWorker` is unchanged.
- What replaces each deleted test file:

| Deleted | Pinned now by |
|---|---|
| `test_session_browser_columns.py` (columns, groups, packing, archived, empty states, order) | `test_browse_state.py`, `test_browse_page.py` |
| `test_session_browser_1e.py` (delegates, selection bar, search, count) | `test_browse_page.py`, `test_session_browser_widget.py` |
| `test_components_selectionbar.py` | Nothing: the component is deleted. The page's bar is in `test_browse_page.py` |
| `TestAgeLabel` | `TestAgeCell` (Task 1) |
| `test_status_channels.py`'s `STATE_STYLES` cases | `test_browse_state.py::test_each_status_has_its_label_tone_dot_and_tab` |

Column sorting is dropped (owner, spec §2), so its three tests have no replacement.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_session_browser_widget.py`:

```python
"""The Browse screen's widget: loading, the writes and Undo (phase 4 spec section 6).

The page itself is tested in test_browse_page.py; these drive the widget
through its bridge and read back the state it pushes.
"""

import json
import shutil
from pathlib import Path
from unittest.mock import Mock, call

import pytest
from PySide6.QtWebEngineWidgets import QWebEngineView

import gui.session_browser_widget as browser_module
from gui.session_browser_widget import _UNDO_KEYS, SessionBrowserWidget
from shopify_tool.session_manager import SessionManager

NAMES = ["2026-09-30_2", "2026-09-30_1", "2026-09-29_1"]


def _path(name):
    return f"/srv/Sessions/CLIENT_ACME/{name}"


def _entry(name, **fields):
    return {
        "session_name": name,
        "session_path": _path(name),
        "status": "active",
        "created_at": "2026-09-30T08:00:00+00:00",
        "comments": "",
        **fields,
    }


@pytest.fixture
def told(monkeypatch):
    """What the error banner was asked to say: (headline, what to do)."""
    seen = []
    monkeypatch.setattr(browser_module, "show_error", lambda _source, *text: seen.append(text))
    return seen


@pytest.fixture
def browser(qtbot, monkeypatch, told):
    """A shown widget over a mocked SessionManager holding three sessions."""
    monkeypatch.setattr(SessionBrowserWidget, "USE_ASYNC", False)
    manager = Mock()
    manager.list_client_sessions.return_value = [_entry(name) for name in NAMES]
    widget = SessionBrowserWidget(manager)
    qtbot.addWidget(widget)
    widget.show()
    widget.set_client("ACME")
    return widget


def _toasts(widget):
    seen = []
    widget.bridge.toastRaised.connect(lambda text, undoable: seen.append((text, undoable)))
    return seen


def _views(widget):
    seen = []
    widget.bridge.stateChanged.connect(lambda: seen.append(widget.bridge.state["view"]))
    return seen


def _rows(widget):
    return [row["name"] for row in widget.bridge.state["rows"]]


# --- loading -----------------------------------------------------------------


def test_it_hosts_one_web_view_edge_to_edge(browser):
    assert isinstance(browser.view, QWebEngineView)
    margins = browser.layout().contentsMargins()
    assert (margins.left(), margins.top(), margins.right(), margins.bottom()) == (0, 0, 0, 0)
    assert browser.layout().count() == 1


def test_before_a_client_is_chosen_the_page_asks_for_one(qtbot):
    widget = SessionBrowserWidget(Mock())
    qtbot.addWidget(widget)
    assert widget.bridge.state == {"view": "no_client", "client": "", "rows": []}


def test_choosing_a_client_loads_every_status(browser):
    assert browser.bridge.state["view"] == "list"
    assert browser.bridge.state["client"] == "ACME"
    assert _rows(browser) == NAMES
    browser.session_manager.list_client_sessions.assert_called_once_with("ACME")


def test_a_loud_refresh_shows_the_skeleton_first(browser):
    views = _views(browser)
    browser.refresh_sessions()
    assert views == ["loading", "list"]


def test_a_quiet_refresh_keeps_the_rows_on_screen(browser):
    browser.session_manager.list_client_sessions.return_value = [_entry(NAMES[0])]
    views = _views(browser)
    browser.refresh_sessions(quiet=True)
    assert views == ["list"]
    assert _rows(browser) == NAMES[:1]


def test_a_failed_load_shows_the_failed_panel_and_no_banner(browser, told):
    browser.session_manager.list_client_sessions.side_effect = OSError("share went away")
    browser.refresh_sessions()
    assert browser.bridge.state == {"view": "failed", "client": "ACME", "rows": []}
    assert told == []

    browser.session_manager.list_client_sessions.side_effect = None
    browser.bridge.refresh()  # the panel's Try again
    assert browser.bridge.state["view"] == "list"


def test_a_worker_error_shows_the_failed_panel(browser):
    browser._on_load_error("timed out")
    assert browser.bridge.state["view"] == "failed"
    assert browser.sessions_data == []


def test_another_client_never_shows_the_previous_clients_rows(browser):
    browser.hide()
    browser.set_client("BETA", auto_refresh=False)
    assert browser.bridge.state == {"view": "loading", "client": "BETA", "rows": []}
    assert browser._is_dirty is True


def test_no_client_empties_the_page(browser):
    browser.set_client("")
    assert browser.bridge.state == {"view": "no_client", "client": "", "rows": []}


def test_a_load_that_arrives_while_shown_is_drawn(browser):
    browser._on_sessions_loaded([_entry("2026-10-01_1")])
    assert _rows(browser) == ["2026-10-01_1"]


def test_a_new_load_cleans_up_the_one_in_flight(browser, monkeypatch):
    started = []

    class FakeWorker:
        def __init__(self, _manager, client_id):
            self.client_id = client_id
            self.finished_with_data = Mock()
            self.error_occurred = Mock()
            self.cleanup = Mock()

        def start(self):
            started.append(self.client_id)

    monkeypatch.setattr(SessionBrowserWidget, "USE_ASYNC", True)
    monkeypatch.setattr(browser_module, "SessionLoaderWorker", FakeWorker)

    browser.refresh_sessions()
    first = browser.worker
    browser.refresh_sessions()

    first.cleanup.assert_called_once()
    assert browser.worker is not first
    assert started == ["ACME", "ACME"]
    browser.worker = None  # nothing real for closeEvent to clean up


# --- what the page asks for --------------------------------------------------


def test_a_status_reaches_every_named_session_as_set_by_hand(browser):
    toasts = _toasts(browser)
    loads = browser.session_manager.list_client_sessions.call_count

    browser.bridge.setStatus([NAMES[1], NAMES[2], "ghost"], "archived")

    assert browser.session_manager.update_session_status.call_args_list == [
        call(_path(NAMES[1]), "archived", manual=True),
        call(_path(NAMES[2]), "archived", manual=True),
    ]
    assert toasts == [("Set 2 sessions to Archived", True)]
    assert browser.session_manager.list_client_sessions.call_count == loads + 1


def test_one_session_is_named_in_the_toast(browser):
    toasts = _toasts(browser)
    browser.bridge.setStatus([NAMES[1]], "completed")
    assert toasts == [("Set 2026-09-30_1 to Completed", True)]


def test_names_this_widget_did_not_load_are_ignored(browser, told):
    toasts = _toasts(browser)
    loads = browser.session_manager.list_client_sessions.call_count
    browser.bridge.setStatus(["ghost", "../../etc"], "archived")
    browser.bridge.setComment(["ghost"], "x")
    browser.session_manager.update_session_status.assert_not_called()
    browser.session_manager.update_session_info.assert_not_called()
    assert toasts == [] and told == []
    assert browser.session_manager.list_client_sessions.call_count == loads


def test_a_comment_is_saved_on_every_named_session(browser):
    toasts = _toasts(browser)
    browser.bridge.setComment([NAMES[0], NAMES[1]], "late van")
    assert browser.session_manager.update_session_info.call_args_list == [
        call(_path(NAMES[0]), {"comments": "late van"}),
        call(_path(NAMES[1]), {"comments": "late van"}),
    ]
    assert toasts == [("Comment saved on 2 sessions", True)]


def test_an_empty_comment_clears(browser):
    toasts = _toasts(browser)
    browser.bridge.setComment([NAMES[0]], "")
    browser.session_manager.update_session_info.assert_called_once_with(
        _path(NAMES[0]), {"comments": ""}
    )
    assert toasts == [("Comment cleared on 2026-09-30_2", True)]


def test_one_failure_in_three_is_reported_and_the_rest_are_done(browser, told):
    def fail_one(path, status, manual=False):
        if path == _path(NAMES[1]):
            raise OSError("share went away")

    browser.session_manager.update_session_status.side_effect = fail_one
    toasts = _toasts(browser)

    browser.bridge.setStatus(NAMES, "archived")

    assert told == [("1 of 3 sessions weren't updated", "Details are in Logs.")]
    assert toasts == [("Set 2 sessions to Archived", True)]
    assert list(browser._undo) == [_path(NAMES[0]), _path(NAMES[2])]


def test_a_single_failed_status_says_what_failed_and_raises_no_toast(browser, told):
    browser.session_manager.update_session_status.side_effect = OSError("share went away")
    toasts = _toasts(browser)
    browser.bridge.setStatus([NAMES[0]], "archived")
    assert told == [("The status wasn't updated", "Details are in Logs.")]
    assert toasts == []
    assert browser._undo == {}


def test_a_single_failed_comment_says_what_failed(browser, told):
    browser.session_manager.update_session_info.side_effect = OSError("share went away")
    browser.bridge.setComment([NAMES[0]], "x")
    assert told == [("The comment wasn't saved", "Details are in Logs.")]


def test_open_emits_the_sessions_path(browser):
    opened = []
    browser.session_selected.connect(opened.append)
    browser.bridge.openSession(NAMES[1])
    browser.bridge.openSession("ghost")
    assert opened == [_path(NAMES[1])]


def test_export_emits_the_paths_in_list_order_and_needs_two(browser):
    exported = []
    browser.multi_export_requested.connect(exported.append)
    browser.bridge.exportCombined([NAMES[2], NAMES[0]])
    browser.bridge.exportCombined([NAMES[0], "ghost"])
    assert exported == [[_path(NAMES[0]), _path(NAMES[2])]]


def test_the_empty_panels_button_asks_for_a_new_session(browser, qtbot):
    with qtbot.waitSignal(browser.new_session_requested, timeout=1000):
        browser.bridge.newSession()


# --- Undo --------------------------------------------------------------------


def test_undo_hands_back_what_each_session_held(browser):
    browser.session_manager.list_client_sessions.return_value = [
        _entry(NAMES[0], comments="first", last_updated="2026-09-30T09:00:00+00:00"),
        _entry(NAMES[1], status="completed", status_manually_set=True),
    ]
    browser.refresh_sessions()

    browser.bridge.setStatus(NAMES[:2], "archived")
    browser.bridge.undo()

    assert browser.session_manager.restore_session_fields.call_args_list == [
        call(
            _path(NAMES[0]),
            {
                "status": "active",
                "status_manually_set": None,
                "status_updated_at": None,
                "comments": "first",
                "last_updated": "2026-09-30T09:00:00+00:00",
            },
        ),
        call(
            _path(NAMES[1]),
            {
                "status": "completed",
                "status_manually_set": True,
                "status_updated_at": None,
                "comments": "",
                "last_updated": None,
            },
        ),
    ]
    assert set(_UNDO_KEYS) == set(
        browser.session_manager.restore_session_fields.call_args_list[0].args[1]
    )


def test_undo_is_spent_once_and_does_nothing_with_nothing_to_undo(browser):
    browser.bridge.undo()
    browser.session_manager.restore_session_fields.assert_not_called()

    browser.bridge.setStatus([NAMES[0]], "archived")
    browser.bridge.undo()
    browser.bridge.undo()
    assert browser.session_manager.restore_session_fields.call_count == 1


def test_the_next_change_replaces_what_undo_remembers(browser):
    browser.bridge.setStatus([NAMES[0]], "archived")
    browser.bridge.setComment([NAMES[1]], "late van")
    browser.bridge.undo()
    assert [c.args[0] for c in browser.session_manager.restore_session_fields.call_args_list] == [
        _path(NAMES[1])
    ]


def test_another_client_forgets_the_undo(browser):
    browser.bridge.setStatus([NAMES[0]], "archived")
    browser.set_client("BETA")
    browser.bridge.undo()
    browser.session_manager.restore_session_fields.assert_not_called()


def test_an_undo_that_fails_is_reported(browser, told):
    browser.bridge.setStatus(NAMES[:2], "archived")
    browser.session_manager.restore_session_fields.side_effect = [None, OSError("share went away")]
    browser.bridge.undo()
    assert told == [("1 of 2 sessions weren't restored", "Details are in Logs.")]

    browser.bridge.setStatus([NAMES[0]], "archived")
    browser.session_manager.restore_session_fields.side_effect = OSError("share went away")
    browser.bridge.undo()
    assert told[-1] == ("The change wasn't undone", "Details are in Logs.")


# --- Undo against the real files ---------------------------------------------


@pytest.fixture
def real(qtbot, monkeypatch, profile_manager, told):
    """A shown widget over a real SessionManager with two sessions on disk."""
    monkeypatch.setattr(SessionBrowserWidget, "USE_ASYNC", False)
    profile_manager.create_client_profile("M", "Test Client")
    manager = SessionManager(profile_manager)
    paths = [manager.create_session("M") for _ in range(2)]
    manager.update_session_info(paths[0], {"comments": "first"})
    widget = SessionBrowserWidget(manager)
    qtbot.addWidget(widget)
    widget.show()
    widget.set_client("M")
    return widget, paths


def _stored(path):
    return json.loads((Path(path) / "session_info.json").read_text())


def test_undo_puts_an_archive_back_exactly(real):
    widget, paths = real
    names = [Path(p).name for p in paths]
    before = [_stored(p) for p in paths]

    widget.bridge.setStatus(names, "archived")
    assert [_stored(p)["status"] for p in paths] == ["archived", "archived"]
    assert [_stored(p)["status_manually_set"] for p in paths] == [True, True]
    assert {row["tab"] for row in widget.bridge.state["rows"]} == {"archived"}

    widget.bridge.undo()

    assert [_stored(p) for p in paths] == before
    assert {row["tab"] for row in widget.bridge.state["rows"]} == {"active"}


def test_undo_puts_a_comment_back_with_its_timestamp(real):
    widget, paths = real
    name = Path(paths[0]).name
    before = _stored(paths[0])

    widget.bridge.setComment([name], "call courier")
    assert _stored(paths[0])["comments"] == "call courier"

    widget.bridge.undo()

    assert _stored(paths[0]) == before
    row = next(r for r in widget.bridge.state["rows"] if r["name"] == name)
    assert row["comment"] == "first"


def test_undo_leaves_what_someone_else_wrote_in_between(real):
    widget, paths = real
    name = Path(paths[0]).name
    widget.bridge.setStatus([name], "archived")

    # Packing Tool records progress while the toast is still up.
    info = _stored(paths[0])
    info["packing_progress"] = {"list0": {"status": "completed"}}
    (Path(paths[0]) / "session_info.json").write_text(json.dumps(info))

    widget.bridge.undo()

    after = _stored(paths[0])
    assert after["status"] == "active"
    assert "status_manually_set" not in after
    assert after["packing_progress"] == {"list0": {"status": "completed"}}


def test_a_session_that_left_the_share_is_reported_and_the_rest_are_written(real, told):
    widget, paths = real
    names = [Path(p).name for p in paths]
    toasts = _toasts(widget)
    shutil.rmtree(paths[0])

    widget.bridge.setStatus(names, "completed")

    assert told == [("1 of 2 sessions weren't updated", "Details are in Logs.")]
    assert _stored(paths[1])["status"] == "completed"
    assert toasts == [(f"Set {names[1]} to Completed", True)]
    assert [row["name"] for row in widget.bridge.state["rows"]] == [names[1]]
```

Replace the whole of `tests/test_session_browser_reload.py` with:

```python
"""Regression tests for the Session Browser getting permanently stuck on its
loading state -- gui.session_browser_widget.SessionBrowserWidget.

Root cause: refresh_sessions() clears _is_dirty synchronously the moment the
background load *starts*, not when it finishes. If the widget becomes hidden
before the async worker's result arrives (e.g. the user switches to another
tab while the file-server load is in flight), _on_sessions_loaded's
isVisible() guard discarded the result -- but left _is_dirty False. Since
showEvent() only reloads when _is_dirty is True, the widget never recovered:
switching back showed the skeleton forever.
"""
from unittest.mock import Mock

import pytest
from PySide6.QtGui import QShowEvent

from gui.session_browser_widget import SessionBrowserWidget


@pytest.fixture
def widget(qtbot):
    w = SessionBrowserWidget(Mock(), parent=None)
    qtbot.addWidget(w)
    w.current_client_id = "CLIENT_1"
    w._is_dirty = False  # mimics state right after refresh_sessions() started a load
    return w


def test_dropped_result_while_hidden_marks_dirty_for_retry(widget, monkeypatch):
    monkeypatch.setattr(widget, "isVisible", lambda: False)

    widget._on_sessions_loaded([{"session_name": "s1", "created_at": ""}])

    assert widget._is_dirty is True
    assert widget.sessions_data == []
    assert widget.bridge.state["rows"] == []


def test_becoming_visible_again_retries_the_load(widget, monkeypatch):
    monkeypatch.setattr(widget, "isVisible", lambda: False)
    widget._on_sessions_loaded([{"session_name": "s1", "created_at": ""}])

    refreshed = Mock()
    monkeypatch.setattr(widget, "refresh_sessions", refreshed)
    monkeypatch.setattr(widget, "isVisible", lambda: True)
    widget.showEvent(QShowEvent())

    refreshed.assert_called_once()


def test_client_switch_refreshes_immediately_when_tab_already_visible(widget, monkeypatch):
    """set_client(..., auto_refresh=False) is called on every client switch
    (gui/main_window_pyside.py) on the assumption that the next showEvent()
    will pick up the resulting dirty flag. But if the Session Browser tab is
    already the active/visible tab -- e.g. the user switches clients from the
    command bar while already browsing sessions -- no showEvent() fires, since
    visibility never changes. Without this, the page would stay on the
    skeleton until some unrelated action (Refresh, or a tab switch away and
    back) happened to trigger a reload.
    """
    monkeypatch.setattr(widget, "isVisible", lambda: True)
    refreshed = Mock()
    monkeypatch.setattr(widget, "refresh_sessions", refreshed)

    widget.set_client("CLIENT_2", auto_refresh=False)

    refreshed.assert_called_once()


def test_client_switch_defers_to_showevent_when_tab_hidden(widget, monkeypatch):
    """Unchanged behavior: when the widget isn't visible, auto_refresh=False
    still defers the reload to the next showEvent() instead of doing a
    network round trip for a tab nobody is looking at."""
    monkeypatch.setattr(widget, "isVisible", lambda: False)
    refreshed = Mock()
    monkeypatch.setattr(widget, "refresh_sessions", refreshed)

    widget.set_client("CLIENT_2", auto_refresh=False)

    refreshed.assert_not_called()
    assert widget._is_dirty is True


def test_setting_the_same_client_again_does_nothing(widget, monkeypatch):
    refreshed = Mock()
    monkeypatch.setattr(widget, "refresh_sessions", refreshed)
    widget.set_client("CLIENT_1")
    refreshed.assert_not_called()
    assert widget._is_dirty is False
```

- [ ] **Step 2: Run them and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_session_browser_widget.py tests/test_session_browser_reload.py`
Expected: an `ImportError` for `_UNDO_KEYS` in the first file; the first reload test fails on
`widget.bridge`.

- [ ] **Step 3: Rewrite the widget**

Replace the whole of `gui/session_browser_widget.py` with the file below. `SessionLoaderWorker` in it is the
class the file already has, character for character: check that with `/usr/bin/git diff` after writing.

```python
"""The Browse screen: the sessions of the selected client (phase 4 spec section 6).

A widget that hosts one web view. It loads the session list off the GUI
thread, hands the page one state map (gui/browse_state.py), and carries out
what the page asks for through BrowseBridge: open, set a status, comment,
export combined stock, Undo.
"""

import logging
from datetime import datetime

from PySide6.QtCore import Signal
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QVBoxLayout, QWidget

from gui.background_worker import BackgroundWorker
from gui.browse_bridge import mount_browse_page
from gui.browse_state import browse_state
from gui.components import show_error
from shopify_tool.session_lifecycle import derive_status_updates
from shopify_tool.session_manager import SessionManager

logger = logging.getLogger(__name__)

# What a status or a comment change can alter in session_info.json, and so
# what Undo puts back. A key the session did not have is restored as absent.
_UNDO_KEYS = (
    "status",
    "status_manually_set",
    "status_updated_at",
    "comments",
    "last_updated",
)


def _what(entries: list[dict]) -> str:
    """How a toast names what it changed: the session, or how many."""
    if len(entries) == 1:
        return entries[0]["session_name"]
    return f"{len(entries)} sessions"


class SessionLoaderWorker(BackgroundWorker):
    """Background worker for loading session list from file server.

    This worker performs the potentially slow I/O operation of listing
    and parsing session metadata files from the network file server.
    """

    def __init__(self, session_manager, client_id, status_filter=None):
        """Initialize session loader worker.

        Args:
            session_manager: SessionManager instance
            client_id: Client ID to load sessions for
            status_filter: Optional status filter (e.g., "active", "completed")
        """
        super().__init__()
        self.session_manager = session_manager
        self.client_id = client_id
        self.status_filter = status_filter

    def run(self):
        """Execute in background thread - load sessions from file server."""
        try:
            if self._is_cancelled:
                return

            logger.debug(f"Loading sessions for CLIENT_{self.client_id}")

            # This is the potentially slow I/O operation (200-1000ms on slow UNC)
            sessions = self.session_manager.list_client_sessions(
                self.client_id, status_filter=self.status_filter
            )

            if self._is_cancelled:
                return

            sessions = self._sync_statuses(sessions)

            self.finished_with_data.emit(sessions)
            logger.debug(f"Loaded {len(sessions)} sessions for CLIENT_{self.client_id}")

        except Exception as e:
            if not self._is_cancelled:
                logger.exception("Error loading sessions")
                self.error_occurred.emit(str(e))

    def _sync_statuses(self, sessions):
        """Apply automatic status changes, then reflect them into `sessions`.

        File I/O only -- this runs on a background thread and must never
        touch a widget. Failures are swallowed: a stale status is survivable,
        a session list that will not load is not.
        """
        # ponytail: the first refresh after this shipped clears the whole
        # backlog in one pass -- 41 of 42 sessions on the data this was built
        # against. It is one-time (the derive returns empty forever after) and
        # runs off the UI thread, so no progress UI or first-run prompt is
        # built. If it drags on the production share, bound the pass to the N
        # oldest sessions per refresh.
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
            logger.exception(
                "Automatic session status sync failed; showing stored statuses"
            )
        return sessions


class SessionBrowserWidget(QWidget):
    """The Browse screen's widget: one web view and the code behind it.

    Signals:
        session_selected: the operator opened a session (session_path: str)
        multi_export_requested: combined stock export for these session paths
        new_session_requested: the "No sessions yet" panel's button
    """

    session_selected = Signal(str)
    multi_export_requested = Signal(list)
    new_session_requested = Signal()

    # Class variable for testing - set to False to load in line, with no thread.
    USE_ASYNC = True

    def __init__(self, session_manager: SessionManager, parent=None):
        super().__init__(parent)
        self.session_manager = session_manager
        self.current_client_id = None
        self.sessions_data = []
        self.worker = None  # the load in flight, if any
        self._is_dirty = True  # forces one load on first show
        self._loading = False
        self._failed = False
        self._undo = {}  # session_path -> the fields the last change replaced

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.view = QWebEngineView(self)
        self.bridge = mount_browse_page(self.view)
        layout.addWidget(self.view, 1)

        self.bridge.refreshRequested.connect(lambda: self.refresh_sessions())
        self.bridge.openRequested.connect(self._open)
        self.bridge.newSessionRequested.connect(self.new_session_requested)
        self.bridge.exportRequested.connect(self._export)
        self.bridge.statusRequested.connect(self._set_status)
        self.bridge.commentRequested.connect(self._set_comment)
        self.bridge.undoRequested.connect(self._undo_last)
        self._push()
        logger.info("SessionBrowserWidget initialized")

    def _push(self) -> None:
        """Build the page's state from what this widget holds and send it."""
        self.bridge.set_state(
            browse_state(
                client=self.current_client_id or "",
                loading=self._loading,
                failed=self._failed,
                sessions=self.sessions_data,
                now=datetime.now().astimezone(),
            )
        )

    # --- loading -------------------------------------------------------------

    def set_client(self, client_id: str, auto_refresh: bool = True):
        """Set the client to show sessions for.

        Args:
            client_id: Client ID to load sessions for
            auto_refresh: If False, skip the immediate refresh and let the next
                showEvent() pick up the dirty flag instead -- unless the widget
                is already visible right now, in which case there's no future
                showEvent to rescue it (the tab isn't changing), so it must
                refresh immediately or the page is left on its skeleton.
        """
        if client_id == self.current_client_id:
            return
        self.current_client_id = client_id
        # The previous client's rows never show under the new client's name.
        self.sessions_data = []
        self._undo = {}
        self._failed = False
        self._loading = bool(client_id)
        self._is_dirty = True
        self._push()
        if auto_refresh or self.isVisible():
            self.refresh_sessions()

    def refresh_sessions(self, quiet: bool = False):
        """Reload the sessions from the server.

        A loud refresh shows the skeleton first. A quiet one, after a write,
        leaves the rows on screen until the new ones arrive.
        """
        self._is_dirty = False
        if not self.current_client_id:
            self.sessions_data = []
            self._loading = self._failed = False
            self._push()
            return

        if not quiet:
            self._loading, self._failed = True, False
            self._push()

        if not self.USE_ASYNC:
            # In line, for tests. It does NOT run SessionLoaderWorker's
            # automatic status sync: test that against the worker directly.
            try:
                sessions = self.session_manager.list_client_sessions(
                    self.current_client_id
                )
            except Exception as error:
                logger.exception("Failed to load sessions")
                self._on_load_error(str(error))
                return
            self._show(sessions)
            return

        # Clean up the previous worker FIRST (critical to prevent crashes).
        if self.worker is not None:
            self.worker.cleanup()
            self.worker = None
        # Every status: the tabs filter in the page.
        self.worker = SessionLoaderWorker(self.session_manager, self.current_client_id)
        self.worker.finished_with_data.connect(self._on_sessions_loaded)
        self.worker.error_occurred.connect(self._on_load_error)
        self.worker.start()
        logger.debug("Session loading worker started")

    def _on_sessions_loaded(self, sessions):
        """A background load finished (main thread)."""
        # The widget may have been hidden while the file-server load was in
        # flight (the user switched tabs). refresh_sessions() already cleared
        # _is_dirty when the load started; re-mark it so the next showEvent()
        # loads again instead of leaving the page on its skeleton forever.
        if not self.isVisible():
            logger.debug("Widget not visible when sessions loaded; will retry on next show")
            self._is_dirty = True
            return
        self._show(sessions)

    def _show(self, sessions) -> None:
        logger.debug(f"Showing {len(sessions)} sessions")
        self.sessions_data = sessions
        self._loading = self._failed = False
        self._push()

    def _on_load_error(self, error_msg):
        """A load failed (main thread). The page shows the failed panel."""
        logger.error(f"Session load error: {error_msg}")
        self.sessions_data = []
        self._loading, self._failed = False, True
        self._push()

    def mark_dirty(self):
        """Call this whenever a session is created/updated for the client this
        widget is currently showing, so the next showEvent() actually refreshes
        instead of reusing a stale list."""
        self._is_dirty = True

    # --- what the page asks for ----------------------------------------------

    def _entries(self, names) -> list[dict]:
        """The loaded sessions with these names, in list order.

        The page sends names only. A name this widget did not load is dropped,
        so nothing from the page is ever used as a path.
        """
        wanted = set(names)
        return [
            entry
            for entry in self.sessions_data
            if isinstance(entry, dict)
            and isinstance(entry.get("session_name"), str)
            and entry["session_name"] in wanted
            and entry.get("session_path")
        ]

    def _open(self, name: str) -> None:
        for entry in self._entries([name]):
            logger.info(f"Opening session: {entry['session_path']}")
            self.session_selected.emit(entry["session_path"])

    def _export(self, names) -> None:
        paths = [entry["session_path"] for entry in self._entries(names)]
        if len(paths) >= 2:
            self.multi_export_requested.emit(paths)

    def _set_status(self, names, status: str) -> None:
        # manual=True stops session_lifecycle from ever managing this session's
        # status again -- otherwise un-archiving an old session would just
        # re-archive it on the next refresh.
        self._write(
            names,
            lambda path: self.session_manager.update_session_status(
                path, status, manual=True
            ),
            done=f"Set {{what}} to {status.capitalize()}",
            one_failed="The status wasn't updated",
        )

    def _set_comment(self, names, text: str) -> None:
        self._write(
            names,
            lambda path: self.session_manager.update_session_info(
                path, {"comments": text}
            ),
            done="Comment saved on {what}" if text else "Comment cleared on {what}",
            one_failed="The comment wasn't saved",
        )

    def _write(self, names, write, *, done: str, one_failed: str) -> None:
        """Apply one change to every named session, then say so once.

        One banner for the sessions that failed, one toast with Undo for the
        ones that were written, and one quiet reload at the end: on the
        production file server that is one round trip, not one per session.
        """
        entries = self._entries(names)
        if not entries:
            return
        written = []
        for entry in entries:
            try:
                write(entry["session_path"])
            except Exception:
                logger.exception(f"Failed to update {entry['session_name']}")
            else:
                written.append(entry)

        failed = len(entries) - len(written)
        if failed:
            show_error(
                self,
                one_failed
                if len(entries) == 1
                else f"{failed} of {len(entries)} sessions weren't updated",
                "Details are in Logs.",
            )
        if written:
            self._undo = {
                entry["session_path"]: {key: entry.get(key) for key in _UNDO_KEYS}
                for entry in written
            }
            self.bridge.raise_toast(done.format(what=_what(written)), True)
        self.refresh_sessions(quiet=True)

    def _undo_last(self) -> None:
        """Put back what the last status or comment change replaced."""
        undo, self._undo = self._undo, {}
        if not undo:
            return
        failed = 0
        for path, fields in undo.items():
            try:
                self.session_manager.restore_session_fields(path, fields)
            except Exception:
                logger.exception(f"Failed to restore {path}")
                failed += 1
        if failed:
            show_error(
                self,
                "The change wasn't undone"
                if len(undo) == 1
                else f"{failed} of {len(undo)} sessions weren't restored",
                "Details are in Logs.",
            )
        self.refresh_sessions(quiet=True)

    # --- widget events -------------------------------------------------------

    def showEvent(self, event):
        """Refresh only if something changed since the last load -- avoids
        re-fetching from the file server every time this widget becomes
        visible with nothing new to show.
        """
        super().showEvent(event)
        if self._is_dirty and self.current_client_id:
            self.refresh_sessions()

    def closeEvent(self, event):
        """Cleanup worker when widget closes.

        CRITICAL: This prevents crashes from worker still running after
        widget destruction (lesson from commit #216).
        """
        if self.worker is not None:
            logger.debug("Cleaning up session browser worker on widget close")
            self.worker.cleanup()
            self.worker = None
        super().closeEvent(event)
```

- [ ] **Step 4: Run the widget tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_session_browser_widget.py tests/test_session_browser_reload.py tests/test_session_browser_lifecycle_sync.py`
Expected: 31 + 5 + 4 passed. `test_session_browser_lifecycle_sync.py` is untouched: it tests the worker.

- [ ] **Step 5: Delete the Qt tree's parts**

1. `/usr/bin/git rm gui/session_row_delegates.py gui/components/selectionbar.py tests/test_session_browser_1e.py tests/test_session_browser_columns.py tests/test_components_selectionbar.py`
2. In `gui/components/__init__.py`, delete the line
   `from gui.components.selectionbar import ContextualSelectionBar` and the line
   `    "ContextualSelectionBar",` in `__all__`.
3. In `shopify_tool/session_lifecycle.py`, delete the whole `age_label` function (from `def age_label(` up to
   the blank lines before `def age_cell(`).
4. In `tests/test_session_lifecycle.py`, delete `age_label,` from the import list and delete the whole
   `class TestAgeLabel:` (ten tests, from `class TestAgeLabel:` up to the blank lines before `class TestNeedsAttention:`).
   `test_the_warning_window_is_derived_not_typed` lives on in `TestAgeCell`.
5. Replace the whole of `tests/test_status_channels.py` with:

```python
"""The status roles the shared chip resolves (shared/theme.py).

The session row's eight states are pinned in tests/test_browse_state.py: the
Browse page draws them as a badge with a dot (phase 4 spec section 4.2), and
the Qt delegate with its STATE_STYLES table is gone.
"""

import pytest

from shared.theme import DARK_THEME, LIGHT_THEME, status_style


@pytest.mark.parametrize("theme", [LIGHT_THEME, DARK_THEME])
def test_a_role_with_no_bg_partner_falls_back_to_surface_sunken(theme):
    # text_secondary has no _bg partner. Force live=True, or the one tolerated
    # missing token in the theme goes untested.
    assert status_style("text_secondary", theme, live=True).fill == theme.surface_sunken
```

6. In `tests/test_status_edge_delegate.py`, replace the function
   `test_role_status_collides_with_no_other_custom_role` with:

```python
def test_role_status_collides_with_no_other_custom_role():
    """Spec §10. ROLE_STATUS is the one custom item role left in the repo.

    The delegate that shares this table is TagDelegate, and it is safe for a
    different reason: it reads only Qt.DisplayRole (gui/tag_delegate.py),
    never a custom role.
    """
    from PySide6.QtCore import Qt

    from gui.pandas_model import ROLE_STATUS

    assert ROLE_STATUS != Qt.ItemDataRole.UserRole
```

7. In `tests/audit/test_05_sessions_sweep.py`, replace the function
   `test_a_comment_that_fails_to_save_is_reported` with:

```python
def test_a_comment_that_fails_to_save_is_reported(qapp, monkeypatch):
    manager = Mock()
    manager.update_session_info.side_effect = OSError("share went away")
    told = []
    monkeypatch.setattr(browser_module, "show_error", lambda *a, **k: told.append(a))

    widget = browser_module.SessionBrowserWidget(manager)
    widget.sessions_data = [
        {
            "session_name": "2026-07-01_1",
            "session_path": "/share/Sessions/CLIENT_M/2026-07-01_1",
        }
    ]
    widget.bridge.setComment(["2026-07-01_1"], "call courier")

    assert told
```

Left alone on purpose: `gui/selection_ring.py` and `gui/status_edge_delegate.py` (the log viewer uses them
until phase 6), `tests/test_selection_ring.py` (it reads this module's source and still passes), and the
mention of `session_row_delegates.py` in a docstring of `tests/test_selection_ring_renders.py` and in ADR 0003
(history; CLAUDE.md, "Doc paths cited in code comments").

- [ ] **Step 6: Find anything else that used what is gone**

Run: `rg -n "session_row_delegates|ContextualSelectionBar|selectionbar|age_label|_IN_FLIGHT|sessions_tree|status_filter\b|_on_comments_changed|_on_status_changed|_populate_tree" gui shopify_tool tests gui_main.py`
Expected: no hit in `gui/` or `shopify_tool/` except `status_filter` inside `SessionLoaderWorker`,
`SessionManager.list_client_sessions` and `ui_manager.refresh_recent_sessions`'s callee. Any hit in `tests/`
is a test of the Qt tree that this step missed: rewrite it against `widget.bridge` and
`widget.bridge.state`, never skip it.

- [ ] **Step 7: Run the suites this touches**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_session_browser_widget.py tests/test_session_browser_reload.py tests/test_session_browser_lifecycle_sync.py tests/test_session_lifecycle.py tests/test_status_channels.py tests/test_status_edge_delegate.py tests/audit/test_05_sessions_sweep.py tests/test_stale_session.py tests/test_shell.py tests/test_results_screen.py tests/test_selection_ring.py tests/test_browse_page.py`
Expected: all pass.

Run: `.venv/bin/ruff check .`
Expected: no findings.

- [ ] **Step 8: Commit**

`/usr/bin/git add -A gui shopify_tool tests`, check `/usr/bin/git status --short` shows only the files this
task names, then commit with:

```
Browse hosts the web page; the Qt session tree and its delegates go

SessionBrowserWidget keeps its name, signals and public methods and becomes
the controller: one web view, the loader, the writes, and one remembered
Undo. Status and comment changes toast with Undo, and Undo restores status,
the hand-set flag, the comment and the timestamps. A failed load is a panel
in the page. Deleted: session_row_delegates, ContextualSelectionBar,
age_label and the tests of the tree; column sorting goes with it.
```

---

### Task 7: The shell: inset, toast router, F5, and where a session opens

**Files:**
- Modify: `gui/ui_manager.py`, `gui/main_window_pyside.py`, `gui/shortcuts_dialog.py`
- Test: `tests/test_shell.py`, `tests/test_toast_router.py`, `tests/audit/test_05_sessions_sweep.py`

**Interfaces:**
- Consumes: `SessionBrowserWidget.view`, `.bridge`, `.refresh_sessions()` (Task 6).
- Produces: `MainWindow._refresh_browse()`; `web_toast` answers on tab 2; `_WEB_PAGES == frozenset({0, 1, 2})`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_shell.py`:

```python
def test_browse_is_one_web_view(main_window):
    """Phase 4 spec section 7: tab 2 holds the Browse page and nothing else."""
    from PySide6.QtWebEngineWidgets import QWebEngineView

    tab = main_window.main_tabs.widget(2)
    assert tab.findChildren(QWebEngineView) == [main_window.session_browser.view]
    margins = tab.layout().contentsMargins()
    assert (margins.left(), margins.top(), margins.right(), margins.bottom()) == (0, 0, 0, 0)


def test_browse_takes_the_page_area_to_its_edges(main_window):
    main_window.resize(1366, 768)
    main_window.main_tabs.setCurrentIndex(2)
    QApplication.processEvents()
    margins = main_window.page_area.layout().contentsMargins()
    assert (margins.left(), margins.top(), margins.right(), margins.bottom()) == (0, 0, 0, 0)
    assert main_window.main_tabs.width() == 1166


def test_f5_reloads_the_session_list_on_browse_only(main_window, monkeypatch):
    calls = []
    monkeypatch.setattr(
        main_window.session_browser, "refresh_sessions", lambda: calls.append("refresh")
    )
    main_window.main_tabs.setCurrentIndex(3)
    main_window._refresh_browse()
    assert calls == []
    main_window.main_tabs.setCurrentIndex(2)
    main_window._refresh_browse()
    assert calls == ["refresh"]
```

In `tests/test_toast_router.py`, add after `test_on_results_the_results_page_draws_it`:

```python
def test_on_browse_the_browse_page_draws_it(main_window):
    main_window.main_tabs.setCurrentIndex(2)
    seen = _raised(main_window.session_browser.bridge)
    other = _raised(main_window.setup_bridge)

    shown = toast(main_window, "Combined stock export saved: stock.xlsx.")

    assert seen == [("Combined stock export saved: stock.xlsx.", False)]
    assert other == []
    assert shown is None
    assert Toast.for_window(main_window) is None
```

In `tests/audit/test_05_sessions_sweep.py`, add after
`test_opening_a_session_without_analysis_drops_the_previous_orders` (it uses that file's `main_window`
fixture, which has the client `acme` loaded):

```python
def test_opening_a_session_without_analysis_lands_on_setup(main_window):
    path = main_window.session_manager.create_session("acme")
    main_window.main_tabs.setCurrentIndex(2)

    main_window.load_existing_session(path)

    assert main_window.main_tabs.currentIndex() == 0
```

- [ ] **Step 2: Run them and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_shell.py tests/test_toast_router.py tests/audit/test_05_sessions_sweep.py`
Expected: five failures: the tab margins are 5, the page inset is 5 on Browse, `_refresh_browse` does not
exist, the Qt toast shows on Browse, and the session stays on tab 2.

- [ ] **Step 3: `gui/shortcuts_dialog.py`**

Replace:

```python
    ("Ctrl+Z", "Undo the last change"),
```

with:

```python
    ("Ctrl+Z", "Undo the last change"),
    ("F5", "Refresh the session list, on Browse"),
```

- [ ] **Step 4: `gui/ui_manager.py`**

Replace:

```python
_WEB_PAGES = frozenset({0, 1})
```

with:

```python
_WEB_PAGES = frozenset({0, 1, 2})
```

Replace:

```python
    def _create_tab3_session_browser(self):
        """Create Tab 3: Session Browser

        Reuses existing SessionBrowserWidget.
        """
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(5)
        layout.setContentsMargins(5, 5, 5, 5)

        # REUSE existing SessionBrowserWidget
        from gui.session_browser_widget import SessionBrowserWidget

        self.mw.session_browser = SessionBrowserWidget(self.mw.session_manager, self.mw)

        layout.addWidget(self.mw.session_browser, 1)  # Full stretch

        return tab
```

with:

```python
    def _create_tab3_session_browser(self):
        """Browse: one QWebEngineView, no Qt inside (phase 4 spec).

        SessionBrowserWidget hosts the view and does the loading and the
        writes; everything drawn on this screen is in gui/web/browse.*.
        """
        from gui.session_browser_widget import SessionBrowserWidget

        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.mw.session_browser = SessionBrowserWidget(self.mw.session_manager, self.mw)
        layout.addWidget(self.mw.session_browser, 1)
        return tab
```

- [ ] **Step 5: `gui/main_window_pyside.py`**

Three edits: `web_toast`, the F5 shortcut at the end of `connect_signals`, and the else-branch of
`load_existing_session`.

Replace:

```python
        bridge = getattr(
            self,
            {0: "setup_bridge", 1: "results_bridge"}.get(
                self.main_tabs.currentIndex(), ""
            ),
            None,
        )
        if bridge is None:
```

with:

```python
        index = self.main_tabs.currentIndex()
        if index == 2:
            bridge = getattr(getattr(self, "session_browser", None), "bridge", None)
        else:
            bridge = getattr(
                self, {0: "setup_bridge", 1: "results_bridge"}.get(index, ""), None
            )
        if bridge is None:
```

Replace:

```python
        # Add Ctrl+Z shortcut for Undo
        QShortcut(QKeySequence("Ctrl+Z"), self, self.undo_last_operation)
```

with:

```python
        # Add Ctrl+Z shortcut for Undo
        QShortcut(QKeySequence("Ctrl+Z"), self, self.undo_last_operation)

        # F5 reloads the session list, on Browse only
        QShortcut(QKeySequence("F5"), self, self._refresh_browse)

    def _refresh_browse(self):
        """F5: reload the sessions, when Browse is the screen showing."""
        if self.main_tabs.currentIndex() == 2:
            self.session_browser.refresh_sessions()
```

Replace:

```python
                else:
                    # Session exists but no analysis yet
                    self.log_activity(
```

with:

```python
                else:
                    # Session exists but no analysis yet: Setup is where its
                    # files and Run analysis are (phase 4 spec section 7).
                    self.main_tabs.setCurrentIndex(0)
                    self.log_activity(
```

The toast "Session … opened. Run an analysis to see results." is raised after the switch, so the Setup page
draws it.

- [ ] **Step 6: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_shell.py tests/test_toast_router.py tests/test_shortcuts_dialog.py tests/audit/test_05_sessions_sweep.py tests/test_session_setup_layout.py tests/test_results_screen.py tests/test_stale_session.py`
Expected: all pass. `test_shortcuts_dialog.py::test_every_listed_shortcut_is_bound` now also finds F5.

- [ ] **Step 7: Commit**

`/usr/bin/git add gui/ui_manager.py gui/main_window_pyside.py gui/shortcuts_dialog.py tests/test_shell.py tests/test_toast_router.py tests/audit/test_05_sessions_sweep.py`,
then commit with:

```
Shell: Browse is a web page, F5 reloads it, and its toasts land in it

Tab 2 joins the web pages, so it loses its inset and the toast router sends
a toast raised on Browse to the page. F5 reloads the session list on Browse.
A session with no analysis opens on Setup, where its files and Run are.
```

---

### Task 8: Docs, the build check, the visual check, the gate

**Files:**
- Modify: `CONTEXT.md`, `docs/adr/0016-the-web-tier-grows-screen-by-screen.md`,
  `docs/design/ui-refresh/roadmap.md`, `.github/workflows/build_release.yml`
- Create: `docs/design/ui-refresh/renders/phase4/*.png`

- [ ] **Step 1: `CONTEXT.md`**

Keep its style (one bold term, a dash, a definition; a glossary only).

1. **Qt tier**: replace `Everything except the two heavy views.` with
   `Everything except the screens that have moved to the web tier.`
2. **Web tier**: replace `Analysis Results and Session Setup today;` with
   `Analysis Results, Session Setup and Browse today;`
3. **Shape**: add this sentence at the end of the entry:
   `No screen of this app draws a shape since Browse moved to the web tier; a session row's **badge** carries a dot instead.`
4. **Badge**: replace the entry with:

```markdown
**Badge** — the web tier's status pill: a tinted fill, no outline and no mark.
Authorship, which the mark carries on a chip, is said in the pane's verdict
instead. A session row's badge adds a dot whose fill says how far the session
has come: hollow before packing starts, half while it is in flight, solid once
it is closed. Not a **chip**, which stays the Qt tier's silhouette.
```

5. **Selection bar**: replace its last sentence (`The results document has one; the Session Browser has a Qt
   one of the same composition and no shared code.`) with
   `The results document has one and the Browse page has one; they share the kit's parts and no script.`
6. In the Sessions section, after **Display status**, add:

```markdown
**Browse state** — the map Python builds for the Browse page: which view
shows, and one record per session with its age, badge, counts, packing and
attention reason already worded. The page filters, counts and groups those
records and decides no fact about a session.

**Needs attention** — the group Browse draws first: sessions that are paused,
stale or incomplete, and sessions still in flight that carry blocked orders.
Each row's reason is named in the group's heading.
```

- [ ] **Step 2: ADR 0016**

In `docs/adr/0016-the-web-tier-grows-screen-by-screen.md`, under **Consequences**, add a bullet after the
one about Setup:

```markdown
- Browse moved in phase 4 (2026-10-01) with the third bridge, `BrowseBridge`, and a third view, on the
  phase 3 measurement (about 31 MB a view). Its page owns its view state (tab, search, checked rows), as
  the results document does; Python owns every fact about a session.
```

- [ ] **Step 3: `docs/design/ui-refresh/roadmap.md`**

1. In phase 3's paragraph, replace
   `every other screen, until Browse, Logs and Tools get their own page heads.` with
   `every other screen, until Logs and Tools get their own page heads (Browse's mockup has none).`
2. Replace the heading `### 4. Browse to the web tier` and its paragraph with:

```markdown
### 4. Browse to the web tier (built in run 44)

Spec: `docs/superpowers/specs/2026-10-01-ui-refresh-phase4-browse-web-design.md`.
Plan: `docs/superpowers/plans/2026-10-01-ui-refresh-phase4-browse-web.md`.

Built as listed below, with these differences. Export combined stock stays in the selection bar (two or more
checked). Column sorting is gone: rows are newest first inside each group. The auto-archive countdown moved
from the Age cell to its tooltip, with the age in the warning colour, and shows only on sessions the
automation will really archive. Packing counts packing lists. A session with no analysis opens on Setup.
Undo restores the status, the hand-set flag, the comment and the timestamps. A failed load is a panel in
the page. The session chip stays in the bar on Browse.

Status tabs with live counts (All, Active, Completed, Abandoned, Archived), search and Refresh on one row. The
"Needs attention" group first, with its reasons, then "Everything else". Eight display statuses as badges.
The Status menu offers the four a person can set and says what each one resolves to. Comment, and an Undo
toast for every change. The packing progress bar. The archived footer. Double-click opens the session.
```

- [ ] **Step 4: The build check**

In `.github/workflows/build_release.yml`, in the `foreach ($name in ...)` list that checks the bundle, add
`"browse.html"` after `"setup.html"`.

- [ ] **Step 5: The visual check (required by CLAUDE.md)**

Write this script under your job's tmp dir, not in the repo, as `render_phase4.py`:

```python
"""Throwaway: render the Browse page in every state and both themes."""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
sys.path[:0] = [os.getcwd(), os.path.join(os.getcwd(), "tests")]

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)

from test_browse_page import SESSIONS
from test_browse_state import make_state

from gui.browse_bridge import mount_browse_page
from gui.theme_manager import get_theme_manager

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)


def pump(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


view = QWebEngineView()
bridge = mount_browse_page(view)
view.resize(1166, 720)  # the page a 1366x768 window gives Browse
view.show()
pump(1500)


def js(code):
    view.page().runJavaScript(code)
    pump(300)


def click(selector):
    js(f"document.querySelector({selector!r}).click()")


def reset():
    """Back to the default list: another client and back clears the view state."""
    bridge.set_state(make_state(SESSIONS, client="OTHER"))
    pump(200)
    bridge.set_state(make_state(SESSIONS))
    pump(300)


def two_checked():
    reset()
    click('[data-row="2026-09-29_2"]')
    click('[data-row="2026-09-26_2"]')


def status_menu():
    two_checked()
    click("#status-button")


def comment_popover():
    reset()
    click('[data-row="2026-09-29_2"]')
    click("#comment-button")


def no_match():
    reset()
    js(
        "var s = document.getElementById('search'); s.value = '2025-12';"
        " s.dispatchEvent(new Event('input'));"
    )


def archived_shown():
    reset()
    click("#footer [data-act='toggle-archived']")


def toast():
    two_checked()
    bridge.raise_toast("Set 2 sessions to Completed", True)
    pump(300)


def plain(state):
    def show():
        bridge.set_state(make_state(client="OTHER"))
        pump(200)
        bridge.set_state(state)
        pump(300)

    return show


STATES = {
    "default": reset,
    "two-checked": two_checked,
    "status-menu": status_menu,
    "comment-popover": comment_popover,
    "no-match": no_match,
    "archived-shown": archived_shown,
    "loading": plain(make_state(SESSIONS, loading=True)),
    "no-client": plain(make_state(client="")),
    "no-sessions": plain(make_state([])),
    "failed": plain(make_state(failed=True)),
    "toast-undo": toast,  # last: the toast stays up for four seconds
}

for theme in ("light", "dark"):
    get_theme_manager().set_theme(theme)
    pump(300)
    for name, show in STATES.items():
        show()
        view.grab().save(str(OUT / f"{theme}-{name}.png"))
    js("document.getElementById('toast-dismiss').click()")
get_theme_manager().set_theme("light")
print("saved to", OUT)
```

Run it: `QT_QPA_PLATFORM=offscreen QTWEBENGINE_DISABLE_SANDBOX=1 .venv/bin/python <tmp>/render_phase4.py <tmp>/renders`
(the working directory must be the worktree root). Read every PNG. Then:

1. Compare `light-default.png` with `docs/design/ui-refresh/mockups/renders/browse.png`, element by element:
   the tabs and their counts, the search box, the count label and Refresh on one row; the header row; the
   two group heads; each column's alignment (Age, Orders, Items and Blocked right-aligned); the badges and
   their dots; the packing text and bar; the footer.
2. For the other states and for dark, unpack `mockups/browse.html` with the script in `mockups/README.md` and
   read the template's `PRESETS` and style helpers, or open the file in Chrome if a browser tool is
   available; compare each with its PNG: two checked, the Status menu, the Comment popover, no match,
   loading, no client, no sessions.
3. Check by eye for what tests cannot: clipped or overlapping text, a badge wider than its 124px column
   ("Not started" and "In progress" are the widest), a packing bar pushed out of its column, a popover cut
   off by the card's edge, a half dot that reads as solid or hollow at this size, a disabled Refresh that
   looks enabled, an unreadable colour pair in dark, the toast covering the footer link.
4. Render the shell: construct `MainWindow` as `tests/test_shell.py`'s `main_window` fixture does (set
   `FULFILLMENT_SERVER_PATH` to a temp dir), `resize(1366, 768)`, `win.main_tabs.setCurrentIndex(2)`, and
   save `win.grab()` in both themes. The web view may come out blank in a window grab offscreen; that is
   expected. Judge that Browse's page area has no 5px ring and that the command bar is unchanged.

The departures the renders will show, all in spec §9: the group dot is `status_warning` (a dark brown in
light), not the mockup's amber; controls and rows take the density tokens; the head row's rule is a hairline;
Export combined stock is a fourth button; packing counts lists.

Fix what is wrong in the CSS or the script, re-run `tests/test_browse_page.py`, and render again. Every
departure you keep must already be in spec §9; if you find a new one, add it to §9 in the same commit and say
so in the PR.

Copy four renders into the repo under `docs/design/ui-refresh/renders/phase4/`: `light-default.png`,
`dark-status-menu.png`, `light-comment-popover.png`, `light-loading.png`.

- [ ] **Step 6: The gate**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
Expected: only the baseline's failures.

Run: `.venv/bin/ruff check .`
Expected: no findings.

Run: `graphify update .`

- [ ] **Step 7: Commit**

`/usr/bin/git add CONTEXT.md docs .github/workflows/build_release.yml`, check `/usr/bin/git status --short`,
and commit with the message `Phase 4 docs: glossary, ADR note, roadmap, renders, and the bundle check`.

- [ ] **Step 8: What the PR must say (for Stage C)**

- The mockup followed (`browse.html`) and the departures (spec §9), with the four renders attached.
- The owner's three decisions (spec §2): Export stays, sorting goes, the countdown is in the tooltip.
- Behaviour changes an operator will notice: status and comment changes can be undone from the toast for
  four seconds; Comment works on several sessions at once and replaces each one's comment; the badge reads
  "In progress" where it read "Active"; Incomplete is red and Abandoned is neutral; column sorting is gone;
  a session with no analysis opens on Setup; F5 refreshes Browse.
- A third `QWebEngineView`: about +31 MB on Linux (ADR 0016). The Windows check over RDP from the phase 3 PR
  now covers three views; do it before the release.
- No Packing Tool work: nothing in `shared/` changed.
- Left for later: Ctrl+F on Browse still goes to Results' search; `gui/selection_ring.py` and
  `gui/status_edge_delegate.py` stay until Logs moves (phase 6).
- The baseline's failures, if any, by name.
