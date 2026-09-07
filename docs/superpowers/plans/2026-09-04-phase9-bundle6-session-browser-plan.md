# Phase 9 Bundle 6 — Session browser implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the Session Browser into a two-group `QTreeWidget` whose eight
states read by shape alone, with Age, Blocked and Comment columns and two empty
states.

**Architecture:** Every derivable fact becomes a pure function in
`shopify_tool/session_lifecycle.py` — no Qt, no I/O, testable without a
`QApplication`. That module is the seam: Tasks 1–3 build and test it with no
widget in sight, and Tasks 5–8 only wire it. The status cell's fourth channel
(shape) is painted by one new function in `shared/theme.py`, authored in
`packing-tool` and synced.

**Tech Stack:** PySide6 (`QTreeWidget`, `QStyledItemDelegate`, `QPainter`),
pytest with `QT_QPA_PLATFORM=offscreen`, ruff.

**Spec:** `docs/superpowers/specs/2026-09-04-phase9-bundle6-session-browser-design.md`

## Global Constraints

- **Run everything through the repo venv.** `python` and `ruff` are not on
  PATH. Use `.venv/bin/python` and `.venv/bin/ruff`, or `scripts/run_tests.sh`.
  First command in a fresh worktree: `./scripts/setup_venv.sh`.
- **Tests:** `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest`.
  Baseline before this plan: **1261 passed**. It must not go down.
- **Lint:** `.venv/bin/ruff check .` must be clean before every commit.
- **Never hand-edit `shared/`.** It is owned by `../packing-tool`. Edit it
  there, then run `python scripts/sync_shared.py ../packing-tool` from this
  repo's root. From a worktree the sibling default resolves wrong, so the path
  argument is required — see Task 4.
- **No hardcoded colours.** Every colour is a `ThemeTokens` attribute read off
  `get_theme_manager().get_current_theme()`.
- **Token names are frozen.** This plan adds no token. It uses
  `text_secondary`, `status_info`, `status_success`, `status_warning`,
  `status_danger`, `selection_border`, `surface`, `border` — all existing.
- **Copy rules:** sentence case, active voice, no exclamation marks, no
  apologies. An empty state names its cause and offers the action that clears
  it.
- **Canonical term is "blocked".** Never `BLK`, never `SHORT ON STOCK`, in
  code, headers, tooltips or comments. The persisted key stays
  `not_fulfillable_orders`.
- **Shapes are painted paths.** Never a character, never an SVG. Nothing may
  depend on a font shipping `◐`.
- **PR-only.** Branch `worktree-phase9-bundle6-session-browser` is already
  checked out. Never commit to `main`.

---

## File structure

| File | Responsibility | Task |
|---|---|---|
| `shopify_tool/session_lifecycle.py` | All four derived facts, pure | 1, 2, 3 |
| `tests/test_session_lifecycle.py` | Their tests, no Qt | 1, 2, 3 |
| `../packing-tool/shared/theme.py` | `QTreeView` QSS + `paint_status_shape` | 4 |
| `gui/selection_ring.py` | `header_of()` accepts a tree header | 5 |
| `gui/session_row_delegates.py` | `STATE_STYLES`, shape painting | 6 |
| `gui/session_browser_widget.py` | Tree, columns, groups, panels, footer | 7, 8, 9 |
| `CONTEXT.md` | Glossary: shape, blocked order, display status | 10 |

---

## Task 1: The blocked count

**Files:**
- Modify: `shopify_tool/session_lifecycle.py`
- Test: `tests/test_session_lifecycle.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `blocked_orders(entry: dict) -> int | None`.

Read spec §2 and §3 before starting. The number is already in the data; this
task adds no key and no migration.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_session_lifecycle.py`:

```python
from shopify_tool.session_lifecycle import blocked_orders


class TestBlockedOrders:
    def test_reads_the_stored_key(self):
        assert blocked_orders({"not_fulfillable_orders": 4}) == 4

    def test_zero_is_zero_not_none(self):
        assert blocked_orders({"not_fulfillable_orders": 0}) == 0

    def test_falls_back_to_the_complement(self):
        entry = {"total_orders": 31, "fulfillable_orders": 27}
        assert blocked_orders(entry) == 4

    def test_stored_key_wins_over_the_complement(self):
        entry = {"not_fulfillable_orders": 4, "total_orders": 31,
                 "fulfillable_orders": 99}
        assert blocked_orders(entry) == 4

    def test_never_analysed_is_none_not_zero(self):
        assert blocked_orders({"session_name": "2026-09-01_1"}) is None

    def test_nonsense_reads_as_none(self):
        assert blocked_orders({"not_fulfillable_orders": "four"}) is None
        assert blocked_orders({"not_fulfillable_orders": -1}) is None
        assert blocked_orders({"total_orders": 3, "fulfillable_orders": 9}) is None

    def test_survives_a_non_dict(self):
        assert blocked_orders(None) is None
        assert blocked_orders([]) is None
```

- [ ] **Step 2: Run them and watch them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_session_lifecycle.py -k Blocked -v`
Expected: FAIL, `ImportError: cannot import name 'blocked_orders'`.

- [ ] **Step 3: Implement it**

Add to `shopify_tool/session_lifecycle.py`, after `is_fully_packed`:

```python
def _count(value) -> int | None:
    """A non-negative int, or None for anything else.

    bool is an int in Python and would sail through isinstance; a True here
    means the file holds something we do not understand, so it reads as None.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value >= 0 else None


def blocked_orders(entry: dict) -> int | None:
    """Orders this session cannot fulfil, or None when it was never analysed.

    None is not 0: a session with no analysis has no answer, and the Blocked
    column must stay blank rather than claim nothing is blocked.

    `core.py` has written `not_fulfillable_orders` into session_info.json on
    every session-mode analysis since the session architecture landed, and the
    index carries whole session_info dicts, so the stored key is the normal
    path. The subtraction is the fallback for a session written by something
    that recorded only the two halves.
    """
    if not isinstance(entry, dict):
        return None

    stored = _count(entry.get("not_fulfillable_orders"))
    if stored is not None:
        return stored

    total = _count(entry.get("total_orders"))
    fulfillable = _count(entry.get("fulfillable_orders"))
    if total is None or fulfillable is None or fulfillable > total:
        return None
    return total - fulfillable
```

- [ ] **Step 4: Run them and watch them pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_session_lifecycle.py -k Blocked -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add shopify_tool/session_lifecycle.py tests/test_session_lifecycle.py
git commit -m "9.19: one accessor for the blocked-order count"
```

---

## Task 2: The eight display statuses

**Files:**
- Modify: `shopify_tool/session_lifecycle.py`
- Test: `tests/test_session_lifecycle.py`

**Interfaces:**
- Consumes: `packing_completion(entry)` and `parse_created_at(value)`, both
  already in this module.
- Produces: `DISPLAY_STATUSES: tuple[str, ...]`,
  `display_status(entry: dict, now: datetime) -> str`.

Read spec §4. The four stored statuses are `active`, `completed`, `abandoned`,
`archived` (`SessionManager.VALID_STATUSES`). The eight displayed ones are the
phase-8 contract table plus `archived`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_session_lifecycle.py`:

```python
from datetime import datetime, timedelta

from shopify_tool.session_lifecycle import DISPLAY_STATUSES, display_status

NOW = datetime(2026, 9, 4, 12, 0).astimezone()


def _entry(status="active", lists=(), progress=None, updated=None):
    entry = {
        "session_name": "2026-09-01_1",
        "status": status,
        "statistics": {"packing_lists": list(lists)},
        "packing_progress": dict(progress or {}),
    }
    if updated:
        entry["last_updated"] = updated.isoformat()
    return entry


class TestDisplayStatus:
    def test_the_vocabulary_is_eight_states(self):
        assert DISPLAY_STATUSES == (
            "not_started", "in_progress", "paused", "stale",
            "completed", "incomplete", "abandoned", "archived",
        )

    def test_active_with_no_progress_is_not_started(self):
        assert display_status(_entry(lists=["a", "b"]), NOW) == "not_started"

    def test_active_with_some_progress_is_in_progress(self):
        entry = _entry(lists=["a", "b"], progress={"a": {"status": "completed"}},
                       updated=NOW - timedelta(days=1))
        assert display_status(entry, NOW) == "in_progress"

    def test_a_paused_list_beats_progress(self):
        entry = _entry(lists=["a", "b"],
                       progress={"a": {"status": "completed"},
                                 "b": {"status": "paused"}},
                       updated=NOW - timedelta(days=1))
        assert display_status(entry, NOW) == "paused"

    def test_in_progress_untouched_a_week_is_stale(self):
        entry = _entry(lists=["a", "b"], progress={"a": {"status": "completed"}},
                       updated=NOW - timedelta(days=8))
        assert display_status(entry, NOW) == "stale"

    def test_not_started_never_goes_stale(self):
        # Nothing has been touched because nothing was started. Age is the
        # column that says so; Stale would be the same fact drawn twice.
        entry = _entry(lists=["a"], updated=NOW - timedelta(days=90))
        assert display_status(entry, NOW) == "not_started"

    def test_completed_and_fully_packed_is_completed(self):
        entry = _entry(status="completed", lists=["a"],
                       progress={"a": {"status": "completed"}})
        assert display_status(entry, NOW) == "completed"

    def test_completed_with_work_left_is_incomplete(self):
        entry = _entry(status="completed", lists=["a", "b"],
                       progress={"a": {"status": "completed"}})
        assert display_status(entry, NOW) == "incomplete"

    def test_completed_with_no_lists_at_all_is_completed(self):
        # packing_completion returns (0, 0) here. A session with nothing to
        # pack that a person called done is done, not unfinished.
        assert display_status(_entry(status="completed"), NOW) == "completed"

    def test_abandoned_and_archived_pass_through(self):
        assert display_status(_entry(status="abandoned"), NOW) == "abandoned"
        assert display_status(_entry(status="archived"), NOW) == "archived"

    def test_an_unknown_stored_status_renders_as_itself(self):
        assert display_status(_entry(status="frozen"), NOW) == "frozen"

    def test_an_unreadable_timestamp_is_not_stale(self):
        entry = _entry(lists=["a", "b"], progress={"a": {"status": "completed"}})
        entry["last_updated"] = "not a date"
        assert display_status(entry, NOW) == "in_progress"

    def test_survives_a_non_dict(self):
        assert display_status(None, NOW) == "active"
```

- [ ] **Step 2: Run them and watch them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_session_lifecycle.py -k DisplayStatus -v`
Expected: FAIL, `ImportError: cannot import name 'DISPLAY_STATUSES'`.

- [ ] **Step 3: Implement it**

Add to `shopify_tool/session_lifecycle.py`:

```python
# The eight states a row shows, in the order they progress. The four a person
# can set live in SessionManager.VALID_STATUSES; the other four are derived
# here from packing progress and idle time.
DISPLAY_STATUSES = (
    "not_started", "in_progress", "paused", "stale",
    "completed", "incomplete", "abandoned", "archived",
)

# An in-flight session nobody has touched for this long has stopped moving.
# Not age from creation -- the Age column already carries that, and drawing
# one fact twice is what this phase keeps deleting.
STALE_AFTER_DAYS = 7


def _has_paused_list(entry: dict) -> bool:
    progress = entry.get("packing_progress")
    if not isinstance(progress, dict):
        return False
    return any(
        isinstance(block, dict) and block.get("status") == "paused"
        for block in progress.values()
    )


def _idle_since(entry: dict):
    """When this session was last written, or None if unreadable.

    packing-tool writes packing_progress through its own path, so
    `last_updated` can be missing on a session it touched last. Falling back
    to created_at makes the answer conservative rather than absent.
    """
    return (
        parse_created_at(entry.get("last_updated"))
        or parse_created_at(entry.get("created_at"))
    )


def display_status(entry: dict, now: datetime) -> str:
    """One of DISPLAY_STATUSES for this entry. Pure, total, never raises.

    An unrecognised stored status is returned unchanged, so a value some
    future version writes renders as its own name rather than as a lie.
    """
    if not isinstance(entry, dict):
        return "active"

    stored = entry.get("status", "active")

    if stored in ("abandoned", "archived"):
        return stored

    packed, total = packing_completion(entry)

    if stored == "completed":
        # A person called it done. If lists are still unpacked, that is a
        # human judgment someone can still act on -- not an automation
        # artefact: derive_status_updates only ever promotes a fully packed
        # session.
        return "incomplete" if total > 0 and packed < total else "completed"

    if stored != "active":
        return stored

    if _has_paused_list(entry):
        return "paused"
    if packed == 0:
        return "not_started"

    idle_since = _idle_since(entry)
    if idle_since is not None and now - idle_since >= timedelta(days=STALE_AFTER_DAYS):
        return "stale"
    return "in_progress"
```

- [ ] **Step 4: Run them and watch them pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_session_lifecycle.py -k DisplayStatus -v`
Expected: 12 passed.

- [ ] **Step 5: Commit**

```bash
git add shopify_tool/session_lifecycle.py tests/test_session_lifecycle.py
git commit -m "9.19: eight display statuses derived from four stored ones"
```

---

## Task 3: Age and needs-attention

**Files:**
- Modify: `shopify_tool/session_lifecycle.py`
- Test: `tests/test_session_lifecycle.py`

**Interfaces:**
- Consumes: `AUTO_ARCHIVE_AFTER_DAYS`, `parse_created_at`, both in this module.
- Produces: `ARCHIVE_WARNING_DAYS: int`,
  `age_label(created, now) -> tuple[str, str]`,
  `needs_attention(state: str, blocked: int | None) -> bool`.

Read spec §6.1 and §7. `age_label` returns `(cell, tooltip)`. The 23-day
threshold is `AUTO_ARCHIVE_AFTER_DAYS - ARCHIVE_WARNING_DAYS`, derived, never
typed as a literal.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_session_lifecycle.py`:

```python
from shopify_tool.session_lifecycle import (
    ARCHIVE_WARNING_DAYS,
    age_label,
    needs_attention,
)


class TestAgeLabel:
    def test_today(self):
        cell, tip = age_label(NOW - timedelta(hours=3), NOW)
        assert cell == "today"
        assert tip.startswith("Created ")

    def test_days(self):
        assert age_label(NOW - timedelta(days=3), NOW)[0] == "3d"

    def test_weeks_start_at_fourteen_days(self):
        assert age_label(NOW - timedelta(days=13), NOW)[0] == "13d"
        assert age_label(NOW - timedelta(days=14), NOW)[0] == "2w"

    def test_months_start_at_sixty_days(self):
        assert age_label(NOW - timedelta(days=59), NOW)[0] == "8w"
        assert age_label(NOW - timedelta(days=60), NOW)[0] == "2mo"

    def test_the_countdown_appears_seven_days_before_archiving(self):
        cell, _ = age_label(NOW - timedelta(days=26), NOW)
        assert cell == "26d · archives in 4d"

    def test_no_countdown_the_day_before_the_window_opens(self):
        cell, _ = age_label(NOW - timedelta(days=22), NOW)
        assert cell == "22d"

    def test_the_countdown_stops_at_zero_it_never_goes_negative(self):
        cell, _ = age_label(NOW - timedelta(days=40), NOW)
        assert "archives in" not in cell

    def test_the_tooltip_carries_the_absolute_stamp(self):
        created = NOW - timedelta(days=3)
        assert age_label(created, NOW)[1] == f"Created {created:%Y-%m-%d %H:%M}"

    def test_an_unreadable_date_says_so(self):
        assert age_label(None, NOW) == ("—", "Created date unreadable")

    def test_the_warning_window_is_derived_not_typed(self):
        assert ARCHIVE_WARNING_DAYS == 7


class TestNeedsAttention:
    def test_the_three_states_that_always_need_it(self):
        assert needs_attention("paused", 0)
        assert needs_attention("stale", 0)
        assert needs_attention("incomplete", 0)

    def test_blocked_work_still_in_flight_needs_it(self):
        assert needs_attention("in_progress", 4)
        assert needs_attention("not_started", 4)

    def test_blocked_work_already_over_does_not(self):
        assert not needs_attention("completed", 4)
        assert not needs_attention("abandoned", 4)
        assert not needs_attention("archived", 4)

    def test_unblocked_work_in_flight_does_not(self):
        assert not needs_attention("in_progress", 0)
        assert not needs_attention("in_progress", None)
```

- [ ] **Step 2: Run them and watch them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_session_lifecycle.py -k "AgeLabel or NeedsAttention" -v`
Expected: FAIL, `ImportError: cannot import name 'ARCHIVE_WARNING_DAYS'`.

- [ ] **Step 3: Implement it**

Add to `shopify_tool/session_lifecycle.py`:

```python
# How long before the auto-archive the row starts counting down. The 23-day
# threshold the countdown appears at is AUTO_ARCHIVE_AFTER_DAYS minus this;
# writing 23 anywhere would let the two drift apart.
ARCHIVE_WARNING_DAYS = 7

# The states still in flight. Blocked orders matter on these and nowhere
# else: a blocked count on a session someone already closed is history.
_IN_FLIGHT = ("not_started", "in_progress", "paused", "stale")


def age_label(created, now: datetime) -> tuple[str, str]:
    """(cell, tooltip) for the Age column.

    The cell is relative and one unit deep -- "3d", "2w", "6mo". The absolute
    stamp goes in the tooltip, which is the only place it was ever read.
    Inside the archive window the cell also carries the countdown.
    """
    if not isinstance(created, datetime):
        return ("—", "Created date unreadable")

    tooltip = f"Created {created:%Y-%m-%d %H:%M}"
    days = max(0, (now - created).days)

    if days == 0:
        cell = "today"
    elif days < 14:
        cell = f"{days}d"
    elif days < 60:
        cell = f"{days // 7}w"
    else:
        cell = f"{days // 30}mo"

    remaining = AUTO_ARCHIVE_AFTER_DAYS - days
    if 0 < remaining <= ARCHIVE_WARNING_DAYS:
        cell = f"{days}d · archives in {remaining}d"
    return (cell, tooltip)


def needs_attention(state: str, blocked: int | None) -> bool:
    """True when this row belongs in the Needs attention group.

    Either the state itself is a request for someone -- paused, stale, or
    finished-but-not-packed -- or the session is still in flight and carrying
    orders it cannot fulfil.
    """
    if state in ("paused", "stale", "incomplete"):
        return True
    return bool(blocked) and state in _IN_FLIGHT
```

- [ ] **Step 4: Run them and watch them pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_session_lifecycle.py -v`
Expected: all pass, including the pre-existing tests in the file.

- [ ] **Step 5: Lint and commit**

```bash
.venv/bin/ruff check shopify_tool/session_lifecycle.py tests/test_session_lifecycle.py
git add shopify_tool/session_lifecycle.py tests/test_session_lifecycle.py
git commit -m "9.19: relative age with an archive countdown, and the needs-attention rule"
```

---

## Task 4: `shared/` — tree selectors and the shape painter

**Files:**
- Modify: `../packing-tool/shared/theme.py`
- Test: `../packing-tool/tests/test_theme.py` (or the nearest existing theme test)
- Then: `shared/theme.py` in this repo, **via the sync script only**

Read spec §7.1 and §5.3. **`shared/` is owned by `packing-tool`.** Editing
`shared/theme.py` in this repo is silently reverted by the next sync. Both
changes are authored there and arrive here through the script.

- [ ] **Step 1: Add `QTreeView` to the four selection rules**

In `../packing-tool/shared/theme.py`, in `build_stylesheet`, the block at
`QTableView {` / `QTableView::item {`. Every selector that mentions
`QTableView` in that block gains a `QTreeView` twin, comma-separated:

```python
        QTableView, QTreeView {{
            background-color: {theme.surface};
            color: {theme.text};
            gridline-color: {theme.border_subtle};
            border-radius: {r + 4}px;
        }}
        QTableView::item, QTreeView::item {{
            border-top: 2px solid transparent;
            border-bottom: 2px solid transparent;
        }}
        QTableView::item:selected, QTreeView::item:selected {{
            background-color: {theme.selection_bg};
            color: {theme.text};
            border-top: 2px solid {theme.selection_border};
            border-bottom: 2px solid {theme.selection_border};
        }}
        QTableView::item:selected:hover,
        QTreeView::item:selected:hover {{ background-color: {theme.selection_bg}; }}
        QTableView::item:hover, QTreeView::item:hover {{ background-color: {theme.hover}; }}
```

Nothing in packing-tool uses a tree today, so this adds rules and changes no
existing rendering there.

- [ ] **Step 2: Write the failing test for the shape painter**

In packing-tool's theme test module:

```python
from PySide6.QtCore import QRectF
from PySide6.QtGui import QImage, QPainter

from shared.theme import LIGHT_THEME, SHAPE_PX, SHAPES, paint_status_shape, status_style


def _render(shape):
    """Paint one shape on white and return the count of non-white pixels."""
    image = QImage(SHAPE_PX * 2, SHAPE_PX * 2, QImage.Format_RGB32)
    image.fill(0xFFFFFF)
    painter = QPainter(image)
    paint_status_shape(
        painter,
        QRectF(SHAPE_PX / 2, SHAPE_PX / 2, SHAPE_PX, SHAPE_PX),
        status_style("status_info", LIGHT_THEME),
        shape,
    )
    painter.end()
    return sum(
        image.pixel(x, y) & 0xFFFFFF != 0xFFFFFF
        for x in range(image.width())
        for y in range(image.height())
    )


def test_the_eight_shapes_are_named():
    assert SHAPES == (
        "ring", "half", "pause", "clock",
        "check", "bang", "slash", "tray",
    )


@pytest.mark.parametrize("shape", SHAPES)
def test_every_shape_paints_something(shape):
    assert _render(shape) > 0


def test_the_shapes_are_distinguishable():
    # Not a rendering assertion -- an ink-coverage one. Two shapes that paint
    # the identical number of pixels are the pair a supervisor cannot tell
    # apart at a glance either.
    inked = [_render(shape) for shape in SHAPES]
    assert len(set(inked)) == len(SHAPES)


def test_an_unknown_shape_falls_back_to_the_ring():
    assert _render("banana") == _render("ring")
```

- [ ] **Step 3: Run it and watch it fail**

Run, from `../packing-tool`:
`QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_theme.py -k shape -v`
Expected: FAIL, `ImportError: cannot import name 'SHAPES'`.

- [ ] **Step 4: Implement the painter**

In `../packing-tool/shared/theme.py`, directly after `paint_status_mark`:

```python
# The state shape: a 12px painted figure that names which of eight states a
# session row is in. Larger than MARK_PX because eight silhouettes have to
# separate at a glance, where two only had to differ.
#
# Painted, never a character and never an SVG -- nothing may depend on a font
# shipping a half-filled disc, and a Lucide glyph is a QIcon snapshot that
# would need re-tinting on every theme toggle.
SHAPE_PX = 12
SHAPE_STROKE = 1.5

SHAPES = ("ring", "half", "pause", "clock", "check", "bang", "slash", "tray")


def paint_status_shape(
    painter: QPainter, rect: QRectF, style: StatusStyle, shape: str
) -> None:
    """Paint one state shape into `rect`, a SHAPE_PX-square QRectF.

    `ring -> half -> check` is one progression, so not-started, working and
    done read as movement along a single form. An unknown name paints the
    ring: a session in a state this build has never heard of is exactly a
    session nothing has started on.
    """
    color = QColor(style.fg)
    pen = QPen(color)
    pen.setWidthF(SHAPE_STROKE)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    inset = SHAPE_STROKE / 2
    circle = rect.adjusted(inset, inset, -inset, -inset)
    w, h = rect.width(), rect.height()
    left, top = rect.left(), rect.top()

    if shape == "half":
        painter.drawEllipse(circle)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        # 16ths of a degree, counter-clockwise from 3 o'clock: the left half.
        painter.drawPie(circle, 90 * 16, 180 * 16)
    elif shape == "pause":
        painter.drawLine(QPointF(left + w * 0.32, top + h * 0.18),
                         QPointF(left + w * 0.32, top + h * 0.82))
        painter.drawLine(QPointF(left + w * 0.68, top + h * 0.18),
                         QPointF(left + w * 0.68, top + h * 0.82))
    elif shape == "clock":
        painter.drawEllipse(circle)
        centre = rect.center()
        painter.drawLine(centre, QPointF(centre.x(), top + h * 0.25))
        painter.drawLine(centre, QPointF(left + w * 0.75, centre.y()))
    elif shape == "check":
        painter.drawPolyline([
            QPointF(left + w * 0.18, top + h * 0.52),
            QPointF(left + w * 0.42, top + h * 0.76),
            QPointF(left + w * 0.84, top + h * 0.24),
        ])
    elif shape == "bang":
        painter.drawLine(QPointF(left + w * 0.5, top + h * 0.14),
                         QPointF(left + w * 0.5, top + h * 0.60))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(QPointF(left + w * 0.5, top + h * 0.84), 1.1, 1.1)
    elif shape == "slash":
        painter.drawEllipse(circle)
        painter.drawLine(QPointF(left + w * 0.26, top + h * 0.74),
                         QPointF(left + w * 0.74, top + h * 0.26))
    elif shape == "tray":
        painter.drawLine(QPointF(left + w * 0.12, top + h * 0.26),
                         QPointF(left + w * 0.88, top + h * 0.26))
        painter.drawPolyline([
            QPointF(left + w * 0.20, top + h * 0.46),
            QPointF(left + w * 0.20, top + h * 0.84),
            QPointF(left + w * 0.80, top + h * 0.84),
            QPointF(left + w * 0.80, top + h * 0.46),
        ])
    else:                                   # "ring", and anything unknown
        painter.drawEllipse(circle)

    painter.restore()
```

`QPointF` must be in the `PySide6.QtCore` import at the top of the module; add
it if it is not there.

- [ ] **Step 5: Run it and watch it pass**

Run, from `../packing-tool`:
`QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_theme.py -k shape -v`
Expected: all pass. If `test_the_shapes_are_distinguishable` fails, two shapes
happen to ink the same pixel count — nudge one geometry constant, do not delete
the test.

- [ ] **Step 6: Commit in packing-tool, on its own branch and PR**

```bash
cd ../packing-tool
git checkout -b shared-tree-selectors-and-status-shapes
git add shared/theme.py tests/test_theme.py
git commit -m "shared: QTreeView selection rules and the eight state shapes"
git push -u origin shared-tree-selectors-and-status-shapes
```

Open a PR there. Follow packing-tool's own CLAUDE.md for its gate.

- [ ] **Step 7: Sync into this repo and commit the result**

From this repo's worktree root. The sibling default resolves to
`.claude/worktrees/packing-tool`, which does not exist, so the path is
required:

```bash
.venv/bin/python scripts/sync_shared.py /home/cognitiveghost/Desktop/Projects/packing-tool
git add shared/
git commit -m "9.19: sync shared -- QTreeView rules and paint_status_shape"
```

- [ ] **Step 8: Confirm the sync landed**

Run: `.venv/bin/python -c "from shared.theme import SHAPES; print(SHAPES)"`
Expected: the eight names.

---

## Task 5: The selection ring survives a tree

**Files:**
- Modify: `gui/selection_ring.py:60-62`
- Test: `tests/test_selection_ring.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `header_of(option)` now returns the header of a `QTreeView` too.

Read spec §7.1. This is the half of the ring that lives in this repo. Without
it, `caps()` returns `(False, False)` on every tree cell and both end caps
vanish with no error.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_selection_ring.py`:

```python
from PySide6.QtWidgets import QStyleOptionViewItem, QTreeWidget

from gui.selection_ring import caps, header_of


class _Option:
    """A QStyleOptionViewItem carries `widget`; this is the part caps() reads."""

    def __init__(self, widget):
        self.widget = widget


def test_header_of_finds_a_tree_header(qtbot):
    tree = QTreeWidget()
    tree.setColumnCount(3)
    assert header_of(_Option(tree)) is tree.header()


def test_a_tree_still_gets_both_end_caps(qtbot):
    tree = QTreeWidget()
    tree.setColumnCount(3)
    assert caps(header_of(_Option(tree)), 0) == (True, False)
    assert caps(header_of(_Option(tree)), 2) == (False, True)
    assert caps(header_of(_Option(tree)), 1) == (False, False)


def test_a_widget_with_neither_header_is_still_none():
    assert header_of(_Option(object())) is None
```

If `tests/test_selection_ring.py` has no `qtbot` fixture in use, check how its
existing tests obtain a `QApplication` and follow that instead — do not add
`pytest-qt` if the file does not already use it.

- [ ] **Step 2: Run it and watch it fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_selection_ring.py -k tree -v`
Expected: FAIL — `header_of` returns `None`, so the first assert fails.

- [ ] **Step 3: Implement it**

Replace `header_of` in `gui/selection_ring.py`:

```python
def header_of(option):
    """The header behind this cell, or None for a view that has none.

    A QTableView calls it horizontalHeader() and a QTreeView calls it
    header(); the QHeaderView they return is the same class, and caps() only
    reads count(), logicalIndex() and isSectionHidden(). Bundle 6 turned the
    Session Browser into a tree, and without this branch the ring's two end
    caps disappeared silently -- caps() returned (False, False) for every
    column and nothing raised.
    """
    widget = option.widget
    if hasattr(widget, "horizontalHeader"):
        return widget.horizontalHeader()
    if hasattr(widget, "header"):
        return widget.header()
    return None
```

- [ ] **Step 4: Run it and watch it pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_selection_ring.py tests/test_selection_ring_renders.py -v`
Expected: all pass, the pre-existing table tests included.

- [ ] **Step 5: Commit**

```bash
.venv/bin/ruff check gui/selection_ring.py tests/test_selection_ring.py
git add gui/selection_ring.py tests/test_selection_ring.py
git commit -m "9.19: the selection ring finds a tree's header too"
```

---

## Task 6: The status cell paints a shape

**Files:**
- Modify: `gui/session_row_delegates.py`
- Test: `tests/test_status_channels.py`

**Interfaces:**
- Consumes: `SHAPE_PX`, `paint_status_shape` from `shared.theme` (Task 4);
  `DISPLAY_STATUSES` from `shopify_tool.session_lifecycle` (Task 2).
- Produces: `STATE_STYLES: dict[str, tuple[str, bool, str]]` keyed by display
  status, values `(role, live, shape)`. `ROLE_TOKEN` and `ROLE_LIVE` stay;
  `ROLE_SHAPE = Qt.UserRole + 2` replaces `ROLE_MANUAL`, which is deleted.

Read spec §5. Shape replaces the mark **in this cell only** — `StatusChip`
elsewhere keeps its authorship mark and is not touched.

- [ ] **Step 1: Write the failing tests**

Replace the body of `tests/test_status_channels.py` (it currently asserts the
four-entry `STATUS_ROLES`):

```python
import pytest

from gui.session_row_delegates import STATE_STYLES
from shared.theme import DARK_THEME, LIGHT_THEME, SHAPES, status_style
from shopify_tool.session_lifecycle import DISPLAY_STATUSES


def test_every_display_status_has_a_style():
    assert tuple(STATE_STYLES) == DISPLAY_STATUSES


def test_the_table_is_exactly_the_spec_table():
    assert STATE_STYLES == {
        "not_started": ("text_secondary", False, "ring"),
        "in_progress": ("status_info", True, "half"),
        "paused": ("status_warning", True, "pause"),
        "stale": ("status_warning", True, "clock"),
        "completed": ("status_success", False, "check"),
        "incomplete": ("status_warning", True, "bang"),
        "abandoned": ("status_danger", False, "slash"),
        "archived": ("text_secondary", False, "tray"),
    }


@pytest.mark.parametrize("state", DISPLAY_STATUSES)
@pytest.mark.parametrize("theme", [LIGHT_THEME, DARK_THEME])
def test_every_role_resolves_in_both_themes(state, theme):
    role, live, _shape = STATE_STYLES[state]
    style = status_style(role, theme, live=live)
    assert style.fg
    assert (style.fill is not None) is live


@pytest.mark.parametrize("state", DISPLAY_STATUSES)
def test_every_shape_is_one_shared_knows(state):
    assert STATE_STYLES[state][2] in SHAPES


def test_the_two_hard_pairs_differ_on_more_than_hue():
    # Active vs Completed: the common terminal state recedes.
    assert STATE_STYLES["in_progress"][1] is True
    assert STATE_STYLES["completed"][1] is False
    # Incomplete vs Abandoned: different role, different shape, and only one
    # of them is still live.
    assert STATE_STYLES["incomplete"][0] != STATE_STYLES["abandoned"][0]
    assert STATE_STYLES["incomplete"][2] != STATE_STYLES["abandoned"][2]
    assert STATE_STYLES["incomplete"][1] != STATE_STYLES["abandoned"][1]


def test_no_two_states_share_a_shape():
    shapes = [shape for _role, _live, shape in STATE_STYLES.values()]
    assert len(set(shapes)) == len(shapes)


def test_role_manual_is_gone():
    # Shape carries the state; authorship is constant per state and rides in
    # the table above. status_manually_set keeps its real job of stopping
    # session_lifecycle, and is no longer drawn.
    import gui.session_row_delegates as delegates

    assert not hasattr(delegates, "ROLE_MANUAL")
```

- [ ] **Step 2: Run them and watch them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_status_channels.py -v`
Expected: FAIL, `ImportError: cannot import name 'STATE_STYLES'`.

- [ ] **Step 3: Replace `STATUS_ROLES` with `STATE_STYLES`**

In `gui/session_row_delegates.py`, replace the roles block:

```python
# Item-data roles. Qt.UserRole itself is already taken on this tree: column 0
# carries the session path, column 6 the packing ratio.
ROLE_TOKEN = Qt.UserRole + 1     # str -- theme token name for the state
ROLE_SHAPE = Qt.UserRole + 2     # str -- which of SHAPES to paint
ROLE_LIVE = Qt.UserRole + 3      # bool -- someone still has to act

# 9.3 §3.5: live-ness is data about a state, so it rides with the role rather
# than in a second table keyed by the same thing. 9.19 adds the fourth channel
# on the same argument -- shape names the state, and authorship, which is
# constant per state, folds in here rather than being drawn.
#
# (role, live, shape), keyed by session_lifecycle.DISPLAY_STATUSES.
STATE_STYLES: dict[str, tuple[str, bool, str]] = {
    "not_started": ("text_secondary", False, "ring"),
    "in_progress": ("status_info", True, "half"),
    "paused": ("status_warning", True, "pause"),
    "stale": ("status_warning", True, "clock"),
    "completed": ("status_success", False, "check"),
    "incomplete": ("status_warning", True, "bang"),
    "abandoned": ("status_danger", False, "slash"),
    "archived": ("text_secondary", False, "tray"),
}

# What an unrecognised state paints: the ring, untinted, in the secondary
# colour. A state this build has never heard of is not an emergency.
UNKNOWN_STATE = ("text_secondary", False, "ring")
```

Delete `ROLE_MANUAL` entirely.

- [ ] **Step 4: Paint the shape instead of the mark**

In `SessionStatusDelegate.paint`, change the import line at the top of the
module from

```python
from shared.theme import MARK_LEFT_PX, MARK_PX, paint_status_mark, status_style
```

to

```python
from shared.theme import MARK_LEFT_PX, SHAPE_PX, paint_status_shape, status_style
```

and inside `paint`, replace the `status_style(...)` call and the
`paint_status_mark(...)` call:

```python
        status = status_style(
            role,
            get_theme_manager().get_current_theme(),
            live=bool(index.data(ROLE_LIVE)),
        )
```

```python
        label_left = MARK_LEFT_PX + SHAPE_PX + 4
```

```python
        paint_status_shape(
            painter,
            QRectF(
                pill.left() + MARK_LEFT_PX,
                pill.center().y() - SHAPE_PX / 2,
                SHAPE_PX,
                SHAPE_PX,
            ),
            status,
            index.data(ROLE_SHAPE) or "ring",
        )
```

Update the class docstring: colour is the role, fill is live-vs-resting, and
shape names the state; authorship is no longer drawn here.

- [ ] **Step 5: Run them and watch them pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_status_channels.py -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
.venv/bin/ruff check gui/session_row_delegates.py tests/test_status_channels.py
git add gui/session_row_delegates.py tests/test_status_channels.py
git commit -m "9.19: shape is the fourth channel -- eight states, eight silhouettes"
```

`tests/test_session_browser_1e.py` still imports `STATUS_ROLES` and will fail
from here until Task 7. That is expected; do not patch it in this task.

---

## Task 7: The table becomes a tree

**Files:**
- Modify: `gui/session_browser_widget.py`
- Test: `tests/test_session_browser_1e.py`, `tests/test_session_browser_columns.py`

**Interfaces:**
- Consumes: everything from Tasks 1–3 and 6.
- Produces: `SessionBrowserWidget.sessions_tree` (a `QTreeWidget`) replacing
  `sessions_table`; `GROUP_ATTENTION = "Needs attention"`,
  `GROUP_REST = "Everything else"`; `_session_items()` yielding every child
  item, and `_selected_session_paths()` unchanged in signature.

Read spec §6 and §7. This is the largest task; it is one task because the
column change and the tree change cannot be tested apart.

- [ ] **Step 1: Write the failing tests**

Replace the column assertions in `tests/test_session_browser_columns.py` and
add to it:

```python
from shopify_tool.session_lifecycle import display_status

HEADERS = ["Session", "Age", "Status", "Orders", "Items",
           "Blocked", "Packing", "Comment"]


def test_the_eight_headers(browser):
    tree = browser.sessions_tree
    assert tree.columnCount() == 8
    assert [tree.headerItem().text(c) for c in range(8)] == HEADERS


def test_packing_lists_count_is_gone(browser):
    # It was the denominator of Packing. One fact, one column.
    assert "Packing Lists" not in [
        browser.sessions_tree.headerItem().text(c) for c in range(8)
    ]


def test_two_groups_in_order(browser, two_group_sessions):
    browser.sessions_data = two_group_sessions
    browser._populate_tree()
    tree = browser.sessions_tree
    assert tree.topLevelItemCount() == 2
    assert tree.topLevelItem(0).text(0).startswith("Needs attention")
    assert tree.topLevelItem(1).text(0).startswith("Everything else")


def test_an_empty_group_is_hidden(browser, calm_sessions):
    browser.sessions_data = calm_sessions
    browser._populate_tree()
    assert browser.sessions_tree.topLevelItemCount() == 1
    assert browser.sessions_tree.topLevelItem(0).text(0).startswith("Everything else")


def test_blocked_is_blank_at_zero_and_at_none(browser, calm_sessions):
    browser.sessions_data = calm_sessions
    browser._populate_tree()
    item = browser.sessions_tree.topLevelItem(0).child(0)
    assert item.text(5) == ""


def test_the_comment_column_carries_the_text(browser, commented_session):
    browser.sessions_data = [commented_session]
    browser._populate_tree()
    item = browser.sessions_tree.topLevelItem(0).child(0)
    assert item.text(7) == commented_session["comments"]


def test_the_name_cell_has_no_icon(browser, commented_session):
    browser.sessions_data = [commented_session]
    browser._populate_tree()
    item = browser.sessions_tree.topLevelItem(0).child(0)
    assert item.icon(0).isNull()
```

Build `two_group_sessions`, `calm_sessions` and `commented_session` as fixtures
in the same file, following the shape the existing fixtures in
`tests/test_session_browser_1e.py` use. Each is a list of entry dicts with
`session_name`, `status`, `created_at`, `statistics`, `packing_progress` and
`comments` — the same shape `list_client_sessions` returns.

- [ ] **Step 2: Run them and watch them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_session_browser_columns.py -v`
Expected: FAIL — `sessions_tree` does not exist.

- [ ] **Step 3: Swap the widget and the columns**

In `_init_ui`, replace the `QTableWidget` block. Imports change:
`QTableWidget`/`QTableWidgetItem` out, `QTreeWidget`/`QTreeWidgetItem` in.

```python
        self.sessions_tree = QTreeWidget()
        self.sessions_tree.setColumnCount(8)
        self.sessions_tree.setHeaderLabels(
            ["Session", "Age", "Status", "Orders", "Items",
             "Blocked", "Packing", "Comment"]
        )
        self.sessions_tree.setSelectionBehavior(QTreeWidget.SelectRows)
        self.sessions_tree.setSelectionMode(QTreeWidget.ExtendedSelection)
        self.sessions_tree.setEditTriggers(QTreeWidget.NoEditTriggers)
        self.sessions_tree.setRootIsDecorated(False)   # groups, not a hierarchy
        self.sessions_tree.setUniformRowHeights(True)
        self.sessions_tree.setSortingEnabled(True)
        self.sessions_tree.doubleClicked.connect(self._on_session_double_clicked)

        self.sessions_tree.setItemDelegateForColumn(2, SessionStatusDelegate(self))
        self.sessions_tree.setItemDelegateForColumn(6, PackingProgressDelegate(self))
        self.sessions_tree.setItemDelegate(SelectionRingDelegate(self))

        header = self.sessions_tree.header()
        for column, width in ((1, 90), (2, 140), (3, 80), (4, 80),
                              (5, 80), (6, 130), (7, 200)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            header.resizeSection(column, width)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
```

`get_density_profile().row_height` was set on the vertical header, which a tree
does not have. Set it with `setUniformRowHeights(True)` plus a
`QTreeWidget.setStyleSheet`-free approach: give the tree
`self.sessions_tree.setIndentation(0)` and leave row height to the density
profile's font, keeping the existing `ponytail:` note about the missing
`density_changed` signal.

Rename `_RatioSortItem` to subclass `QTreeWidgetItem` and compare on
`data(6, Qt.UserRole)`:

```python
class _SessionItem(QTreeWidgetItem):
    """Sorts Packing on the ratio behind "packed/total", not on its text.

    QTreeWidgetItem compares its DisplayRole, so the plain text form puts
    "10/12" above "2/3".
    """

    def __lt__(self, other):
        column = self.treeWidget().sortColumn() if self.treeWidget() else 0
        if column == 6:
            return (self.data(6, Qt.UserRole) or -1.0) < (other.data(6, Qt.UserRole) or -1.0)
        return self.text(column) < other.text(column)
```

- [ ] **Step 4: Rewrite `_populate_table` as `_populate_tree`**

Keep the existing filtering block (archived visibility, search, the count on
the filter bar) verbatim — only the building changes:

```python
    def _populate_tree(self):
        ...  # the existing visibility + search filtering, unchanged
        now = datetime.now().astimezone()
        header = self.sessions_tree.header()
        sort_column = header.sortIndicatorSection()
        sort_order = header.sortIndicatorOrder()
        self.sessions_tree.setSortingEnabled(False)
        self.sessions_tree.clear()

        attention = QTreeWidgetItem([GROUP_ATTENTION])
        rest = QTreeWidgetItem([GROUP_REST])
        for group in (attention, rest):
            group.setFlags(Qt.ItemIsEnabled)      # a group is not selectable
            group.setFirstColumnSpanned(True)

        for session_info in visible_sessions:
            state = display_status(session_info, now)
            blocked = blocked_orders(session_info)
            item = self._build_row(session_info, state, blocked, now)
            parent = attention if needs_attention(state, blocked) else rest
            parent.addChild(item)

        for group in (attention, rest):
            if group.childCount():
                group.setText(0, f"{group.text(0)}  {group.childCount()}")
                self.sessions_tree.addTopLevelItem(group)
                group.setExpanded(True)

        self.sessions_tree.setSortingEnabled(True)
        if sort_column < 0:
            sort_column, sort_order = 1, Qt.DescendingOrder
        self.sessions_tree.sortItems(sort_column, sort_order)
        self._update_archive_footer()
        self._update_empty_state()
```

`_build_row` carries the per-column work:

```python
    def _build_row(self, session_info, state, blocked, now):
        stats = session_info.get("statistics", {})
        comments = session_info.get("comments", "")
        item = _SessionItem()
        theme = get_theme_manager().get_current_theme()

        item.setText(0, session_info.get("session_name", ""))
        item.setData(0, Qt.UserRole, session_info.get("session_path", ""))

        created = parse_created_at(session_info.get("created_at"))
        age_cell, age_tip = age_label(created, now)
        item.setText(1, age_cell)
        if "archives in" in age_cell:
            item.setForeground(1, QColor(theme.status_warning))

        role, live, shape = STATE_STYLES.get(state, UNKNOWN_STATE)
        item.setText(2, state.replace("_", " ").capitalize())
        item.setData(2, ROLE_TOKEN, role)
        item.setData(2, ROLE_LIVE, live)
        item.setData(2, ROLE_SHAPE, shape)

        orders = stats.get("total_orders", 0)
        items = stats.get("total_items", 0)
        item.setText(3, str(orders) if orders else "N/A")
        item.setText(4, str(items) if items else "N/A")

        # Blank at zero and at None, so the column reads as a list of
        # exceptions rather than a field of noughts.
        item.setText(5, str(blocked) if blocked else "")
        if blocked:
            item.setForeground(5, QColor(theme.status_warning))

        packed, total = packing_completion(session_info)
        item.setText(6, f"{packed}/{total}" if total else "—")
        item.setData(6, Qt.UserRole, packed / total if total else -1.0)

        item.setText(7, comments)

        for column in (3, 4, 5, 6):
            item.setTextAlignment(column, Qt.AlignCenter)

        blocked_line = (
            f"{blocked} of {orders} orders cannot be fulfilled"
            if blocked else "No blocked orders"
        )
        tooltip = "\n".join([
            session_info.get("session_name", ""),
            age_tip,
            f"Status: {item.text(2)}",
            f"Orders: {orders if orders else 'N/A'}",
            f"Items: {items if items else 'N/A'}",
            blocked_line,
            f"Packed: {packed}/{total} lists completed in Packing Tool",
            f"Comment: {comments or 'None'}",
        ])
        for column in range(8):
            item.setToolTip(column, tooltip)

        # Abandoned recedes: the system concluded it, it is over. Incomplete
        # stays full strength -- someone can still finish it.
        if state == "abandoned":
            for column in (0, 1, 3, 4, 6, 7):
                item.setForeground(column, QColor(theme.text_secondary))
        return item
```

Add the imports this needs: `QColor` from `PySide6.QtGui`,
`get_theme_manager` (already imported for the density profile — check), and
from `shopify_tool.session_lifecycle`: `age_label`, `blocked_orders`,
`display_status`, `needs_attention`, `packing_completion`, `parse_created_at`.

- [ ] **Step 5: Follow the rename through every caller**

Every `self.sessions_table` reference becomes `self.sessions_tree`, and the
table-only APIs change:

| Was | Becomes |
|---|---|
| `.setRowCount(0)` | `.clear()` |
| `.item(row, 0)` | the `QTreeWidgetItem` itself |
| `.currentRow()` | `.currentItem()` |
| `selectionModel().selectedRows()` | `.selectedItems()`, filtered to items with a parent |
| `.rowCount()` | `sum(g.childCount() for g in groups)` |

`_selected_session_paths` becomes:

```python
    def _selected_session_paths(self) -> list[str]:
        """Session paths for every selected row, in tree order.

        Group headings are ItemIsEnabled-only so they never enter a
        selection, but filtering on `parent()` keeps that a property of this
        method rather than of a flag somewhere else.
        """
        return [
            item.data(0, Qt.UserRole)
            for item in self.sessions_tree.selectedItems()
            if item.parent() is not None and item.data(0, Qt.UserRole)
        ]
```

Delete `_refresh_comment_icons` and the `on_theme_changed(self, ...)` call that
exists only to drive it — the comment icon is gone, so nothing in this widget
is a theme snapshot any more.

- [ ] **Step 6: Run the whole browser suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_session_browser_columns.py tests/test_session_browser_1e.py tests/test_session_browser_reload.py tests/test_session_browser_lifecycle_sync.py -v`
Expected: all pass. `test_session_browser_1e.py` needs updating for
`sessions_tree` and `STATE_STYLES` — do it here, keeping every behaviour it
asserts, changing only how it reaches the widget.

- [ ] **Step 7: Commit**

```bash
.venv/bin/ruff check gui/session_browser_widget.py tests/
git add gui/session_browser_widget.py tests/
git commit -m "9.19: two groups, eight columns, one tree"
```

---

## Task 8: The two empty states

**Files:**
- Modify: `gui/session_browser_widget.py`
- Test: `tests/test_session_browser_columns.py`

**Interfaces:**
- Consumes: `StatePanel` from `gui.components` (9.6).
- Produces: `SessionBrowserWidget._update_empty_state()`, and
  `_empty_reason()` returning `None`, `"nothing"` or `"filtered"`.

Read spec §8. Copy is fixed by the spec: no apologies, no exclamation marks,
each panel names its cause and offers the action that clears it.

- [ ] **Step 1: Write the failing tests**

```python
def test_no_sessions_at_all_offers_a_new_session(browser):
    browser.current_client_id = "M"
    browser.sessions_data = []
    browser._populate_tree()
    assert browser._empty_reason() == "nothing"
    assert not browser.sessions_tree.isVisible()
    assert browser.empty_panel.button.text() == "New session"


def test_a_filter_that_hides_everything_offers_to_clear_it(browser, calm_sessions):
    browser.sessions_data = calm_sessions
    browser.filter_bar.search_field.setText("tuesday")
    browser._populate_tree()
    assert browser._empty_reason() == "filtered"
    assert browser.empty_panel.button.text() == "Clear filters"


def test_clearing_the_filters_brings_the_rows_back(browser, calm_sessions):
    browser.sessions_data = calm_sessions
    browser.filter_bar.search_field.setText("tuesday")
    browser._populate_tree()
    browser.empty_panel.button.click()
    assert browser.filter_bar.search_field.text() == ""
    assert browser._empty_reason() is None
    assert browser.sessions_tree.isVisible()


def test_rows_present_means_no_panel(browser, calm_sessions):
    browser.sessions_data = calm_sessions
    browser._populate_tree()
    assert browser._empty_reason() is None
    assert browser.empty_panel is None or not browser.empty_panel.isVisible()
```

Assert on `StatePanel.button.text()` and on which widget is visible. Do not
assert on the card's internal label widgets — `StatePanel` builds them through
`Card.add_text` and the spec that owns their structure is Bundle 3's, not this
one.

- [ ] **Step 2: Run them and watch them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_session_browser_columns.py -k empty -v`
Expected: FAIL — `_empty_reason` does not exist.

- [ ] **Step 3: Implement**

A `QStackedLayout` is not needed: the tree and the panel are siblings in the
same `QVBoxLayout`, and exactly one is visible.

```python
    def _empty_reason(self):
        """None, "nothing" or "filtered" -- why the tree has no rows.

        "filtered" is not "nothing": one is a filter the user can widen, the
        other is a client with no sessions on the server. A panel that cannot
        tell them apart is the "No data - Nothing to display" this phase
        deleted.
        """
        if any(g.childCount() for g in self._groups()):
            return None
        return "filtered" if self.sessions_data else "nothing"

    def _update_empty_state(self):
        reason = self._empty_reason()
        if self.empty_panel is not None:
            self.empty_panel.deleteLater()
            self.empty_panel = None
        self.sessions_tree.setVisible(reason is None)
        if reason is None:
            return

        if reason == "nothing":
            panel = StatePanel(
                "No sessions yet",
                f"CLIENT_{self.current_client_id} has no sessions on the file server.",
                action_text="New session",
            )
            panel.button.clicked.connect(self.new_session_requested.emit)
        else:
            panel = StatePanel(
                "No sessions match",
                self._filter_sentence(),
                action_text="Clear filters",
                action_role="secondary",
            )
            panel.button.clicked.connect(self._clear_filters)

        self.empty_panel = panel
        self.main_layout.insertWidget(1, panel, 1)

    def _filter_sentence(self) -> str:
        """Names both live filters, and drops the half that is not set."""
        status = self.status_filter.currentText()
        search = self.filter_bar.search_field.text().strip()
        noun = "session" if status == "All" else f"{status} session"
        if search:
            return f'No {noun} matches "{search}".'
        return f"No {noun} is visible with the current filters."

    def _clear_filters(self):
        self.filter_bar.search_field.clear()
        self.status_filter.setCurrentText("All")
        self._show_archived = False
        self.refresh_sessions()
```

Add `self.empty_panel = None` and keep a reference to the main layout as
`self.main_layout` in `_init_ui`. Add the signal
`new_session_requested = Signal()` beside the two that exist, and wire it in
`gui/ui_manager.py` (or wherever the browser is constructed) to whatever
already opens session setup — grep for `session_selected.connect` to find the
one place that owns those connections.

- [ ] **Step 4: Run them and watch them pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_session_browser_columns.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
.venv/bin/ruff check gui/ tests/
git add gui/ tests/
git commit -m "9.19: two empty states that name their cause"
```

---

## Task 9: Archive becomes a footer line

**Files:**
- Modify: `gui/session_browser_widget.py`
- Test: `tests/test_session_browser_columns.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `SessionBrowserWidget.archive_line` (a `QWidget` holding a label
  and a ghost `QPushButton`), `_update_archive_footer()`.
  `show_archived_btn` is deleted.

Read spec §9. Archive stops competing with the two real filters.

- [ ] **Step 1: Write the failing tests**

```python
def test_no_archived_sessions_means_no_line(browser, calm_sessions):
    browser.sessions_data = calm_sessions
    browser._populate_tree()
    assert not browser.archive_line.isVisible()


def test_the_line_counts_the_archived_sessions(browser, sessions_with_archived):
    browser.sessions_data = sessions_with_archived
    browser._populate_tree()
    assert browser.archive_line.isVisible()
    assert browser.archive_count.text() == "3 archived"
    assert browser.archive_toggle.text() == "Show"


def test_showing_them_flips_the_verb_and_keeps_the_count(browser, sessions_with_archived):
    browser.sessions_data = sessions_with_archived
    browser._populate_tree()
    browser.archive_toggle.click()
    assert browser.archive_toggle.text() == "Hide"
    assert browser.archive_count.text() == "3 archived"


def test_the_old_toggle_button_is_gone(browser):
    assert not hasattr(browser, "show_archived_btn")
```

- [ ] **Step 2: Run them and watch them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_session_browser_columns.py -k archive -v`
Expected: FAIL — `archive_line` does not exist.

- [ ] **Step 3: Implement**

Delete `show_archived_btn` and its `filter_layout.addWidget` call. After the
tree, before the selection bar:

```python
        # Archive is a footer, not a third filter. It reports a fact about
        # what is hidden and offers to unhide it; the two controls above
        # narrow what is shown. Different jobs, different bands of chrome.
        self.archive_line = QWidget(self)
        archive_layout = QHBoxLayout(self.archive_line)
        archive_layout.setContentsMargins(0, 0, 0, 0)
        archive_layout.setSpacing(8)
        self.archive_count = QLabel("")
        self.archive_count.setStyleSheet(font_css("caption"))
        self.archive_toggle = QPushButton("Show")
        set_button_role(self.archive_toggle, "ghost")
        self.archive_toggle.clicked.connect(self._on_show_archived_toggled)
        archive_layout.addWidget(self.archive_count)
        archive_layout.addWidget(self.archive_toggle)
        archive_layout.addStretch(1)
        self.archive_line.setVisible(False)
        main_layout.addWidget(self.archive_line)
```

```python
    def _update_archive_footer(self):
        archived = sum(
            1 for s in self.sessions_data if s.get("status") == "archived"
        )
        showing_archived_explicitly = (
            self.status_filter.currentText().lower() == "archived"
        )
        self.archive_line.setVisible(
            bool(archived) and not showing_archived_explicitly
        )
        noun = "archived"
        self.archive_count.setText(f"{archived} {noun}")
        self.archive_toggle.setText("Hide" if self._show_archived else "Show")

    def _on_show_archived_toggled(self):
        """Re-filters the already-loaded self.sessions_data -- no new
        file-server call, since the whole index is already in memory."""
        self._show_archived = not self._show_archived
        self._populate_tree()
```

`_on_show_archived_toggled` no longer takes a `checked` argument; the old
`toggled` connection is gone with the button.

- [ ] **Step 4: Run them and watch them pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_session_browser_columns.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
.venv/bin/ruff check gui/ tests/
git add gui/ tests/
git commit -m "9.19: archive is a footer line, not a third filter"
```

---

## Task 10: Glossary, graph, and the gate

**Files:**
- Modify: `CONTEXT.md`

- [ ] **Step 1: Add the three terms**

Under **Status and selection**, amend the `Channel` entry to name four
channels, and add after `Mark`:

```markdown
**Shape** — the painted figure inside a session row's status cell, one per
state. Never a **glyph**, which is a vendored Lucide drawing, and never a
character. Where a screen shows eight states, shape replaces the **mark**:
authorship is constant per state and rides in the state table, so nothing is
lost by not drawing it.
```

Add a new section after **Session setup**:

```markdown
## Sessions

**Blocked order** — an order this session cannot fulfil, counted as
`blocked_orders`. One number, one name: `SHORT ON STOCK` and `BLK` are both
retired. `not_fulfillable_orders` stays the persisted key, because it is a
file shared with another tool.

**Display status** — one of the eight states a session row shows, derived from
the four stored statuses plus packing progress and idle time. Distinguished
from **stored status**, the four values `SessionManager.VALID_STATUSES`
accepts and a person can set.
```

- [ ] **Step 2: Run the whole gate**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest
.venv/bin/ruff check .
```

Expected: no failures, no lint findings, and a total at or above the 1261
baseline.

- [ ] **Step 3: Update the knowledge graph**

```bash
graphify update .
```

- [ ] **Step 4: Commit and push**

```bash
git add CONTEXT.md graphify-out/
git commit -m "9.19: shape, blocked order, display status"
git push -u origin worktree-phase9-bundle6-session-browser
```

- [ ] **Step 5: Check the screen by hand**

```bash
QT_QPA_PLATFORM=xcb .venv/bin/python run_dev.py
```

Confirm, on the Sessions screen: both groups render with their counts; the
selection ring closes on both ends of a selected row (this is the Task 5
regression — if the ring is open, the sync in Task 4 did not land); Blocked is
blank on unblocked rows; an abandoned row's text is dimmer than an incomplete
one's; and both themes look right.

---

## Self-review

**Spec coverage:** §2/§3 → Task 1. §4 → Task 2. §5 → Tasks 4, 6. §6 → Task 7.
§6.1 → Task 3 + Task 7. §6.2, §6.3 → Task 7. §7 → Tasks 3, 7. §7.1 → Tasks 4,
5. §8 → Task 8. §9 → Task 9. §10 → Tasks 4–7. §11 → Task 10. §12 is a record,
not work. §13 is the open list.

**Names used consistently across tasks:** `blocked_orders`, `display_status`,
`needs_attention`, `age_label`, `DISPLAY_STATUSES`, `STALE_AFTER_DAYS`,
`ARCHIVE_WARNING_DAYS`, `SHAPES`, `SHAPE_PX`, `paint_status_shape`,
`STATE_STYLES`, `UNKNOWN_STATE`, `ROLE_TOKEN`, `ROLE_SHAPE`, `ROLE_LIVE`,
`sessions_tree`, `_populate_tree`, `_build_row`, `_empty_reason`,
`_update_empty_state`, `_update_archive_footer`, `archive_line`,
`archive_count`, `archive_toggle`.

**Deleted, deliberately:** `STATUS_ROLES`, `ROLE_MANUAL`, `_RatioSortItem`,
`_populate_table`, `_refresh_comment_icons`, `show_archived_btn`, the
`Packing Lists` column, and the `message-square` icon on the name cell.

**Known ordering constraint:** Task 6 leaves `tests/test_session_browser_1e.py`
red until Task 7 updates it. Tasks 6 and 7 must land in that order, and the
full gate is only expected green from Task 7 onward.
