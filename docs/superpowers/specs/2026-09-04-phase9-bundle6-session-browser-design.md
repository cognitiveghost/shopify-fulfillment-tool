# Phase 9 Bundle 6 — The session browser

**Item:** 9.19, alone. **Artboards:** D1, D2.
**Roadmap:** `docs/superpowers/plans/2026-09-03-phase9-roadmap.md` § Track Q / 9.19.
**Phase spec:** `docs/superpowers/specs/2026-09-03-phase9-fulfilment-v2-design.md` §5.4, §7.
**Worked from the three contract docs, not the canvas**, per the phase parent's
instruction. Departures from what the artboards drew are listed in §12.

---

## 1. What this changes

The Session Browser is a 7-column `QTableWidget` that shows four statuses as a
coloured pill. After this item it is an 8-column `QTreeWidget` under two group
headings, showing eight states as eight painted shapes, with Age, Blocked and
Comment columns and two empty states.

The order below is the order it must be built: the data question first, because
two columns and one filter read its answer.

---

## 2. The gate is smaller than the roadmap assumed

The roadmap says `session_info.json` has no blocked count because
"`actions_handler` computes `fulfillable_orders` at analysis time and throws
the complement away." That is true of `actions_handler`, and only of it — the
path it describes writes to `StatsManager`, not to the session file.

`shopify_tool/core.py:1069-1084` already writes **both** numbers into
`session_info.json` on every session-mode analysis:

```python
session_manager.update_session_info(working_path, {
    "total_orders": analysis_data["total_orders"],
    "fulfillable_orders": analysis_data["fulfillable_orders"],
    "not_fulfillable_orders": analysis_data["not_fulfillable_orders"],
    ...
})
```

It has done so since the session architecture landed (`2372d2b`), and
`update_session_info` merges rather than replaces, so nothing later drops it.
The browser reads `session_index.json`, whose entries are whole `session_info`
dicts (`_scan_sessions` → `get_session_info`, no projection), so the number is
**already in the entry dicts the widget receives**.

**Therefore: no schema change, no migration, no backfill pass.** The work is
naming and one accessor. `analysis_data.json` — which packing-tool reads — is
untouched.

### 2.1 The accessor

One function in `shopify_tool/session_lifecycle.py`, which is where the
roadmap says the name gets settled:

```python
def blocked_orders(entry: dict) -> int | None:
    """Orders this session cannot fulfil, or None when it was never analysed.

    None is not 0: a session with no analysis has no answer, and the column
    must stay blank rather than claim nothing is blocked.
    """
```

Read order: `not_fulfillable_orders`; else `total_orders - fulfillable_orders`
when both are present and the subtraction is sane; else `None`. Non-numeric or
negative values read as `None` — every value here comes from a file another
tool writes, and this module's rule is that no shape it can take may raise.

---

## 3. Naming: the number is **blocked**

Three names are live for one number today:

| Where | Name |
|---|---|
| Row data (`Order_Fulfillment_Status`) | `Not Fulfillable` |
| `session_info.json` | `not_fulfillable_orders` |
| Analysis Results stat card (`gui/ui_manager.py:665, :1419`) | key `blocked`, label **Blocked** |
| D1 artboard, browser column | `BLK` |
| Analysis Results artboard | `SHORT ON STOCK` |

**Canonical term: a *blocked order*, counted as `blocked_orders`.** It already
ships as the Analysis Results card's key and label, the delegate module already
refers to `blocked_orders` in prose, and CONTEXT.md already uses "blocked"
informally under Selection ring. Picking it renames nothing that ships.

- `SHORT ON STOCK` is **rejected**: it names one cause of blocking, and stock
  is not the only one (a manual `Set Not Fulfillable` blocks an order too).
- `BLK` is **rejected as a term** and rejected as a header: it exists only to
  fit a narrow column, and "Blocked" measures ~55px bold, which fits the 80px
  column. An abbreviation nobody needs is a second name in disguise — the exact
  failure §5.4 of the phase spec asks us to prevent.
- `not_fulfillable_orders` stays as the **persisted key**. It is a written file
  shared with another tool; renaming it buys nothing and costs a migration.
  One canonical term at the boundary, one stable key on disk, one accessor
  between them.

---

## 4. Eight states

`STATUS_ROLES` knows four. The seven the phase-8 contract table fixes
(`docs/superpowers/specs/2026-08-26-phase8-unified-design-system.md` §4) plus
`archived` make eight. Shopify stores only four, so the other four are derived
from data already in the entry.

| State | Label | Derived from |
|---|---|---|
| `not_started` | Not started | stored `active`, no packing progress at all |
| `in_progress` | Active | stored `active`, some progress, not all done |
| `paused` | Paused | stored `active`, a progress block reads `paused` |
| `stale` | Stale | stored `active`, in progress, untouched 7+ days |
| `completed` | Completed | stored `completed`, fully packed |
| `incomplete` | Incomplete | stored `completed`, **not** fully packed |
| `abandoned` | Abandoned | stored `abandoned` |
| `archived` | Archived | stored `archived` |

`incomplete` is the one that needed a definition: a person marked the session
done while packing lists remain unpacked. That is exactly packing-tool's
meaning of the word, and it is exactly the brief's "a person did this, someone
can still finish it". `derive_status_updates` only ever promotes
`active → completed` when fully packed, so every `incomplete` row is a human
judgment, never an automation artefact.

`stale` reads the latest of `last_updated` and every
`packing_progress[*].updated_at`, falling back to `created_at` when none of
them is readable. It is **not** age from creation — Age is its own column, and
drawing the same fact twice is what this phase keeps deleting.

> **Amended at review.** This section first said `last_updated` alone.
> packing-tool never writes that key — its progress writer stamps
> `updated_at` on the block it touched (`packing_tool/session_manager.py:721`)
> — so a session being packed right now read as idle since the day it was
> created, went `stale`, and landed in Needs attention. Reading every stamp is
> what makes the rule true across both writers.

One pure function, beside the accessor:

```python
def display_status(entry: dict, now: datetime) -> str:
```

No Qt, no I/O, total over any dict — an unknown stored status falls through to
itself so a future value renders as its own name rather than as a lie.

---

## 5. Shape is the fourth channel

### 5.1 The naming problem, and its answer

CONTEXT.md already spends both obvious words: **glyph** is a vendored Lucide
drawing on disk, and **mark** is the authorship dot inside a chip. These
painted state figures are neither. They also cannot be called glyphs without
implying an SVG, which §7 of the phase spec explicitly forbids for these.

The three channels are named for what they are — colour, fill, mark. The fourth
is named the same way: **shape**.

> **Colour** is the role, **fill** is live-vs-resting, **mark** is
> person-vs-system, **shape** names the state.

### 5.2 Shape supersedes mark in this cell

A row showing eight states cannot also spend the mark on authorship: a
half-filled disc is neither solid nor hollow, so the two channels collide on
the same 12px square.

They do not need to share it. Authorship is **constant per state** — four of
the eight are only ever system-derived, and the brief already assigns marks by
state, not by flag ("Incomplete stays … with a solid mark"). So authorship
folds into the state table exactly as `live` did in 9.3, for the same stated
reason: it is data about a state, not a second table keyed by the same thing.

**In the session row's status cell, shape replaces the mark.** `ROLE_MANUAL`
stops being set, and `status_manually_set` keeps its real job — stopping
`session_lifecycle` from ever re-managing that session. `StatusChip` elsewhere
is untouched and keeps its mark.

### 5.3 The table

12px square, painted in `style.fg`, in `shared/theme.py`. Never a character —
nothing may depend on a font shipping `◐`.

| State | Shape | Drawn as | Role | Live |
|---|---|---|---|---|
| `not_started` | `ring` | stroked circle | `text_secondary` | no |
| `in_progress` | `half` | circle, left half filled | `status_info` | yes |
| `paused` | `pause` | two vertical bars | `status_warning` | yes |
| `stale` | `clock` | circle, two hands | `status_warning` | yes |
| `completed` | `check` | two-stroke tick | `status_success` | no |
| `incomplete` | `bang` | vertical bar over a dot | `status_warning` | yes |
| `abandoned` | `slash` | circle crossed at 45° | `status_danger` | no |
| `archived` | `tray` | bar over an open box | `text_secondary` | no |

Three families, and they are the reason 40 rows scan: `ring → half → check` is
one progression, so "not started / working / done" reads as movement along a
single form. The two circles that are *not* on that progression (`clock`,
`slash`) are the two the system concluded. The three bar figures (`pause`,
`bang`, `tray`) are held, flagged and filed.

**Completed recedes.** It is `live=False`, so its pill has no tint, and in a
browser where most rows are Completed that is what separates it from Active —
not hue, which stops being seen after ninety rows.

**Abandoned recedes further:** its row's body text drops to `text_secondary`.
The system concluded it; it is over. Incomplete stays full strength.

### 5.4 Incomplete is amber, not red

The phase-8 contract table maps `incomplete` to `status_danger`, and that table
is the contract. This spec changes it to `status_warning`, deliberately:

- The table's own complaint is that `#E74C3C` Incomplete against `#C0392B`
  Abandoned is "two pairs a supervisor scanning a 200-row table has to read the
  label to separate". Mapping both to `status_danger` reproduces that failure
  in tokens instead of hexes.
- The 9.19 brief says Incomplete is "full-strength amber". Amber is
  `status_warning`.
- Semantically it is right: Incomplete is unfinished work someone can still
  pick up. Abandoned is a decision. Red for the decision, amber for the
  backlog.

This is a change to a cross-repo contract table and is listed as an open
question in §13. It changes no code in packing-tool today; it changes what
packing-tool's own migration will be asked to adopt.

---

## 6. Columns

Eight. `Packing Lists` is **deleted** — it holds `packing_lists_count`, which
is already the denominator of `Packing` ("3/5"). Deleting it puts Comment at
column 7, which is where the brief says the comment text lives.

| # | Header | Width | Source |
|---|---|---|---|
| 0 | Session | stretch | `session_name` |
| 1 | Age | 90 | `created_at`, relative |
| 2 | Status | 140 | `display_status()` |
| 3 | Orders | 80 | `statistics.total_orders` |
| 4 | Items | 80 | `statistics.total_items` |
| 5 | Blocked | 80 | `blocked_orders()` |
| 6 | Packing | 130 | `packing_completion()` |
| 7 | Comment | 200 | `comments` |

`Created` becomes `Age` rather than joining it: the absolute timestamp moves to
the tooltip, which is the only place it was being read anyway.

No Client column. The browser lists one client and the shell already names it.

Headers stay title case, as the table ships today. The artboards set them in
caps; that is a canvas convention, and this table's neighbours are all title
case.

### 6.1 Age

Cell: `today`, `3d`, `2w`, `6mo` — relative, one unit, no "ago".
Tooltip: `Created 2026-08-14 09:12`.
Past 23 days (7 before the 30-day auto-archive), the cell gains the countdown
and the warning tint: `26d · archives in 4d`. `AUTO_ARCHIVE_AFTER_DAYS` stays
the single source of the 30; 23 is `30 - 7` and is derived, not typed twice.

`age_label(created, now)` is pure and lives in `session_lifecycle.py` with the
other two.

### 6.2 Blocked

Right-aligned integer. **Blank at zero**, so the column reads as a list of
exceptions rather than a field of noughts, and blank at `None` (never
analysed). Non-zero takes the `status_warning` foreground. Tooltip:
`4 of 31 orders cannot be fulfilled`.

### 6.3 Comment

Plain text, elided. The `message-square` icon on the name cell **goes**, and
`_refresh_comment_icons()` with it — the whole theme-toggle connection that
exists only to repaint those icons is deleted. Writing still goes through the
existing `Comment…` button on the selection bar; the live field is not
restyled, which is the one answer already known to be wrong. The row tooltip
keeps the full text for comments longer than the column.

---

## 7. Two groups, and the ring they break

`QTableWidget` becomes `QTreeWidget`: two top-level items, **Needs attention**
above **Everything else**, sessions as their children. A table has no child
items, so this is not a preference.

A session needs attention when its state is `paused`, `stale` or `incomplete`,
or when it has blocked orders and is not terminal:

```python
def needs_attention(state: str, blocked: int | None) -> bool:
    if state in ("paused", "stale", "incomplete"):
        return True
    return bool(blocked) and state in ("not_started", "in_progress")
```

Pure, in `session_lifecycle.py`, tested at the table.

Empty groups are hidden, not shown empty. Default sort stays created-descending
and now applies within each group, which `QTreeWidget.sortItems` does for free.
`setUniformRowHeights(True)` per the repo's table-performance rule.

### 7.1 The regression this swap causes

**The selection ring silently disappears on a `QTreeWidget`.** Both halves of
it are `QTableView`-only:

- `gui/selection_ring.py:60-62` — `header_of()` returns the widget's
  `horizontalHeader()`, and a `QTreeWidget` has `header()`. It returns `None`,
  `caps()` returns `(False, False)`, and both end caps vanish with no error.
- `shared/theme.py:1110-1121` — the horizontal sides are
  `QTableView::item:selected` rules. A `QTreeView` matches none of them.

Neither fails loudly. Both must be fixed in this cycle or the ring 9.4 shipped
is deleted by accident on this screen.

---

## 8. Empty states

Two, both `StatePanel` (9.6), shown in place of the tree. No apologies, no
exclamation marks; each names its cause and offers the action that clears it.

**Nothing on the server** — this client has no sessions at all:

> **No sessions yet**
> CLIENT_M has no sessions on the file server.
> `[ New session ]`

**Nothing matches** — sessions exist, the filter hides them all:

> **No sessions match**
> No Completed session matches "tuesday".
> `[ Clear filters ]`

The second names both live filters in one sentence and drops the half that is
not set, so a bare search reads `No session matches "tuesday".` The action
clears the search box, the status combo and the archive line together, then
refreshes.

---

## 9. Archive moves out of the filter row

`Show Archived` stops being a toggle button competing with the two filters. It
becomes one footer line under the tree, present only when archived sessions
exist:

> `12 archived · Show`

`Show` is a ghost button; it toggles to `Hide` and the count stays. Picking
`Archived` in the status filter still works and still bypasses the line, as it
does today.

---

## 10. What changes where

### `packing-tool` (canonical source, arrives via `scripts/sync_shared.py`)

1. `shared/theme.py` — add `QTreeView::item` to the four
   `QTableView::item` selectors (§7.1). Harmless there; packing-tool has no
   tree today.
2. `shared/theme.py` — `SHAPE_PX = 12` and
   `paint_status_shape(painter, rect, style, shape)`, the eight paths of §5.3.
   Pure geometry, no shopify vocabulary. It belongs beside `paint_status_mark`
   because the shapes *are* the mark's replacement, and packing-tool owns the
   seven-state vocabulary that will want them next.

The state → (role, live, shape) table stays in this repo. Shared owns how to
draw a half-disc; each app owns which state gets one.

### This repo

3. `shopify_tool/session_lifecycle.py` — `blocked_orders`, `display_status`,
   `needs_attention`, `age_label`. All pure, all no-Qt, all tested without a
   `QApplication`. This is the seam.
4. `gui/selection_ring.py` — `header_of()` accepts `.header()` as well as
   `.horizontalHeader()`.
5. `gui/session_row_delegates.py` — `STATUS_ROLES` becomes `STATE_STYLES`,
   eight entries of `(role, live, shape)`; `SessionStatusDelegate` paints the
   shape instead of the mark; `ROLE_MANUAL` deleted.
6. `gui/session_browser_widget.py` — the tree, the columns, the groups, the
   two panels, the archive footer.
7. `CONTEXT.md` — §11.

---

## 11. CONTEXT.md

Under **Status and selection**, `Channel` gains the fourth channel and a new
entry lands beside `Mark`:

> **Shape** — the painted figure inside a session row's status cell, one per
> state. Never a Lucide **glyph** and never a character. Where a screen shows
> eight states, shape replaces the **mark**: authorship is constant per state
> and rides in the state table, so nothing is lost by not drawing it.

Under a new **Sessions** heading:

> **Blocked order** — an order this session cannot fulfil, counted as
> `blocked_orders`. One number, one name: `SHORT ON STOCK` and `BLK` are both
> retired. `not_fulfillable_orders` remains the persisted key.
>
> **Display status** — one of the eight states a session row shows, derived
> from the four stored statuses plus packing progress and age. Distinguished
> from **stored status**, the four values `SessionManager.VALID_STATUSES`
> accepts and a person can set.

---

## 12. Departures from the artboards

| Drawn | Shipped | Why |
|---|---|---|
| `BLK` header | `Blocked` | The full word fits, and an abbreviation is a second name (§3) |
| `SHORT ON STOCK` on Results | `Blocked` | One number, one name; already the shipped label |
| Caps headers | Title case | Matches the table's neighbours |
| Proposal 3, "last touched" | dropped | Phase spec §3.2 — the only cross-repo data cost |
| Client column | dropped | Phase spec / brief — one client per view |

---

## 13. Open — flagged, not decided here

1. **Shape replaces the mark in this cell** (§5.2). It stops the browser
   drawing `status_manually_set`. Recommended; the alternative is a ninth
   column of pure glyph beside the pill, which draws status twice.
2. **`incomplete` becomes `status_warning`** (§5.4), amending the phase-8
   contract table for both apps.
3. **`paint_status_shape` goes in `shared/`** (§10). It needs a packing-tool PR
   this cycle — but so does the `QTreeView` QSS fix, so the marginal cost is
   one function, not one PR.
4. **`Blocked` over `BLK`** (§3), which is the one visible departure from D1.

None of the four blocks the data work, the Age column, the comment column, the
tree, or the empty states. Only §5.3's table and one QSS hunk move if any
answer changes.
