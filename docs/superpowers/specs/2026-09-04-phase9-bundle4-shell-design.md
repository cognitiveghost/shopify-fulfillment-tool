# Phase 9 Bundle 4 — the shell

Covers 9.7 (shell anatomy and the command bar's four states), 9.8 (five
homeless controls get one home) and 9.9 (first run). Artboards S1–S4.

Worked from the transcription of S1–S4 in the Todoist briefs and the roadmap,
not from the canvas — the phase parent says so explicitly. Departures are
listed in §9.

Prerequisite: Bundle 3, merged 2026-09-04 (`StatePanel`, `StatusChip`'s
`live`/`manual` channels). Both are used here.

---

## 1. The finding that changes the shape of the cycle

**Today the app cannot reach 9.9's screen.** `MainWindow.__init__` calls
`_init_managers()` *before* `create_widgets()`, and `ProfileManager.__init__`
raises `NetworkError` when the share is unreachable. `_init_managers` catches
it, offers a modal recovery prompt, and on decline calls
`QApplication.quit()`. There is no state in which the window opens with an
unreachable share, so "a launch with an unreachable share renders this
screen" is not a layout task — it is a change to the startup contract.

None of the three briefs mention this. It is the largest thing in the bundle
and it is **Q1** in §8.

The rest of the bundle is smaller than it reads:

- The rail already has exactly five destinations. Only the footer is new work.
- `NavRail.button(i).setEnabled(False)` already exists — 9.9's disabled rail
  needs no `shared/` change.
- Theme preference is already `QSettings("ShopifyFulfillmentTool",
  "FulfillmentApp")`, which is already per-machine. 9.8's "stored per machine"
  is satisfied today; nothing to build.
- `ProfileManager` already carries `is_network_available` as a field. The
  raise is the only thing between it and a degraded launch.
- `results_overflow_button` on Analysis Results is a working precedent for a
  themed `QToolButton` + `QMenu` with `InstantPopup`, including the QSS the
  global sheet does not supply for `QToolButton`.

---

## 2. Vocabulary

Three terms enter `CONTEXT.md` with this bundle.

**Destination** — a place the rail navigates to and stays on. The rail holds
destinations and nothing else; anything that *configures* an object is not
one. This is the rule that empties the rail's footer.

**Overflow** — the menu beside an object holding what configures it.
Qualified when the scope matters: the **command-bar overflow** (client and
machine) against the **screen overflow** (`results_overflow_button`, actions
scoped to the screen you are on). Two menus, two scopes, two bands of chrome.

**Connection state** — whether this PC can currently reach the file server.
One boolean, one signal, one source of truth
(`ProfileManager.is_network_available`).

---

## 3. Shell anatomy (9.7)

Measurements every later screen may assume. Rail **56**, command bar **48**,
page padding **16**, status bar **28** — a usable page of 1310×692 at
1366×768.

Rail 56 and the button styling already ship (`shared/navrail.py`,
`RAIL_WIDTH = 56`). What this bundle adds is the command bar's fixed 48, the
status bar's fixed 28, and a test that pins the resulting page width, so a
later screen's "fits at 1310" claim is measured against something.

### 3.1 The four states

```
NO_CLIENT      selector focused · no session · no chip · no primary
NO_SESSION     selector · New Session (beside it) · no chip
SESSION        selector · session id · Open folder · chip · primary (right)
RUNNING        selector · session id · chip · progress · Cancel (danger)
```

`CommandBar.set_state(BarState)` where `BarState` is an `enum.Enum` on the
component. Exactly one primary exists at a time and it moves: New Session
sits in the left group beside the selector, the screen's primary sits right.
Nothing is primary while the machine holds the turn — Cancel takes the danger
outline, which `set_button_role` already supports.

### 3.2 State gates, the screen supplies

`bind_action` and `_SCREEN_ACTIONS` already point the bar's one primary at the
current screen's button. That mechanism is kept, because the four states and
the five screens are different axes and collapsing them loses one:

- **State decides whether a right-hand primary exists.** Only `SESSION` has
  one.
- **Screen decides which button it is.** Run Analysis on Setup, Generate
  Reports on Results.

`CommandBar` holds both `_state` and `_bound` and one `_refresh()` resolves
them. Neither setter reads the other's field.

Two consequences:

- `_SCREEN_ACTIONS` **loses entry 2**. The Browse screen borrows Setup's New
  Session today; under 9.7 New Session is state-owned and always present in
  `NO_SESSION`, so the borrow is dead.
- `mw.new_session_btn` is hidden through the existing `hide_in_page`
  mechanism and the bar's own button forwards to its handler. Bundle 5 (9.18)
  deletes it from the Setup page for real; this bundle only stops drawing it.

### 3.3 Degradation

The ladder at widths below the bar's `sizeHint`, in fixed order:

1. inter-group spacer → 8px
2. client name elides inside its 200px
3. progress drops the phase name, keeps the percentage
4. New Session goes icon-only

**Never elides, at any width:** the session ID, the status chip, the primary
button's label, the overflow button. An elided ID is a wrong ID.

Implemented in `resizeEvent` as an explicit ladder, not as size policies —
Qt's own elision has no order and would take the ID first because it is the
longest string in the row.

---

## 4. The command-bar overflow (9.8)

`OverflowMenu(QMenu)` in `gui/components/overflow.py`, owned by `CommandBar`,
opened by a `QToolButton` with `InstantPopup`. 284px, `surface_overlay`, 1px
`border`, `radius_md`, items on the 28px row rung, hover `selection_bg`. A
16px mark column keeps labels aligned whether or not anything is ticked. No
icons — seven items with seven icons is a colour chart.

Two sections, each a **disabled `QAction`** rather than `QMenu.addSection()`:
`addSection` renders a separator Qt draws itself, and the brief pins the type
treatment, which `QMenu::item:disabled` can carry and a separator cannot.

```
ACME                       ← the client's own name
  Client settings…
THIS PC
  Server connection…
  ✓ Light
    Dark
```

Light and Dark are two exclusive checkable `QAction`s in a `QActionGroup`.
Two items, not a toggle — "Dark mode: off" is a sentence nobody reads
correctly first time. They write through `get_theme_manager().set_theme()`,
which already persists to `QSettings` per machine.

### 4.1 The five, and where each lands

| Control | Lands | How |
|---|---|---|
| New session | Command bar, right of the selector | state-owned, §3.1 |
| Open session folder | Command bar, right of the session ID, icon-only | its target is the string to its left |
| Client settings | Overflow §1 | the header shows the scope a rail item never could |
| Server connection | Overflow §2 | the *indicator* stays in the status bar, §4.3 |
| Light / dark | Overflow §2 | `QActionGroup`, per machine |

### 4.2 What leaves the screen overflow

The rule — *object config goes to the object's overflow* — applies to
`results_overflow_button` too, which today holds both:

- **Light/dark leaves.** `mw.theme_toggle_btn` (a `QAction`) and
  `_update_theme_button_text` are deleted. Keeping it would make theme the
  second duplicated action, and 9.9 is explicit that Server Connection is the
  only one and that the duplication is the point.
- **Settings leaves.** `mw.settings_button_tab2` opens the *client's*
  settings, which is object config. It becomes the overflow's "Client
  settings…".

What is left on the screen overflow is screen-scoped and stays: Add Product
to Order, Configure Columns, Undo.

`tests/test_analysis_results_1b_chrome.py:133` asserts on
`theme_toggle_btn` and moves with it.

### 4.3 The connection indicator

`statusBar().addPermanentWidget()` takes a `StatusChip` — Bundle 3's
component, in its first real use of the `live` channel:

| Connection state | Role | Live | Mark | Label |
|---|---|---|---|---|
| reachable | `status_success` | resting (untinted) | hollow | `Server connected` |
| unreachable | `status_danger` | live (tinted) | hollow | `Server unreachable` |

Hollow in both: the system derived it, no person set it. Tinted only when
someone has to act. This is exactly what the three channels were built to
say, and the status bar is the first place in the app where they say it about
something other than an order.

### 4.4 The rail footer

`ui_manager` stops calling `add_footer_item`; `mw.connection_btn` is deleted
and its handler moves to the overflow's "Server connection…" — the same
`ConnectionSettingsDialog`, the same label, one name through the whole flow.

Whether `add_footer_item` is also deleted from `shared/navrail.py` — which
would make this a two-repo, two-PR cycle for a dead-code deletion — is **Q2**
in §8.

---

## 5. First run (9.9)

The shell with nothing configured, in two beats and no third layout.

### 5.1 The degraded launch

`ProfileManager.__init__` gains `require_connection: bool = True`. When
False, an unreachable share sets `is_network_available = False` and returns
instead of raising. Every field it publishes (`base_path`, `clients_dir`, …)
is still a real `Path`, so no call site becomes `None`-unsafe and no
`None`-guard is written anywhere.

Nothing reads those paths, because **the disabled controls are the guard**.
That is the whole argument for 9.9's "one `connection_state` signal drives
every disabled control on it": the signal is not decoration on top of a
safety mechanism, it *is* the safety mechanism. If a control that reaches the
share is ever left enabled while disconnected, that is the bug — not a
missing null check three layers down.

`MainWindow` gains `connectionChanged = Signal(bool)`, emitted once after
`create_widgets()` and again whenever `ConnectionSettingsDialog` returns a
working path. Its slots:

- rail items 1, 2 and 4 (`Results`, `Browse`, `Tools`) `setEnabled(False)`.
  **Disabled, never hidden** — a rail that grows items as you configure the
  app never lets you learn its shape. `Setup` and `Info` stay enabled; a
  failed install is a log-reading problem.
- the Setup stack switches to page 0.
- `CommandBar.set_state(NO_CLIENT)` and the selector is emptied.
- the status-bar chip, §4.3.

### 5.2 The Setup stack

Setup has no `QStackedWidget` today. It gains one: page 0 is a `StatePanel`,
page 1 is the existing setup content unchanged. This is `StatePanel`'s first
call site — Bundle 3 shipped it wired into nothing, and the signature may
move here.

Two forms, chosen by connection state:

**Unreachable** — `StatePanel.failed`:

> **This PC can't reach the fulfilment server**
> Clients, stock files and past sessions all live on the server. Until this
> PC reaches it, there is nothing to set up.
> `\\192.168.88.101\_Fulfilment_\0UFulfilment`
> **[ Server connection… ]**

**Reachable, no client** — `StatePanel.nothing_loaded`, no action:

> **Choose a client to begin**
> Pick a client in the bar above. Sessions, stock and reports all belong to
> one client.

The button on the first form is the only accent-filled pixel in the window.
The second form has none: its action is the selector, which takes focus, and
the primary reappears in the command bar as New Session the moment a client
is chosen — S2 state a into state b.

The detail line carries the resolved path, so a supervisor can read it aloud
over a phone. It ships at `caption` in `text_secondary`; it gets the one mono
face in 9.11, which owns picking Consolas (ADR 0001). Same departure Bundle 3
recorded, same reason, and `StatePanel` already re-runs that colour on theme
change per ADR 0003.

Centring is a `QVBoxLayout` with stretches, which `StatePanel` already does.

### 5.3 The duplicated action

"Server connection…" appears in the empty state and in the overflow menu, and
that is deliberate: an empty state that explains a problem without offering
the fix is a dead end, and a supervisor should not hunt for a three-dot menu
in their first thirty seconds. After first run the empty state is gone and
the menu is its only home. Both spell it the same way, because an action that
changes name between two places is two actions to the person reading them.

---

## 6. Modules and seams

| Module | Interface | Depth |
|---|---|---|
| `gui/components/overflow.py` | `OverflowMenu(QMenu)`: `add_section(title)`, `add_item(text, slot)`, `add_choice_group(items, current)` | the QSS, the 284px, the mark column and the disabled-action headers live behind three calls |
| `CommandBar` | `set_state(BarState)` added; `bind_action` unchanged | four states × five screens resolved behind one call, §3.2 |
| `ProfileManager` | `require_connection: bool = True` | one keyword; the degraded object is otherwise identical |
| `MainWindow` | `connectionChanged = Signal(bool)` | one signal replaces a modal-or-quit branch |

Test at these seams, not through the window where avoidable:

1. `CommandBar.set_state` × `bind_action` — every (state, bound) pair, asserting
   which of the two buttons is visible. No `MainWindow`.
2. The degradation ladder — a `CommandBar` at 1310px with the longest realistic
   client name and session ID, asserting the four never-elide items are intact
   and that the ladder fired in order.
3. `OverflowMenu` — sections, the exclusive theme group, and that picking one
   repaints (`theme_changed` fires once).
4. `ProfileManager(require_connection=False)` against an unreachable path —
   returns, `is_network_available is False`, `base_path` is a `Path`.
5. `MainWindow` with an unreachable share — the window exists, rail items 1/2/4
   are disabled, Setup is on page 0, and the panel names the path. This is the
   only test that needs the whole window, and it is 9.9's `Done when`.

The `main_window` fixture in `tests/test_shell.py` already builds a real
window against a `tmp_path` server; test 5 is that fixture pointed at a path
that does not exist.

---

## 7. Decisions made here

1. **State gates, screen supplies** (§3.2). Collapsing the two axes into one
   `set_state` would leave Generate Reports with no home.
2. **Disabled `QAction` section headers, not `addSection()`** (§4). The brief
   pins the type treatment; a Qt-drawn separator cannot carry it.
3. **`OverflowMenu` is built fresh, not extracted from
   `results_overflow_button`.** Two call sites is normally a real seam, but
   Bundle 12 replaces the Results screen with the web tier, so the second call
   site is scheduled for deletion. The ~10 lines of `QToolButton` QSS are
   copied with a `ponytail:` comment naming the merge point if Bundle 12 ever
   slips.
4. **`require_connection` on `ProfileManager`, not `None` in `MainWindow`**
   (§5.1). Eleven `profile_manager` call sites stay type-correct and no
   `None`-guard is written.
5. **Client settings and light/dark leave the screen overflow** (§4.2). Both
   are object config; the rule that empties the rail's footer empties this
   too.
6. **The status-bar chip is in scope** (§4.3). 9.8 says the indicator stays
   in the status bar, and there is no indicator there today — the sentence
   describes something that has to be built, not something being left alone.

---

## 8. Open — for the repo owner

**Q1 — What happens on a launch that cannot reach the share?** Today the app
shows a modal recovery prompt and quits if you decline; 9.9's `Done when`
requires the window to open. Options:

- **(a) Open degraded, always.** `ProfileManager(require_connection=False)`,
  the window builds, `connectionChanged(False)` drives the disabled rail and
  the Setup panel. The recovery prompt stops being the first thing you see
  and becomes what "Server connection…" opens.
- **(b) Keep the modal, open degraded only if you decline it.** Smaller diff,
  but the first thing a first-run user sees is still a modal — which is
  precisely what S4 exists to replace.
- **(c) Defer 9.9.** It is 40% of the bundle.

➡️ **(a).** S4 is drawn as a screen, not as a screen behind a dialog, and
option (b) ships the artboard's outcome only for the user who dismisses
something first. The plan is written for (a); under (b) only §5.1 changes and
the plan says so at that task.

**Q2 — Does `add_footer_item` get deleted from `shared/navrail.py`?** 9.8
says "delete the widget rather than hiding it, so nothing can be added back
by accident". The method is dead in both apps — packing-tool's only reference
is its own test. Deleting it makes this a two-repo, two-PR cycle (a
packing-tool PR, then `scripts/sync_shared.py`) for about twenty lines.

- **(a) Shopify only.** Delete the call site and `mw.connection_btn`; add a
  test asserting the rail has five buttons and no footer child. The method
  stays in `shared/` until packing-tool next touches the rail (8.9).
- **(b) Both repos.** Delete the method and packing-tool's test too, exactly
  as the brief reads.

➡️ **(a).** The accident the brief guards against is a shopify accident, and
a shopify test forbidding a footer prevents it more directly than deleting a
method someone could re-add. Bundle 3's two-repo cycle cost a Stage C run to
cross-repo confusion; spending that again on dead code is the wrong trade. If
you prefer (b), only §4.4 and one plan task change.

**Q3 — `Server connected` / `Server unreachable`, or something shorter?**
The status-bar chip is the only permanent text in the 28px band, and the
label has to work for a supervisor glancing at it, not reading it. The
alternative is a bare `Server` whose colour carries everything, which fails
the moment someone photographs the screen in greyscale.

➡️ **Keep both words.** Colour is the fast channel and the label is the
correct one; the chip already has room at 28px.

---

## 9. Departures from the artboards

- **The overflow's section headers are not mono.** The Qt tier has no mono
  family at all — 9.11 owns picking Consolas. They ship uppercase at
  `caption`, and gain the face in Bundle 11. Same departure, same reason, as
  Bundle 3's `StatePanel` detail line.
- **S4 is drawn as a launch state; it is built as a startup-contract change.**
  The artboard cannot show that the app currently quits instead. §1.
- **S3 does not draw the screen overflow that already ships on Analysis
  Results.** Two ⋯ buttons now exist in two different bands. They are not
  merged, and §4.2 says which actions each keeps, so the split is by scope
  rather than by accident.
