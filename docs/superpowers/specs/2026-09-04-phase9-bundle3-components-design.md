# Phase 9 Bundle 3 — three components: status, selection ring, empty state

**Bundle:** Todoist `6hQXj6C4qhvFVrhV`. Covers 9.3 (F5), 9.4 (F4), 9.6 (F7).
**Worked from:** the artboard summaries in
`docs/superpowers/specs/2026-09-03-phase9-fulfilment-v2-design.md` §3.2 and
`docs/superpowers/plans/2026-09-03-phase9-roadmap.md` § Track Q, plus the
per-item briefs on the Todoist subtasks. The canvas itself was not opened —
the phase parent says the three docs are the contract.

**Bundle done when:** every child's `Done when` holds, and a selected-and-
blocked row renders the closed ring with the status edge inset inside it.

---

## 1. What this bundle actually is

Three components that collide on the same pixels. 9.3 decides how a blocked
status renders; 9.4 decides what a selected row looks like; 9.4's acceptance
case is *a row that is both*. 9.6 joins them because it is the third new
component of the F-series and a prerequisite of Bundle 4 (first run's card)
and Bundle 6 (the browser's two empty states).

The work is smaller than it reads, because two of the three are mostly
**deletion**: 9.3 removes a branch (dot vs pill) rather than adding one, and
9.4 removes a QSS rule's failure mode rather than adding a widget.

---

## 2. The load-bearing fact the bundle brief does not mention

**`StatusChip` and `StatusDot` live in `shared/theme.py`, which this repo does
not own.** Per `CLAUDE.md` and CONTEXT.md, every `shared/` change is authored
in `packing-tool` and arrives here through `scripts/sync_shared.py`.

So 9.3 is a **cross-repo item and Bundle 3 is a two-PR cycle**, exactly like
Bundle 1 (shopify #313 + packing-tool #172):

1. a `packing-tool` PR carrying the `shared/theme.py` change, and
2. this repo's PR carrying the sync plus everything Qt-side.

9.4 and 9.6 are shopify-only. See §7 for what the packing-tool half contains
and, deliberately, what it does not.

---

## 3. 9.3 — one status component, three channels

### 3.1 The rule

Colour is the **role**. Fill is **live** — tinted means someone has to act,
untinted means resting or terminal. Mark is **authorship** — a solid dot means
a person set it, a hollow dot means the system derived it.

This supersedes "tint carries authorship", which left nothing to carry
urgency. Today the two authorships are two *silhouettes* — a dot-and-label for
a person-set status, a tinted pill for a system-set one — so the eye reads two
components and the authorship difference disappears into "the design is
inconsistent". After this item there is one silhouette everywhere: a pill,
outlined in the role colour, carrying a mark and a label.

### 3.2 The seam: one pure function, two renderers

The three channels must resolve identically in two places that draw by
different means — `StatusChip` (a `QLabel` styled by QSS) and
`SessionStatusDelegate` (a `QPainter`). Today that duplication already exists
and is held together by a test: `gui/session_row_delegates.py`'s
`chip_colors()` copies `StatusChip.set_status`'s two lines, and its docstring
says outright that the second painted call site is "the moment to hoist".

This is that moment. A two-line rule tolerated a copy; a three-channel rule
with geometry would not.

```python
class StatusStyle(NamedTuple):
    fg: str            # the role's foreground — outline, mark, and label
    fill: str | None   # the tint when live; None when resting
    mark_filled: bool  # solid mark for a person, hollow for the system


def status_style(role, theme, *, live=True, manual=False) -> StatusStyle:
    ...
```

Lives in `shared/theme.py`, beside the two widgets that consume it. `getattr`
still resolves `role`, so a typo raises where it is written rather than
rendering the wrong colour in production — the existing rule, unchanged. The
`<role>_bg` fallback to `surface_sunken` stays, for `text_secondary`, which
has no `_bg` partner.

`chip_colors()` and `SessionStatusDelegate.form()` are **deleted**, not
adapted. `form()`'s whole job was choosing between two silhouettes and there
is now one.

### 3.3 `StatusDot` — the mark

Gains `filled: bool = True`. Hollow paints a 1.5px ring in the role colour on
a transparent ground instead of a disc.

It **stays a public class**. The brief's "survives as the chip's mark, not as
a standalone form" is a rule about the Qt tier's *screens*, and after this
bundle no shopify screen uses one standalone. `packing-tool`'s session list
still does — see §7.

### 3.4 `StatusChip` — the silhouette

`set_status(role, text, theme, *, live=True, manual=False)`. Keyword-only, and
both default to today's behaviour, so the one existing call site
(`gui/components/commandbar.py:105`) compiles unchanged.

- The pill's **outline** is `1px solid fg` in both fill states. The outline is
  what holds the silhouette constant, and it is the channel `validate_theme`
  already proves on all four planes and on `selection_bg` — the fill is not
  trustworthy alone (`status_info_bg` is identical to `selection_bg` in dark).
- **Live** fills with `<role>_bg`. **Resting** fills with `transparent`.
- The **mark** is painted, not a character and not a child widget:
  `paintEvent` calls `super().paintEvent()` and then draws an 8px disc (solid)
  or ring (hollow) in the left padding. Left padding grows `8 → 20px` to
  reserve the space. A child `StatusDot` inside a `QLabel` would need a
  layout on a label; a `●`/`○` character would make the mark depend on a font
  shipping those glyphs, which 9.19 bans for the same reason.
- The `edge` variant is **untouched**. It is a lane marker, not a status
  badge — it carries no label of its own authorship and takes no mark.

### 3.5 Which states are live

`live` is genuinely new: nothing in either app's data says "someone has to
act". It is derived from the rule in §3.1 and recorded here so both repos and
every later bundle agree.

| App | State | Role | Live |
|---|---|---|---|
| Shopify | `active` | `status_info` | **yes** — work in flight |
| Shopify | `completed` | `status_success` | no — terminal |
| Shopify | `abandoned` | `status_danger` | no — terminal |
| Shopify | `archived` | `text_secondary` | no — resting |
| Packing | `not_started` | `text_secondary` | no — resting |
| Packing | `in_progress` | `status_info` | **yes** |
| Packing | `paused` | `status_warning` | **yes** — someone must resume |
| Packing | `stale` | `status_warning` | **yes** — needs attention |
| Packing | `completed` | `status_success` | no — terminal |
| Packing | `incomplete` | `status_danger` | **yes** — still finishable |
| Packing | `abandoned` | `status_danger` | no — terminal |

`incomplete` live and `abandoned` resting is the pair 9.19 already calls out:
"Incomplete stays full-strength (a person did this, someone can still finish
it); Abandoned recedes (the system concluded it, it is over)."

Live-ness is data about a state, so it is stored with the role rather than in
a second table keyed by the same thing. `STATUS_ROLES` in
`gui/session_row_delegates.py` becomes `dict[str, tuple[str, bool]]`; its two
readers move with it.

### 3.6 Departure from the artboard: the "13 states"

F5's `Done when` counts **13 states (6 Shopify, 7 Packing)**. Packing has
exactly 7 (`STATUS_CONFIG`). **Shopify has 4**, not 6 — `STATUS_ROLES` knows
`active`, `completed`, `abandoned`, `archived`. The missing states are
9.19's, which expands the table to seven plus archived and is itself gated on
a `session_info.json` data change (`blocked_orders`).

Bundle 3 therefore renders **11 states, not 13**, and ships the mechanism that
makes the remaining two free. Introducing states here that no screen can
produce until Bundle 6 would be shipping dead vocabulary. 9.19 keeps the
expansion; this spec's §3.5 table is what it extends.

---

## 4. 9.4 — selection becomes a closed ring

### 4.1 Why the QSS ring cannot close

`QTableView::item` styles **cells**. Today's rule gives every item a 2px
`selection_border` top and bottom, which reads as a ring only because
horizontal edges happen to be continuous across cells. Left and right borders
cannot be added: they would repeat at every column boundary. So a selected row
is two horizontal rules, open at both ends — and the status edge then sits
exactly where the ring's left side would be, so a row that is both selected
and blocked reads the red edge as part of the selection.

### 4.2 The mechanism

One helper, `gui/selection_ring.py`:

```python
RING_WIDTH = 2

def paint_selection_ring(painter, option, index) -> None:
    """Paint this cell's slice of the selected row's ring end caps."""
```

Called by every delegate the app installs on a table, after `super().paint()`.
Each cell paints only the caps it owns:

- the **left** cap when `header.visualIndex(index.column()) == 0`
- the **right** cap when the column is the last **visible** logical index

Visual index, not logical, for the same reason `StatusEdgeDelegate.paints_edge`
already uses it: a user who drags a column to the front must still get the cap
on the left of the row. Hidden columns are walked back from the end, which is
usually zero iterations.

No cell paints outside its own rect, so nothing depends on QTableView's
per-cell clipping behaviour.

### 4.3 The top and bottom stay in QSS

**Recommended, and the open question of this bundle — see §8, Q1.**

The QSS rule keeps drawing the top and bottom; the delegate adds the two end
caps. The caps use `option.rect`, which is the same rect Qt gave the QSS
border, so they meet exactly.

The alternative — drop the QSS rule and paint all four sides in the helper —
puts the ring in one place, which is cleaner. It also silently removes the
selection border from the **twelve** tables in this app that have no delegate
(settings, reports, rule-test and groups dialogs, the SKU and activity-log
tables). Those tables would show selection as a plain `selection_bg` tint.

The end-cap version is ~20 lines against ~35, has no blast radius outside the
two tables it targets, and reaches the same drawn result. Its cost is that the
ring's colour and width are named in two places — the same arrangement
`StatusEdgeDelegate` already lives with beside QSS, and it works.

### 4.4 The status edge insets

`StatusEdgeDelegate` currently paints a 3px bar at `rect.x()` for the full
`rect.height()`. On a selected row it now insets by `RING_WIDTH` on the left,
top and bottom, so the edge sits **inside** the ring rather than colliding
with it. This is the bundle's acceptance case.

### 4.5 Also on this artboard

- **Zebra striping stays off.** A stripe on `surface_raised` is the same value
  as a panel, so a striped table stops reading as one plane. Nothing to build
  — a test asserts `setAlternatingRowColors` is not turned on.
- **The sort caret** appears on the sorted column and on hover only. Qt's
  default already draws the indicator on the sorted section alone, so this is
  verify-then-test, plus a `QHeaderView::section:hover` rule using the arrow
  glyphs 9.0 vendored. If the app is found to force an indicator onto every
  header, that is the thing to remove.
- **F4's frozen first column is dropped** — already decided in the phase
  analysis §3.2. Nothing to do.

---

## 5. 9.6 — one empty state, not forty

### 5.1 It composes; it is not a new visual language

`StatePanel` is a `QWidget` holding a **`Card`**, centred by stretches rather
than margins. Composition, not subclassing: the `Card` QSS rule is a type
selector, and `build_stylesheet`'s own comment records that "QSS type
selectors match `className()` exactly, so a future subclass needs its own
selector". Subclassing would mean a second `shared/theme.py` edit — a second
packing-tool PR — to make a shopify-only widget get a plane it can have for
free by holding one.

### 5.2 The four variants

One `__init__`, four classmethod constructors that encode the content rule:

| Constructor | Says | Action |
|---|---|---|
| `nothing_loaded` | what has not been loaded, and where it comes from | one accent-filled |
| `working` | the named step and a count | none |
| `no_results` | which filter emptied the list | **secondary** "Clear all filters" |
| `failed` | the cause, in the file's own words, then two ways out | one accent-filled |

The rule every variant obeys: **name the cause, name the file or filter that
caused it, offer the action that resolves it.** No apologies, no exclamation
marks. Exactly one accent-filled action per panel — "Clear all filters" is
secondary because the operator may actually want the empty answer.

What none of them may be: "No data · Nothing to display." That sentence cannot
distinguish "you have not loaded anything" from "your filter is too tight"
from "the server is unreachable".

`working` carries a named step and a count, not a skeleton shimmer: Qt has no
animation beyond `qlineargradient`, and a supervisor watching a network share
is better served by a step name than by a pulse.

### 5.3 Departure from the artboard: no mono yet

F7 puts technical detail in mono "so it can be read aloud over a phone".
**The Qt tier has no mono face** — `grep` finds no `Consolas`, no
`monospace`, no second `font-family` anywhere outside `shared/theme.py`'s one
`font_family` token. Introducing one means either a hardcoded family in a
component (which the theme rules forbid) or a new `ThemeTokens` field, which
is a third packing-tool PR.

**9.11 already owns that decision** — "one mono face across both renderers,
Consolas" is written into ADR 0001 and is Bundle 11's work. So StatePanel's
detail line ships at `caption` in `text_secondary`, and 9.11 gives it the mono
face when the face exists. Recorded as a deliberate deviation.

### 5.4 Departure from the artboard: zero call sites in this bundle

9.6's `Done when` ends "and no screen in the app renders a bare 'No data'
message." **No screen does today.** The only matches in `gui/` are a combo box
placeholder item, a settings checkbox label, a log line, and one message-box
string in the barcode widget. An empty results table and an empty session
browser render *nothing at all* — worse than a bare message, and precisely
what the component is for.

Every screen that should get a `StatePanel` is claimed by a later bundle in
this same phase:

- the Setup page's first-run card → **Bundle 4** (9.9), which names it
- the session browser's two empty states → **Bundle 6** (9.19), which names them
- the Analysis Results table → **Bundle 12**, and it leaves the Qt tier entirely

So Bundle 3 ships `StatePanel` with four tested variants and **wires it into
nothing**. A component with no consumer is normally a smell; here it has three
named consumers inside the same phase, and the bundle exists precisely because
"it has to land before either, and it is too small to be its own cycle". The
first real consumer (Bundle 4) is where the API gets its shakedown, and the
plan says so out loud so Stage B of Bundle 4 knows it may change the
signature.

---

## 6. Module shape

Four seams, each with a small interface over a decision made once:

| Module | Interface | Depth |
|---|---|---|
| `shared/theme.py: status_style` | one function, one NamedTuple | the three-channel rule, for both renderers |
| `shared/theme.py: StatusChip/Dot` | `set_status(..., live, manual)` | the silhouette |
| `gui/selection_ring.py` | one function | which caps this cell owns |
| `gui/components/state_panel.py` | four classmethods | the content rule for an empty screen |

The deletion test: remove `status_style` and the three-channel rule reappears
in two renderers that must not drift — it earns its keep. Remove
`paint_selection_ring` and the first/last-visible-column logic reappears in
every delegate — same. `StatePanel` has one implementation and three pending
callers; if Bundle 4 and Bundle 6 both end up wanting different shapes, it
should collapse back into them rather than grow a flag.

---

## 7. The packing-tool half

The `packing-tool` PR carries `shared/theme.py` only:
`StatusStyle`, `status_style()`, `StatusDot(filled=...)`,
`StatusChip.set_status(..., live=, manual=)`, and the tests in
`tests/test_shared_theme_widgets.py` / `test_theme.py` that cover them.

**It does not convert `gui/session_browser/sessions_list_widget.py`.** That
screen places a standalone `StatusDot` as a cell widget, which contradicts the
new "mark, not a standalone form" rule. Converting it properly means a painted
delegate — a cell widget in a table swallows clicks and moves selection on
hover, the exact fault Phase 8.7 removed here — and that is a real screen
rebuild in an app whose own v2 is not in Phase 9's scope. `packing-tool`'s 8.9
("give packing-tool its own painted status column") is the right home and
already exists.

The defaults make this safe: `live=True, manual=False` reproduces today's
tinted pill exactly, and `StatusDot(filled=True)` is today's disc. Nothing in
`packing-tool` changes appearance. See §8, Q2 — this is a scope call, not a
technical constraint.

---

## 8. Decisions taken by the user, 2026-09-04

Three questions were put to the repo owner at Stage A. All three came back as
recommended, so every default written into the plan stands and no task
changes. Recorded here as decisions, not options — do not reopen them.

**Q1 — the selection ring's blast radius. → Keep the QSS top/bottom rule and
paint only the two end caps** (§4.3). The alternative — dropping the QSS rule
and painting all four sides in the helper — was rejected: it is one source of
truth for the ring, but it silently removes the selection border from the
twelve tables in this app that have no delegate, leaving them a plain tint.
Same drawn result for ~20 lines instead of ~35, and no blast radius outside
the two tables 9.4 names.

**Q2 — how far the packing-tool PR goes. → Shared component only** (§7).
`packing-tool`'s `sessions_list_widget.py` keeps its standalone `StatusDot`.
The new defaults (`live=True, manual=False`, `filled=True`) reproduce today's
rendering exactly, so no packing-tool screen moves. Converting that screen
properly means a painted delegate — a cell widget swallows clicks and moves
selection on hover — and belongs to packing-tool 8.9, which already exists.

**Q3 — the live/resting table. → As tabled in §3.5.** `paused` and `stale`
are live because a supervisor must do something about them; `archived` is
resting.

---

## 9. Testing

At the seams, not through the screens:

- `status_style()` — a pure function: the four `live` × `manual` combinations
  return four distinguishable `StatusStyle`s, in both themes, for every role
  in §3.5. This is 9.3's `Done when`, tested where it is decided.
- `StatusChip` / `StatusDot` — the QSS string carries the right fill and
  outline per combination; the hollow mark differs from the solid one.
- `paint_selection_ring` — the cap predicate is pure and testable without
  painting: first visible column, last visible column, a hidden last column,
  a dragged column.
- `StatusEdgeDelegate` — the edge rect insets by `RING_WIDTH` when selected
  and does not when it is not.
- `StatePanel` — each of the four constructors builds the labels and the
  button role it promises; `no_results`' action is secondary.
- A render pass through both themes for all eleven states, joining
  `tests/test_components_render_roles.py`.

The acceptance case gets its own test: a row that is both selected and blocked
renders four ring segments with the status edge inside them.
