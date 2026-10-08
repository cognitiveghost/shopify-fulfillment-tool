# Web tier freshness: a page never shows an old session

**Date:** 2026-10-08
**Status:** design approved by the owner 2026-10-08 (runner questions 59 and 60)
**Scope:** `gui/web_page.py` and what every web page shares; the move of that code and `kit.css` to `shared/`.
**Related:** ADR 0016 (the web tier), ADR 0005 (the results document owns its view state), ADR 0017 (`shared/`).

## 1. The report

The owner reported (2026-10-07) that in Fulfilment Tool and in Packer Assistant a web page sometimes shows the
previous session until it is refreshed, and that there are small visual glitches while a screen updates. The
fix goes once into the code every web page shares, before Packer Assistant moves more screens to the web tier.

## 2. What the spike found

Measured on Linux, offscreen, with throwaway scripts (deleted). The Results page, 300 and 120 orders.

| Hypothesis | Verdict | Evidence |
|---|---|---|
| Old frame on show | Confirmed | A hidden page receives the new session and its DOM is current (`document.visibilityState` is `hidden`, the rows are the new ones). On show the view presents its last frame, the old session, for 180 to 240 ms. A page that was never shown is 100×30 px until then and paints three different frames on first show. |
| Half-updated screen | Disproved | QWebChannel sends every property that changed in one tick as one message. A mutation observer saw Results go from session A to session B in a single DOM state. |
| Old session left behind | Confirmed, elsewhere | No Python property is missed. The page's own view state (ADR 0005) survives a session change: with a search typed in session A, session B opened on "no orders match", with A's search and sort still applied. |
| Not on the list | Found | Nothing handles `renderProcessTerminated`. After the render process was killed the page stayed dead: no answer to JavaScript, process id 0, no recovery on the next push. |

Two more measurements shape the design:

- The page trails the Qt chrome by 30 to 70 ms on an ordinary push (QWebChannel's 50 ms property interval plus
  a render). Not addressed here.
- Prototype: with the page stack's layout in `QStackedLayout.StackAll`, covered pages stay
  `visibilityState: visible`, run animation frames and paint. A push made while the page was covered was already
  on the first frame after the switch. When the push and the switch happened in the same tick the old frame
  still showed for about 70 ms. A covered page whose container is disabled (`setEnabled(False)`) still paints
  and still runs animation frames.

### Packer Assistant: "one unmatched scan closed the open order"

Not a web tier bug and not `PackerLogic`. After `NOT-A-BARCODE`, `PackerLogic.current_order_number` was still
`#10407` at 3 of 8. The page was wiped by `MainWindow._handle_order_completion` (`gui/main_window.py`), which
schedules `QTimer.singleShot(3000, self.packer_mode_widget.clear_screen)` after every completed order and never
checks whether another order has been opened since. The repro script packs seven orders in about 1.5 s, so
those timers fired while `#10407` was open. `NOT-A-BARCODE` was the scan in flight; no message box was
involved. On a real scanner the input is disabled for those 3 s, so exposure is low, but the page and the logic
end up disagreeing. It is its own packing-tool task and is not fixed here.

## 3. Decisions

| # | Decision | Chosen over |
|---|---|---|
| D1 | Pages stay painted: the page stack runs in stack-all mode. | Re-send on show and cover the page until it reports (every switch would flash an empty plane). |
| D2 | A different session resets all of the Results view state: search, filters, sort, selection, cursor, scroll, open popovers and pane. Column choices stay. | Keeping sort; leaving it as it is. |
| D3 | Self-heal is a reload when the render process dies. A missed painted report is logged, never acted on. | A watchdog that re-pushes and reloads (a slow render on 10 000 orders could drop what the user typed). |
| D4 | Results keeps its six properties. Every bridge gets a shared revision number and a painted report. | Rewriting Results onto one state object (no observed bug to pay for it). |

## 4. Design

### 4.1 Pages stay painted

`shared/web_page.py` gains:

```python
def keep_pages_painted(stack: QStackedWidget) -> None
```

It sets `stack.layout().setStackingMode(QStackedLayout.StackingMode.StackAll)`, then, now and on every
`stack.currentChanged`, enables the current page widget and disables every other one
(`stack.widget(i).setEnabled(i == stack.currentIndex())`). Disabling is what keeps keyboard focus and Tab out of
a page the user cannot see; it does not stop the page painting (prototype, section 2).

Fulfilment calls it once, in `UIManager._create_tabs`, after the pages are added:
`keep_pages_painted(self.mw.main_tabs.findChild(QStackedWidget))`. `main_tabs` stays a `QTabWidget` with a
hidden tab bar.

Consequence: `view.isVisible()` is now true for every main page, so `switch_theme` waits for all five pages to
report the new theme rather than one. They all paint, so they all report; the 150 ms cap is unchanged.

The Settings dialog's view lives only while the dialog is open and is not in a stack; it is unaffected.

### 4.2 Revision and painted report

`PageBridge` gains:

- `revision`: an `int` property with notify `revisionChanged`. It goes up by one whenever any other property of
  the bridge notifies. This is wired once, in `PageBridge.__init__`, by walking `self.metaObject()` and
  connecting each property's notify signal (every one except `revisionChanged`) to the bump. A bridge that gains
  a property later is covered without touching it. The theme counts as a change.
- `paintedRevision(int)`: a slot the page calls. It stores the number as `painted_revision` and emits the
  Python-facing signal `painted(int)`.

The bump is emitted in the same tick as the change that caused it, so QWebChannel delivers the new revision in
the same message as the new state.

`shared/web/page.js` (new, loaded by every page before its own script) holds one function:

```js
function reportPaints(bridge)
```

It connects `bridge.revisionChanged`, and on each change (and once at start-up) reads `bridge.revision`, waits
two animation frames, writes the number to `document.documentElement.dataset.painted` and calls
`bridge.paintedRevision(n)`. Two frames, because the first callback runs before the frame that holds the new
DOM is painted (the theme report already does this). Every page calls `reportPaints(bridge)` as the last line
of its `QWebChannel` callback. Every page renders synchronously in its signal handlers, so the DOM is current
by the first frame whatever order the handlers ran in.

`shared/web_page.py` gains:

```python
def when_painted(bridge: PageBridge, callback, timeout_ms: int = 150) -> None
```

It runs `callback` once: at once if `bridge.painted_revision >= bridge.revision`, otherwise when a `painted`
report reaches the revision the bridge had at the call, or after `timeout_ms`, whichever comes first. A timeout
logs a warning naming the bridge class and the two revisions. That log line is the whole of "a missed painted
report is logged" (D3).

### 4.3 Opening a session switches once the page has painted

Two places push a session and switch to Results in the same tick: `MainWindow.load_existing_session`
(`gui/main_window_pyside.py`) and the end of an analysis run (`gui/actions_handler.py`, "Auto-switch to
Analysis Results tab"). Both switch through one new method:

```python
def show_results_when_painted(self) -> None:
    when_painted(self.results_bridge, lambda: self.main_tabs.setCurrentIndex(1))
```

`_focus_results_search` (Ctrl+F) keeps its direct `setCurrentIndex(1)`: it pushes nothing.

Known limit: a render that takes longer than 150 ms (10 000 orders) switches at the cap, and the previous frame
can show until the render lands. The cap is what stops a page that never answers from blocking the switch.

### 4.4 A new session forgets the previous one's view (Results)

`ResultsBridge` gains a `sessionEpoch` `int` property (notify `sessionEpochChanged`) and a Python-facing
`forget_view()` that adds one to it. `MainWindow._reset_session_state`, which every way into a session already
calls, calls `self.results_bridge.forget_view()` before `_update_all_views()`.

`results.js` connects `sessionEpochChanged` to a new `resetView()`: clear `state.query` and the search field,
`state.chips`, `state.sort`, `state.selected`, `state.anchorKey`, `state.cursorKey`; close the filter menu, the
bulk popover, the detail pane's menus and the columns panel; scroll `els.scroller` to the top; then `render()`.
`state.columnSettings` is not touched: column choices are saved settings. Reopening the same session also
resets, because it goes through the same call.

Browse already resets its view when the client in its state changes (`onState` in `browse.js`). Setup, Tools
and Logs hold no session-bound view state. They need nothing.

ADR 0005 stands: the page still owns its view state. This adds one command from Python, "forget it".

### 4.5 Reload when a render process dies

`mount_page` connects `view.page().renderProcessTerminated`. On termination it logs a warning with the page
name, status and exit code, then, on the next event loop turn, loads the page again exactly as the first time
(the HTML with the current theme written in). The new document's `QWebChannel` start-up reads every bridge
property, so the page comes back with the current state; Logs calls `start()` at boot and is sent its rows
again. Page-owned view state (a typed search, an open pane) is lost with the process.

Three terminations of one page within 60 seconds stop the reloading and log an error, so a page that crashes
on load cannot spin.

### 4.6 The move to `shared/`

| From | To |
|---|---|
| `gui/web_page.py` | `shared/web_page.py` |
| `gui/web/kit.css` | `shared/web/kit.css` |
| (new) | `shared/web/page.js` |

`shared/` cannot import either app's theme manager, and the two apps keep theirs in different places
(`gui.theme_manager.get_theme_manager()` here, `gui.theme` in Packer Assistant). So the shared functions take
what they need as arguments:

- `mount_page(view, bridge, page, channel_name, *, tokens)`: `tokens` is a zero-argument callable returning the
  app's current `ThemeTokens` (the ones that carry its bundled font family). The base URL is `page.parent`.
- `switch_theme(name, *, current_name, tokens_for, set_theme)`: three callables.

Fulfilment keeps `gui/web_page.py` as a thin adapter, the way `gui/theme_manager.py` already is one. It
re-exports `PageBridge`, `THEME_MARKER`, `when_painted`, `keep_pages_painted`, keeps `WEB_DIR` (still
`gui/web`), and defines `mount_page` and `switch_theme` with this app's theme manager bound in. No bridge and
no test changes its imports.

Every page's HTML links the kit as `../../shared/web/kit.css` and loads `../../shared/web/page.js`; both repos
have `gui/web/` and `shared/web/` two levels below the same root, in a checkout and in the frozen build. The
release workflow adds `--add-data "shared/web;shared/web"`. `tests/web/kit_sheet.html`, `tests/test_web_kit.py`
and `tests/test_results_columns.py` follow the new path. `README.md`, `CONTEXT.md` ("Web kit"), `shared/README.md`
and ADR 0016's consequences are updated; the roadmap's "After the roadmap" line about `kit.css` is struck.

**What Packer Assistant changes when it syncs** (stated in the PR; not done in this task):

1. Bundle `shared/web` in its release build.
2. `PackerBridge` extends `shared.web_page.PageBridge` and drops its own `themeCss`.
3. `mount_packer_page` calls `shared.web_page.mount_page(..., tokens=gui.theme.current_tokens)` and keeps its
   `deny_focus`.
4. `packer.html` loads `../../shared/web/page.js` and `packer.js` calls `reportPaints(bridge)`.
5. `keep_pages_painted(self.stacked_widget)` on its main stack, checked against the scanner invariant (its ADR
   0001): the disabled, covered page must not take the scanner's focus, and the scanner input must keep it.
6. Adopting `kit.css` itself stays with its UI refresh.

Nothing breaks for Packer Assistant at the sync itself: it imports none of this yet.

## 5. Tests

All through a real Chromium, as the page tests already are. Never marked skip.

1. **One per page, in a real `MainWindow`** (`tests/test_web_freshness.py`): for Setup, Results, Browse, Logs and
   Tools, with another page current, push a state that replaces an earlier one, switch to the page, and assert
   that `bridge.painted_revision == bridge.revision`, that `dataset.painted` says the same, and that a marker
   string of the earlier state is nowhere in `document.body.innerText`. Logs has no state property: its test
   sends a batch of rows while covered and asserts the rows are in the DOM after the switch.
2. **Results forgets the view**: type a search, add a filter chip, sort, select; call `forget_view()` and push
   other orders; assert the search field is empty and query, chips, sort and selection are cleared, and that
   the rows shown are the new session's.
3. **Every way in resets**: `_reset_session_state()` raises `sessionEpoch`.
4. **Revision**: for each bridge class, changing any notifying property raises `revision` by at least one, and
   `paintedRevision(n)` sets `painted_revision` and emits `painted`.
5. **`when_painted`**: runs at once when already painted; runs on the report; runs once at the timeout and
   logs; never runs twice.
6. **Stack**: after `keep_pages_painted`, every page widget is visible, only the current one is enabled, and
   that follows a switch.
7. **Crash**: kill a page's render process, assert the page returns to `dataset.bridge === 'ready'` showing the
   current state; and that the third kill inside a minute is not followed by a reload.
8. **Session open**: `load_existing_session` on a session with an analysis ends on Results with the new
   session's orders painted.
9. **`scripts/stress_ui.py`**: two scenarios, "Results pushed while covered, then shown" (fails if the first
   DOM read after the switch holds the previous orders) and "Render process killed, page restored".

## 6. Out of scope

- Packer Assistant's stale `clear_screen` timer (section 2): its own task in the packing-tool section.
- Packer Assistant's pages and its adoption of `shared/web_page.py` (section 4.6 lists the work).
- The 30 to 70 ms the web page trails the Qt chrome on an ordinary update.
- The Qt tables' alternate-row colours in light theme and the status chip in the Statistics SKU column (owner
  decided not to fix).

## 7. Departures from the task as written

- "One snapshot per page, one render function": not done for Results (D4). The revision number and painted
  report are kept; the snapshot rewrite is not, because properties already arrive together.
- "Resync on show": replaced by keeping pages painted (D1), so there is no show to resync on.
- "No report in time means re-push, then reload": reduced to a log line (D3). Reload on render-process death is
  kept.
