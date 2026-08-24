# Session Browser: packing completion, auto-complete, auto-archive

Date: 2026-08-24
Roadmap item: Todoist `6h8v4VvC2G5XjrqV` (Phase 7, last subtask)
Status: design approved, ready for implementation plan

## The problem, as measured

The roadmap item asks for three things: review statuses/stats/comments, add a
column reflecting Packing Tool integration, and auto-archive sessions older
than 30 days. Two of the three premises turned out to be different from how
they read. All numbers below come from the 42 real sessions in `dev-server/`,
not from reasoning about the code.

**The status field is dead in practice.** 41 of 42 sessions are `active`; one
is `completed`. Nothing ever advances it, because advancing it is a manual
combobox edit nobody makes. Comments are used by 0 of 42. That is the real
complaint behind "review statuses/stats/comments".

**The cross-repo plumbing already exists.** `packing_progress` — written by
packing-tool's `update_session_metadata()` (`src/session_manager.py:670`) and
extended with `completed_orders` in packing-tool PR #160 — already flows into
the per-client `session_index.json` and out through
`SessionManager.list_client_sessions()`. `_index_is_stale()` was written
specifically to notice packing-tool's writes. There is no new file, no new
writer, and no new transport in this design. The work is derivation and
display.

**The existing 30-day filter is a no-op on every session that exists.**
`created_at` only became timezone-aware on 2026-07-27 (commit `9386652`,
PR #253). Every session created before that is naive, and
`filter_sessions_by_age` deliberately *keeps* rows it cannot compare. The
30-day cutoff today is **2026-07-25 — two days before that fix**. So the
entire population old enough to archive is exactly the population with
unparsable timestamps. An auto-archive that skipped naive stamps would archive
nothing at all on its first run, forever appearing broken.

## Decisions taken (do not re-litigate)

Settled with the user on 2026-08-24:

1. **Derived column *and* auto-advance status.** Add a read-only `Packing`
   column showing `packed/total`, and automatically flip `active` →
   `completed` when every packing list is done.
2. **Archive in place, naive timestamps read as local time.** Set
   `status: "archived"`; do not move directories. Interpreting naive stamps as
   local is what makes the backlog archivable.
3. **Functional scope only.** Presentation rework of statuses/stats/comments is
   deliberately left to the Phase 8 UI/UX redesign (Todoist `6hM87j3HVcc576vV`,
   re-sequenced to run after Phase 7). Nothing built here should be visual work
   that redesign would discard.

Auto-advancing `status` is safe: `grep` confirms **nothing outside the Session
Browser reads it** — not reports, not repeat detection, not session loading. It
is purely an organisational field.

## The trap: `full_session`

Both tools derive a packing-list key from the same place — the `.json` file
stem (`packing_list_path.stem` in packing-tool `src/main.py:2243`, versus
`glob("*.json")` stems in `calculate_session_statistics`). All 42 sessions
agree exactly, so no normalisation is needed.

But packing-tool's whole-session mode writes the literal key `"full_session"`
(`src/main.py:2249`), which can never equal any list's stem. **Two of the 29
sessions carrying `packing_progress` already use it.** A naive "are all the
packing lists completed?" check scores those sessions `0/N` forever, even
though every order in them was packed.

So `full_session`, when completed, counts as covering the whole session. The
prototype confirms both live cases behave: `2026-07-25_1` (full_session
completed) reads `1/1` fully packed; `2026-07-01_2` (full_session present but
not completed) correctly reads `0/1`.

## Design

### New module: `shopify_tool/session_lifecycle.py`

Pure functions over the entry dicts `list_client_sessions()` already returns.
No I/O, no Qt, no pandas — which is what makes the rules testable without a
file server or a `QApplication`.

```python
FULL_SESSION_KEY = "full_session"
AUTO_ARCHIVE_AFTER_DAYS = 30

def packing_completion(entry) -> tuple[int, int]:
    """(packed, total) packing lists. total == 0 means nothing to pack."""

def is_fully_packed(entry) -> bool:
    """True only when total > 0 and every list is completed."""

def parse_created_at(value) -> datetime | None:
    """ISO string -> aware datetime, or None. Naive stamps are local time."""

def derive_status_updates(entries, now) -> dict[str, str]:
    """{session_name: new_status} for the sessions that should change."""
```

`parse_created_at` is a single `.astimezone()` call with no branch: on a naive
datetime Python attaches the local offset (DST-correctly), and on an
already-aware one it preserves the instant. Verified both ways.

Only `status == "completed"` in a `packing_progress` block counts as packed;
`in_progress` and `paused` do not. The denominator is the lists actually on
disk, so a key in `packing_progress` with no matching file is ignored rather
than allowed to block completion.

### Rules in `derive_status_updates`

- Skip any entry with `status_manually_set` (see below).
- **Auto-complete:** `active` → `completed` when `is_fully_packed(entry)`.
  A session with zero packing lists is never auto-completed — vacuous truth
  would mark all 9 empty sessions complete.
- **Auto-archive:** `active` or `completed` → `archived` when
  `created_at` is older than 30 days. Applied to those two statuses only;
  `abandoned` is an explicit human judgment and is left alone, and `archived`
  is already terminal.
- Archive beats complete when a session qualifies for both. `archived` means
  "get this out of my default view", and the fact that it was fully packed is
  not lost — the `Packing` column still reads `4/4`.
- An unparsable or missing `created_at` is never archived. Same spirit as the
  filter this replaces: never act on a date you could not read.

### Manual edits win permanently

Without a brake, the automation fights the user: they set a 60-day-old session
back to `active`, and the next refresh archives it again. So
`_on_status_changed` writes `status_manually_set: true` alongside the status,
and `derive_status_updates` skips any entry carrying it.

The semantics are deliberately blunt and per-session: **once you set a
session's status by hand, the app stops managing that session's status.** The
cost is that a user who corrects one status loses auto-management for that
session forever. That is predictable, scoped to one row, and cheaper to reason
about than tracking which specific transition was last automated.

### Batched write path — this is a correctness/performance requirement

`update_session_status()` calls `_upsert_index_entry()`, which takes the index
lock, reads the whole index, and rewrites it. Calling it once per session for
a backfill is O(N²) in bytes written.

This is not hypothetical. On the current data **41 of 42 sessions qualify for
archiving on the very first run**, and the index runs ~1 KB per session — so
the naive path would take 41 locks and write ~34 MB to a UNC share to set 41
strings. `session_index.json` also now grows with *order volume*, not just
session count (`completed_orders`), so this gets worse over time.

So `SessionManager` gains a batch method:

```python
def apply_status_updates(self, client_id: str, updates: dict[str, str]) -> int:
    """Write each session's status under its own session_info lock, then
    rewrite the client index exactly once. Returns the number applied."""
```

Per-session `session_info.json` writes keep their existing per-session lock
(they must — packing-tool writes the same files). Only the index write is
batched, under a single index-lock acquisition.

Failures are per-session and best-effort: one unwritable session logs and is
skipped, and the rest still apply. Nothing here may raise into the refresh
path — a session list that will not load is far worse than one with a stale
status.

### Where it runs

In `SessionLoaderWorker.run()`, on the background thread, right after
`list_client_sessions()` and before `finished_with_data.emit()`: derive, apply,
reflect the new statuses into the in-memory entries, then emit. This is file
I/O only — no UI calls from the worker thread, per the repo's hard rule.

It is self-limiting: the first refresh writes the backlog, every later refresh
derives an empty update set and writes nothing.

### Widget changes

- **New `Packing` column** between `Packing Lists` and `Comments`, read-only,
  showing `3/4`, or `—` when the session has no packing lists. Table goes from
  7 to 8 columns. The tooltip already assembled per row gains a line naming
  the lists still outstanding. (Superseded by the plan, which emits the
  simpler `Packed: n/m lists completed in Packing Tool`.)
- **Delete `filter_sessions_by_age` and `DEFAULT_SESSION_AGE_CUTOFF_DAYS`.**
  Their job is now done by a persisted, visible, user-editable `archived`
  status instead of an invisible display-time rule. This is the simplification
  that pays for the feature.
- **"Show Older (30+ days)" becomes "Show Archived".** With the status filter
  on `All`, archived sessions are hidden unless the toggle is on. Selecting
  `Archived` in the status filter explicitly still shows them regardless — the
  filter is server-side, so that path returns only archived rows and the
  toggle must not then hide all of them.

Net effect on the default view is close to today's: recent sessions visible,
old ones hidden behind one toggle. The difference is that the reason a row is
hidden is now a real field the user can see and change.

## First-run behaviour, accepted

On the first refresh after this ships, a client with a long backlog sees most
of its sessions move to `archived` and leave the default view at once — 41 of
42 on the current data. That is the feature working as specified, but it is
abrupt, and the write pass makes that one refresh slower.

Mitigations built in: the work happens on the background thread so the UI stays
responsive; the index is written once; and "Show Archived" brings everything
straight back. Not built: a progress indicator or a first-run confirmation
prompt. If the slow first refresh proves annoying on the production share,
the natural upgrade is to bound the pass to the N oldest sessions per refresh.
Recorded as a `ponytail:` comment rather than built.

## Testing

Pure-function tests need no Qt and no file server:

- `packing_completion`: normal partial (`2/3`), all-complete, zero lists
  (`0/0`), `full_session` completed, `full_session` present-but-incomplete,
  a `packing_progress` key with no file on disk, and malformed blocks
  (`packing_progress` a string, a block a list, a missing `status`).
- `parse_created_at`: naive → local-aware, already-aware preserved, garbage →
  `None`, missing → `None`. Must not raise — a naive stamp once crashed the
  entire refresh and left the widget stuck on "Loading..." forever
  (`test_naive_created_at_is_kept_not_crashed`, the behaviour that regression
  guarded). The replacement tests must keep that property.
- `derive_status_updates`: auto-complete only from `active`; no completion at
  `0/0`; archive from `active` and `completed`; `abandoned` and `archived`
  untouched; `status_manually_set` skipped entirely; unparsable date never
  archived; archive wins over complete.

Integration:

- `apply_status_updates` writes every session file **and rewrites the index
  exactly once** — assert the call count on `_write_index`, not just the
  resulting content. A test that only checks the final statuses passes just as
  happily with the O(N²) implementation, and the batching is the whole point.
- One unwritable session does not prevent the others from applying.

Widget (offscreen):

- The `Packing` column renders `3/4` and `—` in the right rows.
- Archived rows are hidden by default and appear when "Show Archived" is on.
- Selecting `Archived` in the status filter shows rows with the toggle off.

`tests/test_session_browser_filter.py` is deleted with the function it covers;
its five cases are re-expressed against `session_lifecycle`.

## Files

- `shopify_tool/session_lifecycle.py` — new, pure derivation
- `shopify_tool/session_manager.py` — add `apply_status_updates`; add a
  `manual` flag to `update_session_status`
- `gui/session_browser_widget.py` — new column, worker calls the sync, delete
  the age filter, relabel the toggle
- `tests/test_session_lifecycle.py` — new
- `tests/test_session_browser_filter.py` — deleted
- `tests/test_session_manager.py` — batch-write coverage
- `tests/test_session_browser_reload.py` — check for assumptions about the
  column count and the toggle before editing

## Explicitly out of scope

- Any visual restyling of statuses, stats or comments (Phase 8).
- The hardcoded `color: blue/darkgreen/red` in the status combobox, which
  violates the repo's no-hardcoded-colors rule. Left in place deliberately so
  this item ships no throwaway styling; recorded on the Phase 8 task.
- Moving archived sessions to a separate directory.
- Making the 30-day window configurable. One constant, changed in one place if
  it is ever wrong.
