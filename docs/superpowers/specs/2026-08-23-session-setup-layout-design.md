# Session Setup layout: stop the quick-pick panel starving the content column

Date: 2026-08-23
Roadmap: Phase 7, subtask `6h8v4VqJwWpJ2Pf3`
Status: approved (layout chosen by the user 2026-08-23)

## Problem

The roadmap item asks for "a better layout of page" with "Recent sessions in a
smaller window". Both halves are real, and they are the same defect: Tab 1's
splitter is a fixed 60/40, so a list that can show at most five rows is handed
40% of the window while the column holding every primary action is squeezed
below the width it needs.

The squeeze is not cosmetic. It hides buttons.

### Measured, not estimated

All numbers below come from real widget geometry, read from a constructed
`MainWindow` under `QT_QPA_PLATFORM=offscreen`.

The setup column's content requires **706px** — `_create_files_group` lays
"Orders File" (min 328px) and "Stock File" (min 328px) side by side in a
`QHBoxLayout`, and that group reports `minimumSizeHint().width() == 686`.

The column does not get 706px. `_create_session_setup_panel` wraps its content
in a `QScrollArea`, whose own minimum width is tiny because a scroll area is
always willing to scroll instead of asking for room. The splitter therefore
squeezes it freely, a horizontal scrollbar appears, and buttons fall off the
right edge:

| Window | Content column | Needs | Buttons clipped |
|---|---|---|---|
| **1100×900** (the app's own default, `main_window_pyside.py:76`) | 574px | 706px | `Load Stock File (.csv)`, `Add Product to Order`, `Settings`, `Generate Reports`, `Open Session Folder` |
| 1400×900 | 682px | 706px | `Add Product to Order`, `Settings`, `Generate Reports`, `Open Session Folder` |
| 1920×1080 | 994px | 706px | none |

So on first launch, at the geometry the app sets for itself, five controls —
including `Generate Reports` — are reachable only by scrolling sideways. The
page is correct only above roughly 1500px of window width.

Meanwhile `_create_session_browser_panel` holds a title, a `QListWidget` that
`refresh_recent_sessions` caps at **five entries**, and one link button. Its
`sizeHint` is 256×192. It is handed:

| Window | Recent Sessions list |
|---|---|
| 1100×900 | 363 × 692 |
| 1400×900 | 434 × 692 |
| 1920×1080 | 642 × 872 |

Roughly 500px of vertical emptiness, and it is taking exactly the horizontal
room the content column is short of. The two symptoms in the roadmap item have
one cause.

### What is already fine

`2026-07-26-unified-ui-design-system-design.md` already replaced an embedded
second copy of the full `SessionBrowserWidget` with this compact quick-pick.
That change was correct and is not being revisited — the panel's *contents* are
right, only its allocated size is wrong.

## Decision

Three layouts were rendered offscreen and compared. The user chose **B**.

- **A — single column.** Drop the splitter; fold the list into the "Session
  Management" group as a short full-width strip. Content column gets 961px at
  default size (255px of headroom). Rejected as a larger restructure than the
  problem needs.
- **B — narrow right-hand card (chosen).** Keep the splitter, cap the card's
  width, cap the list to five rows, let the content column take all remaining
  width.
- **C — dropdown.** Replace the panel with a "Resume:" combobox. Rejected: it
  costs the at-a-glance view of recent session status.

B as first rendered had one flaw: it cleared the clipping at 1100px with only
46px to spare, so narrowing the window brought it straight back. The design
below closes that by fixing the actual cause — the setup column never declaring
a minimum width — rather than by picking splitter sizes that happen to work.

## Design

Five changes, all in `gui/ui_manager.py`. No logic, no signals, no data.

### 1. The setup column declares the width it needs

`_create_session_setup_panel` sets its own minimum width from its content's
requirement, so the splitter can no longer squeeze it into scrolling:

```python
panel.setMinimumWidth(scroll_widget.minimumSizeHint().width() + _SETUP_COLUMN_SLACK)
```

`_SETUP_COLUMN_SLACK = 24` covers the frame and a vertical scrollbar.

**Verified:** `scroll_widget.minimumSizeHint()` already reports `(706, 587)`
inside the builder, before `show()` — the value does not require a realised
window, so reading it at construction is sound.

This is the root-cause fix. Anything later added to the setup column widens the
minimum automatically; the panel never silently starts hiding controls again.

### 2. The quick-pick card is capped

`_create_session_browser_panel` sets `panel.setMaximumWidth(_RECENT_PANEL_MAX_WIDTH)`
with `_RECENT_PANEL_MAX_WIDTH = 320` — enough for `session_name — status`, and
the panel is never a column again.

### 3. The list is exactly five rows tall

The list currently takes the layout's stretch (`addWidget(..., 1)`), which is
what makes it 692px tall. It gets a fixed height for the five rows it can
actually contain, and gives up the stretch.

```python
_RECENT_SESSIONS_ROWS = 5  # refresh_recent_sessions() shows at most this many

def _recent_list_height(widget: QListWidget) -> int:
    row = QFontMetrics(widget.font()).height()
    return row * _RECENT_SESSIONS_ROWS + 2 * widget.frameWidth() + 4
```

**Verified:** height must come from font metrics, not `sizeHintForRow(0)` —
that returns **-1** while the list is empty, and it is empty when the panel is
built. Font metrics give 17px, exactly matching `sizeHintForRow(0)` once the
list is populated, for a 91px list.

`refresh_recent_sessions`'s hardcoded `[:5]` becomes `[:_RECENT_SESSIONS_ROWS]`
so the row count and the height cannot drift apart.

### 4. The card sits at the top

A trailing `addStretch()` goes *after* the "Open full Session Browser →" button,
so the list and its link stay together under the title. Putting the stretch
between them strands the link at the bottom of the window — that was visible in
the first render of this option.

### 5. Extra width goes to the content, not the card

```python
splitter.setSizes([1100, _RECENT_PANEL_MAX_WIDTH])
splitter.setStretchFactor(0, 1)
splitter.setStretchFactor(1, 0)
splitter.setCollapsible(1, True)
```

The existing 6:4 stretch factors are what re-inflate the card on a wide monitor.
With 1:0 the card holds ~300px and every extra pixel goes to the content column;
`setCollapsible` lets the card be dragged away entirely.

### Resulting geometry (measured on the prototype)

| Window | Content column | Recent Sessions | Clipped |
|---|---|---|---|
| 1920×1080 | 1356px | 280 × 91 | none |
| 1400×900 | 836px | 280 × 91 | none |
| 1100×900 | 730px | 207 × 91 | none |

The list drops from 363×692 to 207×91 at default size — about a seventh of the
area — and the content column gains 156px, clearing its 706px requirement with
room to spare at every size the app can be opened at.

## Known ceiling

The content column cannot go below **730px**. Below roughly a 1050px window the
splitter stops shrinking and the card is pushed against the window edge. That is
strictly better than today (which breaks at 1500px), and the app's own default
is 1100px, so no responsive stacking of Orders/Stock is being built for window
sizes nobody opens. If that ever matters, the fix is in `_create_files_group`:
stack the two file sections vertically below a threshold. Recorded as a
`ponytail:` comment, not built.

## Testing

Layout regressions are invisible to logic tests, so the check is behavioural:
construct the real window at its default geometry and assert nothing is hidden.

`tests/test_session_setup_layout.py`:

1. `test_no_action_button_is_clipped_at_default_window_size` — no button in the
   setup column extends past its scroll viewport.
2. `test_setup_column_never_scrolls_horizontally` — the horizontal scrollbar is
   hidden.
3. `test_recent_sessions_panel_stays_compact` — the card is ≤ 320px wide and the
   list ≤ 200px tall.

**All three were run against the current unfixed code and all three fail**, with
exactly the expected failures (`['Load Stock File...', ...] == []`,
`assert not True`, `assert 383 <= 320`). The fixture points
`FULFILLMENT_SERVER_PATH` at a `tmp_path`, which is enough to construct
`MainWindow` — confirmed working.

## Non-goals

- Changing what the quick-pick shows, or how sessions load. Contents are fine.
- Touching `SessionBrowserWidget` or Tab 3.
- Responsive stacking of the Orders/Stock file sections (see Known ceiling).
- Setting a minimum size on the main window.
- Any change under `shared/`.

## Baseline

`761 passed`, `ruff check . --exclude shared` clean, on
`worktree-session-setup-layout`.
